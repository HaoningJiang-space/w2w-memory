"""Actual expert M dimensions, explicit router/pack/scatter, fixed V3 resources."""
from collections import Counter,defaultdict
from dataclasses import asdict,replace
from math import ceil,log2
from w2w.domain.execution import ComputeTask,ControlEdge,DataEdge,ExecutionGraph,ReadAccess,ResidentObject
from w2w.domain.npu import GemmKernel
from w2w.workloads.captured_moe import build_captured_moe
from w2w.workloads.ir import Operation,Tensor
from w2w.system.npu_kernel import program
from .data_placement import place_weights
from .static_weights import static_weights
from .compute_placement import place_projection_compute
from .lowering import lower

BASELINES=('reference','phase_split','up_local')


def full_catalog(machine,shape,layers,baseline):
    if baseline not in BASELINES or len(set(layers))!=len(layers):raise ValueError('Explicit legal baseline/layers required')
    logical=build_captured_moe((tuple(range(shape['topk'])),),hidden=shape['hidden'],intermediate=shape['intermediate'],
        experts=shape['experts'],topk=shape['topk'],block_width=128,partitions=4)
    reference=place_weights(logical,machine.stack)
    candidate=reference if baseline=='reference' else static_weights(logical,machine.stack,'phase-split')
    spans=Counter()
    for w in candidate:spans[w.memory]=max(spans[w.memory],w.offset_bytes+w.size_bytes)
    router_memory=sorted(spans)[0];router_bytes=shape['hidden']*shape['experts']*2
    stride={m:n+(router_bytes if m==router_memory else 0) for m,n in spans.items()}
    objects=[]
    for index,layer in enumerate(layers):
        objects.extend(ResidentObject(f'L{layer}/'+w.tensor,w.memory,w.offset_bytes+index*stride[w.memory],w.size_bytes,
            storage_id=f'L{layer}/'+w.tensor) for w in candidate)
        objects.append(ResidentObject(f'L{layer}/router',router_memory,spans[router_memory]+index*stride[router_memory],router_bytes,
            storage_id=f'L{layer}/router'))
    capacity={m.id:m.capacity_bytes for m in machine.memories}
    if any(o.offset_bytes+o.size_bytes>capacity[o.memory] for o in objects):
        raise ValueError('Complete independent-layer model catalog exceeds physical DRAM; explicit deployment required')
    return dict(shape=shape,layers=tuple(layers),baseline=baseline,reference=reference,weights=candidate,objects=tuple(objects))


def _pack_scatter(logical):
    members=defaultdict(list)
    for token,selected in enumerate(logical.tokens):
        for expert in selected:members[expert].append(token)
    ops=list(logical.operations);tensors=[];H=logical.shape[0]
    for e,ids in sorted(members.items()):
        pack=f'e{e}/pack';scatter=f'e{e}/scatter'
        ops.extend((Operation(pack,'token_pack',expert=e,token_ids=tuple(ids),vector_ops=len(ids)*H),
                    Operation(scatter,'output_scatter',expert=e,token_ids=tuple(ids),vector_ops=len(ids)*H)))
        consumers=tuple(o.id for o in logical.operations if o.expert==e and o.kind=='gemm' and o.id.endswith(('/gate','/up')))
        tensors.append(Tensor(f'e{e}/packed_X',len(ids)*H*2,'BF16',pack,consumers,f'e{e}/packed_X'))
        tensors.append(Tensor(f'e{e}/packed_output',len(ids)*H*2,'BF16',f'e{e}/reduce',(scatter,),f'e{e}/packed_output'))
    for t in logical.tensors:
        if t.id.startswith('dispatched/'):
            e=int(t.id.rsplit('/e',1)[1]);t=replace(t,consumers=(f'e{e}/pack',))
        elif '/output' in t.id and t.id.startswith('e'):
            e=int(t.id.split('/')[0][1:]);t=replace(t,producer=f'e{e}/scatter')
        tensors.append(t)
    return replace(logical,operations=tuple(ops),tensors=tuple(tensors))


