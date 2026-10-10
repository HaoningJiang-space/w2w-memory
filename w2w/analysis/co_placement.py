"""Saved-result audit of Up-only co-placement; no timing/traffic equality imposed."""
import argparse,gzip,hashlib,json
from collections import Counter,defaultdict
from pathlib import Path
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.common.io import write_json
from w2w.validation.co_placement import audit_co_placement_inputs,up_work_by_cluster
from w2w.validation.vertical_access import audit_vertical_result
from w2w.validation.request_control import audit_request_control
from w2w.analysis.placement_pressure import summarize_pressure
from w2w.analysis.cache_traffic import invocation_traffic
from w2w.analysis.ffn_stages import stages
from w2w.provenance import revision


def traffic_by_operand(result):
    tasks={t['id']:t for t in result['graph']['tasks']};memories={m['id']:m for m in result['spec']['memories']}
    stack=result['spec']['stack'];routers={c['id']:c['router_id'] for c in stack['compute_clusters']}
    gateways={g['id']:g['router_id'] for g in stack['gateways']};edges={e['id']:e for e in result['graph']['data']}
    stats=defaultdict(Counter);macs=Counter();read_bytes=Counter()
    for e in result['events']:
        if e['kind']=='read_deliver':
            tile=tasks[e['task']]['tile'];home=gateways[memories[e['memory']]['gateway_id']]
            row=stats['weight/'+e['task'].rsplit('/',1)[-1]]
            row['committed_bytes']+=e['bytes']
            row['remote_endpoint_payload_bytes']+=e['bytes']*(routers[tile]!=home)
        elif e['kind']=='data_deliver':
            edge=edges[e['edge']];src=tasks[edge['producer']]['tile'];dst=tasks[edge['consumer']]['tile']
            label='X/to_up' if edge['consumer'].endswith('/up') else ('U/to_activation' if edge['producer'].endswith('/up') else 'other_tensor')
            stats[label]['committed_bytes']+=e['bytes']
            stats[label]['remote_endpoint_payload_bytes']+=e['bytes']*(routers[src]!=routers[dst])
        elif e['kind']=='stream_compute':
            tile=tasks[e['task']]['tile'];macs[tile]+=e['macs'];read_bytes[tile]+=e['weight_bytes']
    return dict(operands={k:dict(v) for k,v in stats.items()},actual_macs_by_cluster=dict(macs),
        actual_stream_weight_read_bytes_by_cluster=dict(read_bytes),
        contract='Counts actually committed logical payload with different source/destination routers; not a hop count or energy. '
                 'Full executed flit distance comes separately from BookSim physical channels; input copies remain explicit per consumer.')


