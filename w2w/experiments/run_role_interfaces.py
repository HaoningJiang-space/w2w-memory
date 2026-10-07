"""Registered home/k2/k3 designs through one execution and accounting pipeline."""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import numpy as np
from w2w.constants import BANKS
from w2w.domain import EndpointSpec, NativeProfile
from w2w.endpoints.role_execution import execute_periodic, ratio_sequence
from w2w.provenance import provenance
from w2w.service.guaranteed_service_exchange import contoured_geometry, ExposureFabric, Channels
from w2w.service.cost import CostModel
from w2w.service.evaluator import CandidateEvaluator
from w2w.synthesis.service_driven_fabric import paired_layout
from w2w.synthesis.role_interfaces import catalog, pareto, synthesize_pair_target
from w2w.theory.interfaces import pair_lane_bound


def run(output):
    if subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip():
        raise RuntimeError('Commit source before experiment')
    physical = contoured_geometry()
    pair_fabric = ExposureFabric(physical, tuple((0, 2, 3) for _ in range(BANKS)),
                                 Channels((8000, 0, 8000, 8000, 0)))
    _, matching = paired_layout(pair_fabric)
    pairs = matching['pairs']
    rng = np.random.default_rng(620100)
    scenarios = dict(single=[pairs[0][0]], one_pair=pairs[0], independent=[pairs[0][0], pairs[1][0]],
                     random9=sorted(rng.choice(36, 9, replace=False).tolist()), first9=list(range(9)), full=list(range(36)))
    designs = catalog(physical, pairs)
    rows = []
    for design in designs:
        evaluator = CandidateEvaluator(design)
        population = evaluator.population(9)
        replays = {name: evaluator.replay(active) for name, active in scenarios.items()}
        row = dict(id=design.name, structure=design.structure, endpoint=design.endpoint.record(),
                   home_fraction=str(design.home_fraction), layout_hash=design.layout.sha256,
                   frozen_shares=design.layout.shares, repeated_mask=design.exposure.mask,
                   cost=CostModel.evaluate(design), late_serializer_cost=CostModel.evaluate(design, 'port'),
                   composition=evaluator.composition, traces=evaluator.traces(), population=population,
                   mean=population['exact_mean_tb_s'], full=replays['full']['executed_tb_s'], replays=replays)
        rows.append(row)
        print(design.name, 'mean', round(row['mean'], 9), 'full', round(row['full'], 9),
              'lanes', row['cost']['export_lane_bits'], flush=True)
    budget = dict(export_lane_bits=18432, endpoint_storage_bits=49152)
    eligible = [r for r in rows if r['full'] >= 1 - 1e-9 and all(r['cost'][k] <= v for k, v in budget.items())]
    best = min(eligible, key=lambda r: (-round(r['mean'], 12), r['cost']['endpoint_storage_bits'], r['id']))
    selected_ids = ('k3_equal192_d2', 'k3_s128_matched', 'k3_s160_matched', 'k3_wide_direct')
    sensitivity = []
    finite = []
    for design in designs:
        if design.name not in selected_ids:
            continue
        for profile in (NativeProfile(), NativeProfile('alternate', (1, 0)), NativeProfile('burst4', (1, 1, 1, 1, 0, 0, 0, 0))):
            profiled = replace(design, endpoint=replace(design.endpoint, native=profile))
            evaluator = CandidateEvaluator(profiled)
            sensitivity.append(dict(id=design.name, profile=profile.name,
                                    mean=evaluator.population(9)['exact_mean_tb_s'],
                                    full=float(np.mean(evaluator.achieved_rates(range(36))[0])),
                                    traces=evaluator.traces(), native_mean=sum(profile.ready)/len(profile.ready)))
        seq = ratio_sequence(0, 1, design.home_fraction.numerator, design.home_fraction.denominator)
        for words in (1, 2, 3, 8, 13, 32, 128, 1024):
            home = sum(seq[i % len(seq)] == 0 for i in range(words))
            fraction = home / words
            h, s = design.endpoint.widths[0]/256, design.endpoint.widths[2]/256
            upper = min(h/fraction if fraction else float('inf'), s/(1-fraction) if fraction < 1 else float('inf'))
            finite.append(dict(id=design.name, words_per_bank=words, object_words=32*words,
                               home_words_per_bank=home, peer_words_per_bank=words-home,
                               home_fraction=fraction, error=fraction-float(design.home_fraction),
                               exclusive_fluid_upper=upper,
                               scope='Quantized object stripe capacity bound only; not finite-object completion execution'))
    diagnostic = []
    for depth in (1, 2):
        for profile in (NativeProfile(), NativeProfile('alternate', (1, 0))):
            diagnostic.append(execute_periodic(EndpointSpec((192,), (depth,), native=profile), (0,)))
    result = dict(provenance=provenance(), registration_sha256=hashlib.sha256(
                      Path('docs/methods/ROLE_INTERFACE_METHOD.md').read_bytes()).hexdigest(),
                  scope='Frozen design family, periodic digital service; no DRAM timing or PPA',
                  pairs=pairs, scenarios=scenarios, catalog=rows, budget=budget, selected=best['id'],
                  pareto=pareto(rows), sensitivity=sensitivity, finite_objects=finite,
                  native_ready_diagnostic=diagnostic,
                  restricted_pair_bound=dict(single=pair_lane_bound(18432), mean=1+(pair_lane_bound(18432)-1)*27/35,
                                             family='home<=native; identical banks; two equal shared directions; always-ready'),
                  inverse_design=[synthesize_pair_target('1.5'), synthesize_pair_target('1.625')])
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + '\n')
    print('VERIFIED', len(rows), 'designs;', len(rows)*len(scenarios)*3, 'LPs; selected', best['id'], flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    run(args.output)
