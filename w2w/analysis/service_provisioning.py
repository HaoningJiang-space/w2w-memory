"""Residency coverage and optimistic service/state provisioning bounds.

The bounds describe the existing bank-local replay contract. They neither
implement a pooled engine nor assert that an optimistic capacity is achievable.
"""
from collections import Counter, defaultdict

from w2w.analysis.request_window import (ceil_div, check_bound, completion_lower_bound,
                                        window_certificate)
from w2w.service.read_replay import design_record
from w2w.workloads.read_trace import digest, integer
# Preserve historical analytical imports.
from w2w.theory.service_provisioning import (ceil_fraction, credit_matched_split,
                                            steady_rate_bound, pool_capacity_bound)


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
