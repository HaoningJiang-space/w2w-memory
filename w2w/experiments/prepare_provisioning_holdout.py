"""Freeze owners and held-out cold-read windows from verified raw routing."""
import argparse
from copy import deepcopy
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path

from w2w.provenance import provenance
from w2w.workloads.patterns_trace import compile_patterns_window, load_requests
from w2w.workloads.provisioning_holdout import fit_owners, split_requests
from w2w.workloads.read_trace import digest


METHOD = Path('docs/methods/PROVISIONING_HOLDOUT_STUDY.md')
PREVIOUS = Path('artifacts/provenance/patterns_replay/plan.json')
SPEC = Path('artifacts/provenance/patterns_trace_input/execution.json')


def prepare(manifest_path, output):
    prov = provenance()
    if prov['git_status']:
        raise ValueError('Use clean committed source')
    manifest_path, output = Path(manifest_path).resolve(), Path(output)
    if output.exists():
        raise ValueError('Use a fresh output directory')
    manifest = json.loads(manifest_path.read_text())
    previous = json.loads(PREVIOUS.read_text())
    if (sha256(manifest_path.read_bytes()).hexdigest() != previous['corpus_manifest_sha256']
            or manifest['revision'] != previous['revision'] or manifest['evidence'] != 'captured'):
        raise ValueError('Expected the already registered captured corpus')
    selected = split_requests(manifest, previous)
    by_id = {r['id']: r for r in manifest['requests']}
    base = json.loads(SPEC.read_text())
    base['layers'] = [dict(base['layers'][0], key=key) for key in ('0', '39', '78')]
    base['batching'] = dict(policy='fixed_cohort', batch_size=1, max_decode_steps=None)
    output.mkdir(parents=True)
    (output / 'corpus_manifest.json').write_bytes(manifest_path.read_bytes())

    def save_manifest(ids, folder):
        folder.mkdir(parents=True, exist_ok=True)
        record = dict(manifest, requests=[dict(by_id[key], path=os.path.relpath(
            manifest_path.parent / by_id[key]['path'], folder.resolve())) for key in ids])
        path = folder / 'manifest.json'
        path.write_text(json.dumps(record, indent=2)+'\n')
        return path

    training_path = save_manifest(selected['training'], output / 'training')
    training, _ = load_requests(training_path, base)
    owners = fit_owners(training, base)
    # Small extracted selections permit independent training-score regeneration.
    extracted = [dict(id=r.id, decode=r.decode, source=r.source) for r in training]
    (output / 'training_routes.json.gz').write_bytes(gzip.compress(json.dumps(extracted,
        separators=(',', ':')).encode(), mtime=0))
    (output / 'training_spec.json').write_text(json.dumps(base, indent=2)+'\n')
    (output / 'owners.json').write_text(json.dumps(owners, indent=2)+'\n')
    cases = []
    for gi, (layer, step) in enumerate((('0', 17), ('39', 65), ('78', 113))):
        for batch in (1, 4, 16):
            name = f'h{gi}_b{batch}'
            folder = output / name
            ids = selected['tests'][gi][:batch]
            path = save_manifest(ids, folder)
            spec = deepcopy(base)
            spec['layers'] = [dict(base['layers'][gi], compute_by_expert=owners[layer]['compute_by_expert'])]
            spec['batching']['batch_size'] = batch
            trace, demand = compile_patterns_window(path, spec, step)
            modulo = deepcopy(spec)
            modulo['layers'][0]['compute_by_expert'] = [e % 36 for e in range(128)]
            control, control_demand = compile_patterns_window(path, modulo, step)
            for filename, record in (('spec.json', spec), ('trace.json', trace.record()),
                ('demand.json', demand), ('modulo_spec.json', modulo), ('modulo_trace.json', control.record()),
                ('modulo_demand.json', control_demand)):
                (folder / filename).write_text(json.dumps(record, indent=2)+'\n')
            cases.append(dict(id=name, layer=layer, decode_step=step, batch_size=batch, requests=ids,
                trace_sha256=trace.sha256, modulo_trace_sha256=control.sha256,
                distinct_experts=len(demand['windows'][0]['activated_experts']),
                logical_bytes=demand['total_logical_read_bytes'],
                owner_sha256=digest(spec['layers'][0]['compute_by_expert'])))
    records = []
    for path in sorted(p for p in output.rglob('*') if p.is_file()):
        raw = path.read_bytes()
        records.append(dict(path=str(path.relative_to(output)), bytes=len(raw), sha256=sha256(raw).hexdigest()))
    summary = dict(schema='w2w.provisioning-holdout-input.v1', provenance=prov,
        registration_sha256=sha256(METHOD.read_bytes()).hexdigest(), split=selected, cases=cases,
        source_manifest_sha256=sha256(manifest_path.read_bytes()).hexdigest(), revision=manifest['revision'],
        selected_sources=[by_id[key] for key in selected['training'] + sum(selected['tests'], [])], files=records,
        scope='Request-disjoint from training and previous timed cohorts; this corpus was previously characterized')
    (output / 'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print('FROZEN', len(training), 'training requests;', len(cases), 'test windows;', len(summary['selected_sources']), 'raw hashes')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    prepare(args.manifest, args.output)
