"""Independent complete output-row, FP8 scale and materialized-copy checks."""
from collections import defaultdict
from math import ceil


def _vector_phases(spec,expected):
    """Check descriptor initialization precedes its dependent copy/gather."""
    fields=('activation_sram_bytes','output_sram_bytes','weight_sram_bytes',
        'vector_ops','activation_delivery_bytes','cycles_floor')
    phases=spec.get('phases',())
    if len(phases)!=len(expected):raise ValueError('Projection vector phases missing/repeated')
    for actual,want in zip(phases,expected):
        required=dict(activation_sram_bytes=0,output_sram_bytes=0,weight_sram_bytes=0,
            vector_ops=0,activation_delivery_bytes=0,cycles_floor=1)
        required.update(want)
        if any(actual.get(f)!=required[f] for f in fields):
            raise ValueError('Projection descriptor/copy/gather phase order or work changed')


def _input_tree(assembly,source,tasks,incoming,outgoing,aux,M,K):
    copies=assembly['input_copies'];nodes={c['task']:c for c in copies}
    leaves={s['task'] for s in assembly['shards']};size=2*M*K
    if len(nodes)!=len(copies) or not nodes or set(nodes)&leaves or source in nodes:
        raise ValueError('Projection input tree has duplicate/aliased nodes')
    for key,copy in nodes.items():
        work=aux[key];src=incoming[key];dst=outgoing[key];c=copy['outputs']
        if (key not in tasks or not 1<=c<=4 or copy['input_bytes']!=size or len(src)!=1
                or src[0]['producer']!=copy['source'] or src[0]['size_bytes']!=size or len(dst)!=c
                or any(e['size_bytes']!=size or e['consumer'] not in set(nodes)|leaves for e in dst)
                or len({e['consumer'] for e in dst})!=c
                or (work['activation_sram_bytes'],work['output_sram_bytes'],work['vector_ops'])
                    !=(size+32*c,c*size+32*c,c*(M*K+2))
                or tasks[key]['scratch_bytes']<32*c):
            raise ValueError('Input tree copied or broadcast data without storage/service')
        _vector_phases(work,(dict(output_sram_bytes=32*c,vector_ops=c),
            dict(activation_sram_bytes=size+32*c,output_sram_bytes=c*size,vector_ops=c*(M*K+1))))
    # Each leaf and copy must reach this projection's actual BF16 source.
    # Matching byte counts cannot distinguish another tensor of the same shape.
    for leaf in leaves:
        links=incoming[leaf]
        if len(links)!=1 or links[0]['size_bytes']!=size or links[0]['producer'] not in nodes:
            raise ValueError('Projection shard lacks its materialized BF16 input')
    for key in set(nodes)|leaves:
        at=key;seen=set()
        while at!=source:
            if at in seen:raise ValueError('Projection input copy tree contains a cycle')
            seen.add(at)
            links=incoming[at]
            if len(links)!=1:raise ValueError('Projection input tree is not singly owned')
            at=links[0]['producer']
            if at!=source and at not in nodes:raise ValueError('Projection uses another tensor as its input')


