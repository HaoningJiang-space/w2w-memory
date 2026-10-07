"""Disjoint request selection and training-only, capacity-bounded expert ownership."""
from collections import Counter
from hashlib import sha256


def split_requests(manifest, previous, seed=8108, train_per_subject=8, groups=3):
    """Use identifiers alone; no expert selections or measured completion times."""
    excluded = {r for g in previous['groups'] for r in g['requests']}
    entries = manifest['requests']
    if len({r['id'] for r in entries}) != len(entries):
        raise ValueError('Duplicate corpus request')
    subjects = sorted({r['id'].split('/')[-2] for r in entries})
    train, test = [], [[] for _ in range(groups)]
    for subject in subjects:
        candidates = [r['id'] for r in entries if r['id'].split('/')[-2] == subject and r['id'] not in excluded]
        candidates.sort(key=lambda key: sha256(f'{seed}:{key}'.encode()).hexdigest())
        if len(candidates) < train_per_subject + 2 * groups:
            raise ValueError('Insufficient disjoint requests in subject')
        train.extend(candidates[:train_per_subject])
        for g in range(groups):
            start = train_per_subject + 2 * g
            test[g].extend(candidates[start:start + 2])
    order = lambda key: sha256(f'{seed}:cohort:{key}'.encode()).hexdigest()
    train.sort(key=order)
    for group in test:
        group.sort(key=order)
    chosen = train + [r for group in test for r in group]
    if len(set(chosen)) != len(chosen) or set(chosen) & excluded:
        raise ValueError('Training/test/previous timing requests overlap')
    return dict(seed=seed, training=train, tests=test, excluded_previous=sorted(excluded),
                policy='ID hash within subject, training prefix and disjoint test pairs; cohort hash order')


def assign_owners(scores, compute_count, max_experts):
    """LPT on training cold-union demand with an explicit resident-object limit."""
    if compute_count < 1 or max_experts < 1 or len(scores) > compute_count * max_experts:
        raise ValueError('Insufficient owner capacity')
    if any(type(x) is not int or x < 0 for x in scores):
        raise ValueError('Expected nonnegative integer training scores')
    owners = [-1] * len(scores)
    loads, resident = [0] * compute_count, [0] * compute_count
    for expert in sorted(range(len(scores)), key=lambda e: (-scores[e], e)):
        legal = [c for c in range(compute_count) if resident[c] < max_experts]
        owner = min(legal, key=lambda c: (loads[c], resident[c], c))
        owners[expert] = owner
        loads[owner] += scores[expert]
        resident[owner] += 1
    return owners


def owner_loads(scores, owners, compute_count):
    loads = [0] * compute_count
    for score, owner in zip(scores, owners, strict=True):
        loads[owner] += score
    return loads


def fit_owners(requests, spec, batch_sizes=(1, 4, 16)):
    """Each batch size has equal weight in mean cold-read demand.

    With R requests and S equal-length decode streams, batch-b has RS/b
    windows. Multiplication by b puts their union counts on the common RS
    denominator. Equal object sizes cancel when ranking load.
    """
    lengths = {len(r.decode) for r in requests}
    if not requests or len(lengths) != 1 or not next(iter(lengths)):
        raise ValueError('Training requires equal, nonempty complete decode streams')
    if any(b < 1 or len(requests) % b for b in batch_sizes):
        raise ValueError('Training cohorts must divide the request count')
    if len({r.id for r in requests}) != len(requests):
        raise ValueError('Duplicate training request')
    steps = next(iter(lengths))
    result = {}
    for li, layer in enumerate(spec['layers']):
        scores = [0] * layer['expert_count']
        counts = {}
        for batch in batch_sizes:
            count = Counter()
            for start in range(0, len(requests), batch):
                for step in range(steps):
                    count.update({e for r in requests[start:start + batch] for e in r.decode[step][li]})
            counts[str(batch)] = [count[e] for e in range(layer['expert_count'])]
            scores = [score + batch * count[e] for e, score in enumerate(scores)]
        nc = spec['compute_count']
        cap = (len(scores) + nc - 1) // nc
        lpt = assign_owners(scores, nc, cap)
        modulo = [e % nc for e in range(len(scores))]
        key = lambda owners: (max(owner_loads(scores, owners, nc)),
                              sum(x*x for x in owner_loads(scores, owners, nc)))
        # Keep the stronger ordinary baseline on training data alone.
        chosen = lpt if key(lpt) <= key(modulo) else modulo
        result[layer['key']] = dict(compute_by_expert=chosen, selected='lpt' if chosen == lpt else 'modulo',
            training_scores=scores, union_counts=counts, score_denominator=len(requests)*steps*len(batch_sizes),
            request_count=len(requests), decode_steps=steps, max_experts_per_compute=cap,
            selected_loads=owner_loads(scores, chosen, nc), modulo_loads=owner_loads(scores, modulo, nc),
            lpt_loads=owner_loads(scores, lpt, nc), resident_experts=[chosen.count(c) for c in range(nc)],
            policy='Minimum training max load then squared load, between capacity-bounded LPT and modulo')
    return result
