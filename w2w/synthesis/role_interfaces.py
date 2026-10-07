"""Bounded design construction and selection through public model APIs."""
from fractions import Fraction
from dataclasses import replace
from math import ceil
import numpy as np
from w2w.constants import BANKS
from w2w.domain import EndpointSpec
from w2w.service.adapters import freeze_design
from w2w.service.guaranteed_service_exchange import (
    Channels, ExposureFabric, StripedLayout, balanced_assignment)
from w2w.synthesis.memory_fabric_dse import FractionalLayout


def implementation(home, shared, home_depth=1, shared_depth=None, mode='buffered',
                   serializer_location='bank', directions=(2, 3)):
    if shared_depth is None:
        shared_depth = 1 if not shared or 256 % shared == 0 else 2
    if mode == 'direct':
        home_depth = shared_depth = 0
    widths = tuple(home if p == 0 else (shared if p in directions else 0) for p in range(5))
    depths = tuple(home_depth if p == 0 else (shared_depth if p in directions and shared else 0)
                   for p in range(5))
    return EndpointSpec(widths, depths, mode=mode, serializer_location=serializer_location)


def make_candidate(physical, pairs, name, structure, spec, home_fraction,
                   directions=(2, 3), allow_unmatched=False):
    fraction = Fraction(home_fraction)
    if not 0 < fraction <= 1:
        raise ValueError('Home fraction must be in (0,1]')
    if structure == 'home':
        if fraction != 1 or any(spec.widths[1:]):
            raise ValueError('Home-only requires all data and hardware at home')
        mask = tuple((0,) for _ in range(BANKS))
        ports = (8000, 0, 0, 0, 0)
    elif structure == 'k2':
        mask = balanced_assignment(physical, directions)
        ports = tuple(8000 if p == 0 else (8000 // len(directions) if p in directions else 0)
                      for p in range(5))
    elif structure == 'k3':
        if tuple(directions) not in ((1, 4), (2, 3)):
            raise ValueError('k3 requires two opposite directions')
        mask = tuple((0, *directions) for _ in range(BANKS))
        ports = tuple(8000 if p == 0 or p in directions else 0 for p in range(5))
    else:
        raise ValueError('Unknown structure')
    if any(spec.widths[p] == 0 or ports[p] == 0 for ps in mask for p in ps):
        raise ValueError('Mask points to an unconfigured output')
    fabric = ExposureFabric(physical, mask, Channels(ports, buffer_depth=0))
    home = StripedLayout.home(fabric).shares
    if structure == 'home':
        shares = home
    elif structure == 'k2':
        half = StripedLayout.reciprocal(fabric, .5).shares
        shares = home + 2 * float(1 - fraction) * (half - home)
    else:
        members = [c for pair in pairs for c in pair]
        if (len(members) != len(set(members)) or any(not 0 <= c < fabric.nc for c in members)
                or (not allow_unmatched and sorted(members) != list(range(fabric.nc)))):
            raise ValueError('A full disjoint pairing is required')
        shares = home.copy()
        for a, b in pairs:
            for c, peer in ((a, b), (b, a)):
                shares[c, :] = 0
                shares[c, c * BANKS:(c + 1) * BANKS] = float(fraction) / BANKS
                shares[c, peer * BANKS:(peer + 1) * BANKS] = float(1 - fraction) / BANKS
    layout = FractionalLayout(shares)
    for c, bank in zip(*np.nonzero(layout.shares)):
        if len(fabric.paths.get((c, bank), [])) != 1:
            raise ValueError('Every fixed byte requires one physical route')
    if any(np.count_nonzero(layout.shares[:, b]) > 2 for b in range(fabric.nm * BANKS)):
        raise ValueError('Registered family supports at most two owners per bank')
    return freeze_design(name, structure, fabric, layout, spec, fraction)


def catalog(physical, pairs):
    definitions = [('home_direct', 'home', implementation(256, 0, mode='direct'), Fraction(1))]
    for width in (64, 128, 160, 192, 256):
        for label, fraction in [('matched', Fraction(256, 256 + width)), ('half', Fraction(1, 2))]:
            if width == 256 and label == 'half':
                continue
            definitions.append((f'k2_s{width}_{label}', 'k2', implementation(256, width), fraction))
    definitions.extend([
        ('k3_equal192_d2', 'k3', implementation(192, 192, 2, 2), Fraction(1, 2)),
        ('k3_wide_direct', 'k3', implementation(256, 256, mode='direct'), Fraction(1, 2))])
    for width in (64, 96, 128, 160, 192, 224, 256):
        definitions.append((f'k3_s{width}_matched', 'k3', implementation(256, width), Fraction(256, 256 + width)))
    for width in (128, 160):
        definitions.append((f'k3_s{width}_half', 'k3', implementation(256, width), Fraction(1, 2)))
    return [make_candidate(physical, pairs, *entry) for entry in definitions]


def static_shared_fifo(design):
    """Reuse bank-local storage only when all resident bytes select one direction/M.

    Physical exposure, routes, widths, serializers and frozen data remain intact.
    Configuration is compiled once from the full layout, never from active users.
    """
    if design.structure not in ('k3', 'pair') or design.endpoint.shared_fifo_ports:
        raise ValueError('Static shared FIFO requires an independent full-bank pair design')
    group = tuple(p for p, w in enumerate(design.endpoint.widths) if p and w)
    spec = replace(design.endpoint, shared_fifo_ports=group)
    used = [set() for _ in design.geometry.memory_xy]
    routes = {}
    for c, m, _, p, _, _ in design.geometry.routes:
        routes.setdefault((c, m), set()).add(p)
    nb = len(design.exposure.mask)
    for c, row in enumerate(design.layout.shares):
        for bank, share in enumerate(row):
            if share:
                m, b = divmod(bank, nb)
                used[m].update(routes.get((c, m), set()) & set(design.exposure.mask[b]) & set(group))
    if any(len(ports) > 1 for ports in used):
        raise ValueError('Frozen layout uses multiple shared directions in one memory')
    selected = tuple(next(iter(ports)) if ports else group[0] for ports in used)
    return replace(design, name=design.name + '_static_fifo', endpoint=spec, shared_directions=selected)


def synthesize_pair_target(target, quantum=32):
    """Invert a requested exclusive rate in the registered home-wide family."""
    target = Fraction(target)
    if not 1 <= target <= 2 or 256 % quantum:
        raise ValueError('Target/quantum outside the registered family')
    width = ceil(256 * (target - 1) / quantum) * quantum
    if width == 0:
        return dict(home_width=256, shared_width=0, home_fraction='1', single_upper=1.)
    return dict(home_width=256, shared_width=width,
                home_fraction=str(Fraction(256, 256 + width)), single_upper=1 + width / 256)



def pareto(rows):
    keys = ('bank_port_connections', 'export_lane_bits', 'endpoint_storage_bits',
            'pipeline_register_bits', 'access_wire_bit_mm', 'configured_hb_signal_bits',
            'fixed_sequence_control_bits', 'selector_input_bits')
    def dominates(a, b):
        costs_le = all(a['cost'][key] <= b['cost'][key] + 1e-9 for key in keys)
        rates_ge = (a['mean'] >= b['mean'] - 1e-10 and a['full'] >= b['full'] - 1e-10)
        strict = (any(a['cost'][key] < b['cost'][key] - 1e-9 for key in keys)
                  or a['mean'] > b['mean'] + 1e-10 or a['full'] > b['full'] + 1e-10)
        return costs_le and rates_ge and strict
    return [r['id'] for r in rows if not any(dominates(other, r) for other in rows)]


def clustered_windows():
    """All non-wrapping 3x3 windows of the fixed 6x6 compute index grid."""
    return [tuple((row+i)*6+col+j for i in range(3) for j in range(3))
            for row in range(4) for col in range(4)]


def competition_templates(physical):
    """Exact balanced assignment and graph matching inside registered families."""
    import networkx as nx
    from w2w.service.evaluator import CandidateEvaluator
    templates = []
    def add(name, structure, directions, pairs=(), training='both', policy='fixed'):
        spec = implementation(256, 0 if structure == 'home' else 256,
                              mode='direct', directions=directions)
        design = make_candidate(physical, pairs, name, structure, spec,
                                Fraction(1) if structure == 'home' else Fraction(1, 2),
                                directions, allow_unmatched=True)
        evaluator = CandidateEvaluator(design)
        private = []
        neighbors = []
        for c, row in enumerate(design.layout.shares):
            banks = [b for b, value in enumerate(row) if value > 0]
            private.append(any(evaluator.owners[b] == (c,) for b in banks))
            neighbors.append(sorted({v for b in banks for v in evaluator.owners[b] if v != c}))
        from math import comb
        random_gain = sum(0 if private[c] else comb(35-len(neighbors[c]), 8)/comb(35, 8)
                          for c in range(36))/36
        cluster_gain = sum(sum(not private[c] and not (set(neighbors[c]) & set(active)) for c in active)/9
                           for active in clustered_windows())/16
        templates.append(dict(id=name, structure=structure, directions=list(directions),
                              pairs=[list(p) for p in pairs], training=training, policy=policy,
                              private_clients=[c for c in range(36) if private[c]],
                              neighbors=neighbors, gain=dict(random9=random_gain, clustered9=cluster_gain),
                              maximum_width_composition=evaluator.composition))
    add('home', 'home', ())
    for directions in ((2, 3), (1, 4), (1, 2, 3, 4)):
        add('k2_' + ''.join(map(str, directions)), 'k2', directions)
    for directions in ((2, 3), (1, 4)):
        allowed = {(e['c'], e['m']) for e in physical.edges if e['mp'] in directions
                   and min(e['compute_port_fraction'], e['memory_port_fraction']) >= 1-1e-9}
        for workload in ('random9', 'clustered9'):
            graph = nx.Graph()
            graph.add_nodes_from(range(36))
            for c, peer in sorted(allowed):
                if c >= peer or (peer, c) not in allowed:
                    continue
                weight = (1. if workload == 'random9' else
                          sum((c in active) != (peer in active) for active in clustered_windows())/16/9)
                graph.add_edge(c, peer, weight=weight)
            seen = set()
            for maxcard in (False, True):
                pairs = tuple(sorted(tuple(sorted(pair)) for pair in
                                     nx.max_weight_matching(graph, maxcardinality=maxcard)))
                if pairs in seen:
                    continue
                seen.add(pairs)
                tag = 'maxcard' if maxcard else 'maxweight'
                add(f'k3_{"".join(map(str,directions))}_{workload}_{tag}', 'k3', directions,
                    pairs, workload, tag)
    return templates


def competition_catalog(physical):
    """Inverse ratio design with exact local witnesses; no independent FIFO sweep.

    Each legal implementation reaches its exclusive qH+qS upper bound and full
    native service, or is explicitly left unclosed. Whole-wafer LP verification
    is performed by the experiment on the final nondominated designs.
    """
    from w2w.endpoints.role_execution import execute_periodic, ratio_sequence
    from w2w.service.cost import CostModel
    import hashlib
    import json
    templates = competition_templates(physical)
    witnesses = {}
    def save_trace(spec, sequence):
        trace = execute_periodic(spec, sequence)
        key = hashlib.sha256(json.dumps([spec.record(), sequence], sort_keys=True).encode()).hexdigest()
        witnesses[key] = trace
        return trace, key
    options = []
    for width in range(32, 257, 32):
        for depth in (1, 2):
            if depth == 2 and 256 % width == 0:
                continue
            trace, key = save_trace(EndpointSpec((width,), (depth,)), (0,))
            q = Fraction(trace['delivered_words'][0], trace['period_slots'])
            options.append(dict(width=width, depth=depth, q=q, witness=key))
    # An option inferior in width, storage AND executed single-output service
    # cannot improve this balanced-sequence family. Retain only local tradeoffs.
    options = [v for v in options if not any(
        o['width'] <= v['width'] and o['depth'] <= v['depth'] and o['q'] >= v['q']
        and (o['width'] < v['width'] or o['depth'] < v['depth'] or o['q'] > v['q'])
        for o in options)]
    rows, unclosed = [], []
    counts = dict(proposed=0, rejected_native_sum=0, rejected_private_home=0, accepted=0)
    for template in templates:
        if template['structure'] == 'home':
            implementations = [(dict(width=256, depth=0, q=Fraction(1)),
                                dict(width=0, depth=0, q=Fraction(0)), 'direct')]
        else:
            implementations = [(h, s, 'buffered') for h in options for s in options]
            implementations.append((dict(width=256, depth=0, q=Fraction(1)),
                                    dict(width=256, depth=0, q=Fraction(1)), 'direct'))
        for h, s, mode in implementations:
            counts['proposed'] += 1
            gamma = h['q'] + s['q']
            if gamma < 1:
                counts['rejected_native_sum'] += 1
                continue
            if template['private_clients'] and h['q'] < 1:
                counts['rejected_private_home'] += 1
                continue
            fraction = h['q']/gamma
            sequence = ((0,) if not s['width'] else
                        ratio_sequence(0, 1, fraction.numerator, fraction.denominator))
            local = EndpointSpec((h['width'], s['width']), (h['depth'], s['depth']), mode=mode)
            concurrent, key = save_trace(local, sequence)
            full = concurrent['total_per_native']
            if abs(full-1) > 1e-12:
                unclosed.append(dict(template=template['id'], home=h['width'], shared=s['width'],
                                     depths=[h['depth'],s['depth']], fraction=str(fraction), full=full))
                continue
            name = f"{template['id']}_h{h['width']}s{s['width']}_d{h['depth']}{s['depth']}_{mode}"
            spec = implementation(h['width'], s['width'], h['depth'], s['depth'], mode,
                                  directions=template['directions'])
            design = make_candidate(physical, template['pairs'], name, template['structure'], spec,
                                    fraction, template['directions'], allow_unmatched=True)
            row = dict(id=name, template=template['id'], structure=template['structure'],
                       training=template['training'], directions=template['directions'],
                       pairs=template['pairs'], endpoint=spec.record(), home_fraction=str(fraction),
                       layout_hash=design.layout.sha256, cost=CostModel.evaluate(design),
                       late_serializer_cost=CostModel.evaluate(design, 'port'),
                       single_role_caps=[str(h['q']), str(s['q'])], exclusive_upper=float(gamma),
                       full=full, concurrent_witness=key,
                       scores={w: 1+gain*(float(gamma)-1) for w, gain in template['gain'].items()},
                       ratio_upper_attained=True)
            rows.append(row)
            counts['accepted'] += 1
    return dict(templates=templates, options=[dict(v,q=str(v['q'])) for v in options],
                catalog=rows, witnesses=witnesses, counts=counts, unclosed=unclosed)


COMPETITION_COSTS = ('export_lane_bits', 'endpoint_storage_bits', 'access_wire_bit_mm')


def competition_frontier(rows, workload, extended=False, late=False):
    keys = COMPETITION_COSTS + (('pipeline_register_bits', 'fixed_sequence_control_bits',
            'selector_input_bits', 'bank_port_connections', 'configured_hb_signal_bits') if extended else ())
    cost = 'late_serializer_cost' if late else 'cost'
    eligible = [r for r in rows if r['training'] in ('both', workload)]
    def dominates(a, b):
        return (a['scores'][workload] >= b['scores'][workload]-1e-12
                and all(a[cost][k] <= b[cost][k]+1e-8 for k in keys)
                and (a['scores'][workload] > b['scores'][workload]+1e-12
                     or any(a[cost][k] < b[cost][k]-1e-8 for k in keys)))
    return [r['id'] for r in eligible if not any(dominates(o,r) for o in eligible)]
