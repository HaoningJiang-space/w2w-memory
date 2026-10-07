"""Audit the target extension and compare paired N192 benefit and resource costs."""
import argparse
import csv
from dataclasses import asdict, replace
from hashlib import sha256
import json
from pathlib import Path

from w2w.analysis.service_provisioning import check_provisioning_bound, provisioning_certificate
from w2w.experiments.run_provisioning_target import METHOD
from w2w.experiments.run_service_provisioning import EQUAL_FIELDS
from w2w.service.cost import CostModel
from w2w.service.read_replay import ReadReplayConfig, design_record
from w2w.synthesis.provisioning_catalog import candidate_designs
from w2w.synthesis.provisioning_target import target_design
from w2w.synthesis.read_catalog import archived_cost_matches
from w2w.validation.patterns_replay import check_delivery, check_frozen_accounting
from w2w.validation.provisioning_holdout import audit as audit_primary, audit_inputs, frontier, gain_retention, read_json
from w2w.workloads.read_trace import ReadTrace, digest, synthetic_read_suite


def audit(source, primary, extension):
    primary_audit = audit_primary(source, primary)
    inputs, traces = audit_inputs(source)
    folder = Path(extension)
    summary = read_json(folder / 'summary.json')
    if (summary['provenance']['git_status'] or summary['registration_sha256'] != sha256(METHOD.read_bytes()).hexdigest()
            or summary['inputs_sha256'] != sha256((Path(source) / 'summary.json').read_bytes()).hexdigest()):
        raise ValueError('Extension provenance/input mismatch')
    plans = [target_design(n)[1] for n in (128, 160, 192)]
    if len(summary['derivations']) != len(plans):
        raise ValueError('Missing inverse selection certificate')
    for archived, rebuilt in zip(summary['derivations'], plans):
        if (not archived_cost_matches(rebuilt['cost'], archived['cost'])
                or {k: v for k, v in archived.items() if k != 'cost'} != {k: v for k, v in rebuilt.items() if k != 'cost'}):
            raise ValueError('Inverse selection certificate mismatch')
    design, _ = target_design(192)
    duplicated = replace(design, name=design.name + '_duplicated', shared_directions=(),
        endpoint=replace(design.endpoint, shared_fifo_ports=(), shared_serializer=False))
    designs = dict(candidate_designs()[0], c_n192=design, c_n192_dup=duplicated)
    synthetics = {'synthetic_' + k: v for k, v in synthetic_read_suite(design.geometry.compute_xy).items()}
    expected = {(c['id'], 'c_n192', 192) for c in inputs['cases']}
    expected.update((c['id'], label, 192) for c in inputs['cases'] if c['batch_size'] != 1
                    for label in ('home', 'k2', 'wide', 'b_cfg'))
    expected.update((case, label, 192) for case in synthetics for label in ('c_n192', 'c_n192_dup'))
    keys = [(r['case'], r['label'], r['window']) for r in summary['results']]
    if (len(keys) != 47 or len(set(keys)) != 47 or set(keys) != expected
            or {tuple(k) for k in summary['jobs']} != expected):
        raise ValueError('Extension coverage mismatch')
    observed, words = {}, 0
    for item in summary['results']:
        case, label, window = item['case'], item['label'], item['window']
        path = folder / item['path']
        raw = path.read_bytes()
        if (item['path'] != f'{case}/{label}_n192.json.gz' or len(raw) != item['file_bytes']
                or sha256(raw).hexdigest() != item['file_sha256']):
            raise ValueError('Extension raw output mismatch')
        row = read_json(path)
        trace = synthetics[case] if case in synthetics else traces[case, 'trained']
        cfg = ReadReplayConfig(outstanding_words_per_compute=192, max_trace_words=80000000, max_slots=500000)
        selected = designs[label]
        if (digest(row['config']) != digest(asdict(cfg)) or digest(row['design']) != digest(design_record(selected))
                or not archived_cost_matches(CostModel.evaluate(selected), row['cost'])):
            raise ValueError('Extension uses a different design/config/cost')
        cert = provisioning_certificate(selected, trace, cfg)
        check_delivery(trace, row)
        check_frozen_accounting(cert['word_certificate'], row, trace.word_bytes)
        bound = check_provisioning_bound(cert, row)
        if digest(bound) != digest(row['provisioning_bound']):
            raise ValueError('Extension completion bound mismatch')
        for field in ('trace_sha256', 'design_sha256', 'residence_sha256', 'makespan_slots',
                      'logical_bytes', 'audit', 'delivery_sha256', 'cost', 'provisioning_bound', 'wall_seconds'):
            if digest(item[field]) != digest(row[field]):
                raise ValueError('Extension compact row differs from raw replay')
        observed[case, label, window] = row
        words += row['audit']['delivered_words']
    if words != summary['delivered_words']:
        raise ValueError('Extension word total mismatch')
    if len(summary['ablations']) != 7 or {r['case'] for r in summary['ablations']} != set(synthetics):
        raise ValueError('Missing implementation ablation')
    for case in synthetics:
        for field in EQUAL_FIELDS:
            if observed[case, 'c_n192', 192][field] != observed[case, 'c_n192_dup', 192][field]:
                raise ValueError('192-bit implementation changes delivered service')
        if not next(r for r in summary['ablations'] if r['case'] == case)['equal']:
            raise ValueError('Failed recorded implementation ablation')
    previous = read_json(Path(primary) / 'summary.json')
    combined = previous['results'] + [r for r in summary['results'] if r['case'] not in synthetics]
    indexed = {(r['case'], r['label'], r['window']): r for r in combined}
    if len(indexed) != len(combined):
        raise ValueError('Extension repeats an already executed comparison')
    metrics = []
    for case in inputs['cases']:
        name = case['id']
        home, wide = (indexed[name, label, 192]['makespan_slots'] for label in ('home', 'wide'))
        for label in ('home', 'k2', 'wide', 'b_cfg', 'c_n192'):
            row = indexed[name, label, 192]
            t = row['makespan_slots']
            retention = gain_retention(home, wide, t)
            metrics.append(dict(case=name, label=label, window=192, makespan_slots=t,
                speedup_over_home=home/t, retained_wide_gain=retention,
                meets_75pct_gain=None if retention is None else retention >= .75,
                lower_slots=row['provisioning_bound']['lower_slots'], gap_slots=t-row['provisioning_bound']['lower_slots']))
    return dict(verified=True, source_commit=summary['provenance']['commit'], extension_replays=47,
        real_replays=33, implementation_ablations=7, extension_delivered_words=words,
        primary_audit={k: v for k, v in primary_audit.items() if k not in ('metrics', 'frontiers')},
        combined_real_replays=len(combined), metrics=metrics,
        frontiers={c['id']: frontier([r for r in combined if r['case'] == c['id'] and r['label'] != 'home_mod'])
                   for c in inputs['cases']},
        scope='Paired extension on the same held-out requests; same static pair reference, not full dynamic pooling')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--primary', required=True)
    parser.add_argument('--extension', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = audit(args.source, args.primary, args.extension)
    Path(args.output).write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    with Path(args.output).with_suffix('.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(result['metrics'][0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(result['metrics'])
    print(json.dumps({k: v for k, v in result.items() if k not in ('metrics', 'frontiers')}))
