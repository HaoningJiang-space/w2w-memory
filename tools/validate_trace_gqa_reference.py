"""Qualify every GQA shape in a complete captured cohort, not serving latency."""
import argparse,gzip,json,subprocess,sys,time
from collections import Counter,defaultdict
from pathlib import Path
from tools.validate_gqa_reference import numerical
from tools.validate_npu_reference import reference
from w2w.architecture.llm_deployment import LLMProfile
from w2w.architecture.npu_profile import reference_profile
from w2w.experiments.run_real_moe import paired_batches
from w2w.system.npu_kernel import program
from w2w.workloads.moe_trace import file_sha
from w2w.provenance import revision
from w2w.common.io import write_json


def run(source,cohort_path,registration_path,config,output):
    if output.exists():raise ValueError('Retain previous trace-shape evidence')
    begin=time.monotonic();reg=json.loads(registration_path.read_text())
    cohort=json.load(gzip.open(cohort_path,'rt'));registered=reg['cohorts'][str(len(cohort))]
    if file_sha(cohort_path)!=registered['sha256'] or [c['request_id'] for c in cohort]!=registered['request_ids']:
        raise ValueError('Original registered captured cohort required')
    p=LLMProfile.from_config(json.loads(config.read_text()))
    if (p.query_heads,p.kv_heads,p.head_dim)!=(64,4,128):raise ValueError('Reference implements the declared Qwen GQA dimensions')
    pin=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    if pin!='f79d7bc39a80a21fc35bc667967b76a15b311f49':raise ValueError('Pinned independent primary reference required')
    sys.path.insert(0,str(source.resolve()))
    import scalesim.compute.systolic_compute_os as upstream
    if Path(upstream.__file__).resolve()!=(source/'scalesim/compute/systolic_compute_os.py').resolve():
        raise ValueError('Loaded array reference differs from the declared primary source')
    lengths=Counter();shapes=Counter();windows=[]
    for index,batches in enumerate(paired_batches(cohort,('0','1'),reg['prefill_microbatch'])):
        members=defaultdict(list)
        for row in batches[0].observations:members[row.request_id].append(row)
        for rid,observations in members.items():
            before=lengths[rid];after=before+len(observations)
            if [r.token_position for r in observations]!=list(range(before,after)) or after>p.kv_tokens_per_request:
                raise ValueError('Actual complete KV history is noncontiguous or exceeds the declared bound')
            lengths[rid]=after;shapes[len(observations),after]+=1
            windows.append(dict(window=index,request_id=rid,phase=observations[0].phase,decode_step=observations[0].decode_step,
                query_tokens=len(observations),before=before,after=after))
    if dict(lengths)!={c['request_id']:c['coverage']['prefill_tokens']+c['coverage']['decode_tokens'] for c in cohort}:
        raise ValueError('Reference dropped captured prefill or decode tokens')
    npu=reference_profile();rows=[]
    for (P,length),count in sorted(shapes.items()):
        kernels=[]
        for kind,N,K in (('qk',length,p.head_dim),('pv',p.head_dim,length)):
            M=P*(p.query_heads//p.kv_heads);_,plan=program(M,N,K,'BF16',npu)
            cycles=sum(max(reference(npu.rows,npu.columns,t['M'],t['N'],t['K'])['cycles'] for t in wave) for wave in plan['waves'])
            elements=sum(reference(npu.rows,npu.columns,t['M'],t['N'],t['K'])['filter_reads'] for wave in plan['waves'] for t in wave)
            if cycles!=plan['array_cycles'] or elements!=sum(t['N']*t['K'] for wave in plan['waves'] for t in wave):
                raise ValueError('Actual trace GQA array mapping differs from independent primary schedules')
            kernels.append(dict(kind=kind,M=M,N=N,K=K,array_cycles=cycles,service_cycles=plan['cycles'],
                scratch_bytes=plan['scratch_bytes'],weight_elements=elements,program_sha256=plan['program_sha256']))
        rows.append(dict(query_tokens=P,kv_length=length,occurrences=count,kernels=kernels,numerical=numerical(length,P)))
    write_json(output,dict(passed=True,source_commit=revision(),reference_commit=pin,loaded_reference_path=str(Path(upstream.__file__).resolve()),
        loaded_reference_sha256=file_sha(Path(upstream.__file__)),cohort_sha256=file_sha(cohort_path),registration_sha256=file_sha(registration_path),
        model_config_sha256=file_sha(config),request_ids=registered['request_ids'],original_request_hashes=registered['original_request_hashes'],
        complete_captured_horizon=True,kv_final_lengths=dict(lengths),trace_windows=windows,shape_cases=rows,wall_seconds=time.monotonic()-begin,
        scope='Every distinct causal GQA shape from the complete registered captured cohort is compared with pinned array schedules and independent per-head NumPy math. Numerical values remain synthetic: this is not complete Native serving, captured Qwen tensor inference, optimal mapping or calibrated PPA. Frozen application programs are unchanged.'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('reference-source','cohort','registration','config','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();run(a.reference_source,a.cohort,a.registration,a.config,a.output)
