"""Count actual cache and DRAM traffic by completed layer invocation.

The late window is explicitly finite; it is not a stationary workload claim.
Native results must already have passed the separate hierarchy audit.
"""
import argparse,gzip,json
from collections import Counter
from pathlib import Path
from w2w.common.io import write_json
from w2w.provenance import revision


def invocation_traffic(result, invocations):
    records={i['prefix']:Counter() for i in invocations}
    for e in result['events']:
        if e['kind'] not in ('cache_lookup','read_deliver'):continue
        key=e['task'].split('/')[0]+'/'
        if key not in records:raise ValueError('Cache/read event has no registered layer invocation')
        row=records[key]
        if e['kind']=='read_deliver':row['native_bytes']+=e['bytes'];continue
        if e['hit']:row['hits']+=1;row['hit_bytes']+=e['bytes']
        else:
            row['misses']+=1;row['miss_bytes']+=e['bytes']
            row['reload_bytes' if e['previously_resident'] else 'compulsory_bytes']+=e['bytes']
    totals=Counter()
    for row in records.values():
        if row['miss_bytes']!=row['native_bytes'] or row['miss_bytes']!=row['compulsory_bytes']+row['reload_bytes']:
            raise ValueError('Invocation cache misses differ from actual native deliveries')
        totals.update(row)
    for key in ('hits','hit_bytes','misses','miss_bytes','reload_bytes','compulsory_bytes'):
        if totals[key]!=result['weight_cache']['stats'].get(key,0):raise ValueError('Invocation cache counters differ from global ledger')
    return [dict(**i,traffic=dict(records[i['prefix']])) for i in invocations],dict(totals)


def analyze(study,audited,late_invocations=24):
    reference=json.loads(audited.read_text());reg=json.loads((study/'registration.json').read_text());rows={}
    if not reference['passed'] or reference['source_commit']!=reg['source_commit']:
        raise ValueError('Completed hierarchy must be independently audited first')
    for case in reg['cases']:
        directory=study/'cases'/case;completion=json.loads((directory/'completion.json').read_text())
        with gzip.open(directory/'result.json.gz','rt') as f:result=json.load(f)
        expected=reference['cases'][case]
        if (result['source_commit']!=reg['source_commit'] or result['makespan_ps']!=expected['makespan_ps'] or
            completion['audit']!=expected['audit'] or result['weight_cache']['stats']!=expected['weight_cache']['stats']):
            raise ValueError('Raw invocation source, time or audited cache identity changed')
        per_call,totals=invocation_traffic(result,completion['invocations']);late=per_call[-late_invocations:];traffic=Counter()
        for call in late:traffic.update(call['traffic'])
        if totals.get('native_bytes',0)!=expected['audit']['native_bytes']:raise ValueError('Actual per-call native traffic differs from audit')
        rows[case]=dict(source_commit=result['source_commit'],input_sha256=completion['input_sha256'],totals=totals,invocations=per_call,
            late_window=dict(first_token=late[0]['token'],last_token=late[-1]['token'],layer_invocations=len(late),
                start_ps=late[0]['start_ps'],finish_ps=late[-1]['finish_ps'],duration_ps=late[-1]['finish_ps']-late[0]['start_ps'],traffic=dict(traffic),
                scope='last registered layer invocations, including their actual compulsory/reload bytes; finite trace, not stationary steady state'))
        del result
    a,b=(rows[k]['late_window'] for k in ('central-plus-two-layer','distributed-two-layer'))
    return dict(schema='w2w.cache-invocation-traffic.v1',passed=True,execution_source_commit=reg['source_commit'],analysis_source_commit=revision(),cases=rows,
        late_window_completion_reduction_percent=100*(1-b['duration_ps']/a['duration_ps']),
        limits='counts actual lookup and committed native-read events; preloads excluded; warm reference has fewer total layers; no attention/KV/numerical validation')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--audited',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--late-invocations',type=int,default=24);args=p.parse_args()
    if args.late_invocations<1:p.error('Positive late window required')
    r=analyze(args.source,args.audited,args.late_invocations);write_json(args.output,r)
    print(json.dumps(dict(passed=True,late_window_completion_reduction_percent=r['late_window_completion_reduction_percent'],
        traffic={k:v['late_window']['traffic'] for k,v in r['cases'].items()})))


if __name__=='__main__':main()
