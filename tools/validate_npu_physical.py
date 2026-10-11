"""Full-shape Native kernels and continuous cold-to-warm runtime boundary gate."""
import argparse,gzip,json,time
from dataclasses import asdict
from pathlib import Path
from w2w.architecture.presets.recipes import from_recipe
from w2w.architecture.compiler import compile_machine
from w2w.architecture.npu_profile import reference_profile
from w2w.domain.execution import ComputeTask,ResidentObject,ReadAccess,StreamGemm,DataEdge,ExecutionGraph
from w2w.domain.npu import GemmKernel
from w2w.system.npu_kernel import program,NPUKernelModel
from w2w.system.kernel import execute_system
from w2w.system.runtime_windows import RuntimeWindows
from w2w.system.weight_cache import WeightCacheConfig
from w2w.backends.ramulator import VerticalRWDL
from w2w.backends.booksim.adapter import factory
from w2w.validation.vertical_access import audit_vertical_result
from w2w.validation.request_control import audit_request_control
from w2w.validation.npu_resources import audit_npu_result
from w2w.common.io import write_json
from w2w.workloads.moe_trace import file_sha


def graph(machine,M,N,K,p,tag):
    cluster=machine.stack.compute_clusters[0];memory=next(m for m in machine.memories if m.home_tile==cluster.router_id)
    size=N*K;scales=(N//128)*(K//128)*4
    w=ResidentObject('W',memory.id,0,size+scales)
    key=tag+'/gemm';k=GemmKernel(key,M,N,K,w.id);_,plan=program(M,N,K,k.weight_dtype,p)
    tasks=(ComputeTask(tag+'/input',cluster.id,1),ComputeTask(key,cluster.id,plan['cycles'],
        (ReadAccess(w.id,0,w.size_bytes),),plan['scratch_bytes'],stream=StreamGemm(w.id,size,scales,k.macs,16384,32768)))
    return ExecutionGraph(tasks,(w,),(DataEdge(tag+'/X',tasks[0].id,key,2*M*K),)),{key:k}


def run(root,binary,mode):
    root.mkdir(parents=True,exist_ok=False);machine=compile_machine(from_recipe('configs/machine/v3-small.json','distributed'))
    rows=[]
    cases=[(M,N,K,array,kind) for array in (16,32) for M in (1,2,4,8,16,32)
        for kind,N,K in (('gate',1536,4096),('up',1536,4096),('down',4096,1536))]
    if mode=='boundary':cases=[(1,128,4096,16,'boundary')]
    if mode=='equivalence':cases=[(1,1536,4096,16,'cycles'),(1,1536,4096,16,'epochs')]
    reference=None
    for M,N,K,array,kind in cases:
        p=reference_profile(array);g,ks=graph(machine,M,N,K,p,kind)
        cache=WeightCacheConfig(initial_resident=((g.tasks[-1].tile,'W'),)) if mode=='compute' else WeightCacheConfig()
        directory=root/f'A{array}-M{M}-{kind}';directory.mkdir();source=None
        if mode=='boundary':
            g2,k2=graph(machine,M,N,K,p,'warm')
            meta=lambda keys:dict(npu_kernels={k:asdict(v) for k,v in keys.items()})
            source=RuntimeWindows(directory/'windows',iter(((g2,k2,meta(k2)),)),meta(ks))
        native=VerticalRWDL(machine,request_control=True,refresh=True,gateway_trace_bin_ps=1000000);start=time.monotonic()
        try:r=execute_system(machine,g,native=native,network_factory=factory(binary=binary,directory=directory/'network',
            ready_router_ids=tuple(r.id for r in machine.routers),ready_slots=16),max_ps=2000000000,time_advance='boundaries',
            compute_contexts=2,fetch_contexts=2,read_issue_policy='round_robin',weight_cache=cache,
            operand_readiness='contiguous_prefix',activation_sram_read_bytes_per_cycle=machine.rx_write_bytes_per_cycle,
            npu_model=NPUKernelModel(p,ks,evidence=kind if mode=='equivalence' else 'epochs'),window_source=source)
        finally:native.close()
        if source:
            from w2w.analysis.runtime_windows import audit_window_chain
            a=audit_window_chain(r,directory/'windows')
            if a['native_bytes']!=524416 or len(source.rows)!=2 or source.rows[1]['native_bytes']!=0:
                raise ValueError('Continuous boundary lost warm residency or mathematical work')
        else:
            a=audit_vertical_result(r);audit_request_control(r);audit_npu_result(r)
            if (mode=='compute' and a['native_bytes']) or (mode=='stream' and a['native_bytes']!=N*K+4*N*K//16384):
                raise ValueError('Initial-residency/Native byte contract changed')
        if mode=='equivalence':
            # Names differ only to make immutable case paths distinct.
            text=json.dumps(r,sort_keys=True).replace(kind+'/', 'same/')
            comparable=json.loads(text)
            comparable['events']=[e for e in comparable['events'] if e['kind'] not in ('npu_cycle','npu_epoch')]
            comparable.pop('npu_execution');comparable.pop('input_sha256')
            if reference is None:reference=comparable
            elif comparable!=reference:raise ValueError('Compact array program changed a physical event/resource/integer-ps result')
        path=directory/'result.json.gz'
        with gzip.open(path,'wt') as f:json.dump(r,f)
        rows.append(dict(M=M,N=N,K=K,array=array,kind=kind,mode=mode,makespan_ps=r['makespan_ps'],
            wall_seconds=time.monotonic()-start,audit=a,file=str(path.relative_to(root)),sha256=file_sha(path)))
        write_json(root/'progress.json',dict(passed=True,completed=len(rows),rows=rows));print(json.dumps(rows[-1]),flush=True)
    write_json(root/'receipt.json',dict(passed=True,mode=mode,rows=rows,scope='Full Qwen3 projection shapes, standalone physical microkernels; not trace-level application evidence. Boundary case checks continuous native/cache state.'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    p.add_argument('--booksim-binary',type=Path,required=True);p.add_argument('--mode',choices=('compute','stream','boundary','equivalence'),required=True)
    a=p.parse_args();run(a.root,a.booksim_binary,a.mode)
