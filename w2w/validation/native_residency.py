"""Audit the registered two-layout native experiment without rerunning DRAM."""
import argparse
from dataclasses import replace
from fractions import Fraction
import gzip
from hashlib import sha256
import json
from pathlib import Path

from w2w.analysis.request_window import window_certificate
from w2w.provenance import provenance
from w2w.service.read_replay import ReadReplayConfig, design_record
from w2w.synthesis.provisioning_catalog import candidate_designs
from w2w.validation.patterns_replay import check_delivery, check_frozen_accounting
from w2w.workloads.read_trace import ReadTrace, digest


def check_native_counts(row, words):
    native = row['native_backend']
    if (native['accepted_words'] != words or native['completed_words'] != words
            or native['pending_words'] or native['upstream_pending']):
        raise ValueError('Native completion or pending count differs')
    stats = native['stats']
    if (len(stats['controller']) != 36 or stats['total_num_read_requests'] != words
            or stats['total_num_write_requests']):
        raise ValueError('Native controller population/traffic differs')
    active = []
    for m, controller in enumerate(stats['controller']):
        count = sum(n for bank, n in row['native_words_by_bank'].items() if int(bank)//32 == m)
        if (controller['num_read_reqs'] != count or controller['num_read_reqs_served'] != count
                or controller['num_read_reqs_forwarded'] or controller['num_write_reqs']):
            raise ValueError('Native bank/controller counts differ')
        if count:
            active.append(dict(memory=m, words=count,
                effective_GB_s=count*32/row['makespan_ns'],
                row_hit_fraction=controller['read_row_hits']/count))
    return active


def audit(source):
    source = Path(source)
    manifest = json.loads((source/'manifest.json').read_text())
    archive = Path('artifacts/results/dram/command_bridge')
    old_manifest = json.loads((archive/'manifest.json').read_text())
    old_path = 'b_cfg_hbm2_reference.json.gz'
    old_raw = (archive/old_path).read_bytes()
    old_hash = sha256(old_raw).hexdigest()
    old = json.loads(gzip.decompress(old_raw))
    if old_hash != next(r['sha256'] for r in old_manifest['results'] if r['path'] == old_path):
        raise ValueError('Reference archive changed')
    method = Path('docs/methods/NATIVE_MATCHED_RESIDENCY_PROBE.md')
    if (manifest['schema'] != 'w2w.native-residency-probe.v1'
            or manifest['provenance']['git_status']
            or manifest['registration_sha256'] != sha256(method.read_bytes()).hexdigest()
            or manifest['reference_sha256'] != old_hash
            or manifest['trace_sha256'] != old_manifest['trace_sha256']
            or digest(manifest['trace']) != digest(old_manifest['selected_trace'])
            or digest(manifest['config']) != digest(old['config'])
            or [r['label'] for r in manifest['results']] != ['original', 'native_half']):
        raise ValueError('Registered source, trace, config or coverage differs')
    trace = ReadTrace.from_record(manifest['trace'])
    words = sum(r.size_bytes for task in trace.tasks for r in task.reads)//32
    if words != 589968 or len(trace.objects) != 128:
        raise ValueError('Full pilot object/population required')
    cfg = ReadReplayConfig(**old['config'])
    catalog = candidate_designs()[0]
    original = catalog['b_cfg']
    half = replace(original, name=original.name+'_native_half', layout=catalog['wide'].layout,
                   home_fraction=Fraction(1, 2))
    results = []
    for item, design in zip(manifest['results'], (original, half), strict=True):
        raw = (source/item['path']).read_bytes()
        if sha256(raw).hexdigest() != item['sha256'] or item['path'] != item['label']+'.json.gz':
            raise ValueError('Result identity differs')
        row = json.loads(gzip.decompress(raw))
        if (digest(row['design']) != digest(design_record(design))
                or row['design_sha256'] != digest(design_record(design))
                or row['trace_sha256'] != trace.sha256
                or digest(row['config']) != digest(old['config'])
                or row['slot_ns'] != old['slot_ns']
                or item['home_fraction'] != str(design.home_fraction)):
            raise ValueError('Result hardware/trace/config differs')
        for key in ('upstream_commit', 'bridge_sha256', 'config_sha256', 'config', 'tck_ps', 'slot_ps'):
            if digest(row['native_backend'][key]) != digest(old['native_backend'][key]):
                raise ValueError('Native implementation/profile differs')
        for key in ('makespan_slots', 'makespan_ns', 'design_sha256', 'wall_seconds'):
            if item[key] != row[key]:
                raise ValueError('Summary differs from replay')
        check_delivery(trace, row)
        check_frozen_accounting(window_certificate(design, trace, cfg), row, trace.word_bytes)
        active = check_native_counts(row, words)
        if item['label'] == 'original':
            for key in ('makespan_slots', 'delivery_sha256', 'residence_sha256', 'native_words_by_bank'):
                if row[key] != old[key]:
                    raise ValueError('Original does not reproduce archive')
        results.append(dict(label=item['label'], makespan_slots=row['makespan_slots'],
                            makespan_ns=row['makespan_ns'], active_memories=active))
    ratio = results[1]['makespan_slots']/results[0]['makespan_slots']
    if ratio != manifest['observed_time_ratio'] or not manifest['original_matches_archive']:
        raise ValueError('Comparison summary differs')
    return dict(verified=True, provenance=provenance(), source_commit=manifest['provenance']['commit'],
                records=2, words_per_run=words, results=results, observed_time_ratio=ratio,
                completion_time_reduction=1-ratio,
                scope='Same native profile and endpoint; full single-object diagnostic, not application speedup')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', required=True); p.add_argument('--output', required=True)
    a = p.parse_args()
    result = audit(a.source)
    Path(a.output).write_text(json.dumps(result, indent=2)+'\n')
    print('VERIFIED', result['records'], 'native residency replays')
