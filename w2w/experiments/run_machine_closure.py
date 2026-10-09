"""Same c2_b4 four-way FFN: coordinate geometry, whole versus streaming HBM2."""
import argparse
from dataclasses import asdict
import gzip
import json
from pathlib import Path
import platform
import time

from w2w.common.fingerprints import digest_system_v2 as digest
from w2w.common.io import write_json as write
from w2w.analysis.system_summary import summarize
from w2w.provenance import revision
from w2w.memory.backend import RamulatorAbsolute
from w2w.network.booksim_backend import factory
from w2w.system.kernel import execute_system
from w2w.machine.geometry import from_coordinates
from w2w.validation.system_execution import audit_system_result
from w2w.machine.presets import machine
from w2w.workloads.moe_task_graph import compile_routed_layer
from w2w.workloads.routing_input import load_layer_routing

CASES = ('hbm2-whole', 'hbm2-stream')


def inputs():
    graph, metadata = compile_routed_layer(load_layer_routing(cohort='c2_b4'),residency='four_way')
    spec, physical = from_coordinates(machine())
    record = dict(graph=asdict(graph),metadata=metadata,spec=asdict(spec),physical=physical)
    return graph, spec, record


def prepare(output):
    _, _, record = inputs()
    output.mkdir(parents=True,exist_ok=False)
    write(output/'input.json',record)
    write(output/'registration.json',dict(schema='w2w.machine-closure.v1',
        source_commit=revision(),host=platform.node(),input_sha256=digest(record),
        graph_sha256=digest(record['graph']),machine_sha256=record['physical']['machine_sha256'],
        cases=list(CASES),primary='c2_b4-four_way',max_ps=20_000_000_000,
        controls='same full FFN, frozen all-expert residency, HBM2, descriptors, slots, packet headers, NI/RX',
        comparisons='same coordinate geometry; whole descriptor versus finite contiguous-prefix supply',
        scope='one routed FFN layer on coordinate-derived, uncalibrated stitched candidate'))
    print(json.dumps(dict(prepared=str(output),input_sha256=digest(record))),flush=True)


def run(output,name,binary):
    reg=json.loads((output/'registration.json').read_text())
    graph,spec,record=inputs()
    if reg['source_commit']!=revision() or digest(record)!=reg['input_sha256']:
        raise ValueError('Frozen input or source changed')
    directory=output/'cases'/name
    directory.mkdir(parents=True,exist_ok=False)
    native=RamulatorAbsolute(spec,streaming=name.endswith('stream'))
    print(json.dumps(dict(starting=name,weight_bytes=record['metadata']['weight_read_bytes'])),flush=True)
    start=time.monotonic()
    try:
        result=execute_system(spec,graph,native=native,
            network_factory=factory(binary=binary,directory=directory/'network'),max_ps=reg['max_ps'])
    finally:
        native.close()
    result['scope']='one_routed_ffn_layer_timing'
    result['audit']=audit_system_result(result)
    if not result['audit']['passed']:
        raise RuntimeError('Execution failed byte/resource audit')
    result['wafer_machine']=record['physical']
    with gzip.open(directory/'result.json.gz','wt',compresslevel=5) as f:json.dump(result,f)
    summary=summarize(result)
    first={e['packet']:e['time_ps'] for e in result['events'] if e['kind']=='response_first_supply'}
    ready={e['request']+'/resp':e['time_ps'] for e in result['events'] if e['kind']=='native_ready'}
    summary['streaming_progress']=dict(supplied_descriptors=len(first),
        supply_before_full_native=sum(t<ready[k] for k,t in first.items()))
    summary['wall_seconds']=time.monotonic()-start
    write(directory/'summary.json',summary)
    write(directory/'completion.json',dict(complete=True,case=name,source_commit=reg['source_commit'],
        input_sha256=reg['input_sha256'],makespan_ps=result['makespan_ps'],audit=result['audit']))
    print(json.dumps(dict(completed=name,makespan_us=result['makespan_ps']/1e6,
                          streaming=summary['streaming_progress'],wall_seconds=summary['wall_seconds'])),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare',action='store_true')
    mode.add_argument('--case',choices=CASES)
    p.add_argument('--booksim-binary',type=Path)
    args=p.parse_args()
    if args.prepare:prepare(args.output)
    else:
        if args.booksim_binary is None:p.error('--booksim-binary is required')
        run(args.output,args.case,args.booksim_binary)


if __name__=='__main__':main()
