"""P2-B: same lowered shapes and scale-first supply, independently of row folding."""
import argparse,gzip,json,time
from dataclasses import asdict,replace
from pathlib import Path

from tools.validate_npu_physical import graph
from w2w.architecture.compiler import compile_machine
from w2w.architecture.npu_profile import reference_profile
from w2w.architecture.presets.recipes import from_recipe
from w2w.backends.booksim.adapter import factory
from w2w.backends.ramulator import VerticalRWDL
from w2w.common.io import write_json
from w2w.domain.execution import ReadAccess
from w2w.provenance import revision
from w2w.system.kernel import execute_system
from w2w.system.operand_streaming import StreamingKernelModel,reprogram_streaming_graph
from w2w.system.row_mapping import RowMappingKernelModel,reprogram_graph
from w2w.system.runtime_windows import RuntimeWindows
from w2w.system.weight_cache import WeightCacheConfig
from w2w.validation.npu_resources import audit_npu_result
from w2w.validation.request_control import audit_request_control
from w2w.validation.vertical_access import audit_vertical_result
from w2w.workloads.moe_trace import file_sha


def inputs(machine,p,N,K,tag,policy):
    g,kernels=graph(machine,1,N,K,p,tag);last=g.tasks[-1];data=N*K;scales=4*N*K//16384
    last=replace(last,reads=(ReadAccess('W',data,scales),ReadAccess('W',0,data)))
    g=replace(g,tasks=(*g.tasks[:-1],last))
    if policy=='streaming_os':return reprogram_streaming_graph(g,kernels,p),kernels,StreamingKernelModel(p,kernels)
    if policy=='best_os':return reprogram_graph(g,kernels,p,policy),kernels,RowMappingKernelModel(p,kernels,policy=policy)
    if policy=='aggregate_stream':return g,kernels,None
    raise ValueError('Explicit independent streaming comparison required')


