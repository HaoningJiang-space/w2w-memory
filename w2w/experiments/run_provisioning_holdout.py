"""Execute the registered credit/residency candidates on request-disjoint routing."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import gzip
from hashlib import sha256
import json
from pathlib import Path
import time

from w2w.analysis.service_provisioning import check_provisioning_bound, provisioning_certificate
from w2w.experiments.prepare_provisioning_holdout import METHOD
from w2w.synthesis.provisioning_catalog import candidate_designs
from w2w.provenance import provenance
from w2w.service.cost import CostModel
from w2w.service.read_replay import ReadReplayConfig, replay_reads
from w2w.validation.patterns_replay import check_delivery, check_frozen_accounting
from w2w.workloads.read_trace import ReadTrace


PRIMARY = ('home', 'k2', 'wide', 'a_cfg', 'b_cfg', 'a_n128', 'b_n128')
CONTROL = ('home', 'k2', 'wide', 'b_cfg', 'a_n128')


def jobs(cases):
    return [(c['id'], label, n) for c in cases
            for n, labels in ((128, PRIMARY), (192, CONTROL if c['batch_size'] == 1 else ()),
                              (128, ('home_mod',))) for label in labels]


def execute(key, source, output, design_override=None):
    case, label, window = key
    started = time.monotonic()
    trace_path = Path(source) / case / ('modulo_trace.json' if label == 'home_mod' else 'trace.json')
    trace = ReadTrace.from_record(json.loads(trace_path.read_text()))
    design = design_override or candidate_designs()[0]['home' if label == 'home_mod' else label]
    config = ReadReplayConfig(outstanding_words_per_compute=window, max_trace_words=80000000, max_slots=500000)
    cert = provisioning_certificate(design, trace, config)
    row = replay_reads(design, trace, config)
    check_delivery(trace, row)
    check_frozen_accounting(cert['word_certificate'], row, trace.word_bytes)
    bound = check_provisioning_bound(cert, row)
    row.update(cost=CostModel.evaluate(design), provisioning_bound=bound,
               wall_seconds=time.monotonic()-started)
    relative = f'{case}/{label}_n{window}.json.gz'
    path = Path(output) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = gzip.compress(json.dumps(row, separators=(',', ':'), allow_nan=False).encode(), mtime=0)
    temporary = path.with_suffix('.part')
    temporary.write_bytes(raw)
    temporary.replace(path)
    return dict(case=case, label=label, window=window, path=relative,
                file_sha256=sha256(raw).hexdigest(), file_bytes=len(raw),
                **{k: row[k] for k in ('trace_sha256', 'design_sha256', 'residence_sha256',
                    'makespan_slots', 'logical_bytes', 'audit', 'delivery_sha256', 'cost',
                    'provisioning_bound', 'wall_seconds')})


def run(source, output, workers):
    prov = provenance()
    if prov['git_status'] or not 1 <= workers <= 12:
        raise ValueError('Clean source and 1..12 workers required')
    source, output = Path(source), Path(output)
    if output.exists():
        raise ValueError('Use a fresh output directory')
    raw = (source / 'summary.json').read_bytes()
    inputs = json.loads(raw)
    registration = sha256(METHOD.read_bytes()).hexdigest()
    if inputs['registration_sha256'] != registration:
        raise ValueError('Inputs and execution use different registration')
    for item in inputs['files']:
        payload = (source / item['path']).read_bytes()
        if len(payload) != item['bytes'] or sha256(payload).hexdigest() != item['sha256']:
            raise ValueError('Frozen input changed')
    todo = jobs(inputs['cases'])
    if len(todo) != 87 or len(set(todo)) != 87:
        raise ValueError('Registered execution coverage changed')
    output.mkdir(parents=True)
    started = time.monotonic()
    record = dict(schema='w2w.provisioning-holdout-results.v1', provenance=prov,
        registration_sha256=registration, inputs_sha256=sha256(raw).hexdigest(),
        workers=workers, jobs=todo, input_cases=inputs['cases'])
    (output / 'provenance.json').write_text(json.dumps(record, indent=2)+'\n')
    rows = []
    with ProcessPoolExecutor(max_workers=workers) as pool, (output / 'completed.jsonl').open('w') as journal:
        futures = [pool.submit(execute, key, str(source), str(output)) for key in todo]
        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            journal.write(json.dumps(row, allow_nan=False)+'\n')
            journal.flush()
            print('COMPLETE', len(rows), '/', len(todo), row['case'], row['label'], row['window'],
                  row['makespan_slots'], round(row['wall_seconds'], 2), flush=True)
    rows.sort(key=lambda r: (r['case'], r['window'], r['label']))
    record.update(results=rows, elapsed_seconds=time.monotonic()-started,
                  delivered_words=sum(r['audit']['delivered_words'] for r in rows))
    (output / 'summary.json').write_text(json.dumps(record, indent=2, allow_nan=False)+'\n')
    print('VERIFIED', len(rows), 'replays;', record['delivered_words'], 'words;', record['elapsed_seconds'], 'seconds')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--workers', type=int, default=12)
    args = parser.parse_args()
    run(args.source, args.output, args.workers)
