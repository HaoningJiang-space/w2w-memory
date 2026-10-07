"""Registered disjoint request cohorts, full-sized reads and common credit budgets."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import time

from w2w.analysis.request_window import window_certificate, check_bound, completion_lower_bound
from w2w.synthesis.read_catalog import load_designs
from w2w.service.cost import CostModel
from w2w.service.read_replay import ReadReplayConfig, replay_reads
from w2w.workloads.patterns_trace import compile_patterns_window
from w2w.workloads.read_trace import ReadTrace


def prepare_cases(manifest_path, spec_path, plan, output):
    manifest_path = Path(manifest_path).resolve()
    raw = manifest_path.read_bytes()
    if sha256(raw).hexdigest() != plan['corpus_manifest_sha256']:
        raise ValueError('Corpus manifest differs from preregistration')
    manifest = json.loads(raw)
    if manifest['revision'] != plan['revision'] or manifest['evidence'] != 'captured':
        raise ValueError('Pinned captured routing required')
    ids = [i for group in plan['groups'] for i in group['requests']]
    if len(set(ids)) != len(ids):
        raise ValueError('Independent groups cannot reuse requests')
    by_id = {r['id']: r for r in manifest['requests']}
    base = json.loads(Path(spec_path).read_text())
    cases = []
    for group in plan['groups']:
        for batch in plan['batch_sizes']:
            if len(group['requests']) < batch:
                raise ValueError('Insufficient registered requests; no padding')
            name = f"{group['id']}_b{batch}"
            folder = Path(output) / name
            folder.mkdir(parents=True)
            chosen = [by_id[i] for i in group['requests'][:batch]]
            selected = dict(manifest, requests=[dict(r, path=os.path.relpath(
                manifest_path.parent / r['path'], folder.resolve())) for r in chosen])
            path = folder / 'manifest.json'
            path.write_text(json.dumps(selected, indent=2) + '\n')
            spec = json.loads(json.dumps(base))
            spec['layers'] = [dict(spec['layers'][0], key=group['layer'])]
            spec['batching'] = dict(policy='fixed_cohort', batch_size=batch, max_decode_steps=None)
            trace, demand = compile_patterns_window(path, spec, group['decode_step'])
            if len(demand['windows']) != 1:
                raise ValueError('One layer/window required')
            words = demand['total_logical_read_bytes'] // trace.word_bytes
            if words > plan['max_trace_words']:
                raise ValueError('Word budget exceeded; do not shrink weights')
            for filename, record in [('spec.json', spec), ('trace.json', trace.record()),
                                     ('demand.json', demand)]:
                (folder / filename).write_text(json.dumps(record, indent=2) + '\n')
            windows = [plan['primary_outstanding']]
            if group['id'] in plan['control_groups']:
                windows.append(plan['control_outstanding'])
            cases.append(dict(id=name, group=group['id'], batch_size=batch,
                layer=group['layer'], decode_step=group['decode_step'], request_ids=[r['id'] for r in chosen],
                trace_path=str(folder/'trace.json'), trace_sha256=trace.sha256,
                words=words, read_bytes=words*trace.word_bytes,
                activated_experts=demand['windows'][0]['activated_experts'],
                read_bytes_per_compute=demand['windows'][0]['read_bytes_per_compute'],
                windows=windows))
    return cases


def execute(case, index, window, plan, output):
    trace = ReadTrace.from_record(json.loads(Path(case['trace_path']).read_text()))
    design = load_designs()[0][index]
    config = ReadReplayConfig(outstanding_words_per_compute=window,
        max_trace_words=plan['max_trace_words'], max_slots=plan['max_slots'])
    certificate = window_certificate(design, trace, config)
    start = time.monotonic()
    result = replay_reads(design, trace, config)
    check_bound(certificate, result)
    if result['logical_bytes'] != case['read_bytes'] or result['audit']['delivered_words'] != case['words']:
        raise RuntimeError('Real routing demand to delivered bytes mismatch')
    result.update(id=design.name, cost=CostModel.evaluate(design),
        wall_seconds=time.monotonic()-start,
        lower_bound=dict(with_credit=completion_lower_bound(certificate, window),
                         independent=completion_lower_bound(certificate)))
    relative = f"{case['id']}/design{index}_n{window}.json.gz"
    raw = gzip.compress(json.dumps(result, separators=(',', ':'), allow_nan=False).encode(), mtime=0)
    path = Path(output)/relative
    temporary = path.with_suffix(path.suffix+'.part')
    temporary.write_bytes(raw)
    temporary.replace(path)
    return dict(case=case['id'], design_index=index, window=window, path=relative,
        file_sha256=sha256(raw).hexdigest(), file_bytes=len(raw),
        **{k:result[k] for k in ('id', 'trace_sha256', 'design_sha256', 'residence_sha256',
            'logical_bytes', 'makespan_slots', 'delivery_sha256', 'audit', 'stalls', 'cost',
            'lower_bound', 'wall_seconds')})


def run(args):
    if subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip():
        raise RuntimeError('Commit source before experiments')
    output = Path(args.output)
    if output.exists():
        raise ValueError('Use a new output directory')
    output.mkdir(parents=True)
    plan = json.loads(Path(args.plan).read_text())
    start = time.monotonic()
    record = dict(source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        source_dirty=False, plan=plan, plan_sha256=sha256(Path(args.plan).read_bytes()).hexdigest(),
        scope='Full-size modeled read stages from real routing; not GPU inference or measured DRAM traffic')
    (output/'provenance.json').write_text(json.dumps(record, indent=2)+'\n')
    cases = prepare_cases(args.manifest, args.spec, plan, output)
    (output/'cases.json').write_text(json.dumps(cases, indent=2)+'\n')
    print('PREPARED', [(c['id'], len(c['activated_experts']), c['words']) for c in cases], flush=True)
    rows = []
    with ProcessPoolExecutor(max_workers=plan['workers']) as pool, (output/'completed.jsonl').open('w') as journal:
        futures = [pool.submit(execute, c, i, n, plan, output) for c in cases
                   for n in c['windows'] for i in plan['design_indices']]
        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            journal.write(json.dumps(row, allow_nan=False)+'\n')
            journal.flush()
            print('COMPLETE', len(rows), '/', len(futures), row['case'], row['design_index'],
                  row['window'], row['makespan_slots'], round(row['wall_seconds'], 2), flush=True)
    # Trace/residence identities must remain frozen across credit budgets.
    for c in cases:
        for i in plan['design_indices']:
            selected = [r for r in rows if r['case']==c['id'] and r['design_index']==i]
            if len({r['residence_sha256'] for r in selected}) != 1:
                raise RuntimeError('Changing request budget changed data residency')
    rows.sort(key=lambda r:(r['case'], r['window'], r['design_index']))
    record.update(cases=cases, results=rows, elapsed_seconds=time.monotonic()-start,
                  replay_count=len(rows), delivered_words=sum(r['audit']['delivered_words'] for r in rows))
    (output/'summary.json').write_text(json.dumps(record, indent=2, allow_nan=False)+'\n')
    print('DONE', len(rows), 'replays', record['delivered_words'], 'words', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', default='artifacts/provenance/patterns_replay/plan.json')
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--spec', default='artifacts/provenance/patterns_trace_input/execution.json')
    parser.add_argument('--output', required=True)
    run(parser.parse_args())
