"""Deterministic real-request cohorts; no average expert load or future oracle."""
from dataclasses import dataclass
from collections import defaultdict
from w2w.workloads.patterns_adapter import observations


@dataclass(frozen=True)
class MoEBatch:
    id: str
    layer_id: str
    observations: tuple
    expert_to_tokens: tuple
    token_to_experts: tuple
    router_dependency: str

    @property
    def token_count(self):return len(self.observations)


def group(batch_id,rows):
    rows=tuple(rows)
    if not rows or len({r.layer_id for r in rows})!=1 or len({r.token_id for r in rows})!=len(rows):
        raise ValueError('One real layer and unique token identities required')
    members=defaultdict(list)
    topk=len(rows[0].expert_ids)
    for r in rows:
        if len(r.expert_ids)!=topk or len(set(r.expert_ids))!=topk:
            raise ValueError('Original unique ranked top-k required')
        for expert in r.expert_ids:members[expert].append(r.token_id)
    if sum(map(len,members.values()))!=len(rows)*topk:raise ValueError('Token/expert conservation failed')
    return MoEBatch(batch_id,rows[0].layer_id,rows,tuple((e,tuple(ts)) for e,ts in sorted(members.items())),
        tuple((r.token_id,r.expert_ids) for r in rows),batch_id+'/router_done')


def fixed_cohorts(captures,batch_size):
    captures=tuple(captures)
    if type(batch_size) is not int or batch_size<1 or len(captures)%batch_size:
        raise ValueError('Complete fixed cohorts required; never drop a remainder')
    if len({c['request_id'] for c in captures})!=len(captures):raise ValueError('Request repeated as independent evidence')
    for i in range(0,len(captures),batch_size):yield captures[i:i+batch_size]


def request_windows(cohort,layers,*,prefill_microbatch=32):
    """All original prefill tokens and decode steps, bounded by one layer/batch.

    Prefill chunking is explicit modeled batching, not source arrival timing.
    The caller releases a window only after the preceding window completes.
    """
    cohort=tuple(cohort);layers=tuple(layers)
    if not cohort or prefill_microbatch<1 or len(set(layers))!=len(layers):raise ValueError('Explicit cohort/layers required')
    n={c['coverage']['decode_tokens'] for c in cohort}
    if len(n)!=1:raise ValueError('Use a lifecycle-aware batcher for unequal decode lengths')
    for layer in layers:
        rows=tuple(r for c in cohort for r in observations(c,'prefill',layer))
        for i in range(0,len(rows),prefill_microbatch):
            yield group(f'prefill/L{layer}/chunk{i//prefill_microbatch}',rows[i:i+prefill_microbatch])
    for step in range(next(iter(n))):
        for layer in layers:
            yield group(f'decode/S{step}/L{layer}',tuple(observations(c,'decode',layer,step)[0] for c in cohort))