def lower_batch(batch,machine,catalog,npu_profile,*,prefix):
    if batch.layer_id not in catalog['layers']:raise ValueError('Batch layer has no independent physical weights')
    s=catalog['shape'];logical=_pack_scatter(build_captured_moe(tuple(r.expert_ids for r in batch.observations),
        hidden=s['hidden'],intermediate=s['intermediate'],experts=s['experts'],topk=s['topk'],block_width=128,partitions=4))
    policy='up_local_compute' if catalog['baseline']=='up_local' else 'reference_compute'
    placement=place_projection_compute(logical,machine.stack,catalog['reference'],catalog['weights'],policy)
    graph,meta=lower(logical,machine,catalog['weights'],placement,execution_policy='s1',npu_profile=npu_profile)
    name=lambda k:prefix+k
    obj=lambda k:f'L{batch.layer_id}/'+k
    tasks=[replace(t,id=name(t.id),reads=tuple(replace(r,object_id=obj(r.object_id)) for r in t.reads),
        stream=replace(t.stream,weight_object=obj(t.stream.weight_object)) if t.stream else None) for t in graph.tasks]
    data=[replace(e,id=name(e.id),producer=name(e.producer),consumer=name(e.consumer)) for e in graph.data]
    control=[ControlEdge(name(e.producer),name(e.consumer)) for e in graph.control]
    kernels={name(k):GemmKernel(**dict(v,operation_id=name(k),weight_object=obj(v['weight_object']),scale_group=tuple(v['scale_group'])))
        for k,v in meta['npu_kernels'].items()}
    router_obj=f'L{batch.layer_id}/router';router_id=name('router_matmul');done=name('router_done')
    tile=sorted(machine.stack.compute_clusters,key=lambda c:c.id)[0];router=GemmKernel(router_id,batch.token_count,s['experts'],s['hidden'],router_obj,weight_dtype='BF16')
    _,plan=program(router.M,router.N,router.K,router.weight_dtype,npu_profile)
    tasks.append(ComputeTask(router_id,tile.id,plan['cycles'],(ReadAccess(router_obj,0,router.weight_bytes),),plan['scratch_bytes']))
    topk_ops=batch.token_count*(s['experts']*ceil(log2(s['experts']))+6*s['experts'])
    tasks.append(ComputeTask(done,tile.id,ceil(topk_ops/tile.profile.vector_ops_per_cycle),scratch_bytes=4*batch.token_count*s['experts']))
    kernels[router_id]=router
    data.append(DataEdge(name('router_scores'),router_id,done,4*batch.token_count*s['experts']))
    for token,r in enumerate(batch.observations):
        data.append(DataEdge(name(f'router_X/{token}'),name(f't{token}/input'),router_id,2*s['hidden']))
        # Coefficient availability follows modeled router completion. No values
        # or source timestamps are invented; capture supplies ranked IDs only.
        coeff=name(f'coefficients/t{token}/to/t{token}/combine')
        data=[replace(e,producer=done) if e.id==coeff else e for e in data]
        for expert in r.expert_ids:
            dispatch=name(f't{token}/dispatch/e{expert}')
            data.append(DataEdge(name(f'route/t{token}/e{expert}'),done,dispatch,8))
    graph=ExecutionGraph(tuple(tasks),catalog['objects'],tuple(data),tuple(control))
    meta.update(batch_id=batch.id,layer_id=batch.layer_id,token_ids=[r.token_id for r in batch.observations],
        token_to_experts=[r.expert_ids for r in batch.observations],expert_token_counts={str(e):len(ts) for e,ts in batch.expert_to_tokens},
        expert_macs=3*batch.token_count*s['topk']*s['hidden']*s['intermediate'],router_macs=router.macs,
        router_vector_ops=topk_ops,router_visibility='Captured IDs become hardware-visible only after explicit modeled router matmul/top-k; no route lookahead.',
        scratch_policy='Conservative explicit pack/output copies, paid array/word/partial SRAM, no automatic cache shrink or uncharged broadcast storage.',
        npu_kernels={k:asdict(v) for k,v in kernels.items()},finish_tasks=[name(f't{n}/combine') for n in range(batch.token_count)])
    return graph,kernels,meta
