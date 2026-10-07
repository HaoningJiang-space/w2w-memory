"""Periodic complete-word witnesses for immutable, role-dependent endpoints.

One native admission opportunity per slot, before independent output drain.
Ready bits are admission opportunities, not buffered unsolicited DRAM arrivals.
Inactive sources are removed before execution; active words cannot bypass HOL.
"""
from collections import deque
from dataclasses import asdict
from math import gcd
from w2w.domain.endpoint import EndpointSpec, NativeProfile


def balanced_sequence(home, peer, home_words, peer_words):
    """Compile integer residence weights to a fixed, evenly spaced word order."""
    if min(home_words, peer_words) < 0 or home_words + peer_words <= 0:
        raise ValueError('Nonnegative, nonempty word counts required')
    if any(not isinstance(v, int) for v in (home_words, peer_words)):
        raise ValueError('Word counts must be integers')
    total = home_words + peer_words
    return tuple(home if ((i + 1) * home_words // total > i * home_words // total)
                 else peer for i in range(total))


def execute_periodic(spec: EndpointSpec, sequence, profile: NativeProfile | None = None, credits=None,
                     max_slots=100000):
    """Find a repeated pre-issue state; count EXACTLY one recurrent period.

    Credit rows specify per-slot bit budgets. This witness is for this sequence,
    source and credits only. Queue state contains remaining bits; absolute tags
    are translation invariant and do not influence any transition.
    """
    profile = profile or spec.native
    sequence = tuple(sequence)
    if (not sequence or any(not isinstance(p, int) or not 0 <= p < len(spec.widths)
                            or spec.widths[p] == 0 for p in sequence)):
        raise ValueError('Sequence uses an unconfigured output')
    if not isinstance(max_slots, int) or max_slots <= 0:
        raise ValueError('Positive integer execution limit required')
    credits = tuple(tuple(row) for row in credits) if credits is not None else (spec.widths,)
    if (not credits or any(len(row) != len(spec.widths) for row in credits)
            or any(not isinstance(v, int) or not 0 <= v <= spec.widths[p]
                   for row in credits for p, v in enumerate(row))):
        raise ValueError('Invalid downstream credits')
    queues = [deque() for _ in spec.widths]
    counts = [0] * len(queues)
    sent = [0] * len(queues)
    peaks = [0] * len(queues)
    seen = {}
    cursor = issued = completed = blocked = ready_slots = 0
    for tick in range(max_slots + 1):
        state = (cursor, tick % len(profile.ready), tick % len(credits),
                 tuple(tuple(q) for q in queues))
        if state in seen:
            start, old_counts, old_sent, old_issued, old_blocked, old_ready = seen[state]
            period = tick - start
            delivered = [a - b for a, b in zip(counts, old_counts)]
            emitted = [a - b for a, b in zip(sent, old_sent)]
            assert all(bits == words * spec.word_bits for bits, words in zip(emitted, delivered))
            assert sum(delivered) == issued - old_issued
            return dict(spec=spec.record(), native_profile=asdict(profile),
                        sequence=list(sequence), credits=[list(row) for row in credits],
                        transient_slots=start, period_slots=period,
                        delivered_words=delivered, sent_bits=emitted,
                        rate_per_native=[v / period for v in delivered],
                        total_per_native=sum(delivered) / period,
                        peak_words=peaks, backpressure_slots=blocked - old_blocked,
                        ready_opportunities=ready_slots - old_ready,
                        boundary_state=state, state_repeated=True,
                        conservation_checked_every_slot=True)
        seen[state] = (tick, counts.copy(), sent.copy(), issued, blocked, ready_slots)
        if tick == max_slots:
            break
        p = sequence[cursor]
        if profile.ready[tick % len(profile.ready)]:
            ready_slots += 1
            room = (not any(queues) if spec.mode == 'direct'
                    else len(queues[p]) < spec.depths[p])
            if room:
                queues[p].append(spec.word_bits)
                issued += 1
                cursor = (cursor + 1) % len(sequence)
            else:
                blocked += 1
        for p, q in enumerate(queues):
            peaks[p] = max(peaks[p], len(q))
            budget = credits[tick % len(credits)][p]
            while budget and q:
                amount = min(budget, q[0])
                q[0] -= amount
                budget -= amount
                sent[p] += amount
                if q[0] == 0:
                    q.popleft()
                    completed += 1
                    counts[p] += 1
        assert issued <= ready_slots <= tick + 1
        assert issued == completed + sum(map(len, queues))
        assert issued * spec.word_bits == sum(sent) + sum(sum(q) for q in queues)
        if spec.mode == 'direct':
            assert sum(map(len, queues)) <= 1
        else:
            assert all(len(q) <= d for q, d in zip(queues, spec.depths))
    raise RuntimeError('No repeated state within registered execution limit')


def ratio_sequence(home, peer, numerator, denominator):
    if not 0 <= numerator <= denominator or denominator <= 0:
        raise ValueError('Invalid home fraction')
    scale = gcd(numerator, denominator)
    return balanced_sequence(home, peer, numerator // scale, (denominator - numerator) // scale)
