"""Audit matched receiver-capacity replays and keep RX cost in comparisons."""
import argparse
import csv
from dataclasses import asdict
import gzip
from hashlib import sha256
import json
from pathlib import Path

from w2w.analysis.service_provisioning import check_provisioning_bound, provisioning_certificate
from w2w.experiments.run_return_path_diagnostic import METHOD
from w2w.provenance import provenance
from w2w.service.cost import CostModel
from w2w.service.read_replay import ReadReplayConfig, design_record
from w2w.synthesis.provisioning_catalog import candidate_designs
from w2w.synthesis.provisioning_target import target_design
from w2w.synthesis.read_catalog import archived_cost_matches
from w2w.theory.return_path import packed_rx_requirement, return_path_period
from w2w.validation.patterns_replay import check_delivery, check_frozen_accounting
from w2w.validation.provisioning_holdout import audit_inputs, gain_retention, read_json
from w2w.validation.provisioning_target import audit as audit_target
from w2w.workloads.read_trace import digest, synthetic_read_suite


def audit(source, primary, extension, diagnostic):
    preceding = audit_target(source, primary, extension)
    inputs, traces = audit_inputs(source)
    folder = Path(diagnostic)
    summary = read_json(folder / 'summary.json')
    if (summary['provenance']['git_status'] or summary['registration_sha256'] != sha256(METHOD.read_bytes()).hexdigest()
            or summary['inputs_sha256'] != sha256((Path(source) / 'summary.json').read_bytes()).hexdigest()
            or summary['additional_manufactured_rx_payload_bits_per_memory'] != 24576):
        raise ValueError('Diagnostic provenance/input/cost mismatch')
    profiles = [dict(**return_path_period(w, d, r), full_packing_requirement=packed_rx_requirement(256, w, 1))
                for w, d in ((128, 1), (160, 2), (192, 2), (224, 2), (256, 1)) for r in (2, 3)]
    if digest(profiles) != digest(summary['profiles']):
        raise ValueError('Periodic return-path witness mismatch')
    for archived, rx in zip(summary['target_derivations'], (2, 3)):
        rebuilt = target_design(192, rx_depth=rx)[1]
        if (not archived_cost_matches(archived['cost'], rebuilt['cost'])
                or digest({k:v for k,v in archived.items() if k != 'cost'}) !=
                   digest({k:v for k,v in rebuilt.items() if k != 'cost'})):
            raise ValueError('RX-aware target selection mismatch')
    designs = dict(b_cfg=candidate_designs()[0]['b_cfg'], c_n192=target_design(192)[0])
    synthetics = {'synthetic_' + k:v for k,v in synthetic_read_suite(designs['b_cfg'].geometry.compute_xy).items()}
    expected = {(c, label, 192) for c in [*synthetics, *(c['id'] for c in inputs['cases'])] for label in designs}
    keys = [(r['case'], r['label'], r['window']) for r in summary['results']]
    if len(keys) != 32 or len(set(keys)) != 32 or set(keys) != expected or {tuple(k) for k in summary['jobs']} != expected:
        raise ValueError('Diagnostic coverage mismatch')
    low, combined = {}, []
    for path in (primary, extension):
        for r in read_json(Path(path) / 'summary.json')['results']:
            if r['window'] == 192:
                low[r['case'], r['label']] = read_json(Path(path) / r['path'])
                if not r['case'].startswith('synthetic_'):
                    combined.append(dict(r, rx_depth=2))
    # The earlier synthetic B/reference executions have already been archived.
    with gzip.open('artifacts/results/workload/service_provisioning/replays.jsonl.gz', 'rt') as stream:
        for line in stream:
            r = json.loads(line)
            if r['replay']['config']['outstanding_words_per_compute'] == 192:
                low['synthetic_' + r['case'], r['label']] = r['replay']
    words, effects, synthetic_metrics = 0, [], []
    for item in summary['results']:
        case, label = item['case'], item['label']
        path = folder / item['path']
        raw = path.read_bytes()
        if (item['path'] != f'{case}/{label}_n192.json.gz' or len(raw) != item['file_bytes']
                or sha256(raw).hexdigest() != item['file_sha256']):
            raise ValueError('Diagnostic raw output mismatch')
        row = read_json(path)
        trace = synthetics[case] if case in synthetics else traces[case, 'trained']
        cfg = ReadReplayConfig(outstanding_words_per_compute=192, rx_depth_words=3,
                              max_trace_words=80000000, max_slots=500000)
        selected = designs[label]
        if (digest(row['config']) != digest(asdict(cfg)) or digest(row['design']) != digest(design_record(selected))
                or not archived_cost_matches(CostModel.evaluate(selected), row['cost'])):
            raise ValueError('Diagnostic design/config/cost mismatch')
        cert = provisioning_certificate(selected, trace, cfg)
        check_delivery(trace, row)
        check_frozen_accounting(cert['word_certificate'], row, trace.word_bytes)
        if digest(check_provisioning_bound(cert, row)) != digest(row['provisioning_bound']):
            raise ValueError('Diagnostic completion bound mismatch')
        for field in ('trace_sha256', 'design_sha256', 'residence_sha256', 'makespan_slots',
                      'logical_bytes', 'audit', 'delivery_sha256', 'cost', 'provisioning_bound', 'wall_seconds'):
            if digest(item[field]) != digest(row[field]):
                raise ValueError('Diagnostic compact/raw mismatch')
        baseline = low[case, label]
        for field in ('trace_sha256', 'design_sha256', 'residence_sha256', 'logical_bytes'):
            if row[field] != baseline[field]:
                raise ValueError('RX change changed task/residency/hardware identity')
        ignored = ('rx_depth_words', 'max_slots', 'max_trace_words')
        if ({k:v for k,v in row['config'].items() if k not in ignored} !=
                {k:v for k,v in baseline['config'].items() if k not in ignored}):
            raise ValueError('RX comparison changed another execution parameter')
        words += row['audit']['delivered_words']
        effect = dict(case=case, label=label, rx2_slots=baseline['makespan_slots'], rx3_slots=row['makespan_slots'],
                      speedup_from_rx3=baseline['makespan_slots']/row['makespan_slots'])
        effects.append(effect)
        if case in synthetics:
            home, wide = (low[case, k]['makespan_slots'] for k in ('home', 'wide'))
            synthetic_metrics.append(dict(effect, home_slots=home, wide_slots=wide,
                retained_wide_gain=gain_retention(home, wide, row['makespan_slots'])))
        else:
            combined.append(dict(item, label=label+'_rx3', rx_depth=3))
    if words != summary['delivered_words']:
        raise ValueError('Diagnostic word total mismatch')
    metrics, frontiers = [], {}
    axes = ('export_lane_bits', 'endpoint_storage_bits', 'access_wire_bit_mm',
            'pipeline_register_bits', 'fixed_sequence_control_bits', 'bank_port_connections')
    for case in inputs['cases']:
        name = case['id']
        home, wide = (low[name, k]['makespan_slots'] for k in ('home', 'wide'))
        vectors = {}
        for r in (r for r in combined if r['case'] == name):
            rx_bits = r['cost']['bank_port_connections'] * 256 * r['rx_depth']
            metrics.append(dict(case=name, label=r['label'], makespan_slots=r['makespan_slots'],
                speedup_over_home=home/r['makespan_slots'],
                retained_wide_gain=gain_retention(home, wide, r['makespan_slots']),
                rx_payload_bits_per_memory=rx_bits,
                tx_plus_rx_payload_proxy_bits=r['cost']['endpoint_storage_bits']+rx_bits,
                **{k:r['cost'][k] for k in axes}))
            vectors[r['label']] = (r['makespan_slots'], rx_bits, *(r['cost'][k] for k in axes))
        frontiers[name] = [k for k,v in sorted(vectors.items()) if not any(
            all(a<=b for a,b in zip(u,v)) and any(a<b for a,b in zip(u,v))
            for j,u in vectors.items() if j!=k)]
    owners = []
    old = read_json(Path(primary) / 'summary.json')['results']
    for case in inputs['cases']:
        t = {r['label']:r['makespan_slots'] for r in old if r['case']==case['id'] and r['window']==128}
        owners.append(dict(case=case['id'], trained_home_slots=t['home'], modulo_home_slots=t['home_mod'],
                           trained_speedup_over_modulo=t['home_mod']/t['home']))
    return dict(verified=True, audit_provenance=provenance(), source_commit=summary['provenance']['commit'],
        diagnostic_replays=32, diagnostic_delivered_words=words, total_new_replays=166,
        total_delivered_words=words+preceding['extension_delivered_words']+preceding['primary_audit']['delivered_words'],
        preceding_audit={k:v for k,v in preceding.items() if k not in ('metrics','frontiers')},
        profiles=profiles, metrics=metrics, receiver_effects=effects, synthetic_metrics=synthetic_metrics,
        owner_controls=owners, frontiers_with_rx_payload=frontiers,
        scope='Same-input RX causal diagnostic; finite read stage, manufacturing-direction payload proxy, no RX PPA')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('source','primary','extension','diagnostic','output'):
        p.add_argument('--'+name, required=True)
    args = p.parse_args()
    result = audit(args.source, args.primary, args.extension, args.diagnostic)
    Path(args.output).write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    for key in ('metrics','receiver_effects','synthetic_metrics','owner_controls'):
        with Path(args.output).with_name(key+'.csv').open('w', newline='') as stream:
            w = csv.DictWriter(stream, fieldnames=list(result[key][0]), lineterminator='\n')
            w.writeheader()
            w.writerows(result[key])
    print(json.dumps({k:result[k] for k in ('verified','source_commit','total_new_replays','total_delivered_words')}))
