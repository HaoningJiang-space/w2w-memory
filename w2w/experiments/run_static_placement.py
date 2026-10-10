"""Memory-only locality/balance study with frozen compute and SRAM preload."""
import argparse,gzip,json,os,time
from dataclasses import asdict
from pathlib import Path
from w2w.architecture.presets.recipes import from_recipe
from w2w.architecture.compiler import compile_machine
from w2w.architecture.resources import inventory
from w2w.workloads.routing_input import load_workload
from w2w.workloads.moe import build_moe
from w2w.mapping.static_weights import static_weights,POLICIES,ABLATIONS,CANDIDATES
from w2w.mapping.compute_placement import place_compute
from w2w.mapping.lowering import lower
from w2w.mapping.sequence import lower_sequence
from w2w.analysis.placement_screen import screen
from w2w.common.io import write_json
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.provenance import revision
from w2w.backends.ramulator import VerticalRWDL
from w2w.backends.booksim.adapter import factory
from w2w.system.kernel import execute_system
from w2w.system.weight_cache import WeightCacheConfig
from w2w.validation.vertical_access import audit_vertical_result
from w2w.validation.request_control import audit_request_control


def inputs(policy,mode,execution='s0'):
    if execution not in ('s0','s1'):raise ValueError('Unknown FFN dependency policy')
    machine=compile_machine(from_recipe('configs/machine/v3-small.json','distributed'))
    logical=load_workload('configs/workloads/c0_b1.json')
    reference=static_weights(logical,machine.stack,'reference');weights=static_weights(logical,machine.stack,policy)
    placement=place_compute(logical,machine.stack,reference)
    cache=None
    if mode=='cold':graph,meta=lower(logical,machine,weights,placement,execution_policy=execution)
    elif mode=='multilayer':
        routing=json.loads(Path('configs/workloads/two-layer-decode24.json').read_text())
        catalog=build_moe((routing['token_experts'][0],),**routing['shape'])
        reference=static_weights(catalog,machine.stack,'reference');weights=static_weights(catalog,machine.stack,policy)
        graph,meta,preload=lower_sequence(routing['token_experts'],machine,layers=routing['layers'],shape=routing['shape'],
            weight_layout=weights,compute_reference=reference,execution_policy=execution)
        cache=WeightCacheConfig(initial_resident=preload)
        if meta['active_unique_weight_bytes']<=sum(t.sram_bytes for t in machine.tiles):raise ValueError('Multilayer working set does not exceed physical SRAM')
    else:raise ValueError('Unknown placement workload mode')
    network=dict(ready_router_ids=tuple(sorted(r.id for r in machine.routers)),ready_slots=16)
    record=dict(machine=asdict(machine.stack),graph=asdict(graph),metadata=meta,weights=[asdict(w) for w in weights],
        compute_reference_weights=[asdict(w) for w in reference],
        cache=None if cache is None else asdict(cache),network_policy=network,resources=inventory(machine.stack),
        compute_contexts=2,operand_readiness='contiguous_prefix',refresh=True,request_control=True,
        policy=policy,mode=mode,
        static_policy_contract='complete catalog only; no evaluation routing, activity or future cache state used by placement; compute and initial SRAM follow immutable reference weights')
    if mode=='cold':record['screen']=screen(machine,graph,meta)
    else:record['routing']=routing
    if execution=='s1':record['fetch_policy']=dict(contexts_per_cluster=2,read_issue_policy='round_robin',metadata_bytes_per_cluster=136)
    return machine,graph,cache,record


def prepare(output,mode,policies,reference_case='reference',execution='s0'):
    if reference_case not in policies:raise ValueError('Comparison reference must be registered')
    if any(p in ABLATIONS for p in policies):
        if mode!='cold' or set(policies)!=set(('hybrid',*ABLATIONS)) or reference_case!='hybrid':
            raise ValueError('Controlled gate/up intervention requires a cold Hybrid pair')
    output.mkdir(parents=True,exist_ok=False);(output/'inputs').mkdir()
    rows={};first=None;signatures={};aliases={}
    for policy in policies:
        _,graph,_,data=inputs(policy,mode,execution)
        invariant=dict(tasks=asdict(graph)['tasks'],data=asdict(graph)['data'],control=asdict(graph)['control'],
            cache=data['cache'],compute_reference=data['compute_reference_weights'],resources=data['resources'],network=data['network_policy'])
        if 'fetch_policy' in data:invariant['fetch_policy']=data['fetch_policy']
        if first is not None and invariant!=first:raise ValueError('Memory-only comparison remapped compute, cache or resources')
        first=invariant
        signature=digest(data['weights'])
        if signature in signatures:aliases[policy]=signatures[signature]
        else:signatures[signature]=policy
        with gzip.open(output/'inputs'/f'{policy}.json.gz','wt') as f:json.dump(data,f)
        rows[policy]=dict(input_sha256=digest(data),weight_layout_sha256=signature,
            screen=data.get('screen'),alias_of=aliases.get(policy))
    if any(p in ABLATIONS for p in policies):
        baseline=json.load(gzip.open(output/'inputs/hybrid.json.gz','rt'))
        changed=json.load(gzip.open(output/'inputs/hybrid-gate-up-striped.json.gz','rt'))
        down=lambda data:[w for w in data['weights'] if w['tensor'].endswith('/down')]
        if down(baseline)!=down(changed):raise ValueError('Ablation changed frozen down layout')
    write_json(output/'registration.json',dict(schema='w2w.static-placement-study.v1',source_commit=revision(),mode=mode,
        reference_case=reference_case,execution=execution,
        cases=rows,fixed_invariants_sha256=digest(first),max_ps=60000000000 if mode=='multilayer' else 6000000000,
        selection_contract='cold screening after catalog-only placement is frozen; full executions decide performance; no candidate selected using the multilayer trace',
        scope='fixed distributed vertical architecture, memory-only weight layout; FFN timing proxy, not a numerical or complete Transformer evaluation'))


