"""Fixed c2_b4: RWDL four-way and home, against archived HBM2 streaming."""
import argparse
from dataclasses import asdict, replace
import gzip
import json
from pathlib import Path
import platform
import time

from w2w.analysis.moe_layer import file_record
from w2w.common.fingerprints import digest_system_v2 as digest
from w2w.common.io import write_json as write
from w2w.analysis.system_summary import summarize
from w2w.provenance import revision
from w2w.workloads.semantics import logical_work
from w2w.memory.rwdl_backend import RWDLAbsolute
from w2w.network.booksim_backend import factory
from w2w.system.kernel import execute_system
from w2w.system.wafer_machine import from_coordinates
from w2w.validation.system_execution import audit_system_result
from w2w.workloads.moe_task_graph import compile_layer, machine

CASES = ('rwdl-four_way','rwdl-home')
BASELINE = Path('artifacts/results/system/machine_closure')


def inputs(policy):
    graph,metadata=compile_layer(cohort='c2_b4',residency=policy)
    spec,physical=from_coordinates(replace(machine(),dram_period_ps=3760))
    return graph,spec,dict(graph=asdict(graph),metadata=metadata,spec=asdict(spec),physical=physical)


def prepare(output):
    with gzip.open(BASELINE/'input.json.gz','rt') as f: baseline=json.load(f)
    analysis=json.loads((BASELINE/'analysis.json').read_text())
    four_graph,spec,four=inputs('four_way')
    if (digest(four['graph']) != digest(baseline['graph'])
            or digest(asdict(replace(spec,dram_period_ps=1000))) != digest(baseline['spec'])):
        raise ValueError('RWDL comparison changed archived graph or common machine')
    output.mkdir(parents=True,exist_ok=False)
    (output/'inputs').mkdir()
    cases=[]
    work=digest(logical_work(four_graph))
    for name in CASES:
        policy=name[5:]
        graph,_,record=inputs(policy)
        if digest(logical_work(graph)) != work:
            raise ValueError('Residency changed logical application work')
        write(output/'inputs'/(name+'.json'),record)
        cases.append(dict(name=name,policy=policy,input_sha256=digest(record),
            graph_sha256=digest(record['graph']),logical_work_sha256=work,
            layout_sha256=record['metadata']['layout_sha256']))
    write(output/'registration.json',dict(schema='w2w.rwdl-study.v1',source_commit=revision(),
        host=platform.node(),python=platform.python_version(),cases=cases,cohort='c2_b4',
        max_ps=20_000_000_000,time_advance='boundaries',baseline_rerun=False,
        baseline=analysis['cases']['hbm2-stream'],baseline_analysis=file_record(BASELINE/'analysis.json'),
        scope='one_routed_ffn_layer_timing',
        controls='fixed owner/tokens/compute/NoC geometry/MC32/requester32/4KiB/streaming; 32 logical banks and 512MiB/M',
        memory_change='independent RWDL arrays, assumed timing, bounded shared aggregation; different hardware',
        wide_noc_policy='Only register a costed wider comparison after evidence of network limitation'))
    print(json.dumps(dict(prepared=str(output),cases=list(CASES),logical_work_sha256=work)),flush=True)


def run(output,name,binary):
    reg=json.loads((output/'registration.json').read_text())
    case=next(c for c in reg['cases'] if c['name']==name)
    graph,spec,record=inputs(case['policy'])
    if reg['source_commit'] != revision() or digest(record) != case['input_sha256']:
        raise ValueError('Registered source/input changed')
    directory=output/'cases'/name
    directory.mkdir(parents=True,exist_ok=False)
    native=RWDLAbsolute(spec)
    print(json.dumps(dict(starting=name,source_commit=revision(),weight_bytes=record['metadata']['weight_read_bytes'])),flush=True)
    start=time.monotonic()
    try:
        result=execute_system(spec,graph,native=native,time_advance=reg['time_advance'],
            network_factory=factory(binary=binary,directory=directory/'network'),max_ps=reg['max_ps'])
    finally:native.close()
    result['scope']=reg['scope']
    result['audit']=audit_system_result(result)
    result['wafer_machine']=record['physical']
    value=result['native']
    if (not result['audit']['passed'] or value['pending'] or value['upstream_pending']
            or value['reservations_live'] or value['completed_atoms']*16 != record['metadata']['weight_read_bytes']):
        raise RuntimeError('RWDL byte/resource audit failed')
    with gzip.open(directory/'result.json.gz','wt',compresslevel=5) as f:json.dump(result,f)
    summary=summarize(result)
    summary.update(wall_seconds=time.monotonic()-start,kernel_iterations=result['kernel_iterations'])
    write(directory/'summary.json',summary)
    write(directory/'completion.json',dict(complete=True,case=name,source_commit=reg['source_commit'],
        input_sha256=case['input_sha256'],makespan_ps=result['makespan_ps'],audit=result['audit']))
    print(json.dumps(dict(completed=name,makespan_us=result['makespan_ps']/1e6,
        kernel_iterations=result['kernel_iterations'],wall_seconds=summary['wall_seconds'])),flush=True)


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
