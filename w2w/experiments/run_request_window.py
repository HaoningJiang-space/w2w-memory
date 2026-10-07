"""Find certified minimum request windows for existing frozen finite tasks."""
import argparse
from dataclasses import replace
from fractions import Fraction
import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import time

from w2w.analysis.read_completion import completion_metrics
from w2w.analysis.request_window import (check_bound, completion_lower_bound,
    rate_window_lower_bound, request_cost_frontier, scan_minimum_window, window_certificate)
from w2w.synthesis.read_catalog import load_designs
from w2w.provenance import provenance
from w2w.service.cost import CostModel
from w2w.service.read_replay import ReadReplayConfig, replay_reads
from w2w.workloads.read_trace import ReadTrace, synthetic_read_suite


METHOD = Path('docs/methods/REQUEST_WINDOW_STUDY.md')
ARCHIVE = Path('artifacts/results/workload/finite_read')
SEARCH_CASES = ('dispersed9', 'clustered9', 'full36')
LABELS = ('home', 'k2', 'wide', 'a_dup', 'b_dup', 'a_cfg', 'b_cfg')
EQUAL_FIELDS = ('trace_sha256', 'residence_sha256', 'config', 'makespan_slots', 'tasks',
                'routes', 'audit', 'delivery_sha256', 'stalls', 'native_words_by_bank',
                'peak_outstanding_words')


def encoded(value):
    return (json.dumps(value, separators=(',', ':'), allow_nan=False) + '\n').encode()


def read_archive():
    raw_summary = (ARCHIVE / 'summary.json').read_bytes()
    summary = json.loads(raw_summary)
    cases, hashes = {}, []
    for record in summary['artifacts']:
        raw = (ARCHIVE / record['path']).read_bytes()
        if sha256(raw).hexdigest() != record['sha256']:
            raise ValueError('Input archive hash mismatch')
        cases[record['case'], record['control']] = json.loads(gzip.decompress(raw))
        hashes.append(record)
    return cases, dict(summary_sha256=sha256(raw_summary).hexdigest(), artifacts=hashes,
                       source_commit=summary['provenance']['commit'])


