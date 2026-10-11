"""Audit the existing-machine counterexample, independently of proposal bounds."""
import argparse,gzip,hashlib,json
from collections import Counter,defaultdict
from pathlib import Path
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.common.io import write_json
from w2w.provenance import revision
from w2w.validation.vertical_access import audit_vertical_result
from w2w.validation.request_control import audit_request_control
from w2w.validation.down_prefetch import audit_down_prefetch
from w2w.analysis.placement_pressure import summarize_pressure
from w2w.analysis.co_placement import traffic_by_operand
from w2w.analysis.ffn_stages import stages


def file_identity(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024**2),b''):h.update(b)
    return dict(sha256=h.hexdigest(),bytes=path.stat().st_size)


def down_timelines(r):
    tasks={t['id']:t for t in r['graph']['tasks']};pred=defaultdict(set)
    for e in (*r['graph']['data'],*r['graph']['control']):pred[e['consumer']].add(e['producer'])
    plan={v['task']:v for v in r.get('down_prefetch',{}).get('plan',{}).get('releases',())}
    rows={k:dict(task=k,tile=t['tile'],math_ready_ps=max([t['release_ps'],*(r['tasks'][p]['finish_ps'] for p in pred[k])]),
        compute_start_ps=r['tasks'][k]['start_ps'],compute_finish_ps=r['tasks'][k]['finish_ps'],
        bytes_committed_before_math_ready=0) for k,t in tasks.items() if k.endswith('/down') and t['stream']}
    for k,row in rows.items():
        p=plan[k]['fetch_predecessors'] if k in plan else pred[k]
        row['fetch_eligible_ps']=max([tasks[k]['release_ps'],*(r['tasks'][v]['finish_ps'] for v in p)])
    for e in r['events']:
        row=rows.get(e.get('task'))
        if row is None:continue
        at=e['time_ps'];kind=e['kind']
        if kind=='task_allocate':row['fetch_admitted_ps']=at
        elif kind=='read_issue':
            row.setdefault('first_descriptor_ps',at);row['last_descriptor_ps']=at
        elif kind=='read_deliver':
            row.setdefault('first_weight_commit_ps',at);row['all_weight_committed_ps']=at
            if at<row['math_ready_ps']:row['bytes_committed_before_math_ready']+=e['bytes']
    for row in rows.values():
        row['fetch_admission_wait_ps']=row['fetch_admitted_ps']-row['fetch_eligible_ps']
        row['allocation_lead_before_math_ps']=max(0,row['math_ready_ps']-row['fetch_admitted_ps'])
        if row['fetch_admission_wait_ps']<0 or row['compute_start_ps']<row['math_ready_ps']:
            raise ValueError('Illegal fetch/compute release')
    return dict(tasks=rows,early_admitted=sum(v['allocation_lead_before_math_ps']>0 for v in rows.values()),
        bytes_committed_before_math_ready=sum(v['bytes_committed_before_math_ready'] for v in rows.values()),
        contract='Mathematical ready uses original producer completion; actual H delivery is additionally checked by the system audit. '
            'Fetch interval overlaps and summed leads are observations, not exclusive critical-path stall or saved makespan.')


