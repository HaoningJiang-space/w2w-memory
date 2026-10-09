"""Fixed RWDL layer: clean readiness contrast and one static tensor partition baseline."""
import argparse
from dataclasses import asdict,replace
import gzip
import json
from pathlib import Path
import platform
import time

from w2w.analysis.moe_layer import digest
from w2w.experiments.run_moe_layer import summarize,write
from w2w.experiments.run_residency_study import revision
from w2w.memory.rwdl_backend import RWDLAbsolute
from w2w.network.booksim_backend import factory
from w2w.system.kernel import execute_system
from w2w.system.wafer_machine import from_coordinates
from w2w.validation.system_execution import audit_system_result
from w2w.workloads.moe_task_graph import compile_layer,machine
from w2w.workloads.moe_partition import compile_partitioned_layer,semantic_work

CASES={'gather-stream':('gather',True),'gather-whole':('gather',False),'near-shard-stream':('near_shard',True)}


def inputs(name):
    architecture,streaming=CASES[name]
    graph,metadata=(compile_layer(cohort='c2_b4',residency='four_way') if architecture=='gather'
                    else compile_partitioned_layer(cohort='c2_b4'))
    spec,physical=from_coordinates(replace(machine(),dram_period_ps=3760))
    return graph,spec,dict(graph=asdict(graph),metadata=metadata,spec=asdict(spec),physical=physical,
                          architecture=architecture,streaming=streaming)


def prepare(output):
    output.mkdir(parents=True,exist_ok=False);(output/'inputs').mkdir()
    cases=[];signatures=set();machines=set()
    for name in CASES:
        _,_,record=inputs(name)
        semantic=digest(semantic_work(record['metadata']))
        signatures.add(semantic);machines.add(digest(record['spec']))
        write(output/'inputs'/(name+'.json'),record)
        cases.append(dict(name=name,input_sha256=digest(record),semantic_work_sha256=semantic,
            graph_sha256=digest(record['graph']),architecture=record['architecture'],streaming=record['streaming']))
    if len(signatures)!=1 or len(machines)!=1:raise ValueError('Cases changed application or wafer resources')
    write(output/'registration.json',dict(schema='w2w.compute-placement-study.v1',cases=cases,
        source_commit=revision(),host=platform.node(),max_ps=20_000_000_000,
        scope='one_routed_ffn_layer_timing',local_dma='payload_beats',cell_sideband_bits=64,
        receive_reservation='ideal global reference; protocol RTT not modeled',
        source_sram_read_bytes_per_cycle=256,source_write_ports='one independent read and one receive write per aggregate tile',
        time_advance='boundaries',controls='36 shared engines, 36x512MiB memory, 36x2MiB SRAM; same owner, tokens, RWDL, NoC/credit, MC32/requester32',
        comparisons='gather readiness only; near-shard changes static intermediate weight/compute placement and bills FP32 reduction',
        excluded='Direct HB, endpoint RTL, prefetch, dynamic migration, reticle area DSE'))
    print(json.dumps(dict(prepared=str(output),cases=list(CASES))),flush=True)


def run(output,name,binary):
    reg=json.loads((output/'registration.json').read_text())
    case=next(c for c in reg['cases'] if c['name']==name)
    graph,spec,record=inputs(name)
    if revision()!=reg['source_commit'] or digest(record)!=case['input_sha256']:
        raise ValueError('Frozen source or input changed')
    directory=output/'cases'/name;directory.mkdir(parents=True,exist_ok=False)
    native=RWDLAbsolute(spec,streaming=record['streaming'])
    start=time.monotonic()
    print(json.dumps(dict(starting=name,source_commit=revision(),weight_bytes=record['metadata']['weight_read_bytes'])),flush=True)
    try:
        result=execute_system(spec,graph,native=native,time_advance=reg['time_advance'],
            activation_sram_read_bytes_per_cycle=reg['source_sram_read_bytes_per_cycle'],
            network_factory=factory(binary=binary,directory=directory/'network',
                local_dma=reg['local_dma'],cell_sideband_bits=reg['cell_sideband_bits']),max_ps=reg['max_ps'])
    finally:native.close()
    result.update(scope=reg['scope'],wafer_machine=record['physical'])
    result['audit']=audit_system_result(result)
    n=result['native']
    if (n['pending'] or n['upstream_pending'] or n['reservations_live']
            or n['completed_atoms']*16!=record['metadata']['weight_read_bytes']):
        raise RuntimeError('Native byte/reservation conservation failed')
    with gzip.open(directory/'result.json.gz','wt',compresslevel=5) as f:json.dump(result,f)
    summary=summarize(result)
    summary.update(wall_seconds=time.monotonic()-start,kernel_iterations=result['kernel_iterations'],
                   sram_read_bytes=result['sram_read_bytes'],sram_read_busy_cycles=result['sram_read_busy_cycles'])
    write(directory/'summary.json',summary)
    write(directory/'completion.json',dict(complete=True,case=name,source_commit=reg['source_commit'],
        input_sha256=case['input_sha256'],makespan_ps=result['makespan_ps'],audit=result['audit']))
    print(json.dumps(dict(completed=name,makespan_us=result['makespan_ps']/1e6,wall_seconds=summary['wall_seconds'])),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare',action='store_true');mode.add_argument('--case',choices=CASES)
    p.add_argument('--booksim-binary',type=Path)
    args=p.parse_args()
    if args.prepare:prepare(args.output)
    else:
        if args.booksim_binary is None:p.error('--booksim-binary required')
        run(args.output,args.case,args.booksim_binary)


if __name__=='__main__':main()