def run(output,case,binary):
    reg=json.loads((output/'registration.json').read_text())
    machine,graph,cache,data=inputs(case,reg['mode'],reg.get('execution','s0'))
    if revision()!=reg['source_commit'] or digest(data)!=reg['cases'][case]['input_sha256']:raise ValueError('Registered source or input changed')
    if reg['cases'][case]['alias_of']:raise ValueError('Equivalent layout is an alias; do not duplicate simulation')
    directory=output/'cases'/case;directory.mkdir(parents=True,exist_ok=False)
    trace_bin=1000000 if reg.get('execution')=='s1' or case in CANDIDATES else 0
    native=VerticalRWDL(machine,request_control=True,refresh=True,gateway_trace_bin_ps=trace_bin);start=time.monotonic()
    markers={v['finish_task']:v for v in data['metadata'].get('invocations',())}
    def observe(e):
        if e['kind']=='task_finish' and (e['task'] in markers or e['task'].endswith('/accumulate')):
            print(json.dumps(dict(task=e['task'],invocation=markers.get(e['task']),time_ps=e['time_ps'],wall_seconds=time.monotonic()-start)),flush=True)
    try:
        result=execute_system(machine,graph,native=native,compute_contexts=2,operand_readiness='contiguous_prefix',
            fetch_contexts=data.get('fetch_policy',{}).get('contexts_per_cluster',0),
            read_issue_policy=data.get('fetch_policy',{}).get('read_issue_policy','ordered'),
            weight_cache=cache,event_observer=observe,time_advance='boundaries',max_ps=reg['max_ps'],
            activation_sram_read_bytes_per_cycle=machine.rx_write_bytes_per_cycle,
            network_factory=factory(binary=binary,directory=directory/'network',**data['network_policy']))
    finally:native.close()
    result['source_commit']=revision();result['audit']=audit_vertical_result(result);result['control_audit']=audit_request_control(result)
    with gzip.open(directory/'result.json.gz','wt',compresslevel=3) as f:json.dump(result,f)
    summary=dict(complete=True,source_commit=revision(),input_sha256=digest(data),case=case,mode=reg['mode'],
        makespan_ps=result['makespan_ps'],drained_ps=result['drained_ps'],wall_seconds=time.monotonic()-start,
        audit=result['audit'],control_audit=result['control_audit'],compute_busy_ps=result['compute_busy_ps'],
        gateway_bytes=result['native']['gateway_bytes'],domain_atoms=result['native']['channel_atoms'],
        gateway_busy_cycles=result['native']['gateway_busy_cycles'],gateway_peak_bytes=result['native']['gateway_queue_peak_bytes'],
        hop_flits=sum(result['network']['link_flits'].values()),rx_write_cycles=result['network']['rx_write_cycles'],
        native_last_tail_ps=result['native']['native_last_tail_ps'],sram_peak_bytes=result['sram_peak_bytes'],
        booksim_sha256=result['network']['identity']['binary_sha256'],bridge_sha256=result['native']['bridge_sha256'])
    if cache:summary['cache_stats']=result['weight_cache']['stats']
    write_json(directory/'completion.json',summary);print(json.dumps(summary),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    action=p.add_mutually_exclusive_group(required=True);action.add_argument('--prepare',action='store_true');action.add_argument('--case',choices=POLICIES+ABLATIONS+CANDIDATES)
    p.add_argument('--mode',choices=('cold','multilayer'),default='cold');p.add_argument('--policies',nargs='+',choices=POLICIES+ABLATIONS+CANDIDATES,default=list(POLICIES))
    p.add_argument('--reference-case',choices=POLICIES+CANDIDATES,default='reference');p.add_argument('--execution',choices=('s0','s1'),default='s0')
    p.add_argument('--booksim-binary',type=Path,default=os.getenv('W2W_BOOKSIM_BINARY'));args=p.parse_args()
    if args.prepare:prepare(args.output,args.mode,args.policies,args.reference_case,args.execution)
    elif args.booksim_binary:run(args.output,args.case,args.booksim_binary)
    else:p.error('Native BookSim binary required')


if __name__=='__main__':main()
