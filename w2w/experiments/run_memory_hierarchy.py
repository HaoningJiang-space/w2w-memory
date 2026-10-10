"""Finite distributed SRAM: a whole-layer warm reference and two independent layers."""
import argparse,gzip,json,os,time
from dataclasses import asdict
from pathlib import Path
from w2w.architecture.presets.recipes import from_recipe
from w2w.architecture.compiler import compile_machine
from w2w.architecture.resources import inventory,matched_vertical_budget
from w2w.mapping.sequence import lower_sequence
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.common.io import write_json
from w2w.provenance import revision
from w2w.backends.ramulator import VerticalRWDL
from w2w.backends.booksim.adapter import factory
from w2w.system.kernel import execute_system
from w2w.system.weight_cache import WeightCacheConfig
from w2w.validation.vertical_access import audit_vertical_result
from w2w.validation.request_control import audit_request_control

CASES=('single-layer-warm','central-plus-two-layer','distributed-two-layer')


def inputs(case):
    routing=json.loads(Path('configs/workloads/two-layer-decode24.json').read_text())
    stack=from_recipe('configs/machine/v3-small.json','central' if case.startswith('central') else 'distributed')
    machine=compile_machine(stack)
    graph,meta,preload=lower_sequence(routing['token_experts'],machine,layers=1 if case=='single-layer-warm' else routing['layers'],shape=routing['shape'])
    cache=WeightCacheConfig(initial_resident=preload)
    policy=dict(ready_router_ids=tuple(r.id for r in stack.routers),ready_slots=16)
    data=dict(machine=asdict(stack),graph=asdict(graph),metadata=meta,routing=routing,resources=inventory(stack),
        cache=asdict(cache),network_policy=policy,compute_contexts=2,request_control=True,
        extra_context_bytes=64*len(stack.compute_clusters),selector_metadata_bits=16*96*len(stack.routers),
        preload_contract='All layer-0 experts are present before measurement. Report their full initial load bytes and interface lower bound separately; not a free startup.',
        cache_contract='184 MiB data plus 8592 B tag/lookup state inside each 192 MiB SRAM; LRU without lookahead; fills/in-use weights pinned; same RX/compute service')
    if case!='single-layer-warm' and meta['active_unique_weight_bytes']<=data['resources']['compute']['sram_bytes']:
        raise ValueError('Selected accessed working set does not exceed physical SRAM')
    return machine,graph,cache,data


def prepare(output):
    output.mkdir(parents=True,exist_ok=False);(output/'inputs').mkdir();records={};previous=None
    for case in CASES:
        _,_,_,data=inputs(case)
        if case!='single-layer-warm':
            if previous and any(previous[k]!=data[k] for k in ('graph','metadata','cache','network_policy','compute_contexts','routing')):
                raise ValueError('Vertical comparison changed work, mapping or cache/execution policy')
            previous=data
        with gzip.open(output/'inputs'/f'{case}.json.gz','wt') as f:json.dump(data,f)
        records[case]=dict(input_sha256=digest(data))
    proof=matched_vertical_budget(from_recipe('configs/machine/v3-small.json','central'),from_recipe('configs/machine/v3-small.json','distributed'))
    write_json(output/'registration.json',dict(schema='w2w.memory-hierarchy-study.v1',source_commit=revision(),cases=records,
        max_ps=60000000000,budget_match=proof,scope='two-layer FFN timing proxy, 24 sequential decode tokens; finite pinned cache, warm layer 0, cold layer 1'))


def run(output,case,binary):
    reg=json.loads((output/'registration.json').read_text())
    if revision()!=reg['source_commit']:raise ValueError('Frozen execution source changed')
    spec,graph,cache,data=inputs(case)
    if digest(data)!=reg['cases'][case]['input_sha256']:raise ValueError('Registered input changed')
    directory=output/'cases'/case;directory.mkdir(parents=True,exist_ok=False)
    native=VerticalRWDL(spec,request_control=True);start=time.monotonic()
    markers={i['finish_task']:i for i in data['metadata']['invocations']}
    def observe(e):
        if e['kind']=='task_finish' and e['task'] in markers:
            print(json.dumps(dict(progress=markers[e['task']],time_ps=e['time_ps'],wall_seconds=time.monotonic()-start)),flush=True)
    try:
        result=execute_system(spec,graph,native=native,time_advance='boundaries',max_ps=reg['max_ps'],
            compute_contexts=2,weight_cache=cache,event_observer=observe,
            activation_sram_read_bytes_per_cycle=spec.rx_write_bytes_per_cycle,
            network_factory=factory(binary=binary,directory=directory/'network',**data['network_policy']))
    finally:native.close()
    result['audit']=audit_vertical_result(result);result['control_audit']=audit_request_control(result)
    result['source_commit']=revision()
    with gzip.open(directory/'result.json.gz','wt',compresslevel=3) as f:json.dump(result,f)
    inv=[]
    for item in data['metadata']['invocations']:
        a=result['tasks'][item['input_task']]['start_ps'];b=result['tasks'][item['finish_task']]['finish_ps']
        inv.append(dict(**item,start_ps=a,finish_ps=b,duration_ps=b-a))
    summary=dict(complete=True,case=case,source_commit=revision(),input_sha256=digest(data),
        makespan_ps=result['makespan_ps'],makespan_us=result['makespan_ps']/1e6,drained_ps=result['drained_ps'],
        wall_seconds=time.monotonic()-start,audit=result['audit'],control_audit=result['control_audit'],
        weight_cache=result['weight_cache'],request_control=result['native']['request_control'],
        logical_weight_read_bytes=data['metadata']['logical_weight_read_bytes'],
        active_unique_weight_bytes=data['metadata']['active_unique_weight_bytes'],physical_sram_bytes=data['resources']['compute']['sram_bytes'],
        invocations=inv,hop_flits=sum(result['network']['link_flits'].values()),
        native_last_tail_ps=result['native']['native_last_tail_ps'],binary=result['network']['identity']['binary_sha256'],
        compute_execution=result['compute_execution'],compute_busy_ps=result['compute_busy_ps'],sram_peak_bytes=result['sram_peak_bytes'],
        preload_bytes=result['weight_cache']['initial_resident_bytes'],
        preload_gateway_peak_lower_bound_ps=result['weight_cache']['initial_resident_bytes']/(512/1000),
        preload_scope='lower bound only, array/commands/transport reduce sustained service; initialization is excluded from warm interval')
    if case=='single-layer-warm' and summary['audit']['native_bytes']:raise ValueError('Whole layer was warm but reread weights')
    if case!='single-layer-warm' and not summary['weight_cache']['stats'].get('reload_bytes'):raise ValueError('Capacity reload was not observed')
    write_json(directory/'completion.json',summary);print(json.dumps(summary),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--prepare',action='store_true');mode.add_argument('--case',choices=CASES)
    p.add_argument('--booksim-binary',type=Path,default=os.getenv('W2W_BOOKSIM_BINARY'));args=p.parse_args()
    if args.prepare:prepare(args.output)
    else:
        if args.booksim_binary is None:p.error('Native binary required')
        run(args.output,args.case,args.booksim_binary)

if __name__=='__main__':main()
