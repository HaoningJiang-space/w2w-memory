"""Immutable V3 machine/workload/mapping experiments using the existing kernel."""
import argparse,gzip,json,os,time
from pathlib import Path
from dataclasses import asdict
from w2w.architecture.presets import vertical_memory
from w2w.architecture.compiler import compile_machine
from w2w.architecture.resources import inventory,matched_vertical_budget
from w2w.workloads.moe import build_moe
from w2w.workloads.routing_input import load_layer_routing,INPUTS
from w2w.mapping.data_placement import place_weights
from w2w.mapping.compute_placement import place_compute
from w2w.mapping.lowering import lower
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.common.io import write_json
from w2w.provenance import revision
from w2w.backends.ramulator import VerticalRWDL
from w2w.network.booksim_backend import factory
from w2w.system.kernel import execute_system
from w2w.validation.vertical_access import audit_vertical_result

CASES=('central','distributed','external')


def inputs(case,cohort='c0_b1'):
    routing=load_layer_routing(INPUTS,cohort=cohort)
    logical=build_moe([t['experts'] for t in routing.tokens],name=cohort,
        source_identity=tuple(sorted(routing.source_hashes.items())))
    stack=vertical_memory(case);machine=compile_machine(stack)
    weights=place_weights(logical,stack);placement=place_compute(logical,stack,weights)
    graph,metadata=lower(logical,machine,weights,placement)
    return machine,graph,dict(schema='w2w.vertical-access-input.v3',machine=asdict(stack),
        logical=asdict(logical),weights=[asdict(w) for w in weights],placement=[asdict(p) for p in placement],
        graph=asdict(graph),metadata=metadata,resources=inventory(stack))


def prepare(output,*,cohort='c0_b1',cases=CASES):
    output.mkdir(parents=True,exist_ok=False)
    (output/'inputs').mkdir()
    records={}
    for case in cases:
        _,_,record=inputs(case,cohort)
        write_json(output/'inputs'/f'{case}.json',record)
        records[case]=dict(input_sha256=digest(record),logical_sha256=record['metadata']['logical_sha256'])
    if len({r['logical_sha256'] for r in records.values()})!=1:raise ValueError('Logical workload differs across access organizations')
    proof=matched_vertical_budget(vertical_memory('central'),vertical_memory('distributed'))
    a,b=inputs('central',cohort)[2],inputs('distributed',cohort)[2]
    for key in ('weights','placement','graph'):
        if a[key]!=b[key]:raise ValueError(f'Access intervention also changed {key}')
    write_json(output/'registration.json',dict(schema='w2w.vertical-access-study.v3',source_commit=revision(),
        cohort=cohort,cases=records,budget_match=proof,max_ps=3000000000,
        scope='one routed FFN layer on a new physical machine; not V2 replication',
        baseline_contract='common descriptor-driven GEMM streaming, full matrix storage still reserved; no numerical validation'))


def run(output,case,binary):
    reg=json.loads((output/'registration.json').read_text())
    if revision()!=reg['source_commit']:raise ValueError('Execution source no longer matches frozen registration')
    machine,graph,record=inputs(case,reg['cohort'])
    if digest(record)!=reg['cases'][case]['input_sha256']:raise ValueError('Machine/workload/mapping input changed')
    directory=output/'cases'/case;directory.mkdir(parents=True,exist_ok=False)
    native=VerticalRWDL(machine);start=time.monotonic()
    try:
        result=execute_system(machine,graph,native=native,max_ps=reg['max_ps'],time_advance='boundaries',
            activation_sram_read_bytes_per_cycle=machine.rx_write_bytes_per_cycle,
            network_factory=factory(binary=binary,directory=directory/'network',local_dma='payload_beats',cell_sideband_bits=64))
    finally:native.close()
    result['source_commit']=revision();result['lowering']=record['metadata']
    result['audit']=audit_vertical_result(result)
    with gzip.open(directory/'result.json.gz','wt',compresslevel=4) as f:json.dump(result,f)
    summary=dict(case=case,makespan_ps=result['makespan_ps'],makespan_us=result['makespan_ps']/1e6,
        wall_seconds=time.monotonic()-start,audit=result['audit'],resources=record['resources'],
        native={k:result['native'][k] for k in ('native_last_tail_ps','gateway_bytes','gateway_busy_cycles',
            'reservation_stall_attempts','queue_stall_attempts','collection_atom_ps','cdc_atom_ps','gateway_total_atom_ps')},
        native_config_sha256=result['native']['config_sha256'],
        hop_flits=sum(result['network']['link_flits'].values()),link_flits=result['network']['link_flits'],
        rx_write_cycles=result['network']['rx_write_cycles'],compute_busy_ps=result['compute_busy_ps'],
        engine_context_ps=result['engine_context_ps'],sram_peak_bytes=result['sram_peak_bytes'],
        input_sha256=reg['cases'][case]['input_sha256'],source_commit=revision())
    write_json(directory/'summary.json',summary)
    write_json(directory/'completion.json',dict(complete=True,**summary))
    print(json.dumps({k:summary[k] for k in ('case','makespan_us','wall_seconds','audit')}),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--prepare',action='store_true')
    mode.add_argument('--case',choices=CASES);p.add_argument('--cases',nargs='+',choices=CASES,default=CASES)
    p.add_argument('--cohort',choices=('c0_b1','c2_b4'),default='c0_b1')
    p.add_argument('--booksim-binary',type=Path,default=os.getenv('W2W_BOOKSIM_BINARY'))
    args=p.parse_args()
    if args.prepare:prepare(args.output,cohort=args.cohort,cases=args.cases)
    else:
        if args.booksim_binary is None:p.error('Native BookSim binary required')
        run(args.output,args.case,args.booksim_binary)


if __name__=='__main__':main()
