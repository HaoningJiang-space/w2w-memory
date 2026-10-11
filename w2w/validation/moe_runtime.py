"""Independent real-route mathematical and vector-storage contract checks."""
from collections import Counter


def audit_moe_call(result,batch,prefix):
    H,I=4096,1536;T=8;M=batch.token_count
    metadata=result['runtime_metadata'];npu=result['npu_execution'];aux=npu['auxiliary']
    kernels=npu['kernels'];tasks={t['id']:t for t in result['graph']['tasks']}
    incoming=Counter();outgoing=Counter()
    for edge in result['graph']['data']:
        incoming[edge['consumer']]+=edge['size_bytes'];outgoing[edge['producer']]+=edge['size_bytes']
    if sum(len(ts) for e,ts in batch.expert_to_tokens)!=M*T:raise ValueError('Token/expert work lost')
    expert_macs=0
    for expert,tokens in batch.expert_to_tokens:
        count=len(tokens)
        for block in range(12):
            for kind in ('gate','up','down'):
                key=prefix+f'e{expert}/b{block}/{kind}';k=kernels[key]
                shape=(count,4096,128) if kind=='down' else (count,128,4096)
                if (k['M'],k['N'],k['K'])!=shape:
                    raise ValueError('Projection is not the actual expert token shape')
                expert_macs+=k['M']*k['N']*k['K']
        key=prefix+f'e{expert}/pack'
        if aux[key]['activation_sram_bytes']!=count*2*H or aux[key]['output_sram_bytes']!=count*2*H*24:
            raise ValueError('Explicit block input copies were not paid')
        key=prefix+f'e{expert}/reduce';phases=aux[key]['phases']
        if len(phases)!=4 or [p['name'] for p in phases[:3]]!=[f'ordered-partition-{i}' for i in range(1,4)]:
            raise ValueError('FP32 partition reduction order changed')
        if any(p['activation_sram_bytes']!=8*count*H or p['output_sram_bytes']!=4*count*H for p in phases[:3]):
            raise ValueError('Partial output read/modify/write omitted')
        if phases[-1]['activation_sram_bytes']!=4*count*H or phases[-1]['output_sram_bytes']!=2*count*H:
            raise ValueError('Expert output BF16 conversion omitted')
    if expert_macs!=3*M*T*H*I:raise ValueError('Full three-projection MAC work changed')
    for token,observation in enumerate(batch.observations):
        key=prefix+f't{token}/combine';phases=aux[key]['phases']
        if [p['name'] for p in phases[1:-1]]!=[f'ordered-ranked-expert-{e}' for e in observation.expert_ids]:
            raise ValueError('Combine used an unordered/incorrect selection')
        if len(phases)!=T+2 or incoming[key]!=T*2*H+T*4:
            raise ValueError('Combine lacks an expert output or coefficient identity')
        if any(p['activation_sram_bytes']!=6*H or p['output_sram_bytes']!=4*H or p['vector_ops']!=2*H for p in phases[1:-1]):
            raise ValueError('Ranked weighted FP32 combine not paid')
        if phases[-1]['output_sram_bytes']!=2*H or tasks[key]['scratch_bytes']<6*H+32+npu['profile']['arrays']*32:
            raise ValueError('Combine accumulator/coefficient storage or conversion omitted')
    if any(t['id'].startswith(prefix) and t['id'] not in kernels and t['id'] not in aux for t in tasks.values()):
        raise ValueError('A real MoE vector task has no explicit resource program')
    return dict(passed=True,token_expert_assignments=M*T,expert_macs=expert_macs,
        vector_contract='Materialized block inputs; ordered FP32 partition and ranked expert combine; paid BF16 conversion and bounded coefficient fanout.')
