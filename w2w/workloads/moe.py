"""Gated FFN mathematics and dependencies; no physical endpoint identifiers."""
from collections import defaultdict
from .ir import LogicalWorkload,Operation,Tensor


def build_moe(token_experts, *, name='routed-ffn', hidden=4096, intermediate=1536,
              block_width=128, experts=128, topk=8, partitions=4, source_identity=()):
    if intermediate%block_width or (intermediate//block_width)%partitions or hidden%128:
        raise ValueError('Explicit 128-aligned scales and integral intermediate partitions required')
    tokens=tuple(tuple(e) for e in token_experts)
    if not tokens or any(len(t)!=topk or len(set(t))!=topk or any(not 0<=e<experts for e in t) for t in tokens):
        raise ValueError('Invalid expert selections')
    members=defaultdict(list)
    for n,es in enumerate(tokens):
        for e in es: members[e].append(n)
    blocks=intermediate//block_width; per_part=blocks//partitions
    matrix_bytes=hidden*block_width+(hidden//128)*4
    weights=tuple((f'weight/e{e}/b{b}/{phase}',matrix_bytes)
        for e in range(experts) for b in range(blocks) for phase in ('gate','up','down'))
    ops=[]; tensors=[]
    def tensor(key,size,dtype,producer,consumers):
        tensors.append(Tensor(key,size,dtype,producer,tuple(consumers),key))
    for n in range(len(tokens)):
        ops.extend((Operation(f't{n}/input','input',token_ids=(n,)),
                    Operation(f't{n}/combine','moe_combine',token_ids=(n,),vector_ops=2*topk*hidden)))
    for e, ids in sorted(members.items()):
        n=len(ids); ids=tuple(ids)
        reduce=f'e{e}/reduce'
        ops.append(Operation(reduce,'partition_reduce',expert=e,token_ids=ids,
            vector_ops=(partitions-1)*n*hidden,scratch_bytes=4*n*hidden))
        for p in range(partitions):
            first=p*per_part
            for b in range(first,first+per_part):
                prefix=f'e{e}/b{b}'
                gate,up,act,down,acc=(prefix+'/'+phase for phase in ('gate','up','activation','down','accumulate'))
                for phase, key in (('gate',gate),('up',up),('down',down)):
                    ops.append(Operation(key,'gemm',e,b,p,ids,macs=n*hidden*block_width,
                        weight_tensors=(f'weight/e{e}/b{b}/{phase}',)))
                ops.append(Operation(act,'silu_product',e,b,p,ids,vector_ops=9*n*block_width))
                ops.append(Operation(acc,'block_accumulate',e,b,p,ids,vector_ops=n*hidden,
                    scratch_bytes=4*n*hidden))
                # One logical X has two consumers. Copies are a mapping decision.
                for t in ids:
                    tensor(f'X/t{t}/e{e}/b{b}',hidden*2,'BF16',f't{t}/input',(gate,up))
                tensor(prefix+'/G',4*n*block_width,'FP32',gate,(act,))
                tensor(prefix+'/U',4*n*block_width,'FP32',up,(act,))
                tensor(prefix+'/H',2*n*block_width,'BF16',act,(down,))
                tensor(prefix+'/Z',4*n*hidden,'FP32',down,(acc,))
                if b>first:
                    tensor(prefix+'/previous_sum',4*n*hidden,'FP32',f'e{e}/b{b-1}/accumulate',(acc,))
            tensor(f'e{e}/p{p}/sum',4*n*hidden,'FP32',f'e{e}/b{first+per_part-1}/accumulate',(reduce,))
        for t in ids:
            tensor(f'e{e}/t{t}/output',2*hidden,'BF16',reduce,(f't{t}/combine',))
    return LogicalWorkload(name,(hidden,intermediate,block_width,experts,topk),tokens,
        tuple(ops),tuple(tensors),weights,tuple(source_identity),partitions)
