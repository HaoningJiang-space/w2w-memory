"""Repeated FFN calls with independent layer weights and explicit sequence barriers."""
from collections import Counter
from dataclasses import replace
from w2w.domain.execution import ExecutionGraph,DataEdge,ControlEdge
from w2w.workloads.moe import build_moe
from .data_placement import place_weights
from .compute_placement import place_compute,weight_compute_clusters
from .lowering import lower


def lower_sequence(tokens,machine,*,layers=2,shape=None,weight_layout=None,compute_reference=None,execution_policy='s0'):
    if execution_policy not in ('s0','s1'):raise ValueError('Unknown FFN dependency policy')
    shape=shape or {}
    catalog=build_moe((tokens[0],),**shape)
    weights=place_weights(catalog,machine.stack) if weight_layout is None else tuple(weight_layout)
    reference=weights if compute_reference is None else tuple(compute_reference)
    if ([(w.tensor,w.size_bytes) for w in weights]!=list(catalog.weight_sizes) or
            [(w.tensor,w.size_bytes) for w in reference]!=list(catalog.weight_sizes)):
        raise ValueError('Sequence requires the complete frozen layer weight catalog')
    offsets=Counter()
    for w in weights:offsets[w.memory]=max(offsets[w.memory],w.offset_bytes+w.size_bytes)
    # Explicit reference fixes both compute and initial cache residency when
    # memory layout is varied. Neither follows the candidate's DRAM position.
    clusters=weight_compute_clusters(machine.stack,reference)
    tasks=[];data=[];control=[];objects=[];invocations=[];work={}
    # Catalog placement is frozen for ALL experts, including inactive experts.
    for layer in range(layers):
        for w in weights:
            from w2w.domain.execution import ResidentObject
            name=f'L{layer}/{w.tensor}'
            objects.append(ResidentObject(name,w.memory,w.offset_bytes+layer*offsets[w.memory],w.size_bytes,storage_id=name))
    previous=None;sequence=0;active=set()
    for token,experts in enumerate(tokens):
        for layer in range(layers):
            logical=build_moe((experts,),**shape)
            placement=place_compute(logical,machine.stack,reference)
            # Sequential single-token requests originate at distributed clusters.
            source=machine.stack.compute_clusters[token%len(machine.stack.compute_clusters)].id
            placement=tuple(replace(p,cluster=source) if p.operation.startswith('t0/') else p for p in placement)
            graph,meta=lower(logical,machine,weights,placement,execution_policy=execution_policy)
            prefix=f'I{sequence:04d}/';sequence+=1
            rename=lambda name:prefix+name
            obj=lambda name:f'L{layer}/'+name
            for t in graph.tasks:
                reads=tuple(replace(r,object_id=obj(r.object_id)) for r in t.reads)
                active.update((clusters[r.object_id],obj(r.object_id)) for r in t.reads)
                stream=replace(t.stream,weight_object=obj(t.stream.weight_object)) if t.stream else None
                tasks.append(replace(t,id=rename(t.id),reads=reads,stream=stream))
            data.extend(replace(e,id=rename(e.id),producer=rename(e.producer),consumer=rename(e.consumer)) for e in graph.data)
            control.extend(ControlEdge(rename(e.producer),rename(e.consumer)) for e in graph.control)
            start,end=rename('t0/input'),rename('t0/combine')
            if previous:
                if layer:data.append(DataEdge(prefix+'layer_input',previous,start,catalog.shape[0]*2))
                else:control.append(ControlEdge(previous,start))
            invocations.append(dict(token=token,layer=layer,input_task=start,finish_task=end,source=source,prefix=prefix))
            work.update({rename(k):v for k,v in meta['task_work'].items()})
            previous=end
    graph=ExecutionGraph(tuple(tasks),tuple(objects),tuple(data),tuple(control))
    by_id={o.id:o for o in objects};working=Counter()
    for cluster,name in active:working[cluster]+=by_id[name].size_bytes
    preload=tuple((clusters[w.tensor],f'L0/{w.tensor}') for w in weights)
    metadata=dict(schema='w2w.multilayer-ffn-proxy.v1',layers=layers,tokens=len(tokens),invocations=invocations,
        shape=catalog.shape,partitions=catalog.partitions,task_work=work,
        macs=sum(v['macs'] for v in work.values()),vector_ops=sum(v['vector_ops'] for v in work.values()),
        logical_weight_read_bytes=sum(r.size_bytes for t in tasks for r in t.reads),
        catalog_weight_bytes=sum(o.size_bytes for o in objects),active_unique_weight_bytes=sum(working.values()),
        active_unique_weight_bytes_by_cluster=dict(working),
        initial_resident_bytes=sum(w.size_bytes for w in weights),
        initial_resident_bytes_by_cluster=dict(Counter({c:sum(w.size_bytes for w in weights if clusters[w.tensor]==c) for c in set(clusters.values())})),
        scope='FFN-only sequential token proxy; independent layer weight addresses; same archived routing reused at each layer; no attention/norm/residual or numerical inference')
    if execution_policy=='s1':
        metadata['dependency_policy']='independent gate/up; both wait for previous block accumulate; layer/token barriers and ordered accumulation unchanged'
    return graph,metadata,preload
