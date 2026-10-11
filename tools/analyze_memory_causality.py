"""SHA-bound saved-record diagnosis; a real captured routing witness is required."""
import argparse, gzip, json, re, time
from pathlib import Path
from w2w.analysis.memory_service_causality import explain_pool_window
from w2w.workloads.moe_trace import file_sha
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.common.io import write_json
from w2w.provenance import revision


def analyze(raw, proof_path, case, corpus, capture_index, layer, step, task, output):
    proof = json.loads(proof_path.read_text())
    relative = f'cases/{case}/result.json.gz'
    raw_hash = file_sha(raw)
    if not proof['passed'] or raw_hash != proof['files'][relative]['sha256']:
        raise ValueError('Completed independently audited raw identity required')
    manifest = json.loads((corpus/'manifest.json').read_text())
    coverage = json.loads((corpus/'coverage-audit.json').read_text())
    if not coverage['passed'] or file_sha(corpus/'manifest.json') != coverage['normalized_manifest_sha256']:
        raise ValueError('Independent complete real-corpus coverage audit required')
    row = manifest['requests'][capture_index]; path = corpus/row['path']
    if file_sha(path) != row['file_sha256']:
        raise ValueError('Captured routing changed')
    with gzip.open(path, 'rt') as f: capture = json.load(f)
    if digest(capture) != row['normalized_sha256']:
        raise ValueError('Captured routing content changed')
    selected = capture['decode'][layer][step]
    before = time.monotonic()
    with gzip.open(raw, 'rt') as f: result = json.load(f)
    expected = proof['cases'][case]
    if (result['source_commit'] != proof['execution_source_commit'] or
            result['makespan_ps'] != expected['makespan_ps']):
        raise ValueError('Saved execution identity differs')
    experts = {int(m.group(1)) for t in result['graph']['tasks']
               if (m := re.match(r'^e([0-9]+)/', t['id']))}
    if experts != set(selected):
        raise ValueError('Historical graph expert set differs from captured routing witness')
    diagnosis = explain_pool_window(result, task)
    record = dict(schema='w2w.memory-causality-readback.v1', passed=True, analysis_source_commit=revision(),
        execution_source_commit=result['source_commit'], raw_result_sha256=raw_hash,
        audit_sha256=file_sha(proof_path), case=case, makespan_ps=result['makespan_ps'], diagnosis=diagnosis,
        trace_witness=dict(request_id=row['id'], raw_capture_sha256=row['raw_sha256'],
            normalized_sha256=row['normalized_sha256'], corpus_manifest_sha256=file_sha(corpus/'manifest.json'),
            coverage_audit_sha256=file_sha(corpus/'coverage-audit.json'), dataset_revision=manifest['dataset_revision'],
            original_layer=layer, zero_based_decode_step=step, ranked_experts=selected,
            complete_capture_coverage=capture['coverage'],
            scope='Historical one-token FFN graph agrees with this real routing selection. '
                'It did not execute the complete captured request or full MoE model.'),
        reader_wall_seconds=time.monotonic()-before,
        limits='No new simulation, component idealization, command timing calibration or recoverable-latency claim.')
    if output.exists(): raise ValueError('Never overwrite an analysis receipt')
    write_json(output, record)
    print(json.dumps(dict(passed=True,task=task,makespan_ps=record['makespan_ps'],
        phase_fraction=diagnosis['full_window_phase_fraction'], mc_full_wall_ps=diagnosis['mc_full_wall_ps'])),flush=True)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('raw','proof','corpus','output'): p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--case',required=True);p.add_argument('--capture-index',type=int,required=True)
    p.add_argument('--layer',default='0');p.add_argument('--decode-step',type=int,required=True)
    p.add_argument('--task',required=True);a=p.parse_args()
    analyze(a.raw,a.proof,a.case,a.corpus,a.capture_index,a.layer,a.decode_step,a.task,a.output)
