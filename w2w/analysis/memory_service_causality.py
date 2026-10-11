"""Reconstruct descriptor ownership from saved physical events, without replay.

These are disjoint *slot lifetimes*, not additive application stalls or measured
counterfactual savings. In particular, atom admission overlaps array execution.
"""
from collections import Counter, defaultdict
from .compute_memory_competition import Occupancy

PHASES = (
    'mc_to_vertical_admission',
    'vertical_to_first_atom_admission',
    'atom_admission_span',
    'last_admission_to_last_array_callback',
    'last_array_callback_to_gateway_payload',
    'gateway_payload_to_mc_release',
)
SINGLE = ('read_issue', 'mc_accept', 'native_accept', 'array_first_ready',
          'array_last_ready', 'native_first_ready', 'native_ready', 'mc_release', 'read_deliver')
DOMAIN = ('request_control_send', 'request_control_arrive',
          'domain_descriptor_begin', 'domain_range_issued', 'request_ack_arrive')


def _overlap(a, b, windows):
    return sum(max(0, min(b, y) - max(a, x)) for x, y in windows if x < b and y > a)


def descriptor_lifetimes(result):
    """Require complete control/return evidence and validate both descriptor pools."""
    if not result['native'].get('request_control', {}).get('enabled'):
        raise ValueError('Physical command/ACK evidence is required')
    memories = {m['id']: m for m in result['spec']['memories']}
    periods = {d['id']: d['period_ps'] for d in result['spec']['stack']['dram_domains']}
    paths = {(p['domain_id'], p['gateway_id']): p for p in result['spec']['stack']['collection_paths']}
    events = defaultdict(lambda: defaultdict(list))
    changes = defaultdict(list)
    native_changes = defaultdict(list)
    capacities = {}
    for m in memories.values():
        pool = m.get('mc_pool_id') or m['id']
        if capacities.setdefault(pool, m['transaction_slots']) != m['transaction_slots']:
            raise ValueError('Inconsistent shared descriptor-pool capacity')
    for e in result['events']:
        if e['kind'] in SINGLE + DOMAIN:
            events[e['request']][e['kind']].append(e)
        if e['kind'] in ('mc_accept', 'mc_release'):
            m = memories[e['memory']]; pool = m.get('mc_pool_id') or m['id']
            changes[pool].append((e['time_ps'], e['request'], e['kind'] == 'mc_accept'))
    rows = {}
    for key, ev in events.items():
        if any(len(ev[k]) != 1 for k in SINGLE):
            raise ValueError(f'Incomplete or duplicate descriptor milestone: {key}')
        one = {k: ev[k][0] for k in SINGLE}
        m = memories[one['mc_accept']['memory']]; pool = m.get('mc_pool_id') or m['id']
        if one['mc_release']['memory'] != m['id']:
            raise ValueError('Descriptor released to another memory interface')
        domains = {}
        for kind in DOMAIN:
            group = {e['domain']: e for e in ev[kind]}
            if len(group) != len(ev[kind]) or not group:
                raise ValueError('Missing or duplicate per-domain control milestone')
            if domains and set(group) != set(domains):
                raise ValueError('Per-domain command/admission/ACK coverage differs')
            for d, e in group.items():
                if d not in m['domain_ids'] or e['gateway'] != m['gateway_id']:
                    raise ValueError('Control event uses another physical service domain')
                domains.setdefault(d, {})[kind] = e
        size = one['read_issue']['bytes']; bank = one['read_issue']['bank']
        expected_domains = {d for i, d in enumerate(m['domain_ids'])
                            if ((i-bank) % m['banks'])*32 < size}
        if (type(size) is not int or size < 32 or size % 32 or not 0 <= bank < m['banks']
                or set(domains) != expected_domains):
            raise ValueError('Control coverage does not match descriptor address striping')
        domain_rows = {}
        for d, evd in domains.items():
            send, arrive, begin, end, ack = (evd[k] for k in DOMAIN)
            if (send['arrival_ps'] != arrive['time_ps'] or
                    not send['time_ps'] <= send['end_ps'] <= arrive['time_ps'] <= begin['time_ps'] <= end['time_ps'] <= ack['time_ps']):
                raise ValueError('Illegal command/array-admission/ACK ordering')
            domain_rows[d] = dict(command_send_ps=send['time_ps'], command_arrive_ps=arrive['time_ps'],
                first_atom_admitted_ps=begin['time_ps'], last_atom_admitted_ps=end['time_ps'],
                ack_arrive_ps=ack['time_ps'], frontend_wait_before_first_atom_ps=begin['time_ps']-arrive['time_ps'])
        callback = {}
        for kind in ('array_first_ready', 'array_last_ready'):
            e = one[kind]; period = periods[e['domain']]
            # Existing adapter markers denote the beginning of the final native
            # bus cycle. Its callback/collection-origin timestamp is one tick later.
            tail = e['time_ps'] + period
            p = paths[e['domain'], e['gateway']]
            if e['gateway'] != m['gateway_id'] or e['domain'] not in domains:
                raise ValueError('Raw callback uses another service path')
            if e['hb_tail_ps'] != tail + p['pipeline_cycles'] * p['period_ps']:
                raise ValueError('Array-marker/collection-tail timestamp convention differs')
            callback[kind] = tail
        a = one['mc_accept']['time_ps']; v = one['native_accept']['time_ps']
        first = min(d['first_atom_admitted_ps'] for d in domain_rows.values())
        last = max(d['last_atom_admitted_ps'] for d in domain_rows.values())
        raw = callback['array_last_ready']; payload = one['native_ready']['time_ps']; release = one['mc_release']['time_ps']
        boundary = (a, v, first, last, raw, payload, release)
        if list(boundary) != sorted(boundary):
            raise ValueError('Descriptor lifetime does not follow observed physical stages')
        first_raw = callback['array_first_ready']; first_payload = one['native_first_ready']['time_ps']
        if not (one['read_issue']['time_ps'] <= a and first <= first_raw <= raw
                and first_raw <= first_payload <= payload <= release <= one['read_deliver']['time_ps']):
            raise ValueError('Invalid issue, first return or destination commit ordering')
        row = dict(request=key, task=one['read_issue']['task'], memory=m['id'], gateway=m['gateway_id'],
            pool=pool, bytes=size, bank=one['read_issue']['bank'], word_address=one['read_issue']['word_address'],
            issue_ps=one['read_issue']['time_ps'], mc_accept_ps=a, vertical_admit_ps=v,
            first_atom_admitted_ps=first, last_atom_admitted_ps=last,
            first_array_callback_ps=first_raw, last_array_callback_ps=raw,
            first_gateway_payload_ps=first_payload, last_gateway_payload_ps=payload,
            mc_release_ps=release, operand_committed_ps=one['read_deliver']['time_ps'],
            domains=domain_rows, phase_ps={p: y-x for p, x, y in zip(PHASES, boundary, boundary[1:])},
            boundary_ps=boundary)
        if sum(row['phase_ps'].values()) != release-a:
            raise ValueError('Disjoint ownership phases do not conserve slot time')
        rows[key] = row
        native_changes[pool].extend(((v, key, True), (payload, key, False)))
    if sum(r['bytes'] for r in rows.values()) != result['native']['accepted_atoms'] * 16:
        raise ValueError('Reconstructed descriptors do not conserve native read bytes')
    pools = {p: Occupancy(c, capacities[p]) for p, c in changes.items()}
    # Native grouped admission has a separate finite pool and earlier release.
    vertical_pools = {p: Occupancy(sorted(c, key=lambda e: (e[0], e[2])), capacities[p])
                      for p, c in native_changes.items()}
    return rows, pools, vertical_pools, capacities


