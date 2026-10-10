"""Finite matrix association and descriptor bindings retained through commit.

The additional 8 B/request table is charged explicitly; Python labels are not a
free hardware return map. This first gate is cold-only and does not recycle SRAM.
"""
from collections import Counter
from math import ceil


class ReturnTracker:
    association_bytes=16
    binding_bytes=8

    def __init__(self,host,contexts):
        self.host=host;self.contexts=contexts
        self.live={tile:{} for tile in host.builder.tiles};self.bindings={}
        self.peak=Counter();self.binding_live=Counter();self.binding_peak=Counter()
        self.metadata_bytes=contexts*self.association_bytes+host.spec.outstanding_per_tile*self.binding_bytes

    def can_allocate(self,tile):return len(self.live[tile])<self.contexts

    def acquire(self,key):
        h=self.host;task=h.tasks[key];tile=task.tile
        used={row['slot'] for row in self.live[tile].values()}
        if key in self.live[tile] or not self.can_allocate(tile):raise RuntimeError('Return association overbooked')
        slot=next(i for i in range(self.contexts) if i not in used)
        expected=sum(ceil(r.size_bytes/h.spec.memory_request_bytes) for r in task.reads)
        if not 0<expected<65536:raise ValueError('Declared 16-bit return descriptor counts exceeded')
        self.live[tile][key]=dict(slot=slot,expected=expected,bound=0,committed=0,issued_all=False)
        self.peak[tile]=max(self.peak[tile],len(self.live[tile]))
        h.log('return_context_acquire',task=key,tile=tile,association=slot,expected_descriptors=expected)

    def bind(self,req):
        h=self.host;tile=h.tasks[req.task].tile;row=self.live[tile][req.task]
        if req.id in self.bindings or self.binding_live[tile]>=h.spec.outstanding_per_tile or row['bound']>=row['expected']:
            raise RuntimeError('Return binding duplicated or over capacity')
        row['bound']+=1;self.bindings[req.id]=(tile,req.task,row['slot'])
        self.binding_live[tile]+=1;self.binding_peak[tile]=max(self.binding_peak[tile],self.binding_live[tile])
        h.log('return_request_bind',request=req.id,task=req.task,tile=tile,association=row['slot'])

    def issue_done(self,key):
        h=self.host;tile=h.tasks[key].tile;row=self.live[tile][key]
        if row['issued_all'] or row['bound']!=row['expected']:raise RuntimeError('Issue state released before all descriptor bindings')
        row['issued_all']=True
        h.log('return_issue_complete',task=key,tile=tile,association=row['slot'])

    def commit(self,request):
        if request not in self.bindings:raise RuntimeError('Unknown or duplicated return binding')
        tile,key,slot=self.bindings.pop(request);row=self.live[tile][key]
        if row['slot']!=slot:raise RuntimeError('Return association reused while a descriptor was in flight')
        self.binding_live[tile]-=1;row['committed']+=1
        self.host.log('return_request_commit',request=request,task=key,tile=tile,association=slot)

    def complete(self,key):
        h=self.host;tile=h.tasks[key].tile;row=self.live[tile][key]
        if not row['issued_all'] or row['committed']!=row['expected']:raise RuntimeError('Return association released prematurely')
        del self.live[tile][key]
        h.log('return_context_release',task=key,tile=tile,association=row['slot'])

    def record(self):
        return dict(contexts_per_cluster=self.contexts,association_bytes=self.association_bytes,
            binding_bytes_per_request=self.binding_bytes,binding_capacity_per_cluster=self.host.spec.outstanding_per_tile,
            metadata_bytes_per_cluster=self.metadata_bytes,peak_contexts=dict(self.peak),
            binding_peak=dict(self.binding_peak),live_contexts=sum(map(len,self.live.values())),live_bindings=len(self.bindings),
            contract='16 B/matrix association plus additional 8 B/outstanding descriptor binding; retained until every reply commits. '
                     'Existing committed-prefix bitmap and full matrix SRAM remain separately paid. No physical area/energy calibration.')
