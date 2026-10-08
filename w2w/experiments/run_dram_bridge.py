"""Frozen full-object pilot of the optional HBM2 reference command backend."""
import argparse
from dataclasses import replace, asdict
import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import time

from w2w.provenance import provenance
from w2w.service.dram.ramulator import RamulatorHBM2, UPSTREAM_COMMIT
from w2w.service.read_replay import ReadReplayConfig, replay_reads
from w2w.synthesis.provisioning_catalog import candidate_designs
from w2w.validation.patterns_replay import check_delivery, check_frozen_accounting
from w2w.analysis.request_window import window_certificate
from w2w.workloads.read_trace import ReadTrace

DEFAULT_TRACE = 'artifacts/results/workload/provisioning_holdout/inputs/h0_b1/trace.json'
LABELS = ('home', 'k2', 'wide', 'b_cfg')


def run(args):
    prov = provenance()
    if prov['git_status']:
        raise ValueError('Commit source before running the pilot')
    source = Path(args.ramulator_source).resolve()
    head = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if head != UPSTREAM_COMMIT:
        raise ValueError('Unexpected upstream source revision')
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=False)
    source_raw = Path(args.trace).read_bytes()
    full = ReadTrace.from_record(json.loads(source_raw))
    # Deterministic first read task, complete original spans and object population.
    # This isolates integration; it is not a serving batch or end-to-end MoE run.
    original = next(t for t in full.tasks if t.reads)
    task = replace(original, dependencies=(), release_slot=0, compute_slots=0)
    trace = replace(full, tasks=(task,))
    config = ReadReplayConfig(outstanding_words_per_compute=192, max_slots=2000000)
    patch = subprocess.check_output(['git', '-C', str(source), 'diff', '--binary'])
    (output / 'upstream_generated.patch').write_bytes(patch)
    manifest = dict(schema='w2w.dram-bridge-pilot.v1', provenance=prov,
                    trace_source_sha256=sha256(source_raw).hexdigest(),
                    original_trace_sha256=full.sha256, original_task=asdict(original),
                    selected_trace=trace.record(), trace_sha256=trace.sha256,
                    upstream_commit=head, upstream_diff_sha256=sha256(patch).hexdigest(),
                    library_sha256=sha256((source / 'libramulator.so').read_bytes()).hexdigest(),
                    config=asdict(config), designs=list(LABELS), results=[],
                    scope='First full read task from a frozen real-routing window; all resident objects '
                          'retained; HBM2 reference changes physical service budget; not application speedup')
    designs = candidate_designs()[0]
    for label in LABELS:
        reference = None
        for kind in ('slot_reference', 'hbm2_reference'):
            started = time.monotonic()
            backend = RamulatorHBM2(36) if kind == 'hbm2_reference' else None
            try:
                row = replay_reads(designs[label], trace, config, native_backend=backend)
                check_delivery(trace, row)
                check_frozen_accounting(window_certificate(designs[label], trace, config), row, trace.word_bytes)
            finally:
                if backend is not None:
                    backend.close()
            if reference is None:
                reference = row
            elif (row['residence_sha256'] != reference['residence_sha256'] or
                  row['native_words_by_bank'] != reference['native_words_by_bank']):
                raise RuntimeError('Changing native backend changed frozen bytes')
            row['wall_seconds'] = time.monotonic() - started
            raw = gzip.compress(json.dumps(row, separators=(',', ':'), allow_nan=False).encode(), mtime=0)
            name = f'{label}_{kind}.json.gz'
            (output / name).write_bytes(raw)
            summary = dict(label=label, kind=kind, path=name, sha256=sha256(raw).hexdigest(),
                           **{k: row[k] for k in ('makespan_slots', 'makespan_ns', 'logical_bytes',
                               'residence_sha256', 'audit', 'wall_seconds')})
            if backend is not None:
                summary['backend_counts'] = {k: row['native_backend'][k] for k in
                    ('accepted_words', 'completed_words', 'pending_words', 'upstream_pending', 'rejected_attempts')}
            manifest['results'].append(summary)
            (output / 'manifest.json').write_text(json.dumps(manifest, indent=2, allow_nan=False) + '\n')
            print(label, kind, row['makespan_slots'], row['wall_seconds'], flush=True)
    print('VERIFIED', len(manifest['results']), 'frozen full-object replays', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trace', default=DEFAULT_TRACE)
    parser.add_argument('--ramulator-source', required=True)
    parser.add_argument('--output', required=True)
    run(parser.parse_args())


if __name__ == '__main__':
    main()
