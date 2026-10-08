"""Static expert ownership scored against a frozen fabric's shared resources.

Continuous full-object service scores, not finite-DAG latency predictions.
Only swaps are searched: each compute's resident expert count stays fixed.
"""
from fractions import Fraction
import numpy as np

from w2w.theory.return_path import return_path_period
from w2w.theory.cohort_service import pair_score, independent_object_floor_possible


def resource_matrix(design, window=192, rx_depth=3):
    """Columns encode normalized native-bank, output and request capacities.

An object of d words has ideal duration (d / banks) times the score.
Native arrivals are one word/bank/slot; paths use the exact isolated period.
"""
    banks = len(design.exposure.mask)
    shares = np.asarray(design.layout.shares)
    nc = len(shares)
    from w2w.service.evaluator import CandidateEvaluator
    evaluator = CandidateEvaluator(design)
    path, life = np.zeros(nc), np.zeros(nc)
    rates = {}
    for (c, bank), port in evaluator.ports.items():
        width = design.endpoint.widths[port]
        key = width, max(1, design.endpoint.depths[port])
        if key not in rates:
            rates[key] = float(Fraction(return_path_period(*key, rx_depth)['words_per_slot']))
        path[c] = max(path[c], banks * shares[c, bank] / rates[key])
        life[c] += shares[c, bank] * (2 + (255 + width) // width)
    coefficients = np.column_stack((banks * shares, np.diag(np.maximum(path, banks * life / window))))
    # Identical uniformly striped banks impose the same continuous constraint.
    return np.unique(coefficients, axis=1)


def cohort_matrix(requests, layer_index, expert_count, batches=(1, 4, 16)):
    """Training-only full-step cold unions; each batch size gets equal weight."""
    rows, weights = [], []
    steps = {len(r['decode']) for r in requests}
    if not requests or len(steps) != 1 or 0 in steps:
        raise ValueError('Equal nonempty decode sequences required')
    for batch in batches:
        if batch < 1 or len(requests) % batch:
            raise ValueError('Batch must divide training request count')
        for first in range(0, len(requests), batch):
            for step in range(next(iter(steps))):
                row = np.zeros(expert_count, dtype=np.int16)
                selected = {e for r in requests[first:first+batch] for e in r['decode'][step][layer_index]}
                row[list(selected)] = 1
                rows.append(row)
                weights.append(batch)
    return np.asarray(rows), np.asarray(weights)


def assignment_loads(activation, owners, compute_count):
    one_hot = np.zeros((len(owners), compute_count), dtype=np.int16)
    one_hot[np.arange(len(owners)), owners] = 1
    return activation @ one_hot


def score(activation, weights, owners, coefficients):
    costs = assignment_loads(activation, owners, len(coefficients)) @ coefficients
    peaks = costs.max(axis=1)
    return float(peaks @ weights / weights.sum())


def swap_search(activation, weights, owners, coefficients, rounds=8, candidates=256, seed=8109):
    """Bounded greedy swaps, chosen by cohort completion score alone.

Each round samples candidate expert pairs without replacement using a fixed
seed and accepts its best strictly improving swap. This is not global search.
"""
    owners = np.asarray(owners, dtype=int).copy()
    before_counts = np.bincount(owners, minlength=len(coefficients))
    pairs = np.array([(a, b) for a in range(len(owners)) for b in range(a+1, len(owners))])
    rng = np.random.default_rng(seed)
    history = []
    trials = 0
    for step in range(rounds):
        loads = assignment_loads(activation, owners, len(coefficients))
        costs = loads @ coefficients
        original = best = float(costs.max(axis=1) @ weights)
        selected = None
        cache = {}
        for a, b in pairs[rng.choice(len(pairs), min(candidates, len(pairs)), replace=False)]:
            c, d = owners[a], owners[b]
            if c == d:
                continue
            trials += 1
            key = int(c), int(d)
            if key not in cache:
                delta = coefficients[d] - coefficients[c]
                affected = np.flatnonzero(delta)
                unaffected = np.flatnonzero(delta == 0)
                fixed = costs[:, unaffected].max(axis=1) if len(unaffected) else np.zeros(len(costs))
                cache[key] = affected, delta[affected], fixed
            affected, delta, fixed = cache[key]
            difference = activation[:, a] - activation[:, b]
            changed = costs[:, affected] + difference[:, None] * delta
            peak = np.maximum(fixed, changed.max(axis=1))
            value = float(peak @ weights)
            if value < best - 1e-8:
                best, selected = value, (int(a), int(b))
        if selected is not None:
            a, b = selected
            owners[a], owners[b] = owners[b], owners[a]
            actual = score(activation, weights, owners, coefficients) * weights.sum()
            if not np.isclose(actual, best, rtol=0, atol=1e-7):
                raise ValueError('Incremental objective disagrees with independent full score')
        history.append(dict(round=step, before=original/weights.sum(), after=best/weights.sum(), swap=selected))
        # Fixed rounds allow a later sample to find an improvement after a miss.
    if not np.array_equal(np.bincount(owners, minlength=len(coefficients)), before_counts):
        raise ValueError('Swap changed resident capacity')
    return dict(owners=owners.tolist(), history=history, candidate_evaluations=trials,
                score=score(activation, weights, owners, coefficients))
