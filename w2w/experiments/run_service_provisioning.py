"""Derive credit-aware static splits, replay fixed controls, and analyze archived reads."""
import argparse
import csv
from dataclasses import replace
from fractions import Fraction
import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import time

from w2w.analysis.request_window import audit_archive as audit_windows
from w2w.analysis.service_provisioning import (check_provisioning_bound, credit_matched_split,
    layout_support_certificate, pool_capacity_bound, provisioning_certificate)
from w2w.provenance import provenance
from w2w.service.cost import CostModel
from w2w.service.guaranteed_service_exchange import contoured_geometry
from w2w.service.read_replay import ReadReplayConfig, design_record, replay_reads
from w2w.synthesis.read_catalog import CATALOG, load_designs
from w2w.synthesis.role_interfaces import make_candidate, static_shared_fifo
from w2w.validation.patterns_replay import audit as audit_patterns
from w2w.workloads.read_trace import ReadTrace, digest, synthetic_read_suite


METHOD = Path('docs/methods/SERVICE_PROVISIONING_STUDY.md')
PATTERNS = Path('artifacts/results/workload/patterns_replay/flow')
WINDOWS = Path('artifacts/results/workload/request_window')
PLAN = Path('artifacts/provenance/patterns_replay/plan.json')
N_VALUES = (128, 160, 192)
EQUAL_FIELDS = ('trace_sha256', 'residence_sha256', 'config', 'makespan_slots', 'tasks',
                'routes', 'audit', 'delivery_sha256', 'stalls', 'native_words_by_bank',
                'peak_outstanding_words')


def encode(value):
    return (json.dumps(value, separators=(',', ':'), allow_nan=False) + '\n').encode()


