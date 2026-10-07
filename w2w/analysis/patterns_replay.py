"""Audit the registered full-size routing replays and report paired read times."""
import argparse
import csv
from dataclasses import asdict
import gzip
from hashlib import sha256
import json
import math
from pathlib import Path

from w2w.analysis.request_window import check_bound, completion_lower_bound, window_certificate
from w2w.experiments.run_read_workload import load_designs
from w2w.service.cost import CostModel
from w2w.service.read_replay import ReadReplayConfig
from w2w.workloads.patterns_trace import compile_patterns_window
from w2w.workloads.read_trace import ReadTrace


def expected_keys(plan):
    return {(f"{g['id']}_b{b}", i, n)
            for g in plan['groups'] for b in plan['batch_sizes']
            for i in plan['design_indices']
            for n in ([plan['primary_outstanding'], plan['control_outstanding']]
                      if g['id'] in plan['control_groups'] else [plan['primary_outstanding']])}


def check_coverage(plan, rows):
    keys = [(r['case'], r['design_index'], r['window']) for r in rows]
    if len(set(keys)) != len(keys) or set(keys) != expected_keys(plan):
        raise ValueError('Missing, duplicate or unregistered replay')


def check_delivery(trace, row):
    words = sum(r.size_bytes for t in trace.tasks for r in t.reads) // trace.word_bytes
    audit = row['audit']
    if any(audit[k] != words for k in ('issued_words', 'admitted_words',
                                     'transmitted_words', 'delivered_words')):
        raise ValueError('Incomplete word delivery')
    bits = words * trace.word_bytes * 8
    if (row['logical_bytes'] != words * trace.word_bytes or audit['sent_bits'] != bits
            or sum(r['sent_bits'] for r in row['routes']) != bits
            or sum(r['received_words'] for r in row['routes']) != words
            or sum(row['native_words_by_bank'].values()) != words):
        raise ValueError('Byte/route/native conservation mismatch')
    if not audit['every_slot_conserved'] or not audit['frozen_residence']:
        raise ValueError('Missing per-slot or frozen-residence certificate')
    tasks = {t['id']: t for t in row['tasks']}
    if set(tasks) != {t.id for t in trace.tasks} or len(tasks) != len(row['tasks']):
        raise ValueError('Task coverage mismatch')
    for task in trace.tasks:
        if tasks[task.id]['logical_bytes'] != sum(r.size_bytes for r in task.reads):
            raise ValueError('Task bytes mismatch')


