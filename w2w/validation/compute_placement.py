"""Strict matched-parallelism control; this does not execute or tune placement."""
from collections import Counter
from dataclasses import asdict
from w2w.common.fingerprints import digest_system_v2 as digest
from w2w.system.builder import SystemBuilder
from w2w.workloads.moe_partition import semantic_work


def matched_partition_contract(near, near_metadata, rotated, rotated_metadata, spec):
    builder=SystemBuilder(spec)
    builder.validate_graph(near);builder.validate_graph(rotated)
    def structural(graph):
        value=asdict(graph)
        for task in value['tasks']:del task['tile']
        return value
    def content(graph,metadata):
        return dict(objects=[asdict(o) for o in graph.objects],
            partition_content=[{k:v for k,v in row.items() if k!='compute'}
                               for row in metadata['all_expert_partition_layout']],
            reads={t.id:[asdict(r) for r in t.reads] for t in graph.tasks})
    def engine_work(graph):
        values={}
        for t in graph.tasks:
            row=values.setdefault(t.tile,dict(tasks=0,cycles=0,weight_bytes=0))
            row['tasks']+=1;row['cycles']+=t.compute_cycles
            row['weight_bytes']+=sum(r.size_bytes for r in t.reads)
        return values
    def tensor_routes(graph):
        tasks={t.id:t for t in graph.tasks}
        return Counter((tasks[e.producer].tile,tasks[e.consumer].tile,e.size_bytes) for e in graph.data)
    if (structural(near)!=structural(rotated) or content(near,near_metadata)!=content(rotated,rotated_metadata)
            or semantic_work(near_metadata)!=semantic_work(rotated_metadata)
            or engine_work(near)!=engine_work(rotated) or tensor_routes(near)!=tensor_routes(rotated)):
        raise ValueError('Rotation changed content, addresses, dependency graph or per-engine/tensor work')
    paths=Counter();remote_bytes=0
    objects={o.id:o for o in near.objects}
    for a,b in zip(near.tasks,rotated.tasks):
        if not a.reads:
            if a.tile!=b.tile:raise ValueError('Token or reduction owner moved')
            continue
        for r in a.reads:
            home=builder.memories[objects[r.object_id].memory].home_tile
            route=builder.route(home,b.tile)
            h,n=int(home[1:]),int(b.tile[1:])
            same_group=(h%6//2,h//6//2)==(n%6//2,n//6//2)
            if a.tile!=home or not same_group or len(route)!=1 or any(builder.links[k].kind=='HB' for k in route):
                raise ValueError('Expected local versus exactly one C-C hop within the existing group')
            paths[route[0]]+=r.size_bytes;remote_bytes+=r.size_bytes
    return dict(passed=True,dependency_and_read_graph_without_tiles_sha256=digest(structural(near)),
        content_and_addresses_sha256=digest(content(near,near_metadata)),
        per_engine_work=engine_work(near),semantic_work_sha256=digest(semantic_work(near_metadata)),
        rotated_remote_weight_bytes=remote_bytes,rotated_weight_payload_by_link=dict(paths),
        tensor_route_payload_multiset_sha256=digest(sorted((list(k),v) for k,v in tensor_routes(near).items())),
        scope='fixed four chains, exact reads/content/addresses, fixed reduction and per-engine work; runtime order remains a consequence')
