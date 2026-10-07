"""Fair fixed-H/plus competition, with endpoint-derived layout optimization."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import subprocess
import time
import numpy as np
from w2w.domain import EndpointSpec
from w2w.provenance import provenance
from w2w.service.guaranteed_service_exchange import contoured_geometry
from w2w.service.evaluator import CandidateEvaluator
from w2w.synthesis.role_interfaces import (
    competition_catalog, competition_frontier, make_candidate, clustered_windows, COMPETITION_COSTS)


def rebuild(physical, row):
    args = {k:v for k,v in row['endpoint'].items() if k != 'native'}
    spec = EndpointSpec(**args)
    return make_candidate(physical, row['pairs'], row['id'], row['structure'], spec,
                          Fraction(row['home_fraction']), row['directions'], allow_unmatched=True)


def choose(rows, workload, budget, structure=None):
    eligible = [r for r in rows if r['training'] in ('both', workload)
                and (structure is None or r['structure'] == structure)
                and all(r['cost'][k] <= limit+1e-8 for k,limit in budget.items())]
    if not eligible:
        return None
    return min(eligible, key=lambda r: (-round(r['scores'][workload],12),
               *(r['cost'][k] for k in COMPETITION_COSTS), r['id']))['id']


def run(output):
    if subprocess.check_output(['git','status','--porcelain'],text=True).strip():
        raise RuntimeError('Commit source before experiment')
    started = time.monotonic()
    physical = contoured_geometry()
    search = competition_catalog(physical)
    rows = search['catalog']
    by_id = {r['id']:r for r in rows}
    frontiers = {}
    verify_ids = set()
    for workload in ('random9','clustered9'):
        frontiers[workload] = dict(
            global_primary=competition_frontier(rows,workload),
            global_extended=competition_frontier(rows,workload,extended=True),
            late_serializer=competition_frontier(rows,workload,late=True),
            by_structure={s:competition_frontier([r for r in rows if r['structure']==s],workload)
                          for s in ('home','k2','k3')})
        for key in ('global_primary','global_extended','late_serializer'):
            verify_ids.update(frontiers[workload][key])
        for values in frontiers[workload]['by_structure'].values():
            verify_ids.update(values)
    budgets = []
    for workload in frontiers:
        for lane in (8192,12288,16384,18432,24576):
            for storage in (8192,16384,24576,49152):
                for wire in (125000,215000,245000,300000,350000,480000):
                    budget = dict(zip(COMPETITION_COSTS,(lane,storage,wire)))
                    best = choose(rows,workload,budget)
                    choices = {s:choose(rows,workload,budget,s) for s in ('home','k2','k3')}
                    budgets.append(dict(workload=workload,budget=budget,best=best,by_structure=choices))
                    verify_ids.update(v for v in choices.values() if v is not None)
    print('CATALOG',search['counts'],'unclosed',len(search['unclosed']),
          'witnesses',len(search['witnesses']),'verification IDs',len(verify_ids),flush=True)
    for t in search['templates']:
        print('TEMPLATE',t['id'],'gain',t['gain'],'private',len(t['private_clients']),flush=True)
    # Several named candidates have identical complete designs. Verify their
    # immutable layout+endpoint once; all evidence references retain the aliases.
    verified = {}
    aliases = {}
    rng = np.random.default_rng(620100)
    random9 = sorted(rng.choice(36,9,replace=False).tolist())
    for index, name in enumerate(sorted(verify_ids)):
        row = by_id[name]
        signature = row['layout_hash'] + json.dumps([row['endpoint'],row['directions']],sort_keys=True)
        if signature in aliases:
            row['verification_id'] = aliases[signature]
            continue
        design = rebuild(physical,row)
        if design.layout.sha256 != row['layout_hash']:
            raise RuntimeError('Frozen layout reconstruction failed')
        evaluator = CandidateEvaluator(design)
        template = next(t for t in search['templates'] if t['id']==row['template'])
        private = set(template['private_clients'])
        client = next((c for c in range(36) if c not in private),0)
        scenarios = dict(full=list(range(36)), single=[client],
                         one_pair=row['pairs'][0] if row['pairs'] else [0,1],
                         random9=random9,first9=list(range(9)))
        scenarios.update({f'cluster{i}':list(active) for i,active in enumerate(clustered_windows())})
        replays = {key:evaluator.replay(active) for key,active in scenarios.items()}
        actual = dict(random9=evaluator.population(9)['exact_mean_tb_s'],
                      clustered9=float(np.mean([replays[f'cluster{i}']['executed_tb_s'] for i in range(16)])))
        error = max(abs(actual[w]-row['scores'][w]) for w in actual)
        if error > 1e-9 or not replays['full']['floor_one_feasible']:
            raise RuntimeError('Structural reduction disagrees with common execution/LP')
        verified[name] = dict(layout_hash=design.layout.sha256, scores=actual,replays=replays,
                              coefficient_error=error,composition=evaluator.composition,
                              lp_solves=sum(v['lp_solves'] for v in replays.values()),
                              max_residual=max(v['witness_residual'] for v in replays.values()))
        row['verification_id'] = name
        aliases[signature] = name
        print('VERIFY',index+1,'/',len(verify_ids),name,'scores',actual,flush=True)
    result = dict(provenance=provenance(),
                  registration_sha256=hashlib.sha256(Path('docs/methods/ARCHITECTURE_COMPETITION.md').read_bytes()).hexdigest(),
                  scope='Family-exact role/interface/reciprocal-layout competition under full-load floor 1; not arbitrary fabric optimality',
                  primary_cost_keys=list(COMPETITION_COSTS),
                  workloads=dict(random9='uniform 9-of-36 exact expectation',clustered9=clustered_windows()),
                  search=search,frontiers=frontiers,budgets=budgets,verified=verified,
                  verification=dict(unique_designs=len(verified),aliases=len(verify_ids)-len(verified),
                      lp_solves=sum(v['lp_solves'] for v in verified.values()),
                      max_coefficient_error=max(v['coefficient_error'] for v in verified.values()),
                      max_resource_residual=max(v['max_residual'] for v in verified.values()),
                      all_ratio_bounds_closed=not search['unclosed']),
                  elapsed_seconds=time.monotonic()-started)
    path = Path(output)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,indent=2)+'\n')
    print('VERIFIED',result['verification'],'seconds',result['elapsed_seconds'],flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    run(args.output)