def audit(source, plan_path, verify_inputs=False):
    source, plan_path = Path(source), Path(plan_path)
    summary = json.loads((source / 'summary.json').read_text())
    plan_raw = plan_path.read_bytes()
    plan = json.loads(plan_raw)
    if (summary['plan'] != plan or summary['plan_sha256'] != sha256(plan_raw).hexdigest()
            or summary['source_dirty']):
        raise ValueError('Registered plan or source provenance mismatch')
    rows = summary['results']
    check_coverage(plan, rows)
    if summary['replay_count'] != len(rows):
        raise ValueError('Summary count mismatch')
    groups = {g['id']: g for g in plan['groups']}
    request_ids = [r for g in groups.values() for r in g['requests']]
    if len(set(request_ids)) != len(request_ids):
        raise ValueError('Groups reuse source requests')
    cases = {c['id']: c for c in summary['cases']}
    if (len(cases) != len(summary['cases']) or set(cases) != {k[0] for k in expected_keys(plan)}):
        raise ValueError('Case coverage mismatch')
    designs = load_designs()[0]
    traces, records = {}, {}
    for name, case in cases.items():
        group = groups[case['group']]
        if (case['request_ids'] != group['requests'][:case['batch_size']]
                or case['layer'] != group['layer'] or case['decode_step'] != group['decode_step']):
            raise ValueError('Registered cohort/layer/step mismatch')
        trace = ReadTrace.from_record(json.loads((source / name / 'trace.json').read_text()))
        demand = json.loads((source / name / 'demand.json').read_text())
        if trace.sha256 != case['trace_sha256'] or trace.evidence != 'captured':
            raise ValueError('Captured trace identity mismatch')
        if (demand['trace_sha256'] != trace.sha256
                or demand['total_logical_read_bytes'] != case['read_bytes']
                or demand['windows'][0]['activated_experts'] != case['activated_experts']):
            raise ValueError('Compiled demand mismatch')
        if verify_inputs:
            spec = json.loads((source / name / 'spec.json').read_text())
            rebuilt, rebuilt_demand = compile_patterns_window(source / name / 'manifest.json',
                                                              spec, case['decode_step'])
            if rebuilt.sha256 != trace.sha256 or rebuilt_demand != demand:
                raise ValueError('Recompiled raw routing differs')
        traces[name] = trace
    for item in rows:
        key = (item['case'], item['design_index'], item['window'])
        expected_path = f'{key[0]}/design{key[1]}_n{key[2]}.json.gz'
        if item['path'] != expected_path:
            raise ValueError('Unexpected artifact path')
        raw = (source / expected_path).read_bytes()
        if len(raw) != item['file_bytes'] or sha256(raw).hexdigest() != item['file_sha256']:
            raise ValueError('Replay file integrity mismatch')
        row = json.loads(gzip.decompress(raw))
        for field in ('id', 'trace_sha256', 'design_sha256', 'residence_sha256',
                      'logical_bytes', 'makespan_slots', 'delivery_sha256', 'audit',
                      'stalls', 'cost', 'lower_bound', 'wall_seconds'):
            if row[field] != item[field]:
                raise ValueError('Summary/replay disagreement: ' + field)
        trace, design = traces[key[0]], designs[key[1]]
        config = ReadReplayConfig(outstanding_words_per_compute=key[2],
            max_trace_words=plan['max_trace_words'], max_slots=plan['max_slots'])
        if row['config'] != asdict(config):
            raise ValueError('Replay configuration differs from protocol')
        check_delivery(trace, row)
        certificate = window_certificate(design, trace, config)
        check_bound(certificate, row)
        lower = dict(with_credit=completion_lower_bound(certificate, key[2]),
                     independent=completion_lower_bound(certificate))
        if row['lower_bound'] != lower:
            raise ValueError('Necessary bound mismatch')
        cost = CostModel.evaluate(design)
        if cost.keys() != row['cost'].keys():
            raise ValueError('Cost fields mismatch')
        for field, value in cost.items():
            observed = row['cost'][field]
            same = (math.isclose(value, observed, rel_tol=1e-12, abs_tol=1e-8)
                    if field in ('wire_mm', 'access_wire_bit_mm') else value == observed)
            if not same:
                raise ValueError('Cost ledger mismatch: ' + field)
        records[key] = row
    for name in cases:
        for index in plan['design_indices']:
            identities = {r['residence_sha256'] for k, r in records.items()
                          if k[0] == name and k[1] == index}
            if len(identities) != 1:
                raise ValueError('Request window changed residency')
    delivered = sum(r['audit']['delivered_words'] for r in records.values())
    if delivered != summary['delivered_words']:
        raise ValueError('Total word count mismatch')
    table = []
    for key, row in sorted(records.items()):
        name, index, credit = key
        case = cases[name]
        home = records[name, 0, credit]['makespan_slots']
        table.append(dict(case=name, group=case['group'], batch_size=case['batch_size'],
            layer=case['layer'], decode_step=case['decode_step'], experts=len(case['activated_experts']),
            read_bytes=case['read_bytes'], design_index=index, design=row['id'], outstanding=credit,
            makespan_slots=row['makespan_slots'], home_relative_ratio=home / row['makespan_slots'],
            lower_bound_slots=row['lower_bound']['with_credit'],
            export_lane_bits=row['cost']['export_lane_bits'],
            endpoint_storage_bits=row['cost']['endpoint_storage_bits'],
            access_wire_bit_mm=row['cost']['access_wire_bit_mm']))
    return dict(source_commit=summary['source_commit'], replay_count=len(rows), cases=len(cases),
        delivered_words=delivered, raw_input_recompiled=verify_inputs,
        scope='Full modeled expert-weight read stages; no inference latency claim; no population CI',
        rows=table)


def render(report, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'audit.json').write_text(json.dumps(report, indent=2) + '\n')
    with (output / 'replays.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(report['rows'][0]))
        writer.writeheader()
        writer.writerows(report['rows'])
    primary = max(r['outstanding'] for r in report['rows'])
    groups = sorted({r['group'] for r in report['rows']})
    fig, axes = plt.subplots(1, len(groups), figsize=(11.5, 3.6), constrained_layout=True,
                            squeeze=False)
    names = {0: 'Home', 1: 'k2 direct', 2: 'k3 direct', 6: 'Configurable B'}
    for ax, group in zip(axes[0], groups):
        for index, label in names.items():
            rows = sorted((r for r in report['rows'] if r['group'] == group and
                           r['design_index'] == index and r['outstanding'] == primary),
                          key=lambda r: r['batch_size'])
            ax.plot([r['batch_size'] for r in rows], [r['home_relative_ratio'] for r in rows],
                    'o-', label=label, markersize=4)
        ax.set(xscale='log', xlabel='Fixed decode cohort', ylabel='Home / design read time',
               title=f"{group}: layer {rows[0]['layer']}, step {rows[0]['decode_step']}")
        ax.set_xticks([1, 4, 16], ['1', '4', '16'])
        ax.grid(alpha=.2)
        ax.legend(fontsize=8)
    fig.savefig(output / 'read_completion.svg')
    fig.savefig(output / 'read_completion.png', dpi=160)
    plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--plan', default='artifacts/provenance/patterns_replay/plan.json')
    parser.add_argument('--verify-inputs', action='store_true')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    report = audit(args.source, args.plan, args.verify_inputs)
    render(report, args.output)
    print(json.dumps({k: v for k, v in report.items() if k != 'rows'}))
