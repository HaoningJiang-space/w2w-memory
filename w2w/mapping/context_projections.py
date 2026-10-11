"""Output-channel tensor parallelism on existing clusters and physical paths.

Every shard forms complete hidden reductions. A paid gather restores the full
FP32 projection before normalization; this is not partial-result readiness.
"""
def output_rows(kind,N,K,machine,local_layer,kv_heads):
    tiles=tuple(t.id for t in machine.tiles)
    count=kv_heads if kind in ('k','v') else len(tiles)
    if N%count or (N//count)%128:raise ValueError('Output shards must retain complete FP8 row scale groups')
    width=N//count;rows=[]
    for part in range(count):
        preferred=tiles[(local_layer*kv_heads+part)%len(tiles)] if kind in ('k','v') else tiles[part]
        rows.append(dict(row_begin=part*width,row_end=(part+1)*width,N=width,K=K,
            scale_row_begin=part*width//128,preferred_cluster=preferred))
    return rows


def lower_projection(kind,N,K,source,source_tile,catalog,M,name,scalar,gemm,edge,layer):
    root=f'L{layer}/context/{kind}';shards=catalog['context_projection_shards'][root]
    inputs=2*M*K;groups=[shards[i:i+4] for i in range(0,len(shards),4)];copies=[]
    groups_source=source
    if len(groups)>1:
        groups_source=name(kind+'/input/root')
        scalar(groups_source,source_tile,inputs,len(groups)*inputs,len(groups)*M*K,scratch=32*len(groups))
        edge(kind+'/input/root_source',source,groups_source,inputs)
        copies.append(dict(task=groups_source,source=source,outputs=len(groups),input_bytes=inputs))
    outputs=[]
    for group_index,group in enumerate(groups):
        key=name(kind+f'/input/group{group_index}');tile=catalog['context_placements'][group[0]['weight_object']]
        scalar(key,tile,inputs,len(group)*inputs,len(group)*M*K,scratch=32*len(group))
        edge(kind+f'/input/group{group_index}',groups_source,key,inputs)
        copies.append(dict(task=key,source=groups_source,outputs=len(group),input_bytes=inputs))
        for shard in group:
            tag=kind+f'/rows{shard["row_begin"]:05d}'
            task=gemm(tag,shard['N'],K,key,weight=shard['weight_object'])
            outputs.append(dict(shard,task=task))
    joined=name(kind);scalar(joined,source_tile,4*M*N,4*M*N,M*N,scratch=32*len(shards))
    for output in outputs:
        edge(kind+f'/gather/{output["row_begin"]:05d}',output['task'],joined,4*M*output['N'])
    return joined,dict(task=joined,kind=kind,M=M,N=N,K=K,shards=outputs,input_copies=copies,
        contract='Complete FP32 output rows; paid row-strided gather into token-major full output. Original FP8 128x128 scale identity, finite tree copies and existing physical resources.')