def analyze(source,baseline=None):
    reg=json.loads((source/'registration.json').read_text());inputs={};rows={};files={};tools=set()
    if reg['schema']!='w2w.co-placement-study.v1':raise ValueError('Unknown co-placement study')
    for case,row in reg['cases'].items():
        path=source/'inputs'/f'{case}.json.gz';inputs[case]=json.load(gzip.open(path,'rt'))
        if digest(inputs[case])!=row['input_sha256'] or digest(inputs[case]['graph'])!=row['graph_sha256']:
            raise ValueError('Frozen co-placement input changed')
    proof=audit_co_placement_inputs(inputs)
    if proof!=reg['input_audit']:raise ValueError('Registered input contract changed')
    for case,data in inputs.items():
        directory=source/'cases'/case;completion=json.loads((directory/'completion.json').read_text())
        r=json.load(gzip.open(directory/'result.json.gz','rt'))
        if (not completion['complete'] or r['source_commit']!=reg['source_commit'] or completion['source_commit']!=reg['source_commit'] or
                completion['input_sha256']!=reg['cases'][case]['input_sha256'] or r['graph']!=data['graph'] or
                r['spec']['stack']!=data['machine'] or r['makespan_ps']!=completion['makespan_ps'] or r['drained_ps']!=completion['drained_ps']):
            raise ValueError('Co-placement execution identity changed')
        a=audit_vertical_result(r);b=audit_request_control(r)
        if a!=completion['audit'] or b!=completion['control_audit']:raise ValueError('Saved conservation audit changed')
        if (r['operand_readiness']['policy']!='contiguous_prefix' or r['compute_execution']['contexts_per_cluster']!=2 or
                r['fetch_execution']['contexts_per_cluster']!=2 or r['fetch_execution']['read_issue_policy']!='round_robin' or
                r['fetch_execution']['metadata_bytes_per_cluster']!=136 or 'return_tracking' in r['fetch_execution'] or
                r['network']['source_arbiter']['routers']!=data['network_policy']['ready_router_ids']):
            raise ValueError('Compute/fetch/network policy changed')
        traffic=traffic_by_operand(r)
        if sum(traffic['actual_macs_by_cluster'].values())!=data['metadata']['macs']:raise ValueError('Arithmetic work changed')
        tools.add((r['network']['identity']['binary_sha256'],r['native']['bridge_sha256']))
        stage=stages(r);tail=stage['latest_finishing_predecessor_chain'][-20:]
        row=dict(completion,independent_passed=True,traffic=traffic,pressure=summarize_pressure(r),
            planned_up_work=[dict(cluster=c,kind=k,value=v) for (c,k),v in sorted(up_work_by_cluster(data).items())],
            sram_peak_bytes=r['sram_peak_bytes'],compute_busy_ps=r['compute_busy_ps'],context_occupancy_ps=r['engine_context_ps'],
            phases=stage['phases'],tail_dependency_tasks=tail,
            tail_projection_pairs={k:v for k,v in stage['projection_pairs'].items() if k in {t['task'].rsplit('/',1)[0] for t in tail}},
            native_last_tail_ps=r['native']['native_last_tail_ps'])
        if data['cache']:
            actual=[(e['tile'],e['object']) for e in r['events'] if e['kind']=='cache_initial_resident']
            if actual!=[tuple(v) for v in data['cache']['initial_resident']]:raise ValueError('Executed cache preload differs')
            for field in ('data_bytes_per_cluster','entries_per_cluster','lookup_slots_per_cluster','lookup_cycles'):
                if r['weight_cache'][field]!=data['cache'][field]:raise ValueError('Cache budget/service changed')
            calls=[dict(v,start_ps=r['tasks'][v['input_task']]['start_ps'],finish_ps=r['tasks'][v['finish_task']]['finish_ps']) for v in data['metadata']['invocations']]
            calls,totals=invocation_traffic(r,calls);late=calls[-24:];counts=Counter()
            for v in late:counts.update(v['traffic'])
            row.update(cache=r['weight_cache'],invocation_traffic=calls,traffic_totals=totals,
                late_window=dict(first_token=late[0]['token'],last_token=late[-1]['token'],start_ps=late[0]['start_ps'],finish_ps=late[-1]['finish_ps'],
                    duration_ps=late[-1]['finish_ps']-late[0]['start_ps'],traffic=dict(counts)))
        if case=='reference_compute' and baseline:
            from tools.check_simulator_equivalence import canonical
            old=json.load(gzip.open(baseline/'result.json.gz','rt'))
            audit_vertical_result(old);audit_request_control(old)
            if canonical(old)!=canonical(r):raise ValueError('Frozen Phase-Split reference changed complete physical record')
            row['reference_migration']=dict(passed=True,physical_record_equal=True,baseline_source=old['source_commit'],
                baseline_raw_sha256=hashlib.sha256((baseline/'result.json.gz').read_bytes()).hexdigest())
        rows[case]=row
        for path in (directory/'completion.json',directory/'result.json.gz',source/'inputs'/f'{case}.json.gz'):
            h=hashlib.sha256()
            with path.open('rb') as f:
                for chunk in iter(lambda:f.read(1024**2),b''):h.update(chunk)
            files[str(path.relative_to(source))]=dict(sha256=h.hexdigest(),bytes=path.stat().st_size)
        del r,stage
    if len(tools)!=1:raise ValueError('Native tools differ')
    if reg['mode']=='cold' and len({r['audit']['native_bytes'] for r in rows.values()})!=1:raise ValueError('Cold read work differs')
    ref=rows['reference_compute']
    if reg['mode']=='cold':
        for row in rows.values():
            for resource,field in (('gateways','payload_bytes'),('domains','atoms')):
                if ({k:v[field] for k,v in row['pressure'][resource].items()}!=
                        {k:v[field] for k,v in ref['pressure'][resource].items()}):
                    raise ValueError('Fixed cold weights changed per-Gateway/domain service work')
    if 'up_matched_nonlocal' in rows:
        for field in ('actual_macs_by_cluster','actual_stream_weight_read_bytes_by_cluster'):
            if rows['up_matched_nonlocal']['traffic'][field]!=rows['up_local_compute']['traffic'][field]:
                raise ValueError('Executed nonlocal control did not match per-cluster arithmetic/read work')
    for case,row in rows.items():
        row['completion_reduction_percent']=100*(1-row['makespan_ps']/ref['makespan_ps'])
        row['data_lane_activity_reduction_percent']=100*(1-row['pressure']['actual_data_lane_byte_um']/ref['pressure']['actual_data_lane_byte_um'])
    return dict(schema='w2w.co-placement-analysis.v1',passed=True,execution_source_commit=reg['source_commit'],analysis_source_commit=revision(),
        mode=reg['mode'],input_audit=proof,cases=rows,files=files,native_tools=list(next(iter(tools))),
        limits=['whole-matrix Up-only compute placement, no new physical hardware or numerical inference',
                'matched nonlocal fixes per-cluster work, not arbitration, critical release or input path lengths; cold diagnostic only',
                'warm Up storage is independently preloaded at its consumer; initial load is outside timing, not free migration',
                'later cache misses/reloads need not match; reported observations, not acceptance conditions',
                'byte-distance is a data-lane activity proxy, not calibrated energy/PPA; stage/context sums overlap'])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--baseline',type=Path);a=p.parse_args();d=analyze(a.source,a.baseline);write_json(a.output,d)
    print(json.dumps(dict(passed=True,mode=d['mode'],makespan_ps={k:v['makespan_ps'] for k,v in d['cases'].items()})))


if __name__=='__main__':main()
