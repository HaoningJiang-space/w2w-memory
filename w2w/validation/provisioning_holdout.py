"""Independent frozen-input and resource accounting for the held-out study."""
import argparse
import csv
from dataclasses import asdict
import gzip
from hashlib import sha256
import json
from pathlib import Path

from w2w.analysis.service_provisioning import check_provisioning_bound, provisioning_certificate
from w2w.experiments.prepare_provisioning_holdout import METHOD, PREVIOUS
from w2w.experiments.run_provisioning_holdout import jobs
from w2w.experiments.run_service_provisioning import candidate_designs
from w2w.service.cost import CostModel
from w2w.service.read_replay import ReadReplayConfig, design_record
from w2w.synthesis.read_catalog import archived_cost_matches
from w2w.validation.patterns_replay import check_delivery, check_frozen_accounting, check_routing_union
from w2w.workloads.patterns_trace import RequestRoutes, compile_patterns_window, load_requests
from w2w.workloads.provisioning_holdout import fit_owners, split_requests
from w2w.workloads.read_trace import ReadTrace, digest


def read_json(path):
    path = Path(path)
    if not path.exists() and path.suffix != '.gz':
        path = path.with_suffix(path.suffix + '.gz')
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == '.gz' else raw)


def audit_inputs(source, verify_raw=False):
    source = Path(source)
    summary = read_json(source / 'summary.json')
    if (summary['provenance']['git_status'] or summary['registration_sha256'] != sha256(METHOD.read_bytes()).hexdigest()):
        raise ValueError('Input source/registration mismatch')
    for item in summary['files']:
        raw = (source / item['path']).read_bytes()
        if len(raw) != item['bytes'] or sha256(raw).hexdigest() != item['sha256']:
            raise ValueError('Frozen input hash mismatch')
    corpus_raw = (source / 'corpus_manifest.json').read_bytes()
    previous = read_json(PREVIOUS)
    if sha256(corpus_raw).hexdigest() != previous['corpus_manifest_sha256']:
        raise ValueError('Unexpected corpus manifest')
    corpus = json.loads(corpus_raw)
    selected = split_requests(corpus, previous)
    if selected != summary['split']:
        raise ValueError('Request split differs from ID-only selection')
    by_id = {r['id']: r for r in corpus['requests']}
    selected_ids = selected['training'] + sum(selected['tests'], [])
    if summary['selected_sources'] != [by_id[key] for key in selected_ids]:
        raise ValueError('Selected raw source identities differ')
    extracted = read_json(source / 'training_routes.json.gz')
    if [r['id'] for r in extracted] != selected['training']:
        raise ValueError('Training uses different requests')
    requests = tuple(RequestRoutes(r['id'], 0, r['decode'], r['source']) for r in extracted)
    spec = read_json(source / 'training_spec.json')
    owners = read_json(source / 'owners.json')
    if digest(fit_owners(requests, spec)) != digest(owners):
        raise ValueError('Training scores/owner assignment changed')
    if verify_raw:
        rebuilt, _ = load_requests(source / 'training/manifest.json', spec)
        if digest([dict(id=r.id, decode=r.decode, source=r.source) for r in rebuilt]) != digest(extracted):
            raise ValueError('Extracted training routes differ from raw JSON')
    traces = {}
    expected_cases = {f'h{g}_b{b}' for g in range(3) for b in (1, 4, 16)}
    if {c['id'] for c in summary['cases']} != expected_cases or len(summary['cases']) != 9:
        raise ValueError('Input case coverage mismatch')
    for case in summary['cases']:
        gi = int(case['id'][1])
        if ((case['layer'], case['decode_step']) != (('0', 17), ('39', 65), ('78', 113))[gi]
                or case['requests'] != selected['tests'][gi][:case['batch_size']]):
            raise ValueError('Test window changed')
        folder = source / case['id']
        manifest = read_json(folder / 'manifest.json')
        if [r['id'] for r in manifest['requests']] != case['requests']:
            raise ValueError('Case manifest changed requests')
        for r in manifest['requests']:
            if r['sha256'] != by_id[r['id']]['sha256'] or r['arrival_iteration'] != 0:
                raise ValueError('Case raw source or arrival changed')
        for mode, prefix in (('trained', ''), ('modulo', 'modulo_')):
            current_spec = read_json(folder / (prefix + 'spec.json'))
            trace = ReadTrace.from_record(read_json(folder / (prefix + 'trace.json')))
            demand = read_json(folder / (prefix + 'demand.json'))
            expected_owners = owners[case['layer']]['compute_by_expert'] if mode == 'trained' else [e % 36 for e in range(128)]
            if (current_spec['layers'][0]['compute_by_expert'] != expected_owners
                    or trace.sha256 != case['trace_sha256' if mode == 'trained' else 'modulo_trace_sha256']
                    or demand['trace_sha256'] != trace.sha256
                    or demand['total_logical_read_bytes'] != case['logical_bytes']
                    or len(trace.objects) != 128
                    or sum(o.size_bytes for o in trace.objects) != 128 * 18878976):
                raise ValueError('Frozen ownership/objects/trace mismatch')
            if verify_raw:
                check_routing_union(folder / 'manifest.json', current_spec, case['decode_step'], demand)
                rebuilt, rebuilt_demand = compile_patterns_window(folder / 'manifest.json', current_spec, case['decode_step'])
                if rebuilt.sha256 != trace.sha256 or digest(rebuilt_demand) != digest(demand):
                    raise ValueError('Raw routing recompile mismatch')
            traces[case['id'], mode] = trace
    return summary, traces


