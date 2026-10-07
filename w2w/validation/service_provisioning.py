"""Read back the provisioning study without launching new task replays."""
import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path

from w2w.analysis.service_provisioning import (check_provisioning_bound, layout_support_certificate,
                                              provisioning_certificate)
from w2w.domain import EndpointSpec, Exposure, Geometry, MemoryFabricDesign, StaticLayout
from w2w.domain.endpoint import NativeProfile
from w2w.service.cost import CostModel
from w2w.service.read_replay import ReadReplayConfig, design_record
from w2w.synthesis.read_catalog import archived_cost_matches
from w2w.validation.patterns_replay import check_delivery, check_frozen_accounting
from w2w.workloads.read_trace import ReadTrace, digest


def restore_design(row):
    return MemoryFabricDesign(**{**row, 'geometry': Geometry(**row['geometry']),
        'exposure': Exposure(**row['exposure']), 'layout': StaticLayout(**row['layout']),
        'endpoint': EndpointSpec(**{**row['endpoint'], 'native': NativeProfile(**row['endpoint']['native'])})})


def audit(folder):
    folder = Path(folder)
    plain = folder / 'summary.json'
    summary = json.loads(plain.read_bytes() if plain.exists() else
                         gzip.decompress((folder / 'summary.json.gz').read_bytes()))
    for item in summary['artifacts']:
        raw = (folder / item['path']).read_bytes()
        if len(raw) != item['bytes'] or sha256(raw).hexdigest() != item['sha256']:
            raise ValueError('Output artifact hash mismatch')
    for item in summary['input_files']:
        if sha256(Path(item['path']).read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('Source replay hash mismatch')
    certs = {(r['case'], r['label']): r['certificate'] for r in json.loads(
        gzip.decompress((folder / 'certificates.json.gz').read_bytes()))}
    supports = json.loads(gzip.decompress((folder / 'supports.json.gz').read_bytes()))
    designs = {label: restore_design(row) for label, row in summary['designs'].items()}
    for label, design in designs.items():
        if (layout_support_certificate(design) != supports[label]
                or not archived_cost_matches(CostModel.evaluate(design), summary['costs'][label])):
            raise ValueError('Design support or cost mismatch')
    cases = sorted({r['case'] for r in summary['results']})
    if cases != sorted(('single', 'dispersed9', 'clustered9', 'full36', 'moving9', 'straggler9', 'short9')):
        raise ValueError('Unexpected synthetic case coverage')
    # Existing immutable full logical inputs, not reconstructed from output counters.
    traces = {case: ReadTrace.from_record(json.loads(gzip.decompress(Path(
        'artifacts/results/workload/finite_read', case + '_base.json.gz').read_bytes()))['trace']) for case in cases}
    compact = {(r['case'], r['label'], r['window']): r for r in summary['results']}
    expected = {(case, label, window) for case in cases for label in designs for window in (128, 160, 192)}
    if set(compact) != expected or len(compact) != len(summary['results']):
        raise ValueError('Missing or duplicate main replay')
    rows = {}
    certificates_checked = set()
    words = 0
    with gzip.open(folder / 'replays.jsonl.gz', 'rb') as stream:
        for sequence, (line, index) in enumerate(zip(stream, summary['replay_index'], strict=True)):
            record = json.loads(line)
            row = record['replay']
            key = record['case'], record['label'], row['config']['outstanding_words_per_compute']
            if (index['sequence'] != sequence or index['sha256'] != sha256(line).hexdigest()
                    or key != (index['case'], index['label'], index['window']) or key in rows):
                raise ValueError('Raw row identity/hash mismatch')
            design = restore_design(row['design'])
            if digest(design_record(design)) != row['design_sha256'] or digest(row['residence']) != row['residence_sha256']:
                raise ValueError('Design/residence identity mismatch')
            trace = traces[key[0]]
            check_delivery(trace, row)
            if key in compact:
                if row['design_sha256'] != digest(design_record(designs[key[1]])):
                    raise ValueError('Replay uses a different registered design')
                cert = certs[key[:2]]
                if key[:2] not in certificates_checked:
                    regenerated = provisioning_certificate(design, trace, ReadReplayConfig(**row['config']))
                    if digest(regenerated) != digest(cert):
                        raise ValueError('Certificate differs from frozen logical inputs')
                    certificates_checked.add(key[:2])
                check_frozen_accounting(cert['word_certificate'], row, trace.word_bytes)
                bound = check_provisioning_bound(cert, row)
                for field in ('makespan_slots', 'trace_sha256', 'design_sha256', 'residence_sha256'):
                    if compact[key][field] != row[field]:
                        raise ValueError('Compact result differs from raw record')
                for field in ('lower_slots', 'dag_lower_slots', 'aggregate_cut_lower_slots', 'compute_serial_lower_slots'):
                    if compact[key][field] != bound[field]:
                        raise ValueError('Compact bound differs from certificate')
            words += row['audit']['delivered_words']
            rows[key] = {k: v for k, v in row.items() if k not in ('design', 'residence', 'composition')}
    expected_dup = {(case, label + '_dup', n) for case in cases
                    for label, n in (('a_n128', 128), ('b_n128', 128), ('b_n160', 160))}
    if set(rows) != expected | expected_dup or len(summary['ablations']) != len(expected_dup):
        raise ValueError('Unexpected ablation coverage')
    for item in summary['ablations']:
        left = rows[item['case'], item['label'], item['window']]
        right = rows[item['case'], item['label'] + '_dup', item['window']]
        if not item['equal'] or any(left[k] != right[k] for k in item['fields']):
            raise ValueError('Duplicated/configurable result mismatch')
    real_count = 0
    real_keys = set()
    for item in summary['real_archive_bounds']:
        real_key = item['case'], item['label'], item['window']
        if real_key in real_keys:
            raise ValueError('Duplicate real archive bound')
        real_keys.add(real_key)
        row = json.loads(gzip.decompress(Path(item['source_path']).read_bytes()))
        trace = ReadTrace.from_record(json.loads(Path(item['source_path']).with_name('trace.json').read_text()))
        design = restore_design(row['design'])
        check_delivery(trace, row)
        cert = provisioning_certificate(design, trace, ReadReplayConfig(**row['config']))
        check_frozen_accounting(cert['word_certificate'], row, trace.word_bytes)
        key = 'real/' + item['case'] + '/' + str(item['window']), item['label']
        if digest(cert) != digest(certs[key]):
            raise ValueError('Real input certificate mismatch')
        bound = check_provisioning_bound(cert, row)
        for field in ('lower_slots', 'dag_lower_slots', 'aggregate_cut_lower_slots', 'compute_serial_lower_slots'):
            if item[field] != bound[field]:
                raise ValueError('Real archived bound mismatch')
        real_count += 1
    if real_count != 48 or len(certificates_checked) != 56:
        raise ValueError('Incomplete registered certificate coverage')
    return dict(verified=True, new_replays=len(rows), main_replays=len(compact),
                implementation_ablations=len(expected_dup), model_words=words,
                real_archive_bounds=real_count, regenerated_synthetic_certificates=len(certificates_checked),
                experimental_source_commit=summary['provenance']['commit'],
                raw_archive_sha256=sha256((folder / 'replays.jsonl.gz').read_bytes()).hexdigest(),
                scope='Readback, frozen-input regeneration, per-resource delivery, task timing and bound checks; no new replay')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = audit(args.source)
    Path(args.output).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
