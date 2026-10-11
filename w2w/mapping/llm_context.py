"""GQA/KV/norm/residual tasks on the same shape-aware NPU and physical kernel.

This is a conservative materialized GQA reference, not FlashAttention. KV V
transpose, FP32->BF16, dense causal mask, input copies and SRAM ports are paid.
Captured routes remain gated by the modeled Router and never supply values.
"""
from collections import defaultdict
from dataclasses import asdict
from math import ceil,log2
from w2w.domain.execution import ComputeTask,DataEdge,ControlEdge,ReadAccess,StreamGemm,ExecutionGraph
from w2w.domain.npu import GemmKernel
from w2w.system.npu_kernel import program
from .moe_batch_lowering import lower_batch


def lower_context(batch,machine,catalog,npu_profile,kv_lengths,*,prefix):
    g,kernels,meta=lower_batch(batch,machine,catalog,npu_profile,prefix=prefix)
    tasks=list(g.tasks);data=list(g.data);control=list(g.control);aux=dict(meta['auxiliary']);append=[];reads=[]
    objects={o.id:o for o in catalog['objects']};p=catalog['llm_profile'];H=p['hidden'];D=p['head_dim']
    M=batch.token_count;layer=batch.layer_id;root=f'L{layer}/context/';origin=prefix+'context/'
    name=lambda x:origin+x
    def edge(tag,a,b,size):data.append(DataEdge(name(tag),a,b,size))
    def scalar(key,tile,read=0,write=0,ops=0,weights=0,accesses=(),scratch=0,phases=None):
        from w2w.system.npu_auxiliary import phase,work,auxiliary_program
        spec=work(phases or (phase('vector',read=read,write=write,ops=ops,weights=weights),))
        cycles=len(auxiliary_program(spec,npu_profile))
        tasks.append(ComputeTask(key,tile,cycles,tuple(accesses),scratch));aux[key]=spec;return key
    def norm(kind,N,source):
        from w2w.system.npu_auxiliary import phase
        key=name(kind);obj=objects[root+kind];tile=catalog['context_placements'][obj.id]
        scalar(key,tile,accesses=(ReadAccess(obj.id,0,obj.size_bytes),),scratch=8*M,phases=(
            phase('RMS-reduction',read=2*M*N,ops=3*M*N,floor=1+ceil(log2(N))),
            phase('normalize',read=2*M*N,weights=2*M*N,write=2*M*N,ops=4*M*N)))
        edge(kind+'/input',source,key,2*M*N);return key
    def gemm(kind,N,K,source,weight=None,tile=None,rows=M):
        key=name(kind);weight=weight or root+kind;tile=tile or catalog['context_placements'][weight]
        k=GemmKernel(key,rows,N,K,weight,weight_dtype='FP8_E4M3FN' if weight in objects else 'BF16',cached_weights=weight in objects)
        _,plan=program(rows,N,K,k.weight_dtype,npu_profile)
        accesses=(ReadAccess(weight,0,objects[weight].size_bytes),) if weight in objects else ()
        stream=StreamGemm(weight,N*K,objects[weight].size_bytes-N*K,k.macs,16384,32768) if accesses else None
        tasks.append(ComputeTask(key,tile,plan['cycles'],accesses,plan['scratch_bytes'],stream=stream));kernels[key]=k
        edge(kind+'/activation',source,key,k.activation_storage_bytes);return key
    source=name('input');scalar(source,'c0',2*M*H,4*M*H,M*H,scratch=2*M*H)
    norm0=norm('input_norm',H,source)
    q=gemm('q',p['query_heads']*D,H,norm0);k=gemm('k',p['kv_heads']*D,H,norm0);v=gemm('v',p['kv_heads']*D,H,norm0)
    def convert(kind,N,source,normalize=False):
        from w2w.system.npu_auxiliary import phase
        key=name(kind);tile=next(t.tile for t in tasks if t.id==source);gamma=objects[root+kind.split('/')[0]] if normalize else None
        access=(ReadAccess(gamma.id,0,gamma.size_bytes),) if gamma else ()
        if normalize:
            rope=objects[root+'rope_table'];access+=tuple(ReadAccess(rope.id,row.token_position*D*4,D*4) for row in batch.observations)
        phases=(phase('linear-FP32-to-BF16',read=4*M*N,write=2*M*N,ops=M*N),
            phase('per-head-RMS-reduction',read=2*M*N,ops=3*M*N,floor=1+ceil(log2(D))),
            phase('normalize-to-BF16',read=2*M*N,write=2*M*N,weights=2*M*N,ops=5*M*N),
            phase('RoPE-BF16-pairs',read=2*M*N,write=2*M*N,weights=4*M*N,ops=6*M*N)) if normalize else None
        scalar(key,tile,4*M*N,2*M*N,M*N,accesses=access,
            scratch=(2*M*N+8*M*(N//D)) if normalize else 0,phases=phases)
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
            group=p['query_heads']//p['kv_heads'];value_bytes=D*ceil(length*2/32)*32
            scalar(key_read,tile,2*length*D,2*length*D,length*D)
            scalar(value_read,tile,2*length*D,value_bytes,length*D+D*(ceil(length*2/32)*16-length),scratch=value_bytes)
            control.extend((ControlEdge(add,key_read),ControlEdge(add,value_read)))
            reads.extend((dict(task=key_read,layer=layer,request_id=rid,head=h,length=length,tensor_kind='K'),
                dict(task=value_read,layer=layer,request_id=rid,head=h,length=length,tensor_kind='V_transpose')))
            # Sixteen query heads share one KV head. Flatten their independent
            # query rows into M, reusing one KV matrix on the existing arrays.
            base=f'{rid}/group{h}';R=P*group;packed=name(base+'/query_pack')
            scalar(packed,tile,2*R*D,2*R*D,R*D);edge(base+'/query_rows',q,packed,2*R*D)
            qk=gemm(base+'/qk',length,D,packed,weight=f'KV/L{layer}/{rid}/K{h}',tile=tile,rows=R)
            edge(base+'/K',key_read,qk,2*length*D)
            from w2w.system.npu_auxiliary import phase
            softmax=name(base+'/causal_softmax');padded=R*ceil(length*2/32)*32
            scalar(softmax,tile,scratch=4*R*length,phases=(
                phase('scale-and-causal-mask',read=4*R*length,write=4*R*length,ops=2*R*length),
                phase('causal-mask-max',read=4*R*length,ops=R*length,floor=1+ceil(log2(length))),
                phase('shift-exp-sum',read=4*R*length,write=4*R*length,ops=4*R*length,floor=1+ceil(log2(length))),
                phase('normalize-BF16-zero-padding',read=4*R*length,write=padded,ops=4*R*length+(padded//2-R*length))))
            edge(base+'/scores',qk,softmax,4*R*length)
            pv=gemm(base+'/pv',D,length,softmax,weight=f'KV/L{layer}/{rid}/V{h}',tile=tile,rows=R)
            edge(base+'/V',value_read,pv,value_bytes)
            out=name(base+'/bf16');scalar(out,tile,4*R*D,2*R*D,R*D)
            edge(base+'/output',pv,out,4*R*D);gathered.append((out,2*R*D))
    concat=name('head_concat');scalar(concat,'c0',2*M*p['query_heads']*D,2*M*p['query_heads']*D,M*p['query_heads']*D)
    for i,(a,size) in enumerate(gathered):edge(f'head_concat/{i}',a,concat,size)
    o=gemm('o',H,p['query_heads']*D,concat)
    from w2w.system.npu_auxiliary import phase
    residual=name('attention_residual');scalar(residual,'c0',scratch=2*M*H,phases=(
        phase('attention-O-to-BF16',read=4*M*H,write=2*M*H,ops=M*H),
        phase('BF16-residual',read=4*M*H,write=2*M*H,ops=M*H)))
    edge('attention_output',o,residual,4*M*H);edge('attention_skip',source,residual,2*M*H)
    norm1=norm('post_norm',H,residual)
    finishes=[]
    for t in range(M):
        edge(f'moe_input/{t}',norm1,prefix+f't{t}/input',2*H)
        finish=name(f't{t}/moe_residual');scalar(finish,'c0',4*H,2*H,H)
        edge(f'moe_output/{t}',prefix+f't{t}/combine',finish,2*H)
        edge(f'moe_skip/{t}',residual,finish,2*H);finishes.append(finish)
    meta.update(finish_tasks=finishes,context_input=source,auxiliary=aux,kv_appends=append,kv_reads=reads,
        causal_attention=dict(mode='Dense GQA reference grouping query heads that share KV into M; explicit causal mask, word padding and V transpose; no FlashAttention claim',
            query_heads=p['query_heads'],kv_heads=p['kv_heads'],head_dim=D,
            token_positions=[r.token_position for r in batch.observations],query_row_order='token-major then query-head within each KV group; mask position uses row//query-heads-per-KV',
            scope='Captured token identity; lengths are declared captured-row-count assumptions, no text/numerical values'),
        npu_kernels={key:asdict(value) for key,value in kernels.items()})
    return ExecutionGraph(tuple(tasks),catalog['objects'],tuple(data),tuple(control)),kernels,meta