def run(output):
    if subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip():
        raise RuntimeError('Commit source and run in a clean isolated checkout')
    started = time.monotonic()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    raw_path = output / 'replays.jsonl.gz'
    if raw_path.exists():
        raise ValueError('Output already contains a replay archive; use a new directory')
    designs, catalog = load_designs()
    archived, archive_identity = read_archive()
    traces = synthetic_read_suite(designs[0].geometry.compute_xy)
    for name, trace in traces.items():
        if trace.sha256 != ReadTrace.from_record(archived[name, 'base']['trace']).sha256:
            raise ValueError('Registered task changed')
    base = ReadReplayConfig()
    certificates, cache, records, ablations = {}, {}, [], []
    baseline_matches = []
    costs = {d.name: CostModel.evaluate(d) for d in designs}
    stream_file = raw_path.open('wb')
    stream = gzip.GzipFile(fileobj=stream_file, mode='wb', mtime=0)

    def evaluate(case, index, window):
        key = (case, index, window)
        if key in cache:
            return cache[key]
        design, trace = designs[index], traces[case]
        cert_key = (case, index)
        if cert_key not in certificates:
            certificates[cert_key] = window_certificate(design, trace, base)
        config = replace(base, outstanding_words_per_compute=window)
        row = replay_reads(design, trace, config)
        check_bound(certificates[cert_key], row)
        row.update(id=design.name, cost=costs[design.name], completion=completion_metrics(trace, row))
        row['request_cost'] = dict(entries_per_compute=window, manufactured_compute_count=36,
                                   entries_per_wafer=36 * window, delta_entries_per_compute_vs_128=window - 128,
                                   metadata_bits_per_entry=None, metadata_logic_area=None,
                                   scope='Request tracking capacity, not payload bits or calibrated logic area')
        row['additional_model_resources'] = dict(
            rx_payload_bits_per_memory=row['cost']['bank_port_connections'] * base.rx_depth_words * 256,
            request_path_area=None, physical_support_area=None)
        # Normalize integer bank keys and tuples before comparing with JSON archives.
        row = json.loads(encoded(row))
        payload = encoded(dict(case=case, label=LABELS[index], window=window, replay=row))
        stream.write(payload)
        fields = ('id', 'trace_sha256', 'design_sha256', 'residence_sha256', 'makespan_slots',
                  'delivery_sha256', 'audit', 'stalls', 'completion', 'request_cost')
        records.append(dict(sequence=len(records), case=case, label=LABELS[index], window=window,
                            uncompressed_record_sha256=sha256(payload).hexdigest(),
                            completion_lower_bound=completion_lower_bound(certificates[cert_key], window),
                            **{k: row[k] for k in fields}))
        # Large design/residence tables are retained in the raw archive, not duplicated in RAM.
        cache[key] = {k: v for k, v in row.items() if k not in ('design', 'residence', 'composition')}
        print('REPLAY', case, LABELS[index], 'N', window, 'slots', row['makespan_slots'], flush=True)
        return cache[key]

    def compare_implementation(case, index, window):
        a, b = evaluate(case, index, window), evaluate(case, index + 2, window)
        if any(a[k] != b[k] for k in EQUAL_FIELDS):
            raise ValueError('Duplicated/configurable service differs')
        record = dict(case=case, duplicated=LABELS[index], configurable=LABELS[index + 2],
                      window=window, fields=list(EQUAL_FIELDS), equal=True)
        if record not in ablations:
            ablations.append(record)

    try:
        # Recheck the two known controls against immutable existing evidence first.
        for case in SEARCH_CASES:
            for control, window in (('base', 128), ('credits512', 512)):
                old = {r['id']: r for r in archived[case, control]['results']}
                for index, design in enumerate(designs):
                    row = evaluate(case, index, window)
                    if any(row[k] != old[design.name][k] for k in (*EQUAL_FIELDS, 'design_sha256')):
                        raise ValueError('Frozen 128/512 replay changed: ' + design.name)
                    baseline_matches.append(dict(case=case, label=LABELS[index], window=window))
                for index in (3, 4):
                    compare_implementation(case, index, window)

        searches, selected, selected_cases = [], [], []
        for index, design in enumerate(designs[:5]):
            targets = {}
            reference_search = {}
            for case in SEARCH_CASES:
                reference = evaluate(case, index, 512)['makespan_slots']
                deadlines = sorted({reference, *([88, 77, 60] if case == 'dispersed9' else [])}, reverse=True)
                targets[case] = reference
                for deadline in deadlines:
                    result = scan_minimum_window(certificates[case, index], deadline, 512,
                        lambda n, case=case, index=index: evaluate(case, index, n)['makespan_slots'])
                    searches.append(dict(case=case, label=LABELS[index],
                                         target_is_512_reference=deadline == reference, **result))
                    if deadline == reference:
                        if result['minimum_window'] is None:
                            raise ValueError('Reference target unexpectedly infeasible')
                        reference_search[case] = result['minimum_window']
                    if index in (3, 4) and result['minimum_window'] is not None and case == 'dispersed9':
                        compare_implementation(case, index, result['minimum_window'])
            first_common = max(reference_search.values())
            common_checked = []
            for window in range(first_common, 513):
                times = {case: evaluate(case, index, window)['makespan_slots'] for case in SEARCH_CASES}
                common_checked.append(dict(window=window, times=times))
                if all(times[c] <= targets[c] for c in SEARCH_CASES):
                    break
            else:
                raise ValueError('No common window including known 512 reference')
            selected.append(dict(label=LABELS[index], id=design.name, window=window, targets=targets,
                                 individually_minimum=reference_search, tested_common=common_checked,
                                 minimum_common_certified=True, request_cost=evaluate('dispersed9', index, window)['request_cost']))
            # Fixed hardware N now applies to all seven pre-existing cases, including negative controls.
            for case in traces:
                row = evaluate(case, index, window)
                old = next(r for r in archived[case, 'base']['results'] if r['id'] == design.name)
                selected_cases.append(dict(case=case, label=LABELS[index], window=window,
                                            archived_128_makespan=old['makespan_slots'],
                                            makespan_slots=row['makespan_slots'], cost=row['cost'],
                                            request_cost=row['request_cost'], completion=row['completion']))
                if index in (3, 4):
                    compare_implementation(case, index, window)
                    cfg = evaluate(case, index + 2, window)
                    selected_cases.append(dict(case=case, label=LABELS[index + 2], window=window,
                                                archived_128_makespan=old['makespan_slots'],
                                                makespan_slots=cfg['makespan_slots'], cost=cfg['cost'],
                                                request_cost=cfg['request_cost'], completion=cfg['completion']))

        frontiers = []
        windows = {i: item['window'] for i, item in enumerate(selected)}
        windows.update({5: windows[3], 6: windows[4]})
        for case in traces:
            frontiers.append(dict(case=case, selected_fixed_window_designs=request_cost_frontier(
                [evaluate(case, i, windows[i]) for i in range(7)])))
        rate_bounds = []
        for index, rate in ((0, 32), (2, 64), (3, 48), (4, 52)):
            task = next(t for t in certificates['dispersed9', index]['tasks'] if t['words'])
            rate_bounds.append(dict(label=LABELS[index], reference_words_per_slot=rate,
                                    minimum_window_necessary=rate_window_lower_bound(task, Fraction(rate)),
                                    required_credit_word_slots=task['required_credit_word_slots'], words=task['words']))
    finally:
        stream.close()
        stream_file.close()

    cert_payload = encoded([dict(case=case, label=LABELS[index], certificate=cert)
                            for (case, index), cert in sorted(certificates.items())])
    cert_path = output / 'certificates.json.gz'
    cert_path.write_bytes(gzip.compress(cert_payload, mtime=0))
    result = dict(schema='w2w.request-window-study.v1', provenance=provenance(),
                  registration_sha256=sha256(METHOD.read_bytes()).hexdigest(), catalog=catalog,
                  input_archive=archive_identity, baseline_matches=baseline_matches,
                  searches=searches, selected=selected, selected_cases=selected_cases,
                  steady_rate_necessary_bounds=rate_bounds, ablations=ablations, frontiers=frontiers,
                  replays=records, artifacts=[dict(path=p.name, sha256=sha256(p.read_bytes()).hexdigest(),
                                                  bytes=p.stat().st_size) for p in (raw_path, cert_path)],
                  scope='Finite synthetic target deadlines, integer request-window minima under the unchanged '
                        'executor; necessary bounds plus exhaustive certificates; no global scheduler optimum, '
                        'DRAM/RTL timing equivalence or calibrated request area',
                  elapsed_seconds=time.monotonic() - started)
    (output / 'summary.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print('VERIFIED', len(records), 'replays;', len(ablations), 'implementation ablations;',
          len(baseline_matches), 'unchanged archived controls;', result['elapsed_seconds'], 'seconds', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    run(args.output)


if __name__ == '__main__':
    main()
