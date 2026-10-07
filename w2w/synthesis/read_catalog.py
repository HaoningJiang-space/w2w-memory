"""Reconstruct the frozen read-study catalog independently of experiment runners.

The archived layout and cost ledger are checked before returning candidates.
This module performs no search against requests and launches no experiments.
"""
from fractions import Fraction
import gzip
from hashlib import sha256
import json
from math import isclose
from pathlib import Path

from w2w.domain import EndpointSpec
from w2w.domain.endpoint import NativeProfile
from w2w.service.cost import CostModel
from w2w.service.guaranteed_service_exchange import contoured_geometry
from w2w.synthesis.role_interfaces import make_candidate, static_shared_fifo


CATALOG = 'artifacts/results/endpoint/architecture_competition.json.gz'
PREFIX = 'k3_23_random9_maxweight_'
DESIGNS = ('home_h256s0_d00_direct', 'k2_23_h256s256_d00_direct',
           PREFIX + 'h256s256_d00_direct', PREFIX + 'h256s128_d11_buffered',
           PREFIX + 'h256s160_d12_buffered')


def archived_cost_matches(cost, archived):
    """Ignore only roundoff in accumulated geometric proxies across Python versions.

    Integer resource counts, bandwidths, strings and all other fields remain exact.
    Python 3.12's compensated float sum can differ from 3.10 by a few ulps.
    """
    geometric = {'wire_mm', 'access_wire_bit_mm'}
    return all(k in cost and (isclose(cost[k], v, rel_tol=1e-12, abs_tol=1e-9)
                              if k in geometric else cost[k] == v)
               for k, v in archived.items())


def load_designs(path=CATALOG):
    raw = Path(path).read_bytes()
    archive = json.loads(gzip.decompress(raw) if str(path).endswith('.gz') else raw)
    rows = {row['id']: row for row in archive['search']['catalog']}
    physical = contoured_geometry()
    designs = []
    for key in DESIGNS:
        row = rows[key]
        spec = EndpointSpec(**{**row['endpoint'], 'native': NativeProfile(**row['endpoint']['native'])})
        design = make_candidate(physical, row['pairs'], key, row['structure'], spec,
                                Fraction(row['home_fraction']), row['directions'], allow_unmatched=True)
        if design.layout.sha256 != row['layout_hash']:
            raise RuntimeError('Archived frozen layout failed reconstruction')
        cost = CostModel.evaluate(design)
        if not archived_cost_matches(cost, row['cost']):
            raise RuntimeError('Archived cost contract changed')
        designs.append(design)
    designs.extend(static_shared_fifo(d, share_serializer=True) for d in tuple(designs)
                   if d.structure == 'k3' and d.endpoint.mode == 'buffered')
    return designs, dict(path=str(path), file_sha256=sha256(raw).hexdigest(),
                         source_commit=archive['provenance']['commit'],
                         selection='Five preregistered archived representatives plus two implementation ablations; '
                                   'no layout or interface search on evaluation requests')


