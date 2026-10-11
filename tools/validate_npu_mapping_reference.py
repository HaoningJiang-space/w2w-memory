"""Qualify a stronger legal mapping; never relabel frozen application results."""
import argparse,json,subprocess,time,sys
from pathlib import Path
import numpy as np
from tools.validate_npu_reference import reference,bf16
from w2w.architecture.npu_profile import reference_profile
from w2w.system.npu_kernel import program
from w2w.validation.domain_matrix_math import e4m3fn
from w2w.workloads.moe_trace import file_sha
from w2w.common.io import write_json
from w2w.provenance import revision


def run(source,prior):
    begin=time.monotonic();p=reference_profile();rows=[]
    pin=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    if pin!='f79d7bc39a80a21fc35bc667967b76a15b311f49':raise ValueError('Pinned primary SCALE-Sim source required')
    sys.path.insert(0,str(source.resolve()))
    import scalesim.compute.systolic_compute_os as upstream
    if Path(upstream.__file__).resolve()!=(source/'scalesim/compute/systolic_compute_os.py').resolve():
        raise ValueError('Loaded reference differs from the recorded source')
    baseline=json.loads(prior.read_text())
    if baseline.get('passed') is not True:raise ValueError('Accepted prior full-shape reference required')
    for row in baseline['kernels']:
        profile=reference_profile(row['array_size']);plan=program(row['M'],row['N'],row['K'],'FP8_E4M3FN',profile)[1]
        if plan!=row['plan']:raise ValueError('Default kernel program changed; frozen applications cannot be reinterpreted')
        cycles=sum(max(reference(profile.rows,profile.columns,t['M'],t['N'],t['K'])['cycles'] for t in wave) for wave in plan['waves'])
        reads=sum(reference(profile.rows,profile.columns,t['M'],t['N'],t['K'])['filter_reads'] for wave in plan['waves'] for t in wave)
        if cycles!=plan['array_cycles'] or reads!=plan['service']['weight_sram_bytes']:
            raise ValueError('Prior default reference does not match the explicitly loaded primary source')
    for M in (1,4,8):
        old=program(M,1536,4096,'FP8_E4M3FN',p)[1]
        code,plan=program(M,1536,4096,'FP8_E4M3FN',p,k_partitions=2)
        count=sum(max(reference(p.rows,p.columns,t['M'],t['N'],t['K'])['cycles'] for t in wave) for wave in plan['waves'])
        weights=sum(reference(p.rows,p.columns,t['M'],t['N'],t['K'])['filter_reads'] for wave in plan['waves'] for t in wave)
        if count!=plan['array_cycles'] or weights!=plan['service']['weight_sram_bytes'] or sum(c.macs for c in code)!=M*1536*4096:
            raise ValueError('Explicit mapping differs from independent array demands or mathematical work')
        if plan['cycles']>=old['cycles'] or plan['scratch_bytes']>8*1024**2:raise ValueError('Mapping has no qualified capacity/cycle advantage')
        rng=np.random.default_rng(20261012+M);lut=np.asarray([e4m3fn(i) if i not in (127,255) else 0 for i in range(256)],np.float32)
        X=bf16(rng.integers(-8,9,size=(M,4096)).astype(np.float32)/16)
        W=lut[rng.integers(0,72,size=(1536,4096),dtype=np.uint8)]*np.float32(2**-8)
        Y=np.zeros((M,1536),np.float32)
        for wave in plan['waves']:
            for tile in wave:
                m,n,k,a,b,c=(tile[f] for f in ('m','n','k','M','N','K'))
                Y[m:m+a,n:n+b]+=X[m:m+a,k:k+c]@W[n:n+b,k:k+c].T
        expected=X@W.T;error=float(np.linalg.norm(Y-expected)/np.linalg.norm(expected))
        if error>1e-4:raise ValueError('Ordered K partials change full projection math beyond tolerance')
        rows.append(dict(M=M,N=1536,K=4096,default_cycles=old['cycles'],candidate_cycles=plan['cycles'],candidate_array_cycles=count,
            relative_l2_error=error,scratch_bytes=plan['scratch_bytes'],program_sha256=plan['program_sha256'],candidate_plan=plan))
    return dict(passed=True,analysis_source=revision(),prior_reference_sha256=file_sha(prior),default_36_programs_unchanged=True,
        reference_commit=pin,loaded_reference_file=str(Path(upstream.__file__).resolve()),loaded_reference_sha256=file_sha(Path(upstream.__file__)),
        cases=rows,wall_seconds=time.monotonic()-begin,
        scope='Independent full-shape software mapping qualification: output-stationary arrays may partition K over multiple waves, with original scale identity, paid registers and ordered reduction. The frozen G3/G4 default programs are unchanged. These are kernel service cycles, not application speedups, optimal-mapper proof, calibrated SRAM macros or a new hardware result.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reference-source',type=Path,required=True)
    p.add_argument('--prior-reference',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('Keep previous mapping evidence')
    write_json(a.output,run(a.reference_source,a.prior_reference))
