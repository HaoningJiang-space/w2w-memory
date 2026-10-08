"""Verify raw routing and freeze disjoint finite read tasks, without fitting."""
import argparse
from copy import deepcopy
import gzip
from hashlib import sha256
import json
from pathlib import Path

from w2w.provenance import provenance
from w2w.workloads.cohort_replay import (METHOD, OLD_INPUTS, PROBE_SHA, read_json,
    frozen_owners, select_requests, cases, logical_signature)
from w2w.workloads.patterns_trace import load_requests, compile_patterns_window
from w2w.validation.patterns_replay import check_routing_union


def prepare(manifest_path, output):
    prov = provenance()
    if prov['git_status']:
        raise ValueError('Clean committed source required')
    manifest_path, output = Path(manifest_path).resolve(), Path(output)
    if output.exists():
        raise ValueError('Use a fresh output directory')
    raw = manifest_path.read_bytes()
    old = read_json(OLD_INPUTS/'summary.json')
    if sha256(raw).hexdigest() != old['source_manifest_sha256']:
        raise ValueError('Unexpected corpus manifest')
    corpus = json.loads(raw)
    split = select_requests(corpus, old)
    owners = frozen_owners()
    if len(split['excluded']) != 160 or list(map(len, split['groups'])) != [16]*3:
        raise ValueError('Registered request coverage changed')
    by_id = {r['id']:r for r in corpus['requests']}
    base = read_json(OLD_INPUTS/'training_spec.json')
    base['layers'] = [dict(base['layers'][0], compute_by_expert=owners['marginal'])]
    output.mkdir(parents=True)
    (output/'corpus_manifest.json').write_bytes(raw)

    def manifest(ids, target):
        row = dict(corpus, requests=[dict(by_id[k], path=str((manifest_path.parent/by_id[k]['path']).resolve())) for k in ids])
        target.write_text(json.dumps(row, indent=2)+'\n')
        return target

    all_path = manifest(sum(split['groups'], []), output/'raw_manifest.json')
    requests, _ = load_requests(all_path, base)
    extracted = [dict(id=r.id, source=r.source, decode=r.decode) for r in requests]
    (output/'routes.json.gz').write_bytes(gzip.compress(json.dumps(extracted,separators=(',',':')).encode(),mtime=0))
    (output/'owners.json').write_text(json.dumps(owners,indent=2)+'\n')
    selected = cases(split)
    for case in selected:
        folder = output/case['id']
        folder.mkdir()
        path = manifest(case['requests'], folder/'manifest.json')
        identities = set()
        for name, assignment in owners.items():
            spec = deepcopy(base)
            spec['layers'][0]['compute_by_expert'] = assignment
            spec['batching']['batch_size'] = case['batch_size']
            trace, demand = compile_patterns_window(path, spec, case['decode_step'])
            check_routing_union(path, spec, case['decode_step'], demand)
            identities.add(logical_signature(trace))
            for suffix, value in (('spec',spec),('trace',trace.record()),('demand',demand)):
                (folder/f'{name}_{suffix}.json').write_text(json.dumps(value,indent=2)+'\n')
        if len(identities) != 1:
            raise ValueError('Mapping changed logical tasks or bytes')
        case.update(logical_signature=identities.pop(),logical_bytes=demand['total_logical_read_bytes'],
                    distinct_experts=len(demand['windows'][0]['activated_experts']))
    files = []
    for path in sorted(p for p in output.rglob('*') if p.is_file()):
        data = path.read_bytes()
        files.append(dict(path=str(path.relative_to(output)),bytes=len(data),sha256=sha256(data).hexdigest()))
    summary = dict(schema='w2w.cohort-replay-input.v1',provenance=prov,split=split,cases=selected,
        registration_sha256=sha256(METHOD.read_bytes()).hexdigest(),probe_sha256=PROBE_SHA,
        source_manifest_sha256=sha256(raw).hexdigest(),files=files,
        scope='Fresh requests within previously characterized corpus; layer0 frozen training mappings')
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print('FROZEN',len(requests),'disjoint requests;',len(selected),'windows;',len(files),'hashed files')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',required=True)
    p.add_argument('--output',required=True)
    a=p.parse_args()
    prepare(a.manifest,a.output)
