"""Static intermediate tensor partitioning on the existing four-node groups.

Three whole 128-wide blocks per shard; BF16 input, FP32 partial sum, owner reduce.
This changes task/data placement, retains the 36 shared engines, and adds no weights.
"""
from collections import Counter
from copy import deepcopy
from dataclasses import asdict,replace
from hashlib import sha256
import json
from math import ceil

from w2w.domain.execution import ComputeTask,DataEdge,ExecutionGraph,ReadAccess
from w2w.workloads.moe_task_graph import compile_routed_layer,residency_shards
from w2w.workloads.routing_input import INPUTS,load_layer_routing


def semantic_work(metadata):
    return {k:metadata[k] for k in ('model','shape','precision','tokens','owners','weight_read_bytes')}


def compile_partitioned_layer(inputs=INPUTS,*,cohort='c2_b4',routing=None):
    if routing is None:routing=load_layer_routing(inputs,cohort=cohort)
    base,original=compile_routed_layer(routing,residency='four_way')
    h=original['shape']['hidden'];width=original['shape']['intermediate_tile']
    tile_weight=3*h*width+3*(h//128)*4
    layout=[]
    for expert,owner in enumerate(original['owners']):
        for part,(role,memory) in enumerate(residency_shards(owner,'four_way')):
            layout.append(dict(expert=expert,role=role,memory=f'm{memory}',compute=f'c{memory}',
                intermediate_blocks=list(range(3*part,3*part+3)),object=f'expert{expert}/{role}'))
    placements={(r['expert'],b):r for r in layout for b in r['intermediate_blocks']}
    tasks=[t for t in base.tasks if t.id.startswith('token')]
    descriptions={k:v for k,v in original['task_semantics'].items() if k.startswith('token')}
    members={}
    edges=[]
    for task in base.tasks:
        if not task.id.startswith('expert'):continue
        info=original['task_semantics'][task.id]
        expert,block=info['expert'],info['intermediate_tile']
        members[expert]=info['tokens']
        place=placements[expert,block]
        local_block=block%3
        reads=tuple(ReadAccess(place['object'],local_block*tile_weight+start,min(65536,tile_weight-start))
                    for start in range(0,tile_weight,65536))
        tasks.append(replace(task,tile=place['compute'],reads=reads))
        descriptions[task.id]=dict(info,partition=block//3,compute=place['compute'])
        if local_block:
            edges.append(DataEdge(task.id+'/state',f'expert{expert}/tile{block-1:02}',task.id,len(info['tokens'])*h*6))
    for expert,tokens in members.items():
        owner=f'c{original["owners"][expert]}'
        reduce=f'expert{expert}/reduce'
        ops=3*len(tokens)*h
        tasks.append(ComputeTask(reduce,owner,ceil(ops/256),scratch_bytes=4*len(tokens)*h))
        descriptions[reduce]=dict(stage='four_partial_sum_reduce',expert=expert,tokens=tokens,vector_ops=ops)
        for part in range(4):
            for token in tokens:
                edges.append(DataEdge(f'dispatch/token{token}/expert{expert}/part{part}',
                    f'token{token}/input',f'expert{expert}/tile{part*3:02}',h*2))
            edges.append(DataEdge(f'partial/expert{expert}/part{part}',
                f'expert{expert}/tile{part*3+2:02}',reduce,len(tokens)*h*4))
        for token in tokens:
            edges.append(DataEdge(f'combine/expert{expert}/token{token}',reduce,f'token{token}/combine',h*2))
    graph=ExecutionGraph(tuple(tasks),base.objects,tuple(edges))
    metadata=deepcopy(original)
    metadata.update(architecture='compute_near_shard',residency='three whole intermediate blocks per quarter',
        task_semantics=descriptions,all_expert_partition_layout=layout,
        logical_weight_content_layout_sha256=sha256(json.dumps(layout,sort_keys=True).encode()).hexdigest(),
        weight_read_bytes=sum(r.size_bytes for t in graph.tasks for r in t.reads),
        dispatch_bytes=sum(e.size_bytes for e in edges if e.id.startswith('dispatch/')),
        partial_sum_bytes=sum(e.size_bytes for e in edges if e.id.startswith('partial/')),
        additional_reduction_vector_ops=sum(v['vector_ops'] for v in descriptions.values()
                                             if v['stage']=='four_partial_sum_reduce'),
        remote_weight_bytes=0,arithmetic='gated FFN split along intermediate dimension; FP32 reduce; timing only, not bit-exact inference')
    metadata['compute_model']['policy']='blocking 128-wide tile; four parallel three-block chains; owner partial-sum reduce'
    if semantic_work(metadata)!=semantic_work(original):raise ValueError('Partition changed semantic application work')
    return graph,metadata


def clockwise_compute(tile):
    """Fixed one-hop clockwise permutation in each aligned 2x2 group."""
    n=int(tile[1:]);x,y=n%6,n//6
    if tile!=f'c{n}' or not 0<=n<36:raise ValueError('Expected a 6x6 compute tile')
    target=n+1 if x%2==0 and y%2==0 else n+6 if y%2==0 else n-1 if x%2 else n-6
    return f'c{target}'


def compile_rotated_partition_layer(inputs=INPUTS,*,cohort='c2_b4',routing=None):
    """Same content, addresses and four chains; move each chain one hop clockwise."""
    base,original=compile_partitioned_layer(inputs,cohort=cohort,routing=routing)
    graph=replace(base,tasks=tuple(replace(t,tile=clockwise_compute(t.tile)) if t.reads else t
                                   for t in base.tasks))
    metadata=deepcopy(original)
    metadata['architecture']='compute_rotated_shard'
    metadata['compute_placement']='clockwise one-hop derangement within each fixed aligned 2x2 group'
    for task in graph.tasks:
        if task.reads:metadata['task_semantics'][task.id]['compute']=task.tile
    for row in metadata['all_expert_partition_layout']:row['compute']=clockwise_compute(row['compute'])
    # The historical field hashes a joint content/compute record. Preserve that
    # encoding; the matched-control proof separately hashes content and addresses.
    metadata['logical_weight_content_layout_sha256']=sha256(json.dumps(
        metadata['all_expert_partition_layout'],sort_keys=True).encode()).hexdigest()
    metadata['remote_weight_bytes']=metadata['weight_read_bytes']
    return graph,metadata
