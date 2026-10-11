"""Complete request phases for explicitly selected, independently captured MoE layers."""
from collections import Counter
from dataclasses import replace
from w2w.domain.execution import ExecutionGraph,DataEdge,ControlEdge,ResidentObject
from w2w.workloads.captured_moe import build_captured_moe
from .data_placement import place_weights
from .static_weights import static_weights
from .compute_placement import place_projection_compute
from .lowering import lower


def lower_captured_request(capture,machine,layer_keys,*,projection_policy='up_local_compute'):
    keys=tuple(layer_keys);s=capture['shape']
    if not keys or len(set(keys))!=len(keys) or any(k not in capture['decode'] for k in keys):
        raise ValueError('Explicit unique captured layer keys required')
    if capture['coverage']['omitted_decode_tokens'] or capture['coverage']['omitted_prefill_tokens']:
        raise ValueError('This runner accepts complete request phases only')
    if projection_policy not in ('reference_compute','up_local_compute'):raise ValueError('Unknown static projection policy')
    shape=dict(hidden=s['hidden'],intermediate=s['intermediate'],experts=s['experts'],topk=s['topk'],block_width=128,partitions=4)
    catalog=build_captured_moe((capture['decode'][keys[0]][0],),**shape)
    reference=place_weights(catalog,machine.stack)
    weights=static_weights(catalog,machine.stack,'phase-split')
    spans=Counter()
    for w in weights:spans[w.memory]=max(spans[w.memory],w.offset_bytes+w.size_bytes)
    objects=[]
    for layer in keys:
        for w in weights:
            name=f'L{layer}/{w.tensor}'
            objects.append(ResidentObject(name,w.memory,w.offset_bytes+keys.index(layer)*spans[w.memory],w.size_bytes,storage_id=name))
    groups={g.id:g for g in machine.stack.bank_groups}
    domains={d.id:d for d in machine.stack.dram_domains}
    for o in objects:
        if o.offset_bytes+o.size_bytes>sum(domains[d].capacity_bytes for d in groups[o.memory].domain_ids):
            raise ValueError('Selected real layers exceed physical DRAM capacity')
    tasks=[];data=[];control=[];work={};invocations=[];previous=[];seq=0
    steps=[('prefill',None)]+[('decode',i) for i in range(capture['coverage']['decode_tokens'])]
    for phase,step in steps:
        for layer in keys:
            routes=capture['prefill'][layer] if phase=='prefill' else [capture['decode'][layer][step]]
            logical=build_captured_moe(routes,source_identity=(('raw',capture['raw_sha256']),('layer',layer)),**shape)
            placement=place_projection_compute(logical,machine.stack,reference,weights,projection_policy)
            graph,meta=lower(logical,machine,weights,placement,execution_policy='s1')
            prefix=f'I{seq:04d}/';seq+=1
            rename=lambda k:prefix+k
            obj=lambda k:f'L{layer}/'+k
            for t in graph.tasks:
                tasks.append(replace(t,id=rename(t.id),reads=tuple(replace(r,object_id=obj(r.object_id)) for r in t.reads),
                    stream=replace(t.stream,weight_object=obj(t.stream.weight_object)) if t.stream else None))
            data.extend(replace(e,id=rename(e.id),producer=rename(e.producer),consumer=rename(e.consumer)) for e in graph.data)
            control.extend(ControlEdge(rename(e.producer),rename(e.consumer)) for e in graph.control)
            starts=[rename(f't{n}/input') for n in range(len(routes))]
            ends=[rename(f't{n}/combine') for n in range(len(routes))]
            # All captured batch tokens join before the next layer/phase. Only
            # within-phase adjacent layers have materialized token activations;
            # decode-after-prefill is a sequence barrier, not a reused activation.
            if previous:
                for producer in previous:
                    for consumer in starts:control.append(ControlEdge(producer,consumer))
                if invocations[-1]['phase']==phase and invocations[-1]['decode_step']==step:
                    if len(previous)!=len(starts):raise ValueError('Captured layer token coverage differs')
                    for n,(producer,consumer) in enumerate(zip(previous,starts)):
                        data.append(DataEdge(prefix+f'layer_input/{n}',producer,consumer,s['hidden']*2))
            invocations.append(dict(prefix=prefix,phase=phase,decode_step=step,captured_layer=layer,
                token_count=len(routes),finish_tasks=ends,token_experts=routes))
            work.update((rename(k),v) for k,v in meta['task_work'].items());previous=ends
    graph=ExecutionGraph(tuple(tasks),tuple(objects),tuple(data),tuple(control))
    metadata=dict(schema='w2w.captured-post-router-moe-sequence.v1',request_id=capture['request_id'],
        raw_sha256=capture['raw_sha256'],selected_layer_keys=keys,captured_layer_count=s['layers'],
        omitted_execution_layers=s['layers']-len(keys),prefill_tokens=capture['coverage']['prefill_tokens'],
        decode_tokens=capture['coverage']['decode_tokens'],omitted_execution_tokens=0,
        invocations=invocations,task_work=work,macs=sum(v['macs'] for v in work.values()),
        vector_ops=sum(v['vector_ops'] for v in work.values()),catalog_weight_bytes=sum(o.size_bytes for o in objects),
        scope='Full captured prefill/decode request for selected real layers; explicit token dispatch, expert gated FFNs, '
            'ordered block/partition sums and weighted combine. Post-router timing only: captured IDs, unavailable '
            'coefficient values (4-byte transfer format assumed). No router matmul/top-k, attention/KV/norm/residual '
            'or numerical full-model inference. No layer-route reuse or token truncation.')
    return graph,metadata