def run(output,p2a_receipt,binary):
    prior=json.loads(p2a_receipt.read_text())
    if not prior.get('passed'):raise ValueError('Complete resident P2-A qualification required')
    for row in prior['resident_native']:
        if file_sha(p2a_receipt.parent/row['file'])!=row['sha256']:raise ValueError('Resident P2-A file changed')
    output.mkdir(parents=True,exist_ok=False);start=time.monotonic();p=reference_profile();machine=compile_machine(from_recipe('configs/machine/v3-small.json','distributed'))
    if prior['profile']!=asdict(p):raise ValueError('Streaming changes aggregate resources')
    rows=[]
    for kind,N,K in (('gate',128,4096),('up',128,4096),('down',4096,128)):
        for policy in ('best_os','streaming_os','aggregate_stream'):
            directory=output/(kind+'-'+policy);directory.mkdir();g,kernels,model=inputs(machine,p,N,K,'same',policy)
            native=VerticalRWDL(machine,request_control=True,refresh=True,gateway_trace_bin_ps=1000000);begin=time.monotonic()
            try:
                result=execute_system(machine,g,native=native,network_factory=factory(binary=binary,directory=directory/'network',
                    ready_router_ids=tuple(r.id for r in machine.routers),ready_slots=16),max_ps=2000000000,time_advance='boundaries',
                    compute_contexts=2,fetch_contexts=2,read_issue_policy='round_robin',weight_cache=WeightCacheConfig(),
                    operand_readiness='contiguous_prefix',activation_sram_read_bytes_per_cycle=machine.rx_write_bytes_per_cycle,npu_model=model)
            finally:native.close()
            physical=audit_vertical_result(result);audit_request_control(result)
            npu=audit_npu_result(result) if model else None
            if physical['native_bytes']!=N*K+4*N*K//16384:raise ValueError('Streaming omitted original data/scales')
            key=next(iter(kernels));state=result['tasks'][key]
            weight_ready=max(e['time_ps'] for e in result['events'] if e['kind']=='read_deliver' and e['task']==key)
            path=directory/'result.json.gz'
            with gzip.open(path,'wt') as f:json.dump(result,f)
            rows.append(dict(kind=kind,policy=policy,makespan_ps=result['makespan_ps'],kernel_start_ps=state['start_ps'],
                complete_weight_ready_ps=weight_ready,early_start_ps=max(0,weight_ready-state['start_ps']),
                operand_wait_cycles=npu.get('operand_wait_cycles',0) if npu else None,physical_audit=physical,npu_audit=npu,
                file=str(path.relative_to(output)),sha256=file_sha(path),wall_seconds=time.monotonic()-begin,
                scope='Same scale-first cold lowered matrix. Aggregate StreamGemm is retained as a historical work/byte baseline and has no shape-aware array qualification.' if model is None else 'Actual coordinate-qualified OS execution, no row folding.'))
            write_json(output/'progress.json',dict(stage='cold_native',completed=len(rows),rows=rows));print(json.dumps(rows[-1]),flush=True)
    # A real two-window drain/cache boundary checks that install_window retains
    # the opt-in policy rather than silently recreating the default NPU model.
    directory=output/'continuous-cold-warm';directory.mkdir();g,kernels,model=inputs(machine,p,128,4096,'cold','streaming_os')
    second,k2,_=inputs(machine,p,128,4096,'warm','streaming_os')
    meta=lambda ks:dict(npu_kernels={k:asdict(v) for k,v in ks.items()})
    windows=RuntimeWindows(directory/'windows',iter(((second,k2,meta(k2)),)),meta(kernels))
    native=VerticalRWDL(machine,request_control=True,refresh=True,gateway_trace_bin_ps=1000000)
    try:
        result=execute_system(machine,g,native=native,network_factory=factory(binary=binary,directory=directory/'network',
            ready_router_ids=tuple(r.id for r in machine.routers),ready_slots=16),max_ps=2000000000,time_advance='boundaries',
            compute_contexts=2,fetch_contexts=2,read_issue_policy='round_robin',weight_cache=WeightCacheConfig(),operand_readiness='contiguous_prefix',
            activation_sram_read_bytes_per_cycle=machine.rx_write_bytes_per_cycle,npu_model=model,window_source=windows)
    finally:native.close()
    from w2w.analysis.runtime_windows import audit_window_chain
    boundary=audit_window_chain(result,directory/'windows')
    if boundary['windows']!=2 or windows.rows[1]['native_bytes'] or result['npu_execution']['execution_policy']!='operand_streaming_v1':
        raise ValueError('Streaming policy or warm cache lost at the physical boundary')
    with gzip.open(directory/'result.json.gz','wt') as f:json.dump(result,f)
    from tools.validate_admission_index import qualify
    host_index=qualify(output/'host-index',machine,p,binary)
    comparisons=[]
    for kind in ('gate','up','down'):
        a=next(v for v in rows if v['kind']==kind and v['policy']=='best_os');b=next(v for v in rows if v['kind']==kind and v['policy']=='streaming_os')
        comparisons.append(dict(kind=kind,best_os_ps=a['makespan_ps'],streaming_ps=b['makespan_ps'],
            signed_benefit_ps=a['makespan_ps']-b['makespan_ps'],early_start_ps=b['early_start_ps'],operand_wait_cycles=b['operand_wait_cycles']))
    value=dict(passed=True,source_commit=revision(),P2A_receipt_sha256=file_sha(p2a_receipt),profile=asdict(p),rows=rows,
        continuous_boundary=boundary,continuous_result_sha256=file_sha(directory/'result.json.gz'),comparisons=comparisons,
        host_index_equivalence_sha256=file_sha(output/'host-index/receipt.json'),host_index_equivalence=host_index,
        wall_seconds=time.monotonic()-start,
        scope='Independent P2-B on actual lowered M1 shape: best qualified complete-operand OS versus same OS with paid descriptor-coordinate probes, plus labeled aggregate StreamGemm. Original row-major/scale-first supply, full cache pin and coupled fetch release retained. Negative results accepted. Continuous cold/warm policy/state boundary audited. No original step-0/25 trajectory, full application or silicon benefit claim.')
    write_json(output/'receipt.json',value);return value


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('output','p2a-receipt','booksim-binary'):parser.add_argument('--'+name,type=Path,required=True)
    a=parser.parse_args();run(a.output,a.p2a_receipt,a.booksim_binary)
