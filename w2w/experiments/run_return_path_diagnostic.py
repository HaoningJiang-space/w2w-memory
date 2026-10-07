"""Change only RX reservation capacity on frozen B/C designs and read inputs."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from hashlib import sha256
import json
from pathlib import Path
import time

from w2w.experiments.run_provisioning_holdout import execute
from w2w.provenance import provenance
from w2w.synthesis.provisioning_catalog import candidate_designs
from w2w.synthesis.provisioning_target import target_design
from w2w.theory.return_path import packed_rx_requirement, return_path_period
from w2w.validation.provisioning_holdout import audit_inputs
from w2w.workloads.read_trace import synthetic_read_suite


METHOD = Path('docs/methods/RETURN_PATH_PROVISIONING_DIAGNOSTIC.md')


def run(source, output, workers):
    prov = provenance()
    if prov['git_status'] or not 1 <= workers <= 12:
        raise ValueError('Clean source and 1..12 workers required')
    source, output = Path(source), Path(output)
    if output.exists():
        raise ValueError('Use a fresh output directory')
    inputs, _ = audit_inputs(source)
    designs = dict(b_cfg=candidate_designs()[0]['b_cfg'], c_n192=target_design(192)[0])
    output.mkdir(parents=True)
    synthetic_source = output / 'synthetic_inputs'
    todo = []
    for case, trace in synthetic_read_suite(designs['b_cfg'].geometry.compute_xy).items():
        case = 'synthetic_' + case
        folder = synthetic_source / case
        folder.mkdir(parents=True)
        (folder / 'trace.json').write_text(json.dumps(trace.record(), indent=2)+'\n')
        todo.extend([((case, label, 192), str(synthetic_source), d) for label, d in designs.items()])
    todo.extend([((case['id'], label, 192), str(source), d) for case in inputs['cases'] for label, d in designs.items()])
    assert len(todo) == 32
    profiles = [dict(**return_path_period(w, d, r), full_packing_requirement=packed_rx_requirement(256, w, 1))
                for w, d in ((128, 1), (160, 2), (192, 2), (224, 2), (256, 1)) for r in (2, 3)]
    record = dict(schema='w2w.return-path-diagnostic.v1', provenance=prov,
        registration_sha256=sha256(METHOD.read_bytes()).hexdigest(), workers=workers,
        inputs_sha256=sha256((source / 'summary.json').read_bytes()).hexdigest(),
        profiles=profiles, target_derivations=[target_design(192, rx_depth=r)[1] for r in (2, 3)],
        jobs=[t[0] for t in todo], changed_parameter=dict(rx_depth_words=[2, 3]),
        additional_manufactured_rx_payload_bits_per_memory=32 * 3 * 256,
        scope='Observed-result causal diagnostic on the same inputs; uniform RX3 charges all three directions; '
              'RX payload proxy separate from TX and metadata, no new RX RTL')
    (output / 'provenance.json').write_text(json.dumps(record, indent=2)+'\n')
    started, rows = time.monotonic(), []
    with ProcessPoolExecutor(max_workers=workers) as pool, (output / 'completed.jsonl').open('w') as journal:
        futures = [pool.submit(execute, key, src, str(output), d, 3) for key, src, d in todo]
        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            journal.write(json.dumps(row)+'\n')
            journal.flush()
            print('COMPLETE', len(rows), '/', len(todo), row['case'], row['label'], row['makespan_slots'], flush=True)
    record.update(results=sorted(rows, key=lambda r: (r['case'], r['label'])),
                  elapsed_seconds=time.monotonic()-started,
                  delivered_words=sum(r['audit']['delivered_words'] for r in rows))
    (output / 'summary.json').write_text(json.dumps(record, indent=2, allow_nan=False)+'\n')
    print('VERIFIED', len(rows), 'replays;', record['elapsed_seconds'], 'seconds')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--workers', type=int, default=12)
    args = parser.parse_args()
    run(args.source, args.output, args.workers)