def analyze(source,baseline):
    reg=json.loads((source/'registration.json').read_text());rows={};files={};inputs={};tools=set();work={}
    if reg['schema']!='w2w.domain-organization-foil.v1' or set(reg['cases'])!={'up-local','up-local-down-prefetch'}:
        raise ValueError('Unknown controlled foil')
    for case,registered in reg['cases'].items():
        path=source/'inputs'/f'{case}.json.gz';data=json.load(gzip.open(path,'rt'));inputs[case]=data
        if digest(data)!=registered['input_sha256'] or digest(data['graph'])!=registered['graph_sha256']:
            raise ValueError('Frozen input changed')
        directory=source/'cases'/case;c=json.loads((directory/'completion.json').read_text())
        r=json.load(gzip.open(directory/'result.json.gz','rt'))
        if (not c['complete'] or c['source_commit']!=reg['source_commit'] or r['source_commit']!=reg['source_commit']
                or c['input_sha256']!=registered['input_sha256'] or r['graph']!=data['graph']
                or r['spec']['stack']!=data['machine'] or c['makespan_ps']!=r['makespan_ps'] or c['drained_ps']!=r['drained_ps']):
            raise ValueError('Execution identity changed')
        a=audit_vertical_result(r);b=audit_request_control(r)
        if a!=c['audit'] or b!=c['control_audit']:raise ValueError('Conservation audit changed')
        if (r['compute_execution']['contexts_per_cluster']!=2 or r['fetch_execution']['contexts_per_cluster']!=2
                or r['fetch_execution']['read_issue_policy']!='round_robin' or r['fetch_execution']['metadata_bytes_per_cluster']!=136
                or 'return_tracking' in r['fetch_execution'] or 'weight_cache' in r
                or r['operand_readiness']['policy']!='contiguous_prefix'
                or r['network']['source_arbiter']['routers']!=data['network_policy']['ready_router_ids']):
            raise ValueError('Existing shared-service policy changed')
        if case=='up-local-down-prefetch':
            p=audit_down_prefetch(r)
            if p!=c['prefetch_audit'] or r['down_prefetch']['plan']!=data['down_prefetch_plan']:
                raise ValueError('Down association audit/input changed')
        elif 'down_prefetch' in r or data['down_prefetch_plan'] is not None:raise ValueError('Reference has new policy')
        traffic=traffic_by_operand(r);pressure=summarize_pressure(r)
        if sum(traffic['actual_macs_by_cluster'].values())!=data['metadata']['macs']:raise ValueError('Logical arithmetic changed')
        requests=Counter((e['task'],e['memory'],e['bank'],e['word_address'],e['bytes']) for e in r['events'] if e['kind']=='read_issue')
        work[case]=dict(requests=requests,domains={k:v['atoms'] for k,v in pressure['domains'].items()},
            gateways={k:v['payload_bytes'] for k,v in pressure['gateways'].items()},traffic=traffic)
        tools.add((r['network']['identity']['binary_sha256'],r['native']['bridge_sha256']))
        rows[case]=dict(c,independent_passed=True,pressure=pressure,traffic=traffic,down=down_timelines(r),
            sram_peak_bytes=r['sram_peak_bytes'],compute_busy_ps=r['compute_busy_ps'],
            context_occupancy_ps=r['engine_context_ps'],native_last_tail_ps=r['native']['native_last_tail_ps'])
        stage=stages(r)
        last_down=max(rows[case]['down']['tasks'],key=lambda k:r['tasks'][k]['finish_ps'])
        prefix=last_down[:-4]
        rows[case]['last_down_block']={k:stage['tasks'][k] for k in tasks_in_block(r['graph'],prefix)}
        del stage
        if case=='up-local':
            from tools.check_simulator_equivalence import canonical
            old=json.load(gzip.open(baseline/'result.json.gz','rt'));audit_vertical_result(old);audit_request_control(old)
            if canonical(old)!=canonical(r):raise ValueError('Default execution changed the full frozen physical record')
            rows[case]['migration']=dict(passed=True,physical_record_equal=True,baseline_source=old['source_commit'],
                baseline_raw=file_identity(baseline/'result.json.gz'))
            del old
        for path in (source/'inputs'/f'{case}.json.gz',directory/'result.json.gz',directory/'completion.json'):
            files[str(path.relative_to(source))]=file_identity(path)
        del r
    if len(tools)!=1 or work['up-local']!=work['up-local-down-prefetch']:
        raise ValueError('Native tools, addresses, physical-domain service work or actual arithmetic/committed traffic differ')
    if any(inputs['up-local'][k]!=inputs['up-local-down-prefetch'][k] for k in ('graph','weights','machine','metadata','cache','network_policy')):
        raise ValueError('Mathematics, placement, physical machine or shared policy changed')
    ref=rows['up-local']['makespan_ps'];candidate=rows['up-local-down-prefetch']
    candidate['completion_reduction_percent']=100*(1-candidate['makespan_ps']/ref)
    return dict(schema='w2w.domain-organization-foil-analysis.v1',passed=True,
        execution_source_commit=reg['source_commit'],analysis_source_commit=revision(),cases=rows,files=files,
        same_requests_addresses_and_resource_work=True,native_tools=list(next(iter(tools))),
        limits=['Current 16-cluster cold whole-matrix foil, not an executable 128-domain machine or numeric inference.',
            'Two coupled fetch slots and contexts conserved; 8 B/cluster extra association and full Down SRAM storage charged.',
            'Native row statistics can change with request order; no ACT/PRE command trace equivalence claimed for the intervention.',
            'Valid negative performance is retained. This single spare-slot policy does not rule out all whole-matrix schedulers.',
            'NoC byte-distance and resource work are uncalibrated proxies, not measured energy/PPA.'])


def tasks_in_block(graph,prefix):
    return [t['id'] for t in graph['tasks'] if t['id'].rsplit('/',1)[0]+'/'==prefix]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--baseline',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    r=analyze(a.source,a.baseline);write_json(a.output,r)
    print(json.dumps(dict(passed=True,makespan_ps={k:v['makespan_ps'] for k,v in r['cases'].items()})))


if __name__=='__main__':main()
