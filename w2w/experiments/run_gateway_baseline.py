"""One matched Central+ intervention; retained distributed evidence is separate."""
import argparse,gzip,json,os,time
from dataclasses import asdict
from pathlib import Path
from w2w.architecture.presets.recipes import from_recipe
from w2w.architecture.compiler import compile_machine
from w2w.architecture.resources import inventory,matched_vertical_budget
from w2w.workloads.routing_input import load_workload
from w2w.mapping.data_placement import place_weights
from w2w.mapping.compute_placement import place_compute
from w2w.mapping.lowering import lower
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.common.io import write_json
from w2w.provenance import revision
from w2w.backends.ramulator import VerticalRWDL
from w2w.backends.booksim.adapter import factory
from w2w.system.kernel import execute_system
from w2w.validation.vertical_access import audit_vertical_result

CASES=('central-fifo','distributed-fifo','central-plus')


def inputs(case,contexts=2):
    logical=load_workload(Path('configs/workloads/c0_b1.json'))
    organization='distributed' if case=='distributed-fifo' else 'central'
    stack=from_recipe('configs/machine/v3-small.json',organization);machine=compile_machine(stack)
    weights=place_weights(logical,stack);placement=place_compute(logical,stack,weights)
    graph,metadata=lower(logical,machine,weights,placement)
    nodes=tuple(sorted({g.router_id for g in stack.gateways})) if case=='central-plus' else ()
    policy=dict(ready_router_ids=nodes,ready_slots=16)
    return machine,graph,dict(machine=asdict(stack),graph=asdict(graph),metadata=metadata,
        resources=inventory(stack),network_policy=policy,
        compute_contexts=contexts,additional_compute_state_bytes=(contexts-1)*64*len(stack.compute_clusters),
        selector_cost=dict(entries_per_selected_source=16,metadata_bits_per_entry=96,
            additional_bits=len(nodes)*16*96,data_bytes_added=0,ports_added=0,selection_cycles=1,
            selection_area_um2=None,clock_hz=1e9))


def prepare(output,contexts):
    output.mkdir(parents=True,exist_ok=False);(output/'inputs').mkdir();records={}
    previous=None
    for case in CASES:
        _,_,record=inputs(case,contexts)
        if previous and any(previous[k]!=record[k] for k in ('graph','metadata','compute_contexts')):
            raise ValueError('Access intervention changed work/placement/compute policy')
        previous=record;write_json(output/'inputs'/f'{case}.json',record)
        records[case]=dict(input_sha256=digest(record))
    a,b=inputs('central-fifo',contexts)[2],inputs('central-plus',contexts)[2]
    if any(a[k]!=b[k] for k in ('machine','graph','metadata','resources')):raise ValueError('Central+ changed physical resource/data plan')
    proof=matched_vertical_budget(from_recipe('configs/machine/v3-small.json','central'),from_recipe('configs/machine/v3-small.json','distributed'))
    write_json(output/'registration.json',dict(schema='w2w.gateway-baseline.v1',source_commit=revision(),
        cases=records,max_ps=3000000000,compute_contexts=contexts,budget_match=proof,
        contract='one physical injection/source; same native, HB, buffers, output, graph; finite oldest-ready selection only',
        retained_distributed_reference='v3-first-vertical-20261009; 581.749 us; new machine/graph must be matched before comparison'))


def run(output,case,binary):
    reg=json.loads((output/'registration.json').read_text())
    if revision()!=reg['source_commit']:raise ValueError('Frozen execution source changed')
    spec,graph,data=inputs(case,reg['compute_contexts'])
    if digest(data)!=reg['cases'][case]['input_sha256']:raise ValueError('Registered input changed')
    directory=output/'cases'/case;directory.mkdir(parents=True,exist_ok=False)
    native=VerticalRWDL(spec);start=time.monotonic()
    try:
        r=execute_system(spec,graph,native=native,time_advance='boundaries',max_ps=reg['max_ps'],
            compute_contexts=reg['compute_contexts'],
            activation_sram_read_bytes_per_cycle=spec.rx_write_bytes_per_cycle,
            network_factory=factory(binary=binary,directory=directory/'network',**data['network_policy']))
    finally:native.close()
    r['audit']=audit_vertical_result(r);r['source_commit']=revision()
    arb=r['network']['source_arbiter']
    if (any(n>data['network_policy']['ready_slots'] for n in arb['peak_messages'].values())
            or arb['additional_metadata_bits']!=data['selector_cost']['additional_bits']):raise ValueError('Arbitration state exceeded budget')
    with gzip.open(directory/'result.json.gz','wt',compresslevel=4) as f:json.dump(r,f)
    pressure=r['network']['final']['source_pressure'];pressure={k:v for k,v in pressure.items() if not k.endswith('_by_message')}
    summary=dict(complete=True,case=case,source_commit=revision(),input_sha256=digest(data),
        makespan_ps=r['makespan_ps'],makespan_us=r['makespan_ps']/1e6,wall_seconds=time.monotonic()-start,
        audit=r['audit'],hop_flits=sum(r['network']['link_flits'].values()),
        last_array_beat_tail_ps=r['native']['native_last_tail_ps'],
        source_arbiter=arb,source_pressure=pressure,binary=r['network']['identity']['binary_sha256'])
    summary['compute_execution']=r['compute_execution']
    summary['compute_busy_ps']=r['compute_busy_ps'];summary['engine_context_ps']=r['engine_context_ps']
    write_json(directory/'completion.json',summary);print(json.dumps(summary),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--prepare',action='store_true');mode.add_argument('--case',choices=CASES)
    p.add_argument('--compute-contexts',type=int,choices=(1,2),default=2)
    p.add_argument('--booksim-binary',type=Path,default=os.getenv('W2W_BOOKSIM_BINARY'));args=p.parse_args()
    if args.prepare:prepare(args.output,args.compute_contexts)
    else:
        if args.booksim_binary is None:p.error('Native binary required')
        run(args.output,args.case,args.booksim_binary)


if __name__=='__main__':main()
