"""Declared modeled embedding addresses and full BF16 distributed LM-head argmax."""
from dataclasses import asdict
from hashlib import sha256
from math import ceil,log2
from w2w.domain.execution import ComputeTask,ReadAccess,DataEdge,ExecutionGraph
from w2w.domain.npu import GemmKernel
from w2w.system.npu_kernel import program


def add_boundaries(graph,kernels,metadata,batches,catalog,machine,profile,cohort,*,index,stage,release_ps):
    from dataclasses import replace
    tasks=list(graph.tasks);data=list(graph.data);aux=metadata['auxiliary'];objects={o.id:o for o in graph.objects}
    p=catalog['llm_profile'];H=p['hidden'];V=p['vocabulary'];first=batches[0];last=batches[-1]
    def scalar(key,tile,read=0,write=0,ops=0,weights=0,accesses=(),scratch=0,phases=None):
        from w2w.system.npu_auxiliary import phase,work,auxiliary_program
        spec=work(phases or (phase('vector',read=read,write=write,ops=ops,weights=weights),))
        cycles=len(auxiliary_program(spec,profile));aux[key]=spec
        tasks.append(ComputeTask(key,tile,cycles,tuple(accesses),scratch,release_ps=release_ps));return key
    embeddings=[]
    if catalog['embedding']:
        for t,row in enumerate(first.observations):
            # Explicitly MODELED because capture supplies no vocabulary IDs.
            address=int.from_bytes(sha256(str(row.token_id).encode()).digest()[:8],'big')%V
            start=address//4096*4096;key=f'W{index:04d}/embedding/{t}';obj=objects[f'embedding/{start}']
            scalar(key,catalog['context_placements'][obj.id],write=2*H,ops=H,weights=2*H,
                accesses=(ReadAccess(obj.id,(address-start)*2*H,2*H),))
            data.append(DataEdge(key+'/X',key,metadata['context_inputs'][0],2*H))
            embeddings.append(dict(task=key,token_id=row.token_id,vocabulary_row=address,
                provenance='Modeled stable SHA256 address, not captured vocabulary ID'))
    heads=[]
    if catalog['head']:
        lengths={c['request_id']:c['coverage']['prefill_tokens'] for c in cohort}
        selected=[(t,row) for t,row in enumerate(last.observations) if row.phase=='decode' or row.token_position+1==lengths[row.request_id]]
        if selected:
            M=len(selected);base=f'W{index:04d}/head';normal=base+'/norm';gamma=objects['final_norm']
            from w2w.system.npu_auxiliary import phase
            scalar(normal,'c0',accesses=(ReadAccess(gamma.id,0,gamma.size_bytes),),scratch=8*M,phases=(
                phase('RMS-reduction',read=2*M*H,ops=3*M*H,floor=1+ceil(log2(H))),
                phase('normalize',read=2*M*H,write=2*M*H,weights=2*M*H,ops=4*M*H)))
            for t,row in selected:data.append(DataEdge(base+f'/input/{t}',metadata['finish_tasks'][t],normal,2*H))
            partial=[]
            for start in range(0,V,4096):
                obj=objects[f'lm_head/{start}'];N=min(4096,V-start);key=base+f'/gemm/{start}';tile=catalog['context_placements'][obj.id]
                k=GemmKernel(key,M,N,H,obj.id,weight_dtype='BF16',cached_weights=True);_,plan=program(M,N,H,k.weight_dtype,profile)
                tasks.append(ComputeTask(key,tile,plan['cycles'],(ReadAccess(obj.id,0,obj.size_bytes),),plan['scratch_bytes']))
                kernels[key]=k;data.append(DataEdge(key+'/X',normal,key,2*M*H))
                out=base+f'/local_argmax/{start}';scalar(out,tile,4*M*N,8*M,M*N)
                data.append(DataEdge(out+'/logits',key,out,4*M*N));partial.append(out)
            final=base+'/ordered_argmax';scalar(final,'c0',8*M*len(partial),4*M,M*len(partial))
            for n,key in enumerate(partial):data.append(DataEdge(final+f'/partial/{n}',key,final,8*M))
            heads=[dict(request_id=row.request_id,phase=row.phase,decode_step=row.decode_step,task=final,
                precision='Ordered FP32 max/index partials, BF16 untied LM weights; values unavailable') for t,row in selected]
    # Stage boundary buffers attach to c15 through the real local NoC.
    if not catalog['embedding']:
        ingress=f'W{index:04d}/pipeline/ingress';size=len(first.observations)*2*H
        scalar(ingress,'c15',size,size,len(first.observations)*H,scratch=size)
        data.append(DataEdge(ingress+'/X',ingress,metadata['context_inputs'][0],size))
    export=f'W{index:04d}/pipeline/export'
    if not catalog['head']:
        size=len(last.observations)*2*H;scalar(export,'c15',size,size,len(last.observations)*H)
        for t,key in enumerate(metadata['finish_tasks']):data.append(DataEdge(export+f'/X/{t}',key,export,2*H))
    elif heads:
        size=4*len(heads);scalar(export,'c15',size,size,len(heads))
        data.append(DataEdge(export+'/token',heads[0]['task'],export,size))
    # Every root is delayed until the paid input/feedback link has committed.
    consumers={e.consumer for e in (*data,*graph.control)}
    tasks=[replace(t,release_ps=max(t.release_ps,release_ps)) if t.id not in consumers else t for t in tasks]
    metadata.update(embeddings=embeddings,heads=heads,release_ps=release_ps,stage=stage,
        export_task=export if not catalog['head'] or heads else None,
        npu_kernels={k:asdict(v) for k,v in kernels.items()},
        boundary_contract='Modeled embedding rows explicitly disclosed. Distributed full BF16 LM head, ordered max/index, paid SRAM/Native/cache/ports. No captured numerical output claim.')
    return ExecutionGraph(tuple(tasks),graph.objects,tuple(data),graph.control),kernels,metadata
