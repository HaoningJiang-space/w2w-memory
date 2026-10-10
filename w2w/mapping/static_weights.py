"""Catalog-only memory placement: never reads token routing or changes compute.

Reference is the existing grouped modulo layout. Balanced stripes the nine
matrices of a three-block partition across its region's groups; hybrid stripes
only down-projection blocks. Locality maps to the nearest frozen consumer and
may be identical to reference. All experts, including inactive ones, are placed.
"""
from collections import Counter
from .data_placement import WeightLocation,place_weights
from .compute_placement import weight_compute_clusters

POLICIES=('reference','locality','balanced','hybrid')
ABLATIONS=('hybrid-gate-up-striped',)


def static_weights(logical,stack,policy):
    if policy in ABLATIONS:return gate_up_ablation(logical,stack)
    if policy not in POLICIES:raise ValueError('Unknown static memory policy')
    reference=place_weights(logical,stack)
    if policy=='reference':return reference
    domains={d.id:d for d in stack.dram_domains};groups={g.id:g for g in stack.bank_groups}
    regional={r.id:sorted((g for g in stack.bank_groups if domains[g.domain_ids[0]].region_id==r.id),key=lambda g:g.id)
              for r in stack.memory_regions}
    clusters={c.id:c for c in stack.compute_clusters};anchors=weight_compute_clusters(stack,reference)
    offsets=Counter();result=[];per_part=logical.shape[1]//logical.shape[2]//logical.partitions
    for w in reference:
        candidates=regional[domains[groups[w.memory].domain_ids[0]].region_id]
        base=next(i for i,g in enumerate(candidates) if g.id==w.memory)
        _,_,block,phase=w.tensor.split('/');local_block=int(block[1:])%per_part
        if policy=='locality':
            pos=clusters[anchors[w.tensor]].position_um
            def distance(g):
                center=tuple(sum(domains[d].position_um[k] for d in g.domain_ids)//len(g.domain_ids) for k in (0,1))
                return sum(abs(a-b) for a,b in zip(pos,center)),g.id
            group=min(candidates,key=distance)
        else:
            shift=(3*local_block+('gate','up','down').index(phase)) if policy=='balanced' else (local_block if phase=='down' else 0)
            group=candidates[(base+shift)%len(candidates)]
        result.append(WeightLocation(w.tensor,group.id,offsets[group.id],w.size_bytes));offsets[group.id]+=w.size_bytes
    if [(w.tensor,w.size_bytes) for w in result]!=list(logical.weight_sizes):raise ValueError('Placement changed the full weight catalog')
    for key,stop in offsets.items():
        if stop>sum(domains[d].capacity_bytes for d in groups[key].domain_ids):raise ValueError('Static placement exceeds physical DRAM')
    return tuple(result)


def gate_up_ablation(logical,stack):
    """Keep Hybrid down addresses and unmoved objects; change only gate/up placement.

    Gate/up gateway choices follow Balanced. First-fit fills free native-word
    aligned intervals around the locked Hybrid objects, without relocating down.
    This is an intervention, not another optimized placement policy.
    """
    from dataclasses import replace
    hybrid=static_weights(logical,stack,'hybrid');balanced={w.tensor:w for w in static_weights(logical,stack,'balanced')}
    domains={d.id:d for d in stack.dram_domains};groups={g.id:g for g in stack.bank_groups}
    occupied={g:[] for g in groups};moves=set()
    for w in hybrid:
        if not w.tensor.endswith('/down') and balanced[w.tensor].memory!=w.memory:moves.add(w.tensor)
        else:occupied[w.memory].append((w.offset_bytes,w.offset_bytes+w.size_bytes))
    result=[]
    for w in hybrid:
        if w.tensor not in moves:result.append(w);continue
        memory=balanced[w.tensor].memory;offset=0
        for begin,end in sorted(occupied[memory]):
            if offset+w.size_bytes<=begin:break
            offset=max(offset,end)
        if offset+w.size_bytes>sum(domains[d].capacity_bytes for d in groups[memory].domain_ids):
            raise ValueError('Controlled gate/up movement exceeds physical capacity')
        occupied[memory].append((offset,offset+w.size_bytes))
        result.append(replace(w,memory=memory,offset_bytes=offset))
    for intervals in occupied.values():
        ordered=sorted(intervals)
        if any(a[1]>b[0] for a,b in zip(ordered,ordered[1:])):raise ValueError('Controlled placement overlaps locked objects')
    if [w for w in hybrid if w.tensor.endswith('/down')]!=[w for w in result if w.tensor.endswith('/down')]:
        raise ValueError('Controlled intervention changed Hybrid down addresses')
    return tuple(result)
