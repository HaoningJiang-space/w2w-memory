"""Fixed RWDL layer: clean readiness contrast and one static tensor partition baseline."""
import argparse
from dataclasses import asdict,replace
import gzip
import json
from pathlib import Path
import platform
import time

from w2w.common.fingerprints import digest_system_v2 as digest
from w2w.common.io import write_json as write
from w2w.analysis.system_summary import summarize
from w2w.provenance import revision
from w2w.memory.rwdl_backend import RWDLAbsolute
from w2w.network.booksim_backend import factory
from w2w.system.kernel import execute_system
from w2w.machine.geometry import from_coordinates
from w2w.validation.system_execution import audit_system_result
from w2w.machine.presets import machine
from w2w.workloads.moe_task_graph import compile_routed_layer
from w2w.workloads.routing_input import load_layer_routing
from w2w.workloads.moe_partition import compile_partitioned_layer,compile_rotated_partition_layer,semantic_work
from w2w.validation.compute_placement import matched_partition_contract
from w2w.machine.service_profiles import RWDLProfile,RWDLController,ComputeService,effective_resources

CASES={'gather-stream':('gather',True),'gather-whole':('gather',False),'near-shard-stream':('near_shard',True)}
BASE_CASES=tuple(CASES)
CASES['rotated-shard-stream']=('rotated_shard',True)


def services(name):
    if name=='legacy':return None,None
    if name=='controller4-compute4096':
        return RWDLProfile(controller=RWDLController(read_entries=4,descriptor_window=4,descriptor_policy='round_robin')),ComputeService()
    if name=='controller4-row-compute4096':
        return RWDLProfile(controller=RWDLController(read_entries=4,descriptor_window=4,descriptor_policy='row_batched')),ComputeService()
    raise ValueError('Unknown fixed service profile')


def inputs(name,service_profile='legacy'):
    architecture,streaming=CASES[name]
    routing=load_layer_routing(cohort='c2_b4')
    memory,compute=services(service_profile)
    if architecture=='gather':graph,metadata=compile_routed_layer(routing,residency='four_way',compute_service=compute)
    else:
        compiler=compile_rotated_partition_layer if architecture=='rotated_shard' else compile_partitioned_layer
        graph,metadata=compiler(routing=routing,compute_service=compute)
    spec,physical=from_coordinates(replace(machine(),dram_period_ps=3760))
    record=dict(graph=asdict(graph),metadata=metadata,spec=asdict(spec),physical=physical,
                architecture=architecture,streaming=streaming)
    if memory is not None:record['services']=dict(memory=asdict(memory),compute=compute.record())
    return graph,spec,record


def prepare(output,names=BASE_CASES,reference=None,service_profile='legacy'):
    output.mkdir(parents=True,exist_ok=False);(output/'inputs').mkdir()
    cases=[];signatures=set();machines=set()
    reference_reg=(json.loads((reference/'registration.json').read_text()) if reference is not None else None)
    for name in names:
        _,_,record=inputs(name,service_profile)
        semantic=digest(semantic_work(record['metadata']))
        signatures.add(semantic);machines.add(digest(record['spec']))
        write(output/'inputs'/(name+'.json'),record)
        case=dict(name=name,input_sha256=digest(record),semantic_work_sha256=semantic,
            graph_sha256=digest(record['graph']),architecture=record['architecture'],streaming=record['streaming'])
        if reference is not None and name in BASE_CASES:
            old=next(c for c in reference_reg['cases'] if c['name']==name)
            frozen=json.loads((reference/'inputs'/(name+'.json')).read_text())
            done=json.loads((reference/'cases'/name/'completion.json').read_text())
            if (digest(frozen)!=case['input_sha256'] or old['input_sha256']!=case['input_sha256']
                    or not done['complete'] or done['source_commit']!=reference_reg['source_commit']
                    or done['input_sha256']!=case['input_sha256']):
                raise ValueError('Archived matched reference differs or is incomplete')
            case.update(reference_directory=str((reference/'cases'/name).resolve()),
                        source_commit=reference_reg['source_commit'])
        cases.append(case)
    if len(signatures)!=1 or len(machines)!=1:raise ValueError('Cases changed application or wafer resources')
    registration=dict(schema='w2w.compute-placement-study.v1',cases=cases,
        source_commit=revision(),host=platform.node(),max_ps=20_000_000_000,
        scope='one_routed_ffn_layer_timing',local_dma='payload_beats',cell_sideband_bits=64,
        receive_reservation='ideal global reference; protocol RTT not modeled',
        source_sram_read_bytes_per_cycle=256,source_write_ports='one independent read and one receive write per aggregate tile',
        time_advance='boundaries',controls='36 shared engines, 36x512MiB memory, 36x2MiB SRAM; same owner, tokens, RWDL, NoC/credit, MC32/requester32',
        comparisons='gather readiness only; near-shard changes static intermediate weight/compute placement and bills FP32 reduction',
        excluded='Direct HB, endpoint RTL, prefetch, dynamic migration, reticle area DSE')
    if 'rotated-shard-stream' in names:
        near,spec,a=inputs('near-shard-stream',service_profile);rotated,_,b=inputs('rotated-shard-stream',service_profile)
        registration['matched_parallel_control']=matched_partition_contract(near,a['metadata'],rotated,b['metadata'],spec)
        registration['comparisons']+='; matched four-chain clockwise rotation changes only block compute locations'
    if service_profile!='legacy':registration['service_profile']=service_profile
    write(output/'registration.json',registration)
    print(json.dumps(dict(prepared=str(output),cases=list(names))),flush=True)


