"""Invert a service-retention target using registered full-word contracts."""
from fractions import Fraction
import gzip
from hashlib import sha256
import json
from pathlib import Path

from w2w.domain import EndpointSpec
from w2w.domain.endpoint import NativeProfile
from w2w.service.cost import CostModel
from w2w.service.guaranteed_service_exchange import contoured_geometry
from w2w.synthesis.read_catalog import CATALOG
from w2w.synthesis.role_interfaces import make_candidate, static_shared_fifo
from w2w.theory.service_provisioning import credit_matched_split, steady_rate_bound
from w2w.theory.return_path import return_path_period


def target_design(window, retention=Fraction(3, 4), rx_depth=None):
    """Minimum Shared width, then depth, in the fixed 256-bit Home family.

    Optimize a necessary steady-rate relaxation, not finite completion or total
    area. Every retained/excluded contract is exposed. No workload is consumed.
    """
    retention = Fraction(retention)
    if type(window) is not int or window <= 96 or not 0 < retention <= 1:
        raise ValueError('Require N>96 and a positive retention target at most one')
    reference = min(Fraction(2), Fraction(window, 96))
    target = 1 + retention * (reference - 1)
    fraction = 1 / target
    raw = Path(CATALOG).read_bytes()
    catalog = json.loads(gzip.decompress(raw))
    candidates = []
    rows = [r for r in catalog['search']['catalog']
            if r['template'] == 'k3_23_random9_maxweight' and r['endpoint']['widths'][0] == 256]
    for row in rows:
        width, depth = row['endpoint']['widths'][2], row['endpoint']['depths'][2]
        q = Fraction(row['single_role_caps'][1])
        path_rate = None
        if rx_depth is not None:
            path_rate = return_path_period(width, max(1, depth), rx_depth)['words_per_slot']
            q = min(q, Fraction(path_rate))
        lifetime = 2 + (255 + width) // width
        optimum = credit_matched_split(32, q, window, 3, lifetime)
        upper = Fraction(optimum['normalized_rate_upper'])
        supplied = steady_rate_bound(32, q, fraction, window, 3, lifetime)
        if (upper >= target) != (supplied >= target):
            raise ValueError('Home-saturating fraction disagrees with relaxation optimum')
        candidates.append(dict(id=row['id'], width_bits=width, depth_words=depth,
            shared_rate=str(q), minimum_word_lifetime=lifetime,
            relaxed_max_rate=str(upper), rate_bound_at_target_fraction=str(supplied),
            target_not_excluded=supplied >= target, mode=row['endpoint']['mode']))
        if path_rate is not None:
            candidates[-1]['return_path_rate'] = path_rate
    feasible = [r for r in candidates if r['target_not_excluded']]
    selected = min(feasible, key=lambda r: (r['width_bits'], r['depth_words'], r['id']))
    row = next(r for r in rows if r['id'] == selected['id'])
    spec = EndpointSpec(**{**row['endpoint'], 'native': NativeProfile(**row['endpoint']['native'])})
    design = make_candidate(contoured_geometry(), row['pairs'], f'target_n{window}_eta{retention}',
                            row['structure'], spec, fraction, row['directions'])
    if spec.mode == 'buffered':
        design = static_shared_fifo(design, share_serializer=True)
    plan = dict(window=window, requested_retention=str(retention), reference_rate=str(reference),
        target_rate=str(target), home_fraction=str(fraction), selected=selected, candidates=candidates,
        catalog_sha256=sha256(raw).hexdigest(), cost=CostModel.evaluate(design),
        scope='Minimum Shared width then depth in fixed Home256 contracts; steady necessary bounds; not total-cost optimum')
    if rx_depth is not None:
        plan['rx_depth'] = rx_depth
    return design, plan
