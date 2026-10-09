"""Freeze all expert content before observing the active expert set."""
from collections import Counter
from dataclasses import dataclass
from .partitioning import intermediate_partition


@dataclass(frozen=True)
class WeightLocation:
    tensor: str
    memory: str
    offset_bytes: int
    size_bytes: int


def place_weights(logical, stack):
    domains={d.id:d for d in stack.dram_domains}
    groups={r.id:[g for g in stack.bank_groups if domains[g.domain_ids[0]].region_id==r.id]
            for r in stack.memory_regions}
    regions=sorted(groups); offsets=Counter(); result=[]
    blocks=logical.shape[1]//logical.shape[2]
    for name,size in logical.weight_sizes:
        _,e,b,_=name.split('/'); expert,block=int(e[1:]),int(b[1:])
        part=intermediate_partition(block,blocks,logical.partitions)
        region=regions[(expert+part)%len(regions)]
        candidates=sorted(groups[region],key=lambda g:g.id)
        group=candidates[(expert//len(regions))%len(candidates)]
        result.append(WeightLocation(name,group.id,offsets[group.id],size))
        offsets[group.id]+=size
    for memory,stop in offsets.items():
        group=next(g for g in stack.bank_groups if g.id==memory)
        if stop>sum(domains[d].capacity_bytes for d in group.domain_ids):
            raise ValueError('Frozen all-expert weight layout exceeds DRAM capacity')
    return tuple(result)
