"""Residency coverage and optimistic service/state provisioning bounds.

The bounds describe the existing bank-local replay contract. They neither
implement a pooled engine nor assert that an optimistic capacity is achievable.
"""
from collections import Counter, defaultdict
from fractions import Fraction

from w2w.analysis.request_window import (ceil_div, check_bound, completion_lower_bound,
                                        window_certificate)
from w2w.service.read_replay import design_record
from w2w.workloads.read_trace import digest, integer


def ceil_fraction(value):
    value = Fraction(value)
    return ceil_div(value.numerator, value.denominator)


def credit_matched_split(banks, shared_rate, window, home_lifetime=3, shared_lifetime=4):
    """Maximize a *necessary steady-rate upper bound* over the home fraction.

    Each bank exports at most one home word/slot and shared_rate shared words/
    slot. A compute may use its home and one peer memory; all bank streams have
    the same reciprocal split. The request window covers issue through delivery.
    Rates/lifetimes are explicit inputs, not inferred from nominal link widths.
    """
    for name, value in (('banks', banks), ('window', window), ('home lifetime', home_lifetime),
                        ('shared lifetime', shared_lifetime)):
        integer(value, name, 1)
    shared_rate = Fraction(shared_rate)
    if not 0 < shared_rate <= 1 or shared_lifetime < home_lifetime:
        raise ValueError('Require 0 < shared rate <= 1 and shared lifetime >= home lifetime')
    native_window = banks * home_lifetime
    capacity_fraction = 1 / (1 + shared_rate)
    if window < native_window:
        fraction = Fraction(1)
    else:
        credit_fraction = Fraction(banks * shared_lifetime,
                                   window + banks * (shared_lifetime - home_lifetime))
        fraction = max(capacity_fraction, credit_fraction)
    rate = steady_rate_bound(banks, shared_rate, fraction, window, home_lifetime, shared_lifetime)
    return dict(home_fraction=str(fraction), capacity_matched_home_fraction=str(capacity_fraction),
                normalized_rate_upper=str(rate), native_window_necessary=native_window,
                baseline_not_excluded=rate >= 1,
                scope='Optimum of the stated steady-rate relaxation, not finite replay or hardware optimum')


def steady_rate_bound(banks, shared_rate, home_fraction, window, home_lifetime=3, shared_lifetime=4):
    """Normalized capacity/lifetime bound; aggregate native capacity is two memories."""
    integer(banks, 'banks', 1)
    integer(window, 'window', 1)
    for value in (home_lifetime, shared_lifetime):
        integer(value, 'word lifetime', 1)
    fraction, shared_rate = Fraction(home_fraction), Fraction(shared_rate)
    if not 0 < fraction <= 1 or not 0 < shared_rate <= 1:
        raise ValueError('Invalid fraction or shared service')
    bounds = [Fraction(2), 1 / fraction,
              Fraction(window, banks) / (fraction * home_lifetime + (1 - fraction) * shared_lifetime)]
    if fraction != 1:
        bounds.append(shared_rate / (1 - fraction))
    return min(bounds)


def pool_capacity_bound(banks, engine_rate, home_fraction, engines, target_rate):
    """Necessary shared-engine count at fixed bank-equivalent capacity and split."""
    integer(banks, 'banks', 1)
    integer(engines, 'engines')
    q, fraction, target = Fraction(engine_rate), Fraction(home_fraction), Fraction(target_rate)
    if not 0 < q <= 1 or not 0 < fraction <= 1 or target <= 0:
        raise ValueError('Invalid pool capacity inputs')
    upper = min(Fraction(2 * banks), banks / fraction)
    if fraction != 1:
        upper = min(upper, engines * q / (1 - fraction))
    return dict(engines=engines, required_shared_words_per_slot=str(target * (1 - fraction)),
                minimum_engines_necessary=ceil_fraction(target * (1 - fraction) / q),
                rate_upper_words_per_slot=str(upper),
                reoptimized_split_normalized_upper=str(min(Fraction(2), 1 + engines * q / banks)),
                scope='Aggregate capacity only; cross-bank binding, input transport and arbitration omitted')


