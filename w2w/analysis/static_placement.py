"""Independent raw audit of fixed-compute, fixed-preload memory-only placement."""
import argparse,gzip,hashlib,json
from pathlib import Path
from w2w.common.io import write_json
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.validation.vertical_access import audit_vertical_result
from w2w.validation.request_control import audit_request_control
from w2w.analysis.cache_traffic import invocation_traffic
from w2w.analysis.placement_pressure import summarize_pressure
from w2w.provenance import revision


def analyze(source):
    reg=json.loads((source/'registration.json').read_text());rows={};inputs={};files={};first=None;catalog=None
    if reg['schema']!='w2w.static-placement-study.v1':raise ValueError('Unknown placement registration')
    # JSON writers sort keys; an alias may precede its target in the file.
    for case,registered in sorted(reg['cases'].items(),key=lambda item:bool(item[1]['alias_of'])):
        data=json.load(gzip.open(source/'inputs'/f'{case}.json.gz','rt'))
        if digest(data)!=registered['input_sha256']:raise ValueError('Input identity changed')
        graph=data['graph'];invariant=dict(tasks=graph['tasks'],data=graph['data'],control=graph['control'],
            cache=data['cache'],compute_reference=data['compute_reference_weights'],resources=data['resources'],network=data['network_policy'])
        if digest(invariant)!=reg['fixed_invariants_sha256'] or (first is not None and first!=invariant):raise ValueError('Memory-only invariant changed')
        first=invariant;inputs[case]=data
        identity=[(o['id'],o['size_bytes'],o['storage_id']) for o in graph['objects']]
        if catalog is not None and catalog!=identity:raise ValueError('Placement changed catalog content or storage identity')
        catalog=identity
        if registered['alias_of']:
            if data['weights']!=inputs[registered['alias_of']]['weights']:raise ValueError('False duplicate-placement alias')
            continue
        directory=source/'cases'/case
        completion=json.loads((directory/'completion.json').read_text())
        with gzip.open(directory/'result.json.gz','rt') as f:r=json.load(f)
        if (not completion['complete'] or r['source_commit']!=reg['source_commit'] or completion['source_commit']!=reg['source_commit'] or
                r['graph']!=data['graph'] or r['spec']['stack']!=data['machine'] or
                r['makespan_ps']!=completion['makespan_ps'] or completion['input_sha256']!=registered['input_sha256']):
            raise ValueError('Source, work or completion identity changed')
        a=audit_vertical_result(r);b=audit_request_control(r)
        if a!=completion['audit'] or b!=completion['control_audit']:raise ValueError('Independent physical conservation failed')
        if (r['operand_readiness']['policy']!='contiguous_prefix' or r['compute_execution']['contexts_per_cluster']!=2 or
                r['network']['source_arbiter']['routers']!=data['network_policy']['ready_router_ids'] or
                sum(e.get('macs',0) for e in r['events'] if e['kind']=='stream_compute')!=data['metadata']['macs']):
            raise ValueError('Execution policy or arithmetic work changed')
        row=dict(completion,independent_passed=True)
        row['necessary_executed_service_ps']=dict(native_interface=max(r['native']['channel_atoms'].values())*r['native']['tck_ps'],
            gateway_payload=max((v*1000//next(g['data_bytes_per_cycle'] for g in data['machine']['gateways'] if g['id']==k)
                for k,v in r['native']['gateway_bytes'].items()),default=0),
            receiver_write=max(r['network']['rx_write_cycles'].values(),default=0)*r['spec']['noc_period_ps'],
            busiest_channel=max(r['network']['link_flits'].values(),default=0)*r['spec']['noc_period_ps'],
            compute_arithmetic=max(r['compute_busy_ps'].values(),default=0))
        row['source_pressure']=r['network']['final']['source_pressure_nodes']
        row['executed_pressure']=summarize_pressure(r)
        if data['cache'] is not None:
            initial=[(e['tile'],e['object']) for e in r['events'] if e['kind']=='cache_initial_resident']
            if initial!=[tuple(v) for v in data['cache']['initial_resident']]:raise ValueError('Initial cache residency changed')
            for field in ('data_bytes_per_cluster','entries_per_cluster','lookup_slots_per_cluster','lookup_cycles'):
                if r['weight_cache'][field]!=data['cache'][field]:raise ValueError('Cache service or capacity changed')
            invocations=[dict(v,start_ps=r['tasks'][v['input_task']]['start_ps'],finish_ps=r['tasks'][v['finish_task']]['finish_ps'])
                for v in data['metadata']['invocations']]
            per_call,totals=invocation_traffic(r,invocations);late=per_call[-24:]
            from collections import Counter
            traffic=Counter()
            for v in late:traffic.update(v['traffic'])
            row.update(invocation_traffic=per_call,traffic_totals=totals,
                late_window=dict(first_token=late[0]['token'],last_token=late[-1]['token'],
                    start_ps=late[0]['start_ps'],finish_ps=late[-1]['finish_ps'],
                    duration_ps=late[-1]['finish_ps']-late[0]['start_ps'],traffic=dict(traffic)))
        rows[case]=row
        for path in (directory/'completion.json',directory/'result.json.gz',source/'inputs'/f'{case}.json.gz'):
            h=hashlib.sha256()
            with path.open('rb') as f:
                for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
            files[str(path.relative_to(source))]=dict(bytes=path.stat().st_size,sha256=h.hexdigest())
    if len({(r['booksim_sha256'],r['bridge_sha256']) for r in rows.values()})!=1:raise ValueError('Placement cases used different native tools')
    if reg['mode']=='cold' and len({r['audit']['native_bytes'] for r in rows.values()})!=1:raise ValueError('Cold placement changed read work')
    reference_case=reg.get('reference_case','reference')
    if reference_case not in rows:raise ValueError('Registered comparison reference is not executed')
    if 'hybrid-gate-up-striped' in rows:
        down=lambda case:[w for w in inputs[case]['weights'] if w['tensor'].endswith('/down')]
        if reference_case!='hybrid' or down('hybrid')!=down('hybrid-gate-up-striped'):
            raise ValueError('Controlled comparison changed Hybrid down physical addresses')
    reference=rows[reference_case]['makespan_ps']
    for case,row in rows.items():row['completion_reduction_vs_reference_percent']=100*(1-row['makespan_ps']/reference)
    selected=min((k for k in rows if k!=reference_case),key=lambda k:(rows[k]['makespan_ps'],k)) if len(rows)>1 else reference_case
    return dict(schema='w2w.static-placement-analysis.v1',passed=True,execution_source_commit=reg['source_commit'],analysis_source_commit=revision(),
        mode=reg['mode'],reference_case=reference_case,cases=rows,files=files,selected_nonreference=selected,best_overall=min(rows,key=lambda k:rows[k]['makespan_ps']),
        aliases={k:v['alias_of'] for k,v in reg['cases'].items() if v['alias_of']},
        limits=['catalog-only static policies; no dynamic mapping or optimality claim','same compute and initial cache does not guarantee same later misses: report observed traffic',
            'FFN-only timing proxy and declared physical resource budgets; not calibrated PPA','service/pressure counters overlap and are not an additive stall decomposition'])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=analyze(a.source);write_json(a.output,r)
    print(json.dumps(dict(passed=True,makespan_ps={k:v['makespan_ps'] for k,v in r['cases'].items()},best_overall=r['best_overall'],selected_nonreference=r['selected_nonreference'])))


if __name__=='__main__':main()
