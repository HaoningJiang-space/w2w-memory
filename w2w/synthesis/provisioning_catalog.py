"""Frozen credit-aware residency candidates shared by studies and validation.

Reconstructs the registered designs without running experiments or selecting on
workload inputs. Historical experiment-module imports remain compatible.
"""
from fractions import Fraction
import gzip
import json
from pathlib import Path

from w2w.theory.service_provisioning import credit_matched_split
from w2w.service.guaranteed_service_exchange import contoured_geometry
from w2w.synthesis.read_catalog import CATALOG, load_designs
from w2w.synthesis.role_interfaces import make_candidate, static_shared_fifo


def candidate_designs():
    existing, identity = load_designs()
    designs = dict(zip(('home', 'k2', 'wide', 'a_cfg', 'b_cfg'),
                       (existing[0], existing[1], existing[2], existing[5], existing[6])))
    catalog = json.loads(gzip.decompress(Path(CATALOG).read_bytes()))
    rows = {r['id']: r for r in catalog['search']['catalog']}
    physical = contoured_geometry()
    derivations, duplicated = [], {}
    for label, index, window, shared_rate in (('a_n128', 3, 128, Fraction(1, 2)),
                                             ('b_n128', 4, 128, Fraction(5, 8)),
                                             ('b_n160', 4, 160, Fraction(5, 8))):
        old = existing[index]
        row = rows[old.name]
        derived = credit_matched_split(32, shared_rate, window)
        dup = make_candidate(physical, row['pairs'], label + '_duplicated', old.structure,
                             old.endpoint, Fraction(derived['home_fraction']), row['directions'])
        cfg = static_shared_fifo(dup, share_serializer=True)
        # Only the byte split, its configuration-derived quota, and names change.
        if (cfg.geometry != old.geometry or cfg.exposure != old.exposure
                or cfg.endpoint != existing[index + 2].endpoint
                or cfg.shared_directions != existing[index + 2].shared_directions):
            raise ValueError('Unexpected geometry/interface/partner change')
        designs[label] = cfg
        duplicated[label] = (dup, window)
        derivations.append(dict(label=label, original_id=old.name, window=window,
                                shared_words_per_slot_per_bank=str(shared_rate), **derived))
    return designs, duplicated, derivations, identity