def explain_pool_window(result, task):
    rows, pools, vertical_pools, capacities = descriptor_lifetimes(result)
    target = sorted((r for r in rows.values() if r['task'] == task), key=lambda r: r['issue_ps'])
    if not target:
        raise ValueError('Requested task has no saved descriptors')
    pool_ids = {r['pool'] for r in target}
    if len(pool_ids) != 1:
        raise ValueError('This diagnosis requires one shared MC pool per matrix')
    pool = next(iter(pool_ids)); begin, end = target[0]['issue_ps'], target[-1]['issue_ps']
    if end <= begin:
        raise ValueError('A nonempty descriptor issue window is required')
    windows = [(max(a, begin), min(b, end)) for a, b in pools[pool].full if a < end and b > begin]
    full_ps = sum(b-a for a, b in windows)
    phase = Counter(); owners = defaultdict(Counter); witnesses = []
    for r in rows.values():
        if r['pool'] != pool or r['mc_accept_ps'] >= end or r['mc_release_ps'] <= begin:
            continue
        amounts = {p: _overlap(a, b, windows) for p, a, b in zip(PHASES, r['boundary_ps'], r['boundary_ps'][1:])}
        phase.update(amounts); owners[r['task']].update(amounts)
        witnesses.append(dict(request=r['request'], task=r['task'], mc_accept_ps=r['mc_accept_ps'],
            mc_release_ps=r['mc_release_ps'], boundary_ps=r['boundary_ps'], full_window_phase_slot_ps=amounts))
    if sum(phase.values()) != capacities[pool] * full_ps:
        raise ValueError('Full-pool phase accounting does not conserve capacity × wall time')
    return dict(task=task, pool=pool, capacity=capacities[pool], descriptor_count=len(target),
        bytes=sum(r['bytes'] for r in target), issue_window_ps=[begin, end], issue_window_duration_ps=end-begin,
        mc_full_wall_ps=full_ps, vertical_pool_full_wall_ps=vertical_pools[pool].blocked_time(begin, end),
        full_intervals_ps=windows, full_window_phase_slot_ps=dict(phase),
        full_window_phase_fraction={k: v/(capacities[pool]*full_ps) if full_ps else 0 for k, v in phase.items()},
        owner_phase_slot_ps={k: dict(v) for k, v in owners.items()}, pool_ownership_witnesses=witnesses,
        target_descriptors=target,
        native_profile=result['spec']['stack']['native_policy'],
        array_marker_contract='array_*_ready marker + physical domain period = native callback bus tail; '
            'native_*_ready means gateway payload availability, not raw array completion.',
        scope='Saved-record ownership diagnosis. Atom-admission span includes frontend contention, finite reservations, '
            'controller/refresh service and overlapping returns. These phases cannot be treated as independent stalls '
            'or recoverable makespan. No hypothetical component change or new simulation is performed.')
