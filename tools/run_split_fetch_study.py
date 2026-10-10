#!/usr/bin/env python3
"""Three finite matrix controllers on the frozen release/placement fixture."""
import argparse,gzip,hashlib,json,os,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.run_fetch_factor_probe import inputs as factor_inputs
from tools.check_simulator_equivalence import canonical
from w2w.common.io import write_json
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.provenance import revision
from w2w.backends.ramulator import VerticalRWDL
from w2w.backends.booksim.adapter import factory
from w2w.system.kernel import execute_system
from w2w.validation.vertical_access import audit_vertical_result
from w2w.validation.request_control import audit_request_control
from w2w.validation.return_tracking import audit_return_tracking
from w2w.analysis.ffn_stages import stages
from w2w.analysis.placement_pressure import summarize_pressure
from w2w.analysis.service_bounds import service_bounds

CONTROLLERS={'coupled2':dict(issue=2,returns=0,control_bytes=136),
             'coupled3':dict(issue=3,returns=0,control_bytes=200),
             'split2r3':dict(issue=2,returns=3,control_bytes=440)}
CASES={f'{policy}-{controller}':(policy,controller) for policy in ('reference','hybrid','phase-split') for controller in CONTROLLERS}


def inputs(case):
    policy,controller=CASES[case];spec,graph,meta,data=factor_inputs('d1-round_robin-'+policy)
    if controller!='coupled2':data=dict(data,fetch_controller=CONTROLLERS[controller])
    return spec,graph,meta,data


def prepare(root):
    root.mkdir(exist_ok=False);(root/'logs').mkdir();rows={}
    for case in CASES:
        _,graph,meta,data=inputs(case)
        rows[case]=dict(input_sha256=digest(data),graph_sha256=digest(data['graph']),settings=CONTROLLERS[CASES[case][1]])
    write_json(root/'registration.json',dict(schema='w2w.split-fetch-study.v1',source_commit=revision(),cases=rows,
        contract='The same fixed two-expert, hidden1024/intermediate1536, D1+round-robin fixture and full catalog as the 12-case probe. '
            'Same math/placement for each controller intervention, same domains, HB, gateways, two compute contexts, issue width2/outstanding32 and prefix operands. '
            'Split has two 64 B issue contexts, three 16 B associations and an additional 32x8 B descriptor-binding table: 440 B/cluster; '
            'coupled2/3 selector state is 136/200 B. Prefix bitmaps and full matrix SRAM are separately funded and remain live. '
            'These are conservative declared control-state bytes, not transistor area; common NI/request metadata is not calibrated. '
            'No cache, fragment, Down prefetch, new physical topology or performance-driven retry.'))


def run_case(root,case,binary):
    reg=json.loads((root/'registration.json').read_text());spec,graph,meta,data=inputs(case)
    if revision()!=reg['source_commit'] or digest(data)!=reg['cases'][case]['input_sha256']:raise ValueError('Frozen source/input changed')
    setting=CONTROLLERS[CASES[case][1]];d=root/'cases'/case;d.mkdir(parents=True,exist_ok=False);start=time.monotonic()
    native=VerticalRWDL(spec,refresh=True,request_control=True,gateway_trace_bin_ps=100000)
    try:
        r=execute_system(spec,graph,native=native,compute_contexts=2,fetch_contexts=setting['issue'],return_contexts=setting['returns'],
            read_issue_policy='round_robin',operand_readiness='contiguous_prefix',activation_sram_read_bytes_per_cycle=128,
            time_advance='boundaries',max_ps=1000000000,
            network_factory=factory(binary=binary,directory=d/'network',ready_router_ids=tuple(x.id for x in spec.routers),ready_slots=16))
    finally:native.close()
    r['source_commit']=revision();r['input_sha256']=digest(data)
    a=audit_vertical_result(r);b=audit_request_control(r)
    if sum(e.get('macs',0) for e in r['events'] if e['kind']=='stream_compute')!=meta['macs']:raise ValueError('Controller changed arithmetic work')
    with gzip.open(d/'result.json.gz','wt',compresslevel=3) as f:json.dump(r,f)
    write_json(d/'completion.json',dict(complete=True,source_commit=revision(),input_sha256=digest(data),makespan_ps=r['makespan_ps'],
        wall_seconds=time.monotonic()-start,audit=a,control_audit=b))
    print(json.dumps(dict(case=case,complete=True,makespan_ps=r['makespan_ps'])),flush=True)