def gain_retention(home, wide, candidate):
    if min(home, wide, candidate) <= 0:
        raise ValueError('Positive completion times required')
    return ((1/candidate - 1/home) / (1/wide - 1/home)) if wide < home else None


def frontier(rows):
    axes = ('export_lane_bits', 'endpoint_storage_bits', 'access_wire_bit_mm',
            'pipeline_register_bits', 'fixed_sequence_control_bits', 'bank_port_connections')
    vectors = {(r['label'], r['window']): (r['makespan_slots'], r['window'], *(r['cost'][k] for k in axes)) for r in rows}
    return [dict(label=key[0], window=key[1]) for key, value in sorted(vectors.items()) if not any(
        all(a <= b for a, b in zip(other, value)) and any(a < b for a, b in zip(other, value))
        for name, other in vectors.items() if name != key)]


def audit(source, results, verify_raw=False):
    inputs, traces = audit_inputs(source, verify_raw)
    folder = Path(results)
    summary = read_json(folder / 'summary.json')
    if (summary['provenance']['git_status'] or summary['registration_sha256'] != inputs['registration_sha256']
            or summary['inputs_sha256'] != sha256((Path(source) / 'summary.json').read_bytes()).hexdigest()
            or summary['input_cases'] != inputs['cases']):
        raise ValueError('Execution input identity mismatch')
    keys = [(r['case'], r['label'], r['window']) for r in summary['results']]
    expected = set(jobs(inputs['cases']))
    if len(keys) != len(set(keys)) or set(keys) != expected or {tuple(k) for k in summary['jobs']} != expected:
        raise ValueError('Missing/duplicate/unregistered execution')
    designs = candidate_designs()[0]
    words, observed, residences = 0, {}, {}
    for item in summary['results']:
        key = item['case'], item['label'], item['window']
        if item['path'] != f'{key[0]}/{key[1]}_n{key[2]}.json.gz':
            raise ValueError('Unexpected raw output path')
        raw = (folder / item['path']).read_bytes()
        if len(raw) != item['file_bytes'] or sha256(raw).hexdigest() != item['file_sha256']:
            raise ValueError('Raw output hash mismatch')
        row = json.loads(gzip.decompress(raw))
        design = designs['home' if key[1] == 'home_mod' else key[1]]
        trace = traces[key[0], 'modulo' if key[1] == 'home_mod' else 'trained']
        cfg = ReadReplayConfig(outstanding_words_per_compute=key[2], max_trace_words=80000000, max_slots=500000)
        if (digest(row['config']) != digest(asdict(cfg)) or digest(row['design']) != digest(design_record(design))
                or not archived_cost_matches(CostModel.evaluate(design), row['cost'])):
            raise ValueError('Execution configuration/cost changed')
        cert = provisioning_certificate(design, trace, cfg)
        check_delivery(trace, row)
        check_frozen_accounting(cert['word_certificate'], row, trace.word_bytes)
        bound = check_provisioning_bound(cert, row)
        if digest(bound) != digest(row['provisioning_bound']):
            raise ValueError('Completion bound changed')
        for field in ('trace_sha256', 'design_sha256', 'residence_sha256', 'makespan_slots',
                      'logical_bytes', 'audit', 'delivery_sha256', 'cost', 'provisioning_bound', 'wall_seconds'):
            if digest(item[field]) != digest(row[field]):
                raise ValueError('Compact row differs from raw replay')
        words += row['audit']['delivered_words']
        residences.setdefault(key[:2], set()).add(row['residence_sha256'])
        observed[key] = row
    if words != summary['delivered_words'] or any(len(v) != 1 for v in residences.values()):
        raise ValueError('Word total or frozen-across-N residency mismatch')
    metrics = []
    for item in summary['results']:
        case, label, n = item['case'], item['label'], item['window']
        if label == 'home_mod':
            continue
        home = observed[case, 'home', n]['makespan_slots']
        wide = observed[case, 'wide', n]['makespan_slots']
        current = item['makespan_slots']
        metrics.append(dict(case=case, label=label, window=n, makespan_slots=current,
            home_slots=home, wide_slots=wide, speedup_over_home=home/current,
            retained_wide_gain=gain_retention(home, wide, current),
            lower_slots=item['provisioning_bound']['lower_slots'],
            gap_slots=current-item['provisioning_bound']['lower_slots']))
    return dict(verified=True, source_commit=summary['provenance']['commit'],
        replay_count=len(keys), delivered_words=words, raw_inputs_recompiled=verify_raw,
        training_requests=64, disjoint_test_requests=48, cases=9, metrics=metrics,
        frontiers={c['id']: frontier([r for r in summary['results'] if r['case'] == c['id'] and r['label'] != 'home_mod'])
                   for c in inputs['cases']},
        scope='Frozen routing/owners and complete modeled read stages; no inference or global dynamic sharing claim')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--results')
    parser.add_argument('--verify-raw', action='store_true')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if args.results:
        result = audit(args.source, args.results, args.verify_raw)
    else:
        inputs, _ = audit_inputs(args.source, args.verify_raw)
        result = dict(verified=True, training_requests=64, test_requests=48, cases=len(inputs['cases']),
                      raw_inputs_recompiled=args.verify_raw)
    Path(args.output).write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    if args.results:
        path = Path(args.output).with_suffix('.csv')
        with path.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(result['metrics'][0]), lineterminator='\n')
            writer.writeheader()
            writer.writerows(result['metrics'])
    print(json.dumps({k: v for k, v in result.items() if k not in ('metrics', 'frontiers')}))
