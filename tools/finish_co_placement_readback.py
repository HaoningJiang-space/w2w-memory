#!/usr/bin/env python3
"""Finish independent readback/summary of the already registered background pair."""
import argparse,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from w2w.analysis.co_placement import analyze
from w2w.common.io import write_json


def finish(root,baseline):
    while True:
        complete=[root/'multilayer/cases'/case/'completion.json' for case in ('reference_compute','up_local_compute')]
        if all(p.exists() for p in complete):break
        log=(root/'logs/controller-r1.log').read_text()
        if 'Traceback (most recent call last)' in log:raise RuntimeError('Original campaign failed; retain evidence instead of retrying')
        time.sleep(30)
    proof=analyze(root/'multilayer',baseline);write_json(root/'multilayer/independent-readback.json',proof)
    cold=json.loads((root/'cold/independent-readback.json').read_text())
    if not cold['passed'] or cold['execution_source_commit']!=proof['execution_source_commit'] or cold['native_tools']!=proof['native_tools']:
        raise ValueError('Cold/warm identities differ')
    a,b=(proof['cases'][case] for case in ('reference_compute','up_local_compute'))
    summary=dict(passed=True,execution_source_commit=proof['execution_source_commit'],analysis_source_commit=proof['analysis_source_commit'],
        cold_completion_reduction_percent=cold['cases']['up_local_compute']['completion_reduction_percent'],
        cold_activity_reduction_percent=cold['cases']['up_local_compute']['data_lane_activity_reduction_percent'],
        warm_completion_reduction_percent=b['completion_reduction_percent'],warm_activity_reduction_percent=b['data_lane_activity_reduction_percent'],
        late_window_completion_reduction_percent=100*(1-b['late_window']['duration_ps']/a['late_window']['duration_ps']),
        warm_observed_traffic={case:proof['cases'][case]['traffic_totals'] for case in proof['cases']},
        contract='All registered outcomes retained. Warm traffic need not match; initialization is independent and outside timing. No calibrated energy/PPA or full Transformer claim.')
    write_json(root/'completed-summary.json',summary)
    lines=['# Completed Up compute/memory co-placement gate','',
        'Independent source/input, physical-resource, operand/cache, real-traffic and drain checks pass.',
        'Execution: `'+proof['execution_source_commit']+'`; analysis: `'+proof['analysis_source_commit']+'`.','',
        '| Warm metric | Reference compute | Up-local compute |','|---|---:|---:|']
    for name,values in [('Complete time (ms)',[x['makespan_ps']/1e9 for x in (a,b)]),
                        ('Token-12–23 time (ms)',[x['late_window']['duration_ps']/1e9 for x in (a,b)]),
                        ('Native bytes',[x['audit']['native_bytes'] for x in (a,b)]),
                        ('Reload bytes',[x['traffic_totals']['reload_bytes'] for x in (a,b)]),
                        ('NoC data-lane byte·um',[x['pressure']['actual_data_lane_byte_um'] for x in (a,b)])]:
        lines.append('| '+name+' | '+str(values[0])+' | '+str(values[1])+' |')
    lines.extend(['','Warm completion reduction: '+str(summary['warm_completion_reduction_percent'])+'%.',
        'Warm activity reduction: '+str(summary['warm_activity_reduction_percent'])+'%.','',summary['contract'],
        'See `multilayer/independent-readback.json` for per-invocation traffic and readiness/resource evidence.',''])
    (root/'COMPLETED_RESULTS.md').write_text('\n'.join(lines));print(json.dumps(summary),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True)
    a=p.parse_args();finish(a.root,a.baseline)


if __name__=='__main__':main()
