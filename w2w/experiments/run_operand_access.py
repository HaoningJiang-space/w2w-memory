"""Frozen full-size cold FFN pair with paid contiguous operands and command/ACK."""
import argparse,gzip,json,time,os
from pathlib import Path
from dataclasses import asdict
from w2w.architecture.presets.recipes import from_recipe
from w2w.architecture.compiler import compile_machine
from w2w.architecture.resources import inventory,matched_vertical_budget
from w2w.workloads.routing_input import load_workload
from w2w.mapping.data_placement import place_weights
from w2w.mapping.compute_placement import place_compute
from w2w.mapping.lowering import lower
from w2w.common.io import write_json
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.provenance import revision
from w2w.backends.ramulator import VerticalRWDL
from w2w.backends.booksim.adapter import factory
from w2w.system.kernel import execute_system
from w2w.validation.vertical_access import audit_vertical_result
from w2w.validation.request_control import audit_request_control

CASES=('central-plus','distributed')


def inputs(case):
    if case not in CASES:raise ValueError('Unknown paired access case')
    logical=load_workload('configs/workloads/c0_b1.json')
    stack=from_recipe('configs/machine/v3-small.json','central' if case=='central-plus' else 'distributed')
    machine=compile_machine(stack);weights=place_weights(logical,stack);placement=place_compute(logical,stack,weights)
    graph,meta=lower(logical,machine,weights,placement)
    data=dict(machine=asdict(stack),logical=asdict(logical),graph=asdict(graph),metadata=meta,
        weights=[asdict(w) for w in weights],placement=[asdict(p) for p in placement],resources=inventory(stack),
        operand_readiness='contiguous_prefix',request_control=True,refresh=True,compute_contexts=2,
        cache=None,network_policy=dict(ready_router_ids=tuple(sorted(r.id for r in stack.routers)),ready_slots=16),
        selector_bits=len(stack.routers)*16*96,
        scope='one cold full-size routed FFN, one archived decode token, eight selected experts; not multi-layer Transformer or numerical inference')
    return machine,graph,data


def prepare(output):
    output.mkdir(parents=True,exist_ok=False);(output/'inputs').mkdir();cases={};records={}
    for case in CASES:
        machine,_,data=inputs(case);records[case]=data
        write_json(output/'inputs'/f'{case}.json',data);cases[case]=dict(input_sha256=digest(data))
    a,b=(records[k] for k in CASES)
    for key in ('logical','weights','placement','graph','metadata','operand_readiness','request_control','refresh','compute_contexts','cache','network_policy','selector_bits'):
        if a[key]!=b[key]:raise ValueError('Access pair changed work or execution contract')
    proof=matched_vertical_budget(from_recipe('configs/machine/v3-small.json','central'),from_recipe('configs/machine/v3-small.json','distributed'))
    write_json(output/'registration.json',dict(schema='w2w.operand-access-pair.v1',source_commit=revision(),cases=cases,
        budget_match=proof,max_ps=3000000000,scope=a['scope'],
        contract='same full-size graph/addresses/placement; two shared-service contexts; finite 16-entry admission-priority selector at every router; contiguous matrix descriptors; physical command/ACK and refresh; no cache'))


def run(output,case,binary):
    reg=json.loads((output/'registration.json').read_text());spec,graph,data=inputs(case)
    if revision()!=reg['source_commit'] or digest(data)!=reg['cases'][case]['input_sha256']:
        raise ValueError('Registered source or paired input changed')
    directory=output/'cases'/case;directory.mkdir(parents=True,exist_ok=False)
    native=VerticalRWDL(spec,request_control=True,refresh=True);start=time.monotonic()
    def progress(e):
        if e['kind']=='task_finish' and e['task'].endswith('/accumulate'):
            print(json.dumps(dict(case=case,task=e['task'],time_ps=e['time_ps'],wall_seconds=time.monotonic()-start)),flush=True)
    try:
        r=execute_system(spec,graph,native=native,compute_contexts=2,operand_readiness='contiguous_prefix',
            activation_sram_read_bytes_per_cycle=spec.rx_write_bytes_per_cycle,time_advance='boundaries',max_ps=reg['max_ps'],
            event_observer=progress,network_factory=factory(binary=binary,directory=directory/'network',**data['network_policy']))
    finally:native.close()
    r['source_commit']=revision();r['audit']=audit_vertical_result(r);r['control_audit']=audit_request_control(r)
    with gzip.open(directory/'result.json.gz','wt',compresslevel=3) as f:json.dump(r,f)
    summary=dict(complete=True,case=case,source_commit=revision(),input_sha256=digest(data),makespan_ps=r['makespan_ps'],
        drained_ps=r['drained_ps'],wall_seconds=time.monotonic()-start,audit=r['audit'],control_audit=r['control_audit'],
        operand_readiness=r['operand_readiness'],native_config_sha256=r['native']['config_sha256'],
        booksim_sha256=r['network']['identity']['binary_sha256'],bridge_sha256=r['native']['bridge_sha256'],
        hop_flits=sum(r['network']['link_flits'].values()),native_last_tail_ps=r['native']['native_last_tail_ps'],
        gateway_bytes=r['native']['gateway_bytes'],gateway_busy_cycles=r['native']['gateway_busy_cycles'],
        rx_write_cycles=r['network']['rx_write_cycles'],compute_busy_ps=r['compute_busy_ps'],engine_context_ps=r['engine_context_ps'],
        sram_peak_bytes=r['sram_peak_bytes'],source_arbiter=r['network']['source_arbiter'])
    write_json(directory/'completion.json',summary);print(json.dumps(dict(complete=True,case=case,makespan_ps=r['makespan_ps'])),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--prepare',action='store_true');mode.add_argument('--case',choices=CASES)
    p.add_argument('--booksim-binary',type=Path,default=os.getenv('W2W_BOOKSIM_BINARY'));args=p.parse_args()
    if args.prepare:prepare(args.output)
    else:
        if args.booksim_binary is None:p.error('Native binary required')
        run(args.output,args.case,args.booksim_binary)


if __name__=='__main__':main()
