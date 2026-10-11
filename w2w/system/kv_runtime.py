"""Finite BF16 SRAM KV ownership and append/read visibility on unified events."""
from collections import Counter
from .runtime_windows import RuntimeWindows


class KVRuntimeWindows(RuntimeWindows):
    def __init__(self,root,producer,metadata,catalog,request_ids):
        super().__init__(root,producer,metadata);self.catalog=catalog;self.request_ids=tuple(request_ids)
        self.lengths={};self.head_lengths={};p=catalog['llm_profile'];self.reserved=Counter()
        for index,layer in enumerate(catalog['layers']):
            for h in range(p['kv_heads']):
                # Paged KV: bounded 256-token allocation plus finite association.
                self.reserved[f'c{index*p["kv_heads"]+h}']+=len(request_ids)*(4*p['head_dim']*p['kv_tokens_per_request']+128)

    def persistent_record(self,initial=False):
        return dict(persistent_sram={} if initial else dict(self.reserved),
            kv_state=[] if initial else [dict(layer=k[0],request_id=k[1],head=k[2],length=v) for k,v in sorted(self.head_lengths.items())])

    def start(self,e):
        super().start(e)
        for tile,size in self.reserved.items():e._sram(tile,size,'kv-residency')
        if e.event_observer is not None:raise ValueError('KV runtime owns explicit append/read observer')
        e.event_observer=lambda event:self.observe(e,event)

    def observe(self,e,event):
        if event['kind'] not in ('task_start','task_finish'):return
        task=event['task']
        if event['kind']=='task_finish':
            for row in self.metadata['kv_appends']:
                if row['task']!=task:continue
                key=(row['layer'],row['request_id'],row['head'])
                if self.head_lengths.get(key,0)!=row['before']:raise ValueError('KV overwrite, skipped append or future data')
                self.head_lengths[key]=row['after'];self.lengths[key[:2]]=row['after']
                e.log('kv_append',**row)
        else:
            for row in self.metadata['kv_reads']:
                if row['task']!=task:continue
                if self.head_lengths.get((row['layer'],row['request_id'],row['head']),0)!=row['length']:
                    raise ValueError('Attention reads uncommitted or future KV')
                e.log('kv_read',**row)

    def finish(self,e):
        for tile,size in self.reserved.items():e._sram(tile,-size,'kv-residency')
