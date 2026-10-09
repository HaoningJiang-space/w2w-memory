"""Placement selects resources; it never changes logical operation work."""
from dataclasses import dataclass


@dataclass(frozen=True)
class OperationLocation:
    operation: str
    cluster: str


def place_compute(logical, stack, weights):
    domains={d.id:d for d in stack.dram_domains}
    groups={g.id:g for g in stack.bank_groups}
    locations={w.tensor:w for w in weights}
    clusters=sorted(stack.compute_clusters,key=lambda c:c.id)
    weight_clusters={}
    for w in weights:
        ds=[domains[d] for d in groups[w.memory].domain_ids]
        center=tuple(sum(d.position_um[k] for d in ds)//len(ds) for k in (0,1))
        weight_clusters[w.tensor]=min(clusters,key=lambda c:(sum(abs(a-b) for a,b in zip(c.position_um,center)),c.id)).id
    result=[]
    for op in logical.operations:
        if op.expert is not None and op.block is not None:
            cluster=weight_clusters[f'weight/e{op.expert}/b{op.block}/gate']
        elif op.expert is not None:
            cluster=clusters[op.expert%len(clusters)].id
        else:
            cluster=clusters[op.token_ids[0]%len(clusters)].id
        result.append(OperationLocation(op.id,cluster))
    return tuple(result)
