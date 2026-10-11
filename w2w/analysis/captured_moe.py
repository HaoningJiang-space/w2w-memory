"""Independent saved-result readback of a full-phase captured MoE request."""
import argparse,gzip,json
from collections import Counter
from pathlib import Path
from w2w.common.io import write_json
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.provenance import revision
from w2w.workloads.moe_trace import file_sha
from w2w.validation.vertical_access import audit_vertical_result
from w2w.validation.request_control import audit_request_control
from w2w.analysis.placement_pressure import summarize_pressure


def analyze(root):
    reg=json.loads((root/'registration.json').read_text());capture=json.load(gzip.open(root/'capture.json.gz','rt'))
    if digest(capture)!=reg['capture_sha256'] or reg['execution_omitted_tokens']:
        raise ValueError('Captured request changed or was truncated')
    rows={};files={};tools=set()
    for case,registered in reg['cases'].items():
        data=json.load(gzip.open(root/'inputs'/f'{case}.json.gz','rt'))
        if digest(data)!=registered['input_sha256']:raise ValueError('Frozen execution input changed')
        path=root/'cases'/case/'result.json.gz';completion=json.loads((path.parent/'completion.json').read_text())
        r=json.load(gzip.open(path,'rt'))
        if (not completion['complete'] or r['source_commit']!=reg['source_commit']
                or completion['source_commit']!=reg['source_commit'] or r['graph']!=data['graph']
                or r['spec']['stack']!=data['machine'] or completion['input_sha256']!=registered['input_sha256']
                or r['makespan_ps']!=completion['makespan_ps'] or r['drained_ps']!=completion['drained_ps']):
            raise ValueError('Captured execution/source identity differs')
        a=audit_vertical_result(r);b=audit_request_control(r)
        if a!=completion['audit'] or b!=completion['control_audit']:raise ValueError('Saved resource conservation differs')
        if (r['operand_readiness']['policy']!='contiguous_prefix' or r['compute_execution']['contexts_per_cluster']!=2
                or r['fetch_execution']['contexts_per_cluster']!=2
                or r['fetch_execution']['read_issue_policy']!='round_robin'):
            raise ValueError('Registered finite service policy changed')
        finished=Counter(e['task'] for e in r['events'] if e['kind']=='task_finish')
        if finished!=Counter({t['id']:1 for t in data['graph']['tasks']}):raise ValueError('Tasks missing or duplicated')
        if sum(e.get('macs',0) for e in r['events'] if e['kind']=='stream_compute')!=data['metadata']['macs']:
            raise ValueError('Actual arithmetic work differs')
        calls=data['metadata']['invocations'];expected_calls=(1+reg['decode_tokens'])*len(reg['layer_keys'])
        if len(calls)!=expected_calls:raise ValueError('Request phase/layer invocation dropped')
        milestones=[]
        for i,call in enumerate(calls):
            phase='prefill' if i<len(reg['layer_keys']) else 'decode'
            step=None if phase=='prefill' else i//len(reg['layer_keys'])-1
            layer=reg['layer_keys'][i%len(reg['layer_keys'])]
            selections=capture['prefill'][layer] if phase=='prefill' else [capture['decode'][layer][step]]
            if (call['phase']!=phase or call['decode_step']!=step or call['captured_layer']!=layer
                    or call['token_experts']!=selections or call['token_count']!=len(selections)):
                raise ValueError('Independent captured routing was replaced or omitted')
            dispatch={t['id'] for t in data['graph']['tasks'] if t['id'].startswith(call['prefix']) and '/dispatch/' in t['id']}
            expected={call['prefix']+f't{t}/dispatch/e{e}' for t,selected in enumerate(selections) for e in selected}
            if dispatch!=expected:raise ValueError('Actual token dispatch membership differs')
            finish=max(r['tasks'][key]['finish_ps'] for key in call['finish_tasks'])
            milestones.append(dict(phase=phase,decode_step=step,captured_layer=layer,finish_ps=finish))
        if max(v['finish_ps'] for v in milestones)!=r['makespan_ps']:raise ValueError('Final combine is not measured output completion')
        if r['weight_cache'].get('initial_resident_bytes',0) or any(e['kind']=='cache_initial_resident' for e in r['events']):
            raise ValueError('Unregistered initial cache residency')
        tool=(r['network']['identity']['binary_sha256'],r['native']['bridge_sha256']);tools.add(tool)
        rows[case]=dict(independent_passed=True,makespan_ps=r['makespan_ps'],drained_ps=r['drained_ps'],
            actual_completed_tasks=sum(finished.values()),invocations=len(calls),milestones=milestones,
            native_bytes=a['native_bytes'],cache_stats=r['weight_cache']['stats'],pressure=summarize_pressure(r),
            sram_peak_bytes=r['sram_peak_bytes'],wall_seconds=completion['wall_seconds'])
        files[str(path.relative_to(root))]=dict(sha256=file_sha(path),bytes=path.stat().st_size)
        del r
    if len(tools)!=1:raise ValueError('Compared cases used different native tools')
    return dict(schema='w2w.captured-moe-readback.v1',passed=True,analysis_source_commit=revision(),
        execution_source_commit=reg['source_commit'],registration_sha256=file_sha(root/'registration.json'),
        capture_sha256=reg['capture_sha256'],cases=rows,files=files,booksim_and_bridge_sha256=list(next(iter(tools))),
        scope=reg['scope'],contract='Every actual task, registered independent-layer route, selected-layer phase and byte/resource drain audited. '
            'Retain observed cache/traffic differences and negative performance. No full-model or numerical-inference claim.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=analyze(a.root);write_json(a.output,r)
    print(json.dumps(dict(passed=True,makespans={k:v['makespan_ps'] for k,v in r['cases'].items()})))