def layout_support_certificate(design):
    """Use every positive byte in the complete layout, never an activity mask.

    An engine is bound to one direction for the whole deployment. Counting the
    union over time is necessary even when directions never overlap in time.
    These are direction-context counts, not calibrated engine area or bit rate.
    """
    nb, nm = len(design.exposure.mask), len(design.geometry.memory_xy)
    routes = defaultdict(list)
    for route in design.geometry.routes:
        routes[route[0], route[1]].append(route)
    support = [set() for _ in range(nb * nm)]
    for compute, shares in enumerate(design.layout.shares):
        for bank, fraction in enumerate(shares):
            if fraction == 0:
                continue
            memory, local = divmod(bank, nb)
            legal = [r for r in routes[compute, memory] if r[3] in design.exposure.mask[local]]
            if len(legal) != 1:
                raise ValueError('Every resident byte requires one explicit legal physical route')
            support[bank].add(legal[0][3])
    instances, template = [], []
    for memory in range(nm):
        shared = sorted(set().union(*(support[memory * nb + b] - {0} for b in range(nb))))
        instances.append(dict(memory=memory, required_shared_directions=shared,
                              bank_required_directions=[sorted(support[memory * nb + b]) for b in range(nb)]))
        if design.endpoint.shared_fifo_ports and any(p != design.shared_directions[memory] for p in shared):
            raise ValueError('Complete residency violates the frozen shared binding')
    for bank, ports in enumerate(design.exposure.mask):
        required = [sorted(support[m * nb + bank] - {0}) for m in range(nm)]
        maximum = max(map(len, required))
        template.append(dict(bank=bank, potential_shared_directions=sorted(set(ports) - {0}),
                             minimum_fixed_direction_contexts=maximum,
                             witness_memory=next(m for m, ps in enumerate(required) if len(ps) == maximum)))
    return dict(schema='w2w.layout-service-support.v1', design_sha256=digest(design_record(design)),
                layout_sha256=design.layout.sha256, instances=instances, template=template,
                dedicated_shared_direction_contexts_per_memory=sum(len(r['potential_shared_directions']) for r in template),
                required_shared_direction_contexts_per_memory=sum(r['minimum_fixed_direction_contexts'] for r in template),
                memory_wide_single_direction_compatible=all(len(r['required_shared_directions']) <= 1 for r in instances),
                scope='Complete frozen layout; necessary static direction coverage; retains all bank parallelism; '
                      'not a sufficient binding network or a total engine/storage minimum')


def provisioning_certificate(design, trace, config):
    """Add aggregate resource cuts to the existing address-level word certificate."""
    base = window_certificate(design, trace, config)
    native, egress = Counter(), Counter()
    widths = {}
    for task in base['tasks']:
        for route in task['routes']:
            bank, port = route['bank'], route['port']
            native[bank] += route['words']
            egress[bank, port] += route['words'] * design.endpoint.word_bits
            widths[bank, port] = route['width_bits']
    cuts = [dict(kind='native_bank', resource=[b], work_words=n, lower_slots=n)
            for b, n in sorted(native.items())]
    cuts.extend(dict(kind='bank_egress', resource=list(key), work_bits=bits,
                     width_bits=widths[key], lower_slots=ceil_div(bits, widths[key]))
                for key, bits in sorted(egress.items()))
    return dict(schema='w2w.service-provisioning-certificate.v1', word_certificate=base,
                aggregate_cuts=cuts,
                scope='Necessary bounds for one active task per compute and bank-local outputs; '
                      'ignores shared HB limits, native gaps, arbitration phase and queue interference')


def provisioning_lower_bound(certificate, window):
    integer(window, 'window', 1)
    base = certificate['word_certificate']
    work, release = Counter(), {}
    for task in base['tasks']:
        if task['compute'] is None:
            continue
        c = task['compute']
        duration = max(task['independent_read_slots'],
                       ceil_div(task['required_credit_word_slots'], window)) + task['compute_slots']
        work[c] += duration
        release[c] = min(release.get(c, task['release_slot']), task['release_slot'])
    serial = [dict(compute=c, busy_slots_lower=work[c], first_release_lower=release[c],
                   completion_lower=work[c] + release[c]) for c in sorted(work)]
    dag = completion_lower_bound(base, window)
    cut = max((r['lower_slots'] for r in certificate['aggregate_cuts']), default=0)
    serial_bound = max((r['completion_lower'] for r in serial), default=0)
    return dict(lower_slots=max(dag, cut, serial_bound), dag_lower_slots=dag,
                aggregate_cut_lower_slots=cut, compute_serial_lower_slots=serial_bound,
                compute_serial=serial)


def check_provisioning_bound(certificate, row):
    check_bound(certificate['word_certificate'], row)
    bound = provisioning_lower_bound(certificate, row['config']['outstanding_words_per_compute'])
    if row['makespan_slots'] < bound['lower_slots']:
        raise ValueError('Replay violates the provisioning lower bound')
    intervals = defaultdict(list)
    for task in row['tasks']:
        if task['compute'] is not None:
            intervals[task['compute']].append((task['start_slot'], task['finish_slot']))
    for values in intervals.values():
        values.sort()
        if any(a[1] > b[0] for a, b in zip(values, values[1:])):
            raise ValueError('Compute tasks overlap; serial bound does not apply')
    return bound