def save_csv(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


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


def compact_bound(case, label, row, bound):
    return dict(case=case, label=label, window=row['config']['outstanding_words_per_compute'],
                design_sha256=row['design_sha256'], trace_sha256=row['trace_sha256'],
                residence_sha256=row['residence_sha256'], makespan_slots=row['makespan_slots'],
                lower_slots=bound['lower_slots'], dag_lower_slots=bound['dag_lower_slots'],
                aggregate_cut_lower_slots=bound['aggregate_cut_lower_slots'],
                compute_serial_lower_slots=bound['compute_serial_lower_slots'],
                unexplained_slots=row['makespan_slots'] - bound['lower_slots'],
                delivered_words=row['audit']['delivered_words'])


def run(output):
    if subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip():
        raise RuntimeError('Use a clean committed checkout')
    started = time.monotonic()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    raw_path = output / 'replays.jsonl.gz'
    if raw_path.exists():
        raise ValueError('Use a fresh output directory')
    designs, duplicates, derived, catalog = candidate_designs()
    costs = {label: CostModel.evaluate(d) for label, d in designs.items()}
    supports = {label: layout_support_certificate(d) for label, d in designs.items()}
    traces = synthetic_read_suite(designs['home'].geometry.compute_xy)
    base = ReadReplayConfig()
    certificates = {(case, label): provisioning_certificate(d, trace, base)
                    for case, trace in traces.items() for label, d in designs.items()}
    old_audit = audit_windows(WINDOWS)
    real_audit = audit_patterns(PATTERNS, PLAN)
    known = {}
    with gzip.open(WINDOWS / 'replays.jsonl.gz', 'rb') as stream:
        for line in stream:
            record = json.loads(line)
            key = record['case'], record['label'], record['window']
            if record['label'] in designs and record['window'] in N_VALUES:
                known[key] = {k: record['replay'][k] for k in EQUAL_FIELDS}
    results, ablations, matches, raw_index = [], [], [], []
    current = {}

    with raw_path.open('wb') as raw_file, gzip.GzipFile(fileobj=raw_file, mode='wb', mtime=0) as stream:
        def save(case, label, row):
            payload = encode(dict(case=case, label=label, replay=row))
            stream.write(payload)
            raw_index.append(dict(sequence=len(raw_index), case=case, label=label,
                                  window=row['config']['outstanding_words_per_compute'],
                                  sha256=sha256(payload).hexdigest()))

        for case, trace in traces.items():
            for window in N_VALUES:
                config = replace(base, outstanding_words_per_compute=window)
                for label, design in designs.items():
                    row = replay_reads(design, trace, config)
                    bound = check_provisioning_bound(certificates[case, label], row)
                    row['cost'] = costs[label]
                    row = json.loads(encode(row))
                    save(case, label, row)
                    record = compact_bound(case, label, row, bound)
                    record.update(cost=costs[label], bound_compute_details=bound['compute_serial'])
                    results.append(record)
                    key = case, label, window
                    if key in known:
                        if any(row[k] != known[key][k] for k in EQUAL_FIELDS):
                            raise ValueError('An existing replay changed: ' + str(key))
                        matches.append(dict(case=case, label=label, window=window))
                    current[key] = {k: row[k] for k in EQUAL_FIELDS}
                    print('REPLAY', case, label, window, row['makespan_slots'], 'bound', bound['lower_slots'], flush=True)
            for label, (dup, window) in duplicates.items():
                row = replay_reads(dup, trace, replace(base, outstanding_words_per_compute=window))
                row = json.loads(encode(row))
                if any(row[k] != current[case, label, window][k] for k in EQUAL_FIELDS):
                    raise ValueError('New static split violates implementation equivalence')
                save(case, label + '_dup', row)
                ablations.append(dict(case=case, label=label, window=window, equal=True, fields=EQUAL_FIELDS))

    real, input_files = [], []
    existing = load_designs()[0]
    real_summary = json.loads((PATTERNS / 'summary.json').read_text())
    for item in real_summary['results']:
        path = PATTERNS / item['path']
        payload = path.read_bytes()
        row = json.loads(gzip.decompress(payload))
        trace = ReadTrace.from_record(json.loads((PATTERNS / item['case'] / 'trace.json').read_text()))
        design = existing[item['design_index']]
        cert = provisioning_certificate(design, trace, ReadReplayConfig(**row['config']))
        bound = check_provisioning_bound(cert, row)
        label = {0: 'home', 1: 'k2', 2: 'wide', 6: 'b_cfg'}[item['design_index']]
        record = compact_bound(item['case'], label, row, bound)
        record.update(bound_compute_details=bound['compute_serial'], source_path=str(path),
                      source_sha256=sha256(payload).hexdigest())
        real.append(record)
        certificates['real/' + item['case'] + '/' + str(record['window']), label] = cert
        input_files.append(dict(path=str(path), sha256=sha256(payload).hexdigest()))

    pool = []
    for engines in (1, 2, 4, 8, 16, 20, 24, 32):
        for target in (32, 52):
            pool.append(dict(target_words_per_slot=target, **pool_capacity_bound(
                32, Fraction(5, 8), Fraction(8, 13), engines, target)))
    cert_path = output / 'certificates.json.gz'
    cert_path.write_bytes(gzip.compress(encode([dict(case=k[0], label=k[1], certificate=v)
                                              for k, v in sorted(certificates.items())]), mtime=0))
    support_path = output / 'supports.json.gz'
    support_path.write_bytes(gzip.compress(encode(supports), mtime=0))
    save_csv(output / 'synthetic.csv', [{k: v for k, v in r.items() if k not in ('cost', 'bound_compute_details')}
                                       for r in results])
    save_csv(output / 'real_bounds.csv', [{k: v for k, v in r.items() if k != 'bound_compute_details'} for r in real])
    save_csv(output / 'pool_bounds.csv', pool)
    artifacts = [dict(path=p.name, sha256=sha256(p.read_bytes()).hexdigest(), bytes=p.stat().st_size)
                 for p in (raw_path, cert_path, support_path, output / 'synthetic.csv',
                           output / 'real_bounds.csv', output / 'pool_bounds.csv')]
    summary = dict(schema='w2w.service-provisioning-study.v1', provenance=provenance(),
        registration_sha256=sha256(METHOD.read_bytes()).hexdigest(), catalog=catalog,
        derivations=derived, designs={k: design_record(d) for k, d in designs.items()}, costs=costs,
        results=results, real_archive_bounds=real, pool_bounds=pool, ablations=ablations,
        matched_existing_replays=matches, replay_index=raw_index, artifacts=artifacts,
        request_window_audit=old_audit, real_archive_audit={k: v for k, v in real_audit.items() if k != 'rows'},
        existing_deadline_certificates=json.loads((WINDOWS / 'summary.json').read_text())['searches'],
        input_files=input_files, elapsed_seconds=time.monotonic() - started,
        scope='Three analytically derived static byte/quota configurations; synthetic replay validation; '
              'stronger necessary bounds on unchanged real-routing archives; no new real-routing replay, '
              'engine pool, RTL or physical cost calibration')
    (output / 'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False) + '\n')
    print('VERIFIED', len(results), 'main replays;', len(ablations), 'equal ablations;',
          len(real), 'real archive bounds;', len(matches), 'old matches;', summary['elapsed_seconds'], 'seconds')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    run(parser.parse_args().output)
