"""Post-router MoE math: explicit dispatch, expert FFNs and weighted combine.

Ranked IDs are captured. Coefficient packet size is explicit BF16/FP32 timing
format; coefficient values/router execution are unavailable, never invented.
"""
from collections import defaultdict
from dataclasses import replace
from .ir import Operation,Tensor
from .moe import build_moe


def build_captured_moe(token_experts,**kwargs):
    base=build_moe(token_experts,**kwargs);hidden=base.shape[0]
    operations=list(base.operations);tensors=[];dispatch=defaultdict(list)
    for token,experts in enumerate(base.tokens):
        for expert in experts:
            key=f't{token}/dispatch/e{expert}'
            # A fixed expert anchor from the full catalog, before compute placement.
            operations.append(Operation(key,'moe_dispatch',expert=expert,block=0,partition=0,
                token_ids=(token,),vector_ops=hidden))
            dispatch[token].append(key)
            consumers=tuple(o.id for o in base.operations if o.kind=='gemm' and o.expert==expert
                and token in o.token_ids and o.id.endswith(('/gate','/up')))
            tensors.append(Tensor(f'dispatched/t{token}/e{expert}',2*hidden,'BF16',key,consumers,
                f'dispatched/t{token}/e{expert}'))
        # The source records IDs only. These 4-byte coefficients are an explicit
        # transfer-format assumption for timing, not captured values or uniform probabilities.
        tensors.append(Tensor(f'coefficients/t{token}',4*len(experts),'FP32',f't{token}/input',
            (f't{token}/combine',),f'coefficients/t{token}'))
    for tensor in base.tensors:
        if tensor.id.startswith('X/t'):
            token=int(tensor.id[3:]);tensor=replace(tensor,consumers=tuple(dispatch[token]))
        tensors.append(tensor)
    return replace(base,name='captured-post-router-moe',operations=tuple(operations),tensors=tuple(tensors))
