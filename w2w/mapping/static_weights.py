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


def static_weights(logical,stack,policy):
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
