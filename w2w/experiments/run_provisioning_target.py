"""Execute the independently frozen N192 target extension beside old controls."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
import gzip
from hashlib import sha256
import json
from pathlib import Path
import time

from w2w.experiments.run_provisioning_holdout import execute
from w2w.experiments.run_service_provisioning import EQUAL_FIELDS
from w2w.provenance import provenance
from w2w.synthesis.provisioning_catalog import candidate_designs
from w2w.synthesis.provisioning_target import target_design
from w2w.validation.provisioning_holdout import audit_inputs
from w2w.workloads.read_trace import synthetic_read_suite


METHOD = Path('docs/methods/PROVISIONING_TARGET_EXTENSION.md')


def run(source, output, workers):
    prov = provenance()
    if prov['git_status'] or not 1 <= workers <= 12:
        raise ValueError('Clean source and 1..12 workers required')
    source, output = Path(source), Path(output)
    if output.exists():
        raise ValueError('Use a fresh output directory')
    inputs, _ = audit_inputs(source)
    design, plan = target_design(192)
    duplicated = replace(design, name=design.name + '_duplicated', shared_directions=(),
        endpoint=replace(design.endpoint, shared_fifo_ports=(), shared_serializer=False))
    output.mkdir(parents=True)
    synthetic_source = output / 'synthetic_inputs'
    synthetic = synthetic_read_suite(design.geometry.compute_xy)
    todo = []
    for case, trace in synthetic.items():
        case = 'synthetic_' + case
        folder = synthetic_source / case
        folder.mkdir(parents=True)
        (folder / 'trace.json').write_text(json.dumps(trace.record(), indent=2)+'\n')
        todo.extend([((case, label, 192), str(synthetic_source), d)
                     for label, d in (('c_n192', design), ('c_n192_dup', duplicated))])
    controls = candidate_designs()[0]
    for case in inputs['cases']:
        todo.append(((case['id'], 'c_n192', 192), str(source), design))
        if case['batch_size'] != 1:
            todo.extend([((case['id'], label, 192), str(source), controls[label])
                         for label in ('home', 'k2', 'wide', 'b_cfg')])
    if len(todo) != 47:
        raise ValueError('Registered target extension coverage changed')
    started = time.monotonic()
    record = dict(schema='w2w.provisioning-target-results.v1', provenance=prov,
        registration_sha256=sha256(METHOD.read_bytes()).hexdigest(),
        inputs_sha256=sha256((source / 'summary.json').read_bytes()).hexdigest(),
        derivations=[target_design(n)[1] for n in (128, 160, 192)], workers=workers,
        jobs=[t[0] for t in todo])
    (output / 'provenance.json').write_text(json.dumps(record, indent=2)+'\n')
    rows = []
    with ProcessPoolExecutor(max_workers=workers) as pool, (output / 'completed.jsonl').open('w') as journal:
        futures = [pool.submit(execute, key, src, str(output), d) for key, src, d in todo]
        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            journal.write(json.dumps(row)+'\n')
            journal.flush()
            print('COMPLETE', len(rows), '/', len(todo), row['case'], row['label'], row['makespan_slots'], flush=True)
    indexed = {(r['case'], r['label']): r for r in rows}
    ablations = []
    for case in synthetic:
        key = 'synthetic_' + case
        records = [json.loads(gzip.decompress((output / indexed[key, label]['path']).read_bytes()))
                   for label in ('c_n192', 'c_n192_dup')]
        if any(records[0][k] != records[1][k] for k in EQUAL_FIELDS):
            raise ValueError('192-bit duplicated/configurable mismatch')
        ablations.append(dict(case=key, equal=True, fields=EQUAL_FIELDS))
    record.update(results=sorted(rows, key=lambda r: (r['case'], r['label'])), ablations=ablations,
                  elapsed_seconds=time.monotonic()-started,
                  delivered_words=sum(r['audit']['delivered_words'] for r in rows))
    (output / 'summary.json').write_text(json.dumps(record, indent=2, allow_nan=False)+'\n')
    print('VERIFIED', len(rows), 'replays;', len(ablations), 'equal ablations;', record['elapsed_seconds'], 'seconds')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--workers', type=int, default=12)
    args = parser.parse_args()
    run(args.source, args.output, args.workers)