def run(output,name,binary):
    reg=json.loads((output/'registration.json').read_text())
    case=next(c for c in reg['cases'] if c['name']==name)
    if 'reference_directory' in case:raise ValueError('Archived reference is read-only; do not rerun it')
    profile_name=reg.get('service_profile','legacy')
    graph,spec,record=inputs(name,profile_name)
    memory,compute=services(profile_name)
    if revision()!=reg['source_commit'] or digest(record)!=case['input_sha256']:
        raise ValueError('Frozen source or input changed')
    directory=output/'cases'/name;directory.mkdir(parents=True,exist_ok=False)
    native=RWDLAbsolute(spec,streaming=record['streaming'],profile=memory)
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
    if memory is not None:result['effective_resources']=effective_resources(spec,result['native']['resources'],compute.record())
    n=result['native']
    if (n['pending'] or n['upstream_pending'] or n['reservations_live']
            or n['completed_atoms']*16!=record['metadata']['weight_read_bytes']):
        raise RuntimeError('Native byte/reservation conservation failed')
    with gzip.open(directory/'result.json.gz','wt',compresslevel=5) as f:json.dump(result,f)
    summary=summarize(result)
    summary.update(wall_seconds=time.monotonic()-start,kernel_iterations=result['kernel_iterations'],
                   sram_read_bytes=result['sram_read_bytes'],sram_read_busy_cycles=result['sram_read_busy_cycles'])
    if 'effective_resources' in result:summary['effective_resources']=result['effective_resources']
    write(directory/'summary.json',summary)
    write(directory/'completion.json',dict(complete=True,case=name,source_commit=reg['source_commit'],
        input_sha256=case['input_sha256'],makespan_ps=result['makespan_ps'],audit=result['audit']))
    print(json.dumps(dict(completed=name,makespan_us=result['makespan_ps']/1e6,wall_seconds=summary['wall_seconds'])),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare',action='store_true');mode.add_argument('--case',choices=CASES)
    p.add_argument('--cases',nargs='+',choices=CASES,default=BASE_CASES,help='Cases to register; original three by default')
    p.add_argument('--reference',type=Path,help='Reuse completed original cases from an immutable full study')
    p.add_argument('--service-profile',choices=('legacy','controller4-compute4096','controller4-row-compute4096'),default='legacy')
    p.add_argument('--booksim-binary',type=Path)
    args=p.parse_args()
    if args.prepare:prepare(args.output,args.cases,args.reference,args.service_profile)
    else:
        if args.booksim_binary is None:p.error('--booksim-binary required')
        run(args.output,args.case,args.booksim_binary)


if __name__=='__main__':main()
