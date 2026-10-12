"""P2-A: exact lowered kernels, independent references, paid resident Native runs."""
import argparse,gzip,json,subprocess,sys,time
from dataclasses import asdict
from pathlib import Path

import numpy as np
from tools.validate_npu_reference import bf16,reference
from tools.validate_npu_physical import graph
from w2w.architecture.compiler import compile_machine
from w2w.architecture.npu_profile import reference_profile
from w2w.architecture.presets.recipes import from_recipe
from w2w.architecture.resources import inventory
from w2w.backends.booksim.adapter import factory
from w2w.backends.ramulator import VerticalRWDL
from w2w.common.io import write_json
from w2w.provenance import revision
from w2w.system.kernel import execute_system
from w2w.system.row_mapping import RowMappingKernelModel,reprogram_graph,select_program
from w2w.system.weight_cache import WeightCacheConfig
from w2w.validation.domain_matrix_math import e4m3fn
from w2w.validation.npu_resources import audit_npu_result
from w2w.validation.request_control import audit_request_control
from w2w.validation.row_mapping import row_work
from w2w.validation.vertical_access import audit_vertical_result
from w2w.workloads.moe_trace import file_sha


def numerical(M,N,K,plan,seed):
    rng=np.random.default_rng(seed)
    lut=np.asarray([e4m3fn(i) if i not in (127,255) else 0 for i in range(256)],np.float32)
    codes=rng.integers(0,72,size=(N,K),dtype=np.uint8)|(rng.integers(0,2,size=(N,K),dtype=np.uint8)<<7)
    scales=rng.uniform(.001,.015,size=(N//128,K//128)).astype(np.float32)
    W=lut[codes]*np.repeat(np.repeat(scales,128,axis=0),128,axis=1)
    X=bf16(rng.normal(0,.25,size=(M,K)).astype(np.float32));expected=X@W.T;pieces={}
    for wave in plan['waves']:
        for tile in wave:
            m,n,k,a,b,c=(tile[f] for f in ('m','n','k','M','N','K'))
            pieces[m,n,k]=X[m:m+a,k:k+c]@W[n:n+b,k:k+c].T
    actual=np.zeros((M,N),np.float32)
    for (m,n,k),part in sorted(pieces.items()):actual[m:m+part.shape[0],n:n+part.shape[1]]+=part
    relative=float(np.linalg.norm(actual-expected)/max(1e-30,np.linalg.norm(expected)))
    maximum=float(np.max(np.abs(actual-expected)))
    normalized=maximum/max(1e-30,float(np.max(np.abs(expected))))
    if relative>1e-4 or normalized>1e-4:raise ValueError('Changed FP32 association exceeded declared independent error limits')
    return dict(seed=seed,relative_l2_error=relative,maximum_absolute_error=maximum,normalized_maximum_error=normalized,
        limits=dict(relative_l2=1e-4,normalized_maximum=1e-4),
        contract='Signed synthetic E4M3FN codes, varying non-power-of-two original FP32 block scales and BF16 inputs. Direct full GEMM versus actual tile coordinates/increasing-K FP32 partial sums. Tolerance qualification, not bitwise captured inference.')


def run(output,reference_source,p1_receipt,binary):
    receipt=json.loads(p1_receipt.read_text())
    if not receipt.get('passed') or file_sha(p1_receipt.parent/'analysis.json')!=receipt['analysis_sha256']:
        raise ValueError('Accepted P1 explanation required before P2-A execution')
    pin=subprocess.check_output(['git','-C',str(reference_source),'rev-parse','HEAD'],text=True).strip()
    if pin!='f79d7bc39a80a21fc35bc667967b76a15b311f49':raise ValueError('Pinned primary SCALE-Sim reference required')
    sys.path.insert(0,str(reference_source.resolve()))
    import scalesim.compute.systolic_compute_os as upstream
    if Path(upstream.__file__).resolve()!=(reference_source/'scalesim/compute/systolic_compute_os.py').resolve():
        raise ValueError('Wrong SCALE-Sim module loaded')
    output.mkdir(parents=True,exist_ok=False);start=time.monotonic();p=reference_profile();machine=compile_machine(from_recipe('configs/machine/v3-small.json','distributed'))
    p.validate_cluster(machine.stack.compute_clusters[0]);references=[]
    for M in (1,2,4,8,16,32):
        for kind,N,K in (('gate',128,4096),('up',128,4096),('down',4096,128)):
            for policy in ('reference_os','best_os','row_auto'):
                code,plan=select_program(M,N,K,'FP8_E4M3FN',p,policy)
                folded=plan.get('row_mapping');cycles=0;weights=0
                for wave in plan['waves']:
                    demands=[]
                    for tile in wave:
                        r=reference(folded['rows_per_group'] if folded else p.rows,p.columns,tile['M'],tile['N'],tile['K'])
                        demands.append(tile.get('start_tick',0)+r['cycles']);weights+=r['filter_reads']
                    cycles+=max(demands)
                if cycles!=plan['array_cycles'] or weights!=plan['service']['weight_sram_bytes'] or sum(i.macs for i in code)!=M*N*K:
                    raise ValueError('Array subgroup timing/weight demands differ from independent primary reference')
                if folded:row_work(dict(M=M,N=N,K=K,weight_dtype='FP8_E4M3FN'),plan,asdict(p))
                number=numerical(M,N,K,plan,2026101200+M*3+(0 if kind=='gate' else 1 if kind=='up' else 2))
                references.append(dict(M=M,N=N,K=K,kind=kind,policy=policy,plan=plan,numerical=number,
                    scalesim_core_cycles=cycles,scalesim_weight_elements=weights))
    write_json(output/'reference.json',dict(passed=True,analysis_source=revision(),reference_commit=pin,
        primary_file_sha256=file_sha(Path(upstream.__file__)),cases=references,
        scope='Primary OS reference validates each independent subgroup, not the added row injection/routing implementation. Port/storage and numerical checks are separate; added capabilities remain uncalibrated.'))
    native_rows=[]
    for kind,N,K in (('gate',128,4096),('up',128,4096),('down',4096,128)):
        for policy in ('reference_os','best_os','row_auto'):
            directory=output/f'M1-{kind}-{policy}';directory.mkdir()
            g,kernels=graph(machine,1,N,K,p,'same')
            g=reprogram_graph(g,kernels,p,policy);model=RowMappingKernelModel(p,kernels,policy=policy)
            cache=WeightCacheConfig(initial_resident=((g.tasks[-1].tile,'W'),));native=VerticalRWDL(machine,request_control=True,refresh=True,gateway_trace_bin_ps=1000000)
            begin=time.monotonic()
            try:
                result=execute_system(machine,g,native=native,network_factory=factory(binary=binary,directory=directory/'network',
                    ready_router_ids=tuple(r.id for r in machine.routers),ready_slots=16),max_ps=2000000000,time_advance='boundaries',
                    compute_contexts=2,fetch_contexts=2,read_issue_policy='round_robin',weight_cache=cache,
                    operand_readiness='contiguous_prefix',activation_sram_read_bytes_per_cycle=machine.rx_write_bytes_per_cycle,npu_model=model)
            finally:native.close()
            path=directory/'result.json.gz'
            with gzip.open(path,'wt') as f:json.dump(result,f)
            physical=audit_vertical_result(result);audit_request_control(result);npu=audit_npu_result(result)
            if physical['native_bytes']:raise ValueError('Resident fixture performed Native weight reads')
            key=next(iter(kernels));plan=model.plans[key];task=result['tasks'][key]
            native_rows.append(dict(kind=kind,M=1,N=N,K=K,policy=policy,makespan_ps=result['makespan_ps'],
                kernel_context_ps=task['finish_ps']-task['start_ps'],service_cycles=plan['cycles'],scratch_bytes=plan['scratch_bytes'],
                program_sha256=plan['program_sha256'],physical_audit=physical,npu_audit=npu,
                file=str(path.relative_to(output)),sha256=file_sha(path),wall_seconds=time.monotonic()-begin))
            write_json(output/'progress.json',dict(stage='resident_native',completed=len(native_rows),rows=native_rows))
            print(json.dumps(native_rows[-1]),flush=True)
    comparisons=[]
    for kind in ('gate','up','down'):
        a=next(w for w in native_rows if w['kind']==kind and w['policy']=='best_os')
        b=next(w for w in native_rows if w['kind']==kind and w['policy']=='row_auto')
        comparisons.append(dict(kind=kind,best_os_ps=a['makespan_ps'],row_auto_ps=b['makespan_ps'],
            signed_benefit_ps=a['makespan_ps']-b['makespan_ps'],service_cycle_benefit=a['service_cycles']-b['service_cycles']))
    value=dict(passed=True,source_commit=revision(),P1_receipt_sha256=file_sha(p1_receipt),profile=asdict(p),resources=inventory(machine.stack),
        reference_sha256=file_sha(output/'reference.json'),resident_native=native_rows,comparisons=comparisons,wall_seconds=time.monotonic()-start,
        scope='Actual full-size lowered Gate/Up/Down resident M1 kernels, same aggregate MAC/SRAM/cache/bank/Native/NoC budgets, conditional supplied inputs and declared initial residency. Strong legal OS K-partition search, independent subgroup/core and numerical qualification; signed outcomes retained. Extra row weight steering/word/control/scale resources are funded and counted but no equal-PPA, silicon or original-step trajectory claim.')
    write_json(output/'receipt.json',value);return value


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('output','reference-source','p1-receipt','booksim-binary'):parser.add_argument('--'+name,type=Path,required=True)
    a=parser.parse_args();run(a.output,a.reference_source,a.p1_receipt,a.booksim_binary)
