"""GQA/KV/norm/residual tasks on the same shape-aware NPU and physical kernel.

This is a conservative materialized GQA reference, not FlashAttention. KV V
transpose, FP32->BF16, dense causal mask, input copies and SRAM ports are paid.
Captured routes remain gated by the modeled Router and never supply values.
"""
from collections import defaultdict
from dataclasses import asdict
from math import ceil
from w2w.domain.execution import ComputeTask,DataEdge,ControlEdge,ReadAccess,StreamGemm,ExecutionGraph
from w2w.domain.npu import GemmKernel
from w2w.system.npu_kernel import program
from .moe_batch_lowering import lower_batch


def lower_context(batch,machine,catalog,npu_profile,kv_lengths,*,prefix):
    g,kernels,meta=lower_batch(batch,machine,catalog,npu_profile,prefix=prefix)
    tasks=list(g.tasks);data=list(g.data);control=list(g.control);aux={};append=[];reads=[]
    objects={o.id:o for o in catalog['objects']};p=catalog['llm_profile'];H=p['hidden'];D=p['head_dim']
    M=batch.token_count;layer=batch.layer_id;root=f'L{layer}/context/';origin=prefix+'context/'
    name=lambda x:origin+x
    def edge(tag,a,b,size):data.append(DataEdge(name(tag),a,b,size))
    def scalar(key,tile,read=0,write=0,ops=0,weights=0,accesses=(),scratch=0):
        work=dict(activation_sram_bytes=read,output_sram_bytes=write,vector_ops=ops,weight_sram_bytes=weights)
        limits=dict(activation_sram_bytes=npu_profile.activation_read_bytes_per_cycle,
            output_sram_bytes=npu_profile.output_write_bytes_per_cycle,vector_ops=npu_profile.vector_ops_per_cycle,
            weight_sram_bytes=npu_profile.weight_read_bytes_per_cycle)
        cycles=max(1,max(ceil(work[f]/limits[f]) for f in work))
        tasks.append(ComputeTask(key,tile,cycles,tuple(accesses),scratch));aux[key]=work;return key
    def norm(kind,N,source):
        key=name(kind);obj=objects[root+kind];tile=catalog['context_placements'][obj.id]
        scalar(key,tile,4*M*N,2*M*N,7*M*N,2*N,(ReadAccess(obj.id,0,obj.size_bytes),))
        edge(kind+'/input',source,key,2*M*N);return key
    def gemm(kind,N,K,source,weight=None,tile=None,rows=M):
        key=name(kind);weight=weight or root+kind;tile=tile or catalog['context_placements'][weight]
        k=GemmKernel(key,rows,N,K,weight,weight_dtype='FP8_E4M3FN' if weight in objects else 'BF16',cached_weights=weight in objects)
        _,plan=program(rows,N,K,k.weight_dtype,npu_profile)
        accesses=(ReadAccess(weight,0,objects[weight].size_bytes),) if weight in objects else ()
        stream=StreamGemm(weight,N*K,objects[weight].size_bytes-N*K,k.macs,16384,32768) if accesses else None
        tasks.append(ComputeTask(key,tile,plan['cycles'],accesses,plan['scratch_bytes'],stream=stream));kernels[key]=k
        edge(kind+'/activation',source,key,2*rows*K);return key
    source=name('input');tasks.append(ComputeTask(source,'c0',1))
    norm0=norm('input_norm',H,source)
    q=gemm('q',p['query_heads']*D,H,norm0);k=gemm('k',p['kv_heads']*D,H,norm0);v=gemm('v',p['kv_heads']*D,H,norm0)
    def convert(kind,N,source,normalize=False):
        key=name(kind);tile=next(t.tile for t in tasks if t.id==source);gamma=objects[root+kind.split('/')[0]] if normalize else None
        access=(ReadAccess(gamma.id,0,gamma.size_bytes),) if gamma else ()
        scalar(key,tile,4*M*N,2*M*N,(14 if normalize else 1)*M*N,
            gamma.size_bytes if gamma else 0,access)
        edge(kind+'/input',source,key,4*M*N);return key
    q=convert('q_norm/rope',p['query_heads']*D,q,True)
    k=convert('k_norm/rope',p['kv_heads']*D,k,True);v=convert('v_bf16',p['kv_heads']*D,v)
    members=defaultdict(list)
    for index,row in enumerate(batch.observations):members[row.request_id].append((index,row))
    gathered=[];local_layer=catalog['layers'].index(layer)
    for rid,rows in members.items():
        positions=[r.token_position for _,r in rows];before=kv_lengths.get((layer,rid),0)
        if positions!=list(range(before,before+len(rows))):raise ValueError('KV append skips, repeats or uses unavailable context positions')
        length=before+len(rows);P=len(rows)
        if length>p['kv_tokens_per_request']:raise ValueError('Context exceeds declared SRAM KV capacity; no silent truncation/offload')
        for h in range(p['kv_heads']):
            tile=f'c{local_layer*p["kv_heads"]+h}';tag=f'{rid}/kv{h}'
            add=name(tag+'/append');scalar(add,tile,4*P*D,4*P*D,P*2*D)
            edge(tag+'/new_K',k,add,2*P*D);edge(tag+'/new_V',v,add,2*P*D)
            append.append(dict(task=add,layer=layer,request_id=rid,head=h,before=before,after=length,bytes=4*P*D,tile=tile))
            key_read=name(tag+'/K_read');value_read=name(tag+'/V_transpose')
            group=p['query_heads']//p['kv_heads']
            scalar(key_read,tile,2*length*D*group,2*length*D*group,length*D*group)
            scalar(value_read,tile,2*length*D*(group+1),2*length*D*(group+1),length*D*(group+1))
            control.extend((ControlEdge(add,key_read),ControlEdge(add,value_read)))
            reads.extend((dict(task=key_read,layer=layer,request_id=rid,head=h,length=length,kind='K'),
                dict(task=value_read,layer=layer,request_id=rid,head=h,length=length,kind='V_transpose')))
            for head in range(h*group,(h+1)*group):
                base=f'{rid}/head{head}'
                qk=gemm(base+'/qk',length,D,q,weight=f'KV/L{layer}/{rid}/K{h}',tile=tile,rows=P)
                edge(base+'/K',key_read,qk,2*length*D)
                softmax=name(base+'/causal_softmax');scalar(softmax,tile,4*P*length,2*P*length,9*P*length)
                edge(base+'/scores',qk,softmax,4*P*length)
                pv=gemm(base+'/pv',D,length,softmax,weight=f'KV/L{layer}/{rid}/V{h}',tile=tile,rows=P)
                edge(base+'/V',value_read,pv,2*length*D)
                out=name(base+'/bf16');scalar(out,tile,4*P*D,2*P*D,P*D)
                edge(base+'/output',pv,out,4*P*D);gathered.append((out,2*P*D))
    concat=name('head_concat');scalar(concat,'c0',2*M*p['query_heads']*D,2*M*p['query_heads']*D,M*p['query_heads']*D)
    for i,(a,size) in enumerate(gathered):edge(f'head_concat/{i}',a,concat,size)
    o=gemm('o',H,p['query_heads']*D,concat)
    residual=name('attention_residual');scalar(residual,'c0',6*M*H,2*M*H,2*M*H)
    edge('attention_output',o,residual,4*M*H);edge('attention_skip',source,residual,2*M*H)
    norm1=norm('post_norm',H,residual)
    finishes=[]
    for t in range(M):
        edge(f'moe_input/{t}',norm1,prefix+f't{t}/input',2*H)
        finish=name(f't{t}/moe_residual');scalar(finish,'c0',4*H,2*H,H)
        edge(f'moe_output/{t}',prefix+f't{t}/combine',finish,2*H)
        edge(f'moe_skip/{t}',residual,finish,2*H);finishes.append(finish)
    meta.update(finish_tasks=finishes,context_input=source,auxiliary=aux,kv_appends=append,kv_reads=reads,
        causal_attention=dict(mode='Dense materialized GQA reference, explicit causal mask; no FlashAttention/reuse efficiency claim',
            query_heads=p['query_heads'],kv_heads=p['kv_heads'],head_dim=D,
            token_positions=[r.token_position for r in batch.observations],scope='Captured token identity; lengths are declared captured-row-count assumptions, no text/numerical values'),
        npu_kernels={key:asdict(value) for key,value in kernels.items()})
    return ExecutionGraph(tuple(tasks),catalog['objects'],tuple(data),tuple(control)),kernels,meta
