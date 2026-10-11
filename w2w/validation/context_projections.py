"""Independent complete output-row, FP8 scale and materialized-copy checks."""
from collections import defaultdict
from math import ceil


def audit_projection_call(result,batch,catalog,prefix):
    p=catalog['llm_profile'];M=batch.token_count;H=p['hidden'];D=p['head_dim']
    kernels=result['npu_execution']['kernels'];aux=result['npu_execution']['auxiliary']
    tasks={t['id']:t for t in result['graph']['tasks']};objects={o['id']:o for o in result['graph']['objects']}
    incoming=defaultdict(list);outgoing=defaultdict(list)
    for edge in result['graph']['data']:incoming[edge['consumer']].append(edge);outgoing[edge['producer']].append(edge)
    assemblies={a['kind']:a for a in result['runtime_metadata'].get('projection_assemblies',()) if a['task'].startswith(prefix)}
    if catalog.get('context_projection_shards') and set(assemblies)!={'q','k','v','o'}:
        raise ValueError('Sharded projections omitted a complete output assembly')
    total=0
    for kind,N,K in (('q',p['query_heads']*D,H),('k',p['kv_heads']*D,H),('v',p['kv_heads']*D,H),('o',H,p['query_heads']*D)):
        root=f'L{batch.layer_id}/context/{kind}';key=prefix+'context/'+kind
        if kind in assemblies:
            assembly=assemblies[kind]
            if (assembly['task'],assembly['M'],assembly['N'],assembly['K'])!=(key,M,N,K):raise ValueError('Projection logical shape changed')
            pieces=sorted(assembly['shards'],key=lambda a:a['row_begin']);at=0;expected=catalog['context_projection_shards'][root]
            if len(pieces)!=len(expected):raise ValueError('Output shard count changed')
            for part,want in zip(pieces,expected):
                if (part['row_begin']!=at or part['row_end']-at!=part['N'] or at%128
                        or part['scale_row_begin']!=at//128 or any(part[k]!=v for k,v in want.items())):
                    raise ValueError('Output rows/scales overlap, skip or alias another source')
                at=part['row_end']
                links=outgoing[part['task']]
                if len(links)!=1 or links[0]['consumer']!=key or links[0]['size_bytes']!=4*M*part['N']:
                    raise ValueError('Row gather did not transport the full shard')
            if at!=N:raise ValueError('Projection lost output channels')
            gather=aux[key]
            descriptors=32*len(pieces)
            if (gather['activation_sram_bytes'],gather['output_sram_bytes'],gather['vector_ops'])!=(4*M*N+descriptors,4*M*N+descriptors,M*N+2*len(pieces)) or tasks[key]['scratch_bytes']<descriptors:
                raise ValueError('FP32 row-strided gather or bounded association state unpaid')
            for copy in assembly['input_copies']:
                work=aux[copy['task']];src=incoming[copy['task']];dst=outgoing[copy['task']];c=copy['outputs'];size=2*M*K
                if (not 1<=c<=4 or copy['input_bytes']!=size or len(src)!=1 or src[0]['producer']!=copy['source']
                        or src[0]['size_bytes']!=size or len(dst)!=c or any(e['size_bytes']!=size for e in dst)
                        or (work['activation_sram_bytes'],work['output_sram_bytes'],work['vector_ops'])!=(size+32*c,c*size+32*c,c*(M*K+2))
                        or tasks[copy['task']]['scratch_bytes']<32*c):raise ValueError('Input tree copied or broadcast data without storage/service')
        else:pieces=[dict(task=key,weight_object=root,N=N)]
        for part in pieces:
            k=kernels[part['task']];obj=objects[part['weight_object']]
            if ((k['M'],k['N'],k['K'])!=(M,part['N'],K) or k['weight_dtype']!='FP8_E4M3FN'
                    or k['weight_object']!=obj['id'] or obj['size_bytes']!=part['N']*K+4*ceil(part['N']/128)*ceil(K/128)):
                raise ValueError('Projection did not form complete original hidden reductions/scales')
            total+=M*part['N']*K
    expected=M*H*D*(2*p['query_heads']+2*p['kv_heads'])
    if total!=expected:raise ValueError('Q/K/V/O mathematical work changed')
    return dict(passed=True,projection_macs=total,sharded=bool(assemblies),
        scope='Complete original dot products and paid copies/gathers; no captured numerical tensors or architecture performance claim.')