def audit_projection_call(result,batch,catalog,prefix):
    p=catalog['llm_profile'];M=batch.token_count;H=p['hidden'];D=p['head_dim']
    kernels=result['npu_execution']['kernels'];aux=result['npu_execution']['auxiliary']
    tasks={t['id']:t for t in result['graph']['tasks']};objects={o['id']:o for o in result['graph']['objects']}
    incoming=defaultdict(list);outgoing=defaultdict(list)
    for edge in result['graph']['data']:incoming[edge['consumer']].append(edge);outgoing[edge['producer']].append(edge)
    records=[a for a in result['runtime_metadata'].get('projection_assemblies',()) if a['task'].startswith(prefix)]
    assemblies={a['kind']:a for a in records}
    if len(records)!=len(assemblies):raise ValueError('Projection output assembly repeated')
    sharded=bool(catalog.get('context_projection_shards'))
    if sharded and set(assemblies)!={'q','k','v','o'}:
        raise ValueError('Sharded projections omitted a complete output assembly')
    if not sharded and assemblies:raise ValueError('Projection policy differs from its registered catalog')
    total=0
    for kind,N,K in (('q',p['query_heads']*D,H),('k',p['kv_heads']*D,H),('v',p['kv_heads']*D,H),('o',H,p['query_heads']*D)):
        root=f'L{batch.layer_id}/context/{kind}';key=prefix+'context/'+kind
        if kind in assemblies:
            assembly=assemblies[kind]
            if (assembly['task'],assembly['M'],assembly['N'],assembly['K'])!=(key,M,N,K):raise ValueError('Projection logical shape changed')
            pieces=sorted(assembly['shards'],key=lambda a:a['row_begin']);at=0;expected=catalog['context_projection_shards'][root]
            if len(pieces)!=len(expected):raise ValueError('Output shard count changed')
            for part,want in zip(pieces,expected):
                if (part['task']!=prefix+f'context/{kind}/rows{at:05d}'
                        or part['row_begin']!=at or part['row_end']-at!=part['N'] or at%128
                        or part['scale_row_begin']!=at//128 or any(part[k]!=v for k,v in want.items())):
                    raise ValueError('Output rows/scales overlap, skip or alias another source')
                at=part['row_end']
                links=outgoing[part['task']]
                if len(links)!=1 or links[0]['consumer']!=key or links[0]['size_bytes']!=4*M*part['N']:
                    raise ValueError('Row gather did not transport the full shard')
            if at!=N:raise ValueError('Projection lost output channels')
            if len(incoming[key])!=len(pieces) or {e['producer'] for e in incoming[key]}!={a['task'] for a in pieces}:
                raise ValueError('Row gather has missing, repeated or unrelated inputs')
            gather=aux[key]
            descriptors=32*len(pieces)
            if (gather['activation_sram_bytes'],gather['output_sram_bytes'],gather['vector_ops'])!=(4*M*N+descriptors,4*M*N+descriptors,M*N+2*len(pieces)) or tasks[key]['scratch_bytes']<descriptors:
                raise ValueError('FP32 row-strided gather or bounded association state unpaid')
            _vector_phases(gather,(dict(output_sram_bytes=descriptors,vector_ops=len(pieces)),
                dict(activation_sram_bytes=4*M*N+descriptors,output_sram_bytes=4*M*N,vector_ops=M*N+len(pieces))))
            source=prefix+'context/'+('head_concat' if kind=='o' else 'input_norm')
            _input_tree(assembly,source,tasks,incoming,outgoing,aux,M,K)
        else:pieces=[dict(task=key,weight_object=root,N=N)]
        for part in pieces:
            task=tasks[part['task']];k=kernels[part['task']];obj=objects[part['weight_object']]
            if ((k['M'],k['N'],k['K'])!=(M,part['N'],K) or k['weight_dtype']!='FP8_E4M3FN'
                    or k['operation_id']!=part['task'] or k['input_dtype']!='BF16' or k['accumulator_dtype']!='FP32'
                    or tuple(k['scale_group'])!=(128,128) or k['cached_weights'] is not True
                    or k['weight_object']!=obj['id'] or obj['size_bytes']!=part['N']*K+4*ceil(part['N']/128)*ceil(K/128)
                    or task['tile']!=catalog['context_placements'][obj['id']]
                    or tuple(task['reads'])!=(dict(object_id=obj['id'],offset_bytes=0,size_bytes=obj['size_bytes']),)):
                raise ValueError('Projection did not form complete original hidden reductions/scales')
            if not sharded:
                source=prefix+'context/'+('head_concat' if kind=='o' else 'input_norm');links=incoming[part['task']]
                if len(links)!=1 or links[0]['producer']!=source or links[0]['size_bytes']!=2*M*K:
                    raise ValueError('Projection uses another tensor as its input')
            total+=M*part['N']*K
    expected=M*H*D*(2*p['query_heads']+2*p['kv_heads'])
    if total!=expected:raise ValueError('Q/K/V/O mathematical work changed')
    return dict(passed=True,projection_macs=total,sharded=bool(assemblies),
        scope='Complete original dot products and paid copies/gathers; no captured numerical tensors or architecture performance claim.')
