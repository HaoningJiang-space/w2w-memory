"""Explicit physical copies and task lifecycle lower into the existing execution IR."""
from dataclasses import asdict
from math import ceil
from w2w.domain.execution import ComputeTask,DataEdge,ControlEdge,ExecutionGraph,ReadAccess,ResidentObject,StreamGemm
from w2w.common.fingerprints import digest_read_v1


def lower(logical, machine, weights, placement, *, streaming_compute=True,execution_policy='s0'):
    if execution_policy not in ('s0','s1'):raise ValueError('Unknown FFN dependency policy')
    locations={w.tensor:w for w in weights}
    ops={p.operation:p.cluster for p in placement}
    profiles={c.id:c.profile for c in machine.stack.compute_clusters}
    tasks=[]; work={}
    objects=tuple(ResidentObject(w.tensor,w.memory,w.offset_bytes,w.size_bytes,storage_id=w.tensor) for w in weights)
    for op in logical.operations:
        cluster=ops[op.id]; profile=profiles[cluster]
        reads=tuple(ReadAccess(name,0,locations[name].size_bytes) for name in op.weight_tensors)
        stream=None
        if streaming_compute and op.kind=='gemm':
            if len(op.weight_tensors)!=1:raise ValueError('One explicit GEMM matrix per streaming task')
            name=op.weight_tensors[0];data_bytes=logical.shape[0]*logical.shape[2]
            scales=locations[name].size_bytes-data_bytes
            reads=(ReadAccess(name,data_bytes,scales),ReadAccess(name,0,data_bytes))
            stream=StreamGemm(name,data_bytes,scales,op.macs,profile.macs_per_cycle,profile.weight_read_bytes_per_cycle)
        bytes_=sum(r.size_bytes for r in reads)
        cycles=profile.cycles(op.macs,op.vector_ops,bytes_)
        tasks.append(ComputeTask(op.id,cluster,cycles,reads,scratch_bytes=op.scratch_bytes,stream=stream))
        work[op.id]=dict(kind=op.kind,macs=op.macs,vector_ops=op.vector_ops,weight_bytes=bytes_,
            compute_profile=asdict(profile))
    edges=[]; copies=[]
    for tensor in logical.tensors:
        if tensor.producer is None: continue
        for consumer in tensor.consumers:
            key=tensor.id+'/to/'+consumer
            edges.append(DataEdge(key,tensor.producer,consumer,tensor.bytes))
            copies.append(dict(id=key,tensor=tensor.id,storage_id=tensor.storage_id,
                source=ops[tensor.producer],destination=ops[consumer],bytes=tensor.bytes,
                policy='explicit conservative copy, reserved until consumer executes; no implicit alias'))
    # S0 retains historical resource-order barriers. S1 removes gate->up, but
    # keeps the previous-block barrier for BOTH projections; S2 is not implied.
    control=[]
    for op in logical.operations:
        if execution_policy=='s0' and op.kind=='gemm' and op.id.endswith('/up'):
            control.append(ControlEdge(op.id[:-2]+'gate',op.id))
        if op.kind=='gemm' and op.block is not None:
            previous=op.block-1
            blocks=logical.shape[1]//logical.shape[2]
            part_blocks=blocks//logical.partitions
            if (op.id.endswith('/gate') or (execution_policy=='s1' and op.id.endswith('/up'))) and op.block%part_blocks:
                control.append(ControlEdge(f'e{op.expert}/b{previous}/accumulate',op.id))
    graph=ExecutionGraph(tuple(tasks),objects,tuple(edges),tuple(control))
    meta=dict(schema='w2w.execution-lowering.v3',logical_sha256=digest_read_v1(asdict(logical)),
        weight_layout_sha256=digest_read_v1([asdict(w) for w in weights]),
        compute_placement_sha256=digest_read_v1([asdict(p) for p in placement]),
        task_work=work,physical_copies=copies,
        arithmetic='gated FFN; SiLU only after complete gate/up GEMM; FP32 partial sums; timing, not numerical validation',
        macs=sum(o.macs for o in logical.operations),vector_ops=sum(o.vector_ops for o in logical.operations),
        weight_read_bytes=sum(r.size_bytes for t in graph.tasks for r in t.reads),
        copy_contract='Logical tensor identity is distinct from these deliberately materialized execution copies')
    meta['compute_contract']=('scale first, then data-driven GEMM on committed descriptor payload; complete gate/up before SiLU; full matrix storage still reserved'
        if streaming_compute else 'blocking GEMM reference')
    if execution_policy=='s1':meta['dependency_policy']='independent gate/up; both wait for previous block accumulate; activation/down and ordered accumulate data edges unchanged'
    return graph,meta
