"""Read back native-pilot artifacts against frozen logical bytes and source IDs."""
import argparse
from dataclasses import replace, asdict
import gzip
from hashlib import sha256
import json
from pathlib import Path

from w2w.analysis.request_window import window_certificate
from w2w.service.dram.ramulator import UPSTREAM_COMMIT
from w2w.service.read_replay import ReadReplayConfig
from w2w.synthesis.provisioning_catalog import candidate_designs
from w2w.validation.patterns_replay import check_delivery, check_frozen_accounting
from w2w.workloads.read_trace import ReadTrace, digest


def audit(source, trace_source):
    source = Path(source)
    manifest = json.loads((source / 'manifest.json').read_text())
    raw_trace = Path(trace_source).read_bytes()
    full = ReadTrace.from_record(json.loads(raw_trace))
    original = next(t for t in full.tasks if t.reads)
    trace = replace(full, tasks=(replace(original, dependencies=(), release_slot=0, compute_slots=0),))
    if (sha256(raw_trace).hexdigest() != manifest['trace_source_sha256'] or
            full.sha256 != manifest['original_trace_sha256'] or
            json.loads(json.dumps(asdict(original))) != manifest['original_task'] or
            trace.sha256 != manifest['trace_sha256'] or
            ReadTrace.from_record(manifest['selected_trace']).sha256 != trace.sha256 or
            manifest['upstream_commit'] != UPSTREAM_COMMIT or
            sha256((source / 'upstream_generated.patch').read_bytes()).hexdigest() != manifest['upstream_diff_sha256']):
        raise ValueError('Input/source identity mismatch')
    designs = candidate_designs()[0]
    config = ReadReplayConfig(**manifest['config'])
    expected = {(label, kind) for label in ('home', 'k2', 'wide', 'b_cfg')
                for kind in ('slot_reference', 'hbm2_reference')}
    rows, seen = {}, set()
    for item in manifest['results']:
        key = item['label'], item['kind']
        if key not in expected or key in seen:
            raise ValueError('Unexpected or repeated pilot result')
        seen.add(key)
        expected_path = f'{key[0]}_{key[1]}.json.gz'
        if item['path'] != expected_path:
            raise ValueError('Unexpected artifact path')
        raw = (source / expected_path).read_bytes()
        if sha256(raw).hexdigest() != item['sha256']:
            raise ValueError('Artifact hash mismatch')
        row = json.loads(gzip.decompress(raw))
        if row['trace_sha256'] != trace.sha256 or row['config'] != json.loads(json.dumps(asdict(config))):
            raise ValueError('Trace/config mismatch')
        certificate = window_certificate(designs[key[0]], trace, config)
        if any(row[k] != certificate[k] for k in ('design_sha256', 'residence_sha256')):
            raise ValueError('Frozen candidate changed')
        check_delivery(trace, row)
        check_frozen_accounting(certificate, row, trace.word_bytes)
        for field in ('makespan_slots', 'makespan_ns', 'logical_bytes', 'residence_sha256', 'audit'):
            if item[field] != row[field]: raise ValueError('Summary mismatch')
        if key[1] == 'hbm2_reference':
            b = row['native_backend']
            words = row['audit']['delivered_words']
            if (b['upstream_commit'] != UPSTREAM_COMMIT or b['config_sha256'] != digest(b['config']) or
                    b['accepted_words'] != words or b['completed_words'] != words or
                    b['pending_words'] != 0 or b['upstream_pending'] != 0 or
                    b['slot_ps'] != 1024 or b['tck_ps'] != 1000 or
                    item['backend_counts'] != {k: b[k] for k in item['backend_counts']}):
                raise ValueError('Native service accounting mismatch')
        elif 'native_backend' in row:
            raise ValueError('Legacy reference has a native backend')
        rows[key] = row
    if seen != expected: raise ValueError('Incomplete pilot')
    for label in ('home', 'k2', 'wide', 'b_cfg'):
        a, b = rows[label, 'slot_reference'], rows[label, 'hbm2_reference']
        if any(a[k] != b[k] for k in ('residence_sha256', 'native_words_by_bank', 'logical_bytes')):
            raise ValueError('Native timing changed residency or requested bytes')
    return dict(schema='w2w.dram-bridge-audit.v1', records=len(rows),
                delivered_words=sum(r['audit']['delivered_words'] for r in rows.values()),
                native_delivered_words=sum(r['audit']['delivered_words'] for k, r in rows.items()
                                           if k[1] == 'hbm2_reference'),
                trace_sha256=trace.sha256, artifact_hashes=True,
                frozen_route_and_bank_accounting=True, native_completions_drained=True,
                scope='Independent artifact/accounting reconstruction; not independent DRAM timing validation')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--trace-source', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = audit(args.source, args.trace_source)
    Path(args.output).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__': main()
