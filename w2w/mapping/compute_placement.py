"""Placement selects resources; it never changes logical operation work."""
from dataclasses import dataclass


@dataclass(frozen=True)
class OperationLocation:
    operation: str
    cluster: str


def weight_compute_clusters(stack,weights):
    domains={d.id:d for d in stack.dram_domains}
    groups={g.id:g for g in stack.bank_groups}
    clusters=sorted(stack.compute_clusters,key=lambda c:c.id)
    weight_clusters={}
    for w in weights:
        ds=[domains[d] for d in groups[w.memory].domain_ids]
        center=tuple(sum(d.position_um[k] for d in ds)//len(ds) for k in (0,1))
        weight_clusters[w.tensor]=min(clusters,key=lambda c:(sum(abs(a-b) for a,b in zip(c.position_um,center)),c.id)).id
    return weight_clusters


def place_compute(logical, stack, weights):
    weight_clusters=weight_compute_clusters(stack,weights)
    clusters=sorted(stack.compute_clusters,key=lambda c:c.id)
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


PROJECTION_POLICIES=('reference_compute','up_local_compute','up_matched_nonlocal')


def gateway_compute_clusters(stack,weights):
    """Exact existing Gateway/cluster co-location; no nearest-node shortcut."""
    groups={g.id:g for g in stack.bank_groups};gateways={g.id:g for g in stack.gateways}
    result={}
    for w in weights:
        gateway=gateways[groups[w.memory].gateway_id]
        candidates=[c for c in stack.compute_clusters if c.router_id==gateway.router_id
                    and c.position_um==gateway.position_um]
        if len(candidates)!=1:raise ValueError('Projection co-placement requires one existing co-located cluster per Gateway')
        result[w.tensor]=candidates[0].id
    return result


def projection_weight_clusters(stack,reference_weights,candidate_weights,policy):
    """Full-catalog cache destinations; no active-expert or future-cache input."""
    if policy not in ('reference_compute','up_local_compute'):
        raise ValueError('Matched nonlocal is a cold diagnostic, not a catalog cache policy')
    result=weight_compute_clusters(stack,reference_weights)
    if policy=='up_local_compute':
        local=gateway_compute_clusters(stack,candidate_weights)
        result.update((name,tile) for name,tile in local.items() if name.endswith('/up'))
    return result


def place_projection_compute(logical,stack,reference_weights,candidate_weights,policy='reference_compute'):
    """Move only Up arithmetic; weights, mathematical graph and non-Up stay fixed.

    Matched nonlocal is a registered cold mechanism control. A deterministic
    matching preserves Up work/count per cluster while excluding both its
    weight-local and reference cluster. It uses this call's known logical work,
    not performance, future routing, cache state or a searched objective.
    """
    if policy not in PROJECTION_POLICIES:raise ValueError('Unknown projection compute policy')
    base=place_compute(logical,stack,reference_weights)
    if policy=='reference_compute':return base
    clusters={c.id:c for c in stack.compute_clusters};anchors={p.operation:p.cluster for p in base}
    local=gateway_compute_clusters(stack,candidate_weights);weights={w.tensor:w for w in candidate_weights}
    operations={op.id:op for op in logical.operations};chosen={}
    ups=[op for op in logical.operations if op.kind=='gemm' and op.id.endswith('/up')]
    for op in ups:
        if len(op.weight_tensors)!=1:raise ValueError('One explicit Up weight required')
        chosen[op.id]=local[op.weight_tensors[0]]
        if clusters[chosen[op.id]].profile!=clusters[anchors[op.id]].profile:
            raise ValueError('Co-placement cannot change compute service profile')
    if policy=='up_matched_nonlocal':
        from collections import defaultdict,Counter
        batches=defaultdict(list)
        for op in ups:
            c=clusters[chosen[op.id]]
            batches[(c.reticle_id,c.profile,op.macs,op.vector_ops,op.scratch_bytes,
                     len(op.token_ids),weights[op.weight_tensors[0]].size_bytes)].append(op.id)
        for keys in batches.values():
            counts=Counter(chosen[k] for k in keys)
            slots=[tile for tile,count in sorted(counts.items()) for _ in range(count)]
            owner={}
            def match(key,seen):
                for slot,tile in enumerate(slots):
                    if slot in seen or tile in (chosen[key],anchors[key]):continue
                    seen.add(slot)
                    if slot not in owner or match(owner[slot],seen):owner[slot]=key;return True
                return False
            for key in sorted(keys):
                if not match(key,set()):
                    raise ValueError('Frozen call has no same-reticle, moved nonlocal control with matched per-cluster Up work')
            assigned={key:slots[slot] for slot,key in owner.items()}
            if Counter(assigned.values())!=counts:raise ValueError('Nonlocal control did not preserve Up work')
            chosen.update(assigned)
    return tuple(OperationLocation(p.operation,chosen.get(p.operation,p.cluster)) for p in base)
