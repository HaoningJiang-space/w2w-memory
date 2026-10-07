"""One-factor configurable shared-egress comparison, using archived A/B layouts."""
import argparse
from collections import Counter
from dataclasses import replace
from fractions import Fraction
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import time
import numpy as np
from w2w.domain import EndpointSpec
from w2w.endpoints.role_execution import execute_periodic
from w2w.provenance import provenance
from w2w.service.cost import CostModel
from w2w.service.evaluator import CandidateEvaluator
from w2w.service.guaranteed_service_exchange import contoured_geometry
from w2w.synthesis.role_interfaces import make_candidate, static_shared_fifo, clustered_windows


def run(source, output):
    if subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip():
        raise RuntimeError('Commit source before experiment')
    started = time.monotonic()
    raw = Path(source).read_bytes()
    archived = json.loads(gzip.decompress(raw) if str(source).endswith('.gz') else raw)
    physical = contoured_geometry()
    prefix = 'k3_23_random9_maxweight_'
    a_id, b_id = prefix+'h256s128_d11_buffered', prefix+'h256s160_d12_buffered'
    identifiers = ('home_h256s0_d00_direct', 'k2_23_h256s256_d00_direct',
                   prefix+'h256s256_d00_direct', a_id, b_id)
    old_rows = {r['id']: r for r in archived['search']['catalog']}
    designs = []
    for name in identifiers:
        row = old_rows[name]
        spec = EndpointSpec(**{k: v for k, v in row['endpoint'].items() if k != 'native'})
        design = make_candidate(physical, row['pairs'], name, row['structure'], spec,
                                Fraction(row['home_fraction']), row['directions'], allow_unmatched=True)
        assert design.layout.sha256 == row['layout_hash']
        designs.append(design)
    designs.extend(static_shared_fifo(d) for d in list(designs) if d.name in (a_id, b_id))
    evaluators = {d.name: CandidateEvaluator(d) for d in designs}
    k2 = evaluators[identifiers[1]]
    private = [c for c in range(k2.f.nc) if any(
        k2.owners[int(b)] == (c,) for b in np.flatnonzero(k2.layout.shares[c]))]
    interior = [c for c in range(k2.f.nc) if c not in private]
    population_groups = dict(with_private_bank=private, without_private_bank=interior)
    reference = archived['verified'][old_rows[a_id]['verification_id']]
    scenarios = dict(full=list(range(36)), single=[0], one_pair=old_rows[a_id]['pairs'][0],
                     random9=reference['replays']['random9']['active'], first9=list(range(9)))
    scenarios.update({f'cluster{i}': list(a) for i, a in enumerate(clustered_windows())})
    results = []
    for d in designs:
        e = evaluators[d.name]
        population = e.population(9)
        replays = {name: e.replay(active) for name, active in scenarios.items()}
        scores = dict(random9=population['exact_mean_tb_s'],
                      clustered9=float(np.mean([replays[f'cluster{i}']['executed_tb_s'] for i in range(16)])))
        cost = CostModel.evaluate(d)
        if d.name in old_rows:
            for key, value in old_rows[d.name]['cost'].items():
                assert cost[key] == value, (d.name, key)
            for w in scores:
                assert abs(scores[w] - old_rows[d.name]['scores'][w]) < 1e-12
        row = dict(id=d.name, endpoint=d.endpoint.record(), shared_directions=list(d.shared_directions),
                   configured_direction_counts=dict(Counter(d.shared_directions)),
                   home_fraction=str(d.home_fraction), layout_hash=d.layout.sha256,
                   scores=scores, cost=cost, full=replays['full']['executed_tb_s'],
                   composition=e.composition, population=population,
                   population_group_means={name: float(np.mean([population['clients'][c]['mean'] for c in clients]))
                                           for name, clients in population_groups.items()},
                   replays=replays, traces=e.traces())
        results.append(row)
        print('DESIGN', d.name, scores, 'endpoint bits', cost['endpoint_storage_bits'], flush=True)
    by_id = {r['id']: r for r in results}
    trace_comparisons = []
    reductions = []
    unchanged_costs = ('bank_port_connections', 'export_lane_bits', 'pipeline_register_bits',
                       'wire_mm', 'access_wire_bit_mm', 'configured_hb_signal_bits',
                       'configured_hb_tb_s', 'port_bits', 'fixed_sequence_control_bits',
                       'selector_input_bits', 'serializer_instances')
    for name in (a_id, b_id):
        old, new = by_id[name], by_id[name+'_static_fifo']
        assert old['layout_hash'] == new['layout_hash']
        assert old['scores'] == new['scores']
        for scenario in scenarios:
            for key in ('served_tb_s', 'common_tb_s', 'executed_tb_s', 'fluid_upper_tb_s'):
                assert np.allclose(old['replays'][scenario][key], new['replays'][scenario][key], atol=1e-12, rtol=0)
        for key in unchanged_costs:
            assert old['cost'][key] == new['cost'][key], key
        before_by_sequence = {tuple(t['sequence']): t for t in old['traces']}
        for after in new['traces']:
            before = before_by_sequence[tuple(after['sequence'])]
            for key in ('transient_slots', 'period_slots', 'delivered_words', 'sent_bits',
                        'peak_words', 'backpressure_slots', 'ready_opportunities'):
                assert before[key] == after[key], key
            assert before['boundary_state'][:3] == after['boundary_state'][:3]
            for i, ports in enumerate(after['queue_port_groups']):
                p = after['selected_shared_port'] if len(ports) > 1 else ports[0]
                assert after['boundary_state'][3][i] == before['boundary_state'][3][p]
            assert after['physical_fifo_count'] == 2
            trace_comparisons.append(dict(baseline=name, sequence=after['sequence'],
                                          selected_shared_port=after['selected_shared_port'],
                                          period_metrics_equal=True, boundary_projection_equal=True))
        saved = old['cost']['endpoint_storage_bits'] - new['cost']['endpoint_storage_bits']
        reductions.append(dict(baseline=name, configurable=new['id'], saved_endpoint_bits=saved,
                               endpoint_reduction=saved/old['cost']['endpoint_storage_bits'],
                               endpoint_plus_pipeline_reduction=saved/(old['cost']['endpoint_storage_bits']+
                                                                      old['cost']['pipeline_register_bits']),
                               unchanged_cost_keys=list(unchanged_costs),
                               full_cost_dominance_claimed=False))
    old_spec = evaluators[b_id].spec
    new_spec = evaluators[b_id+'_static_fifo'].spec
    independent = execute_periodic(old_spec, (2, 3))
    collapsed = execute_periodic(old_spec, (2,))
    try:
        execute_periodic(new_spec, (2, 3), selected_shared_port=2)
    except ValueError as exc:
        rejected = str(exc)
    else:
        raise RuntimeError('Simultaneous directions were incorrectly admitted')
    assert independent['total_per_native'] == 1 and collapsed['total_per_native'] == .625
    p1, p2 = Fraction(27, 35), Fraction(27*26, 35*34)
    assert len(private) == 16 and len(interior) == 20
    assert abs(by_id[identifiers[1]]['population_group_means']['without_private_bank'] - float(1+p2)) < 1e-12
    result = dict(provenance=provenance(), input_path=str(source), input_sha256=hashlib.sha256(raw).hexdigest(),
                  input_experiment_commit=archived['provenance']['commit'],
                  registration_sha256=hashlib.sha256(Path('docs/methods/STATIC_SHARED_FIFO.md').read_bytes()).hexdigest(),
                  scope='One-factor bank-local FIFO reuse with frozen direction; serializers and physical routes retained; no RTL/PPA',
                  scenarios=scenarios, population_groups=population_groups, designs=results,
                  reductions=reductions, trace_comparisons=trace_comparisons,
                  counterexample=dict(independent=independent, incorrect_collapse=collapsed,
                                      configurable_rejected=rejected),
                  k2_decomposition=dict(p_one_idle=str(p1), p_two_idle=str(p2),
                      multiple_partner_gap=float(p1-p2), private_coverage_term=float(Fraction(16,36)*p2),
                      total_gap_to_k3_direct=float(p1-Fraction(20,36)*p2),
                      scope='Algebraic terms of current registered constructions, not free boundary repair'),
                  verification=dict(designs=len(results), lp_solves=sum(p['lp_solves'] for r in results for p in r['replays'].values()),
                      max_resource_residual=max(max(p['witness_residual'],p['lp_residual']) for r in results for p in r['replays'].values()),
                      actual_sequence_classes=sum(len(by_id[name]['traces']) for name in (a_id,b_id)),
                      configured_trace_comparisons=len(trace_comparisons), all_service_equal=True,
                      original_baselines_match_archive=True), elapsed_seconds=time.monotonic()-started)
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, indent=2)+'\n')
    print('VERIFIED', result['verification'], 'seconds', result['elapsed_seconds'], flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default='artifacts/results/endpoint/architecture_competition.json.gz')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    run(args.input, args.output)