def analyze(root,baseline):
    reg=json.loads((root/'registration.json').read_text());cases={};tools=set();work=set()
    for case,row in reg['cases'].items():
        spec,graph,meta,data=inputs(case);d=root/'cases'/case;raw=d/'result.json.gz';completion=json.loads((d/'completion.json').read_text())
        with gzip.open(raw,'rt') as f:r=json.load(f)
        if (not completion['complete'] or digest(data)!=row['input_sha256'] or r['source_commit']!=reg['source_commit'] or
                r['input_sha256']!=row['input_sha256'] or digest(r['graph'])!=row['graph_sha256'] or
                digest(r['spec']['stack'])!=digest(data['machine']) or r['makespan_ps']!=completion['makespan_ps']):raise ValueError('Saved identity differs')
        a=audit_vertical_result(r);b=audit_request_control(r);setting=CONTROLLERS[CASES[case][1]]
        if a!=completion['audit'] or b!=completion['control_audit']:raise ValueError('Saved independent resource audit differs')
        if r['fetch_execution']['contexts_per_cluster']!=setting['issue'] or r['fetch_execution']['read_issue_policy']!='round_robin':raise ValueError('Issue policy differs')
        return_audit=audit_return_tracking(r) if setting['returns'] else None
        paid=r['fetch_execution']['metadata_bytes_per_cluster']+(r['fetch_execution'].get('return_tracking',{}).get('metadata_bytes_per_cluster',0))
        if paid!=setting['control_bytes']:raise ValueError('Return table/control state was not fully funded')
        if r['compute_execution']['contexts_per_cluster']!=2 or sum(e.get('macs',0) for e in r['events'] if e['kind']=='stream_compute')!=meta['macs']:
            raise ValueError('Controller duplicated arithmetic')
        tools.add((r['network']['identity']['binary_sha256'],r['native']['bridge_sha256']));work.add((a['native_bytes'],a['tasks'],a['physical_domains'],meta['macs']))
        stage=stages(r);times={}
        issue_release={e['task']:e['time_ps'] for e in r['events'] if e['kind']=='fetch_context_release'}
        for key,value in stage['tasks'].items():
            if not next(t['reads'] for t in r['graph']['tasks'] if t['id']==key):continue
            m=value['milestones'];times[key]=dict(eligible_ps=m['dependency_ready'],admitted_ps=m['allocate'],
                last_issue_ps=m['read_issue_last'],operand_committed_ps=m['read_deliver_last'],issue_context_released_ps=issue_release[key])
        migration=None
        if CASES[case][1]=='coupled2':
            path=baseline/'cases'/('d1-round_robin-'+CASES[case][0])/'result.json.gz'
            with gzip.open(path,'rt') as f:old=json.load(f)
            if canonical(old)!=canonical(r):raise ValueError('Coupled reference changed any complete physical record')
            migration=dict(passed=True,physical_record_equal=True,events=len(r['events']))
        cases[case]=dict(makespan_ps=r['makespan_ps'],independent_passed=True,raw_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),
            audit=a,control_audit=b,return_audit=return_audit,control_metadata_bytes_per_cluster=paid,reference_migration=migration,
            matrix_times=times,bounds=service_bounds(r),pressure=summarize_pressure(r),sram_peak_bytes=r['sram_peak_bytes'],fetch_execution=r['fetch_execution'])
    if len(work)!=1 or len(tools)!=1:raise ValueError('Controller gate changed native work or tools')
    return dict(schema='w2w.split-fetch-analysis.v1',passed=True,execution_source_commit=reg['source_commit'],analysis_source_commit=revision(),
        native_tools=list(next(iter(tools))),cases=cases,contract=reg['contract'])


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.add_mutually_exclusive_group(required=True);a.add_argument('--prepare',action='store_true');a.add_argument('--run',action='store_true')
    a.add_argument('--case',choices=CASES);a.add_argument('--analyze',action='store_true')
    p.add_argument('--baseline',type=Path);p.add_argument('--booksim-binary',type=Path,default=os.getenv('W2W_BOOKSIM_BINARY'));args=p.parse_args()
    if args.prepare:prepare(args.output)
    elif args.case:run_case(args.output,args.case,args.booksim_binary)
    elif args.run:
        for case in json.loads((args.output/'registration.json').read_text())['cases']:
            with (args.output/'logs'/f'{case}.log').open('xb') as log:
                subprocess.run([sys.executable,__file__,'--output',str(args.output),'--case',case,'--booksim-binary',str(args.booksim_binary)],stdout=log,stderr=subprocess.STDOUT,check=True)
            print(json.dumps(dict(case=case,complete=True)),flush=True)
        if args.baseline is None:raise ValueError('Frozen reference archive required for migration')
        write_json(args.output/'analysis.json',analyze(args.output,args.baseline))
        print(json.dumps(dict(complete=True,independent_passed=True)),flush=True)
    else:write_json(args.output/'independent-readback.json',analyze(args.output,args.baseline))


if __name__=='__main__':main()
