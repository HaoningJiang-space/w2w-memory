"""Bounded design construction and selection through public model APIs."""
from fractions import Fraction
from math import ceil
import numpy as np
from w2w.constants import BANKS
from w2w.domain import EndpointSpec
from w2w.service.adapters import freeze_design
from w2w.service.guaranteed_service_exchange import (
    Channels, ExposureFabric, StripedLayout, balanced_assignment)
from w2w.synthesis.memory_fabric_dse import FractionalLayout


def implementation(home, shared, home_depth=1, shared_depth=None, mode='buffered',
                   serializer_location='bank'):
    if shared_depth is None:
        shared_depth = 1 if not shared or 256 % shared == 0 else 2
    if mode == 'direct':
        home_depth = shared_depth = 0
    return EndpointSpec((home, 0, shared, shared, 0),
                              (home_depth, 0, shared_depth if shared else 0,
                               shared_depth if shared else 0, 0),
                              mode=mode, serializer_location=serializer_location)


def make_candidate(physical, pairs, name, structure, spec, home_fraction):
    fraction = Fraction(home_fraction)
    if not Fraction(1, 2) <= fraction <= 1:
        raise ValueError('This frozen family requires home fraction in [1/2,1]')
    if structure == 'home':
        if fraction != 1 or any(spec.widths[1:]):
            raise ValueError('Home-only requires all data and hardware at home')
        mask = tuple((0,) for _ in range(BANKS))
        ports = (8000, 0, 0, 0, 0)
    elif structure == 'k2':
        mask = balanced_assignment(physical, (2, 3))
        ports = (8000, 0, 4000, 4000, 0)
    elif structure == 'k3':
        mask = tuple((0, 2, 3) for _ in range(BANKS))
        ports = (8000, 0, 8000, 8000, 0)
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
        if sorted(members) != list(range(fabric.nc)):
            raise ValueError('A full disjoint pairing is required')
        shares = np.zeros_like(home)
        for a, b in pairs:
            for c, peer in ((a, b), (b, a)):
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
