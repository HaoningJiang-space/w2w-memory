"""Full H=4096/I=1536 kernels against pinned upstream SCALE-Sim OS traces."""
import argparse,json,subprocess,time
from collections import Counter
from functools import lru_cache
from pathlib import Path
import numpy as np
from w2w.architecture.npu_profile import reference_profile
from w2w.system.npu_kernel import program
from w2w.common.io import write_json
from w2w.workloads.moe_trace import file_sha
from w2w.provenance import revision


@lru_cache(maxsize=128)
def reference(rows,columns,M,N,K):
    from scalesim.scale_config import scale_config
    from scalesim.compute.systolic_compute_os import systolic_compute_os
    cfg=scale_config();cfg.array_rows=rows;cfg.array_cols=columns;cfg.valid_conf_flag=True
    model=systolic_compute_os();model.set_params(cfg,np.zeros((M,K)),np.zeros((M,N)),np.zeros((K,N)))
    a,b,c=model.get_demand_matrices()
    if a.shape[0]!=b.shape[0] or b.shape[0]!=c.shape[0]:raise ValueError('Upstream operand schedules differ')
    return dict(cycles=a.shape[0],ifmap_reads=int(np.count_nonzero(a>=0)),
        filter_reads=int(np.count_nonzero(b>=0)),ofmap_values=int(np.count_nonzero(c>=0)))


def bf16(x):
    bits=np.asarray(x,dtype=np.float32).view(np.uint32)
    return ((bits+np.uint32(0x7fff)+((bits>>16)&1))&np.uint32(0xffff0000)).view(np.float32)


def numerical(M):
    from w2w.validation.domain_matrix_math import e4m3fn
    rng=np.random.default_rng(20261011+M);lut=np.asarray([e4m3fn(i) if i not in (127,255) else 0 for i in range(256)],np.float32)
    X=bf16(rng.integers(-8,9,size=(M,4096),dtype=np.int16).astype(np.float32)/16)
    weights=[]
    for N,K in ((1536,4096),(1536,4096),(4096,1536)):
        codes=rng.integers(0,72,size=(N,K),dtype=np.uint8)|(rng.integers(0,2,size=(N,K),dtype=np.uint8)<<7)
        # Original 128×128 scale identity is preserved; powers of two keep
        # the gate/up reference stable while exercising real E4M3FN values.
        scale=np.full((N//128,K//128),2**-8,np.float32)
        weights.append(lut[codes]*np.repeat(np.repeat(scale,128,axis=0),128,axis=1))
    def tiled(x,w):
        N,K=w.shape;_,plan=program(M,N,K,'FP8_E4M3FN',reference_profile())
        pieces={}
        for wave in plan['waves']:
            for t in wave:
                m,n,k,a,b,c=(t[v] for v in ('m','n','k','M','N','K'))
                pieces[m,n,k]=x[m:m+a,k:k+c]@w[n:n+b,k:k+c].T
        y=np.zeros((M,N),np.float32)
        for m,n,k in sorted(pieces):
            v=pieces[m,n,k];y[m:m+v.shape[0],n:n+v.shape[1]]+=v
        return y
    g,u=X@weights[0].T,X@weights[1].T
    gt=np.concatenate([tiled(X,weights[0][b:b+128]) for b in range(0,1536,128)],axis=1)
    ut=np.concatenate([tiled(X,weights[1][b:b+128]) for b in range(0,1536,128)],axis=1)
    h=bf16((g/(1+np.exp(-g)))*u);ht=bf16((gt/(1+np.exp(-gt)))*ut)
    y=h@weights[2].T
    partials=[tiled(ht[:,b:b+128],weights[2][:,b:b+128]) for b in range(0,1536,128)]
    yt=np.zeros_like(y)
    for part in range(4):
        subtotal=np.zeros_like(y)
        for block in range(part*3,part*3+3):subtotal+=partials[block]
        yt+=subtotal
    error=float(np.linalg.norm(yt-y)/max(1e-30,np.linalg.norm(y)))
    if error>1e-4:raise ValueError('Tiled FP32/BF16 gated FFN differs from independent NumPy math')
    return dict(M=M,relative_l2_error=error,maximum_absolute_error=float(np.max(np.abs(yt-y))),
        scope='Finite deterministic synthetic E4M3FN/scales/BF16 values at full expert shape. '
            'Ordered K partials before SiLU; not numerical execution of captured Qwen weights.')


def run(source,output):
    begin=time.monotonic();pin=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    rows=[]
    for size in (16,32):
        p=reference_profile(size)
        for M in (1,2,4,8,16,32):
            for phase,N,K in (('gate',1536,4096),('up',1536,4096),('down',4096,1536)):
                code,plan=program(M,N,K,'FP8_E4M3FN',p);total=0;weight=0;inputs=0
                for wave in plan['waves']:
                    refs=[reference(p.rows,p.columns,t['M'],t['N'],t['K']) for t in wave]
                    total+=max(v['cycles'] for v in refs)
                    weight+=sum(v['filter_reads'] for v in refs)
                    inputs+=sum(v['ifmap_reads'] for v in refs)
                if total!=plan['array_cycles'] or weight!=plan['service']['weight_sram_bytes']:
                    raise ValueError('Concrete array schedule differs from independent upstream reference')
                rows.append(dict(array_size=size,M=M,N=N,K=K,phase=phase,plan=plan,
                    scalesim_array_cycles=total,scalesim_element_weight_reads=weight,
                    scalesim_unbroadcast_input_elements=inputs,logical_macs=M*N*K))
                print(json.dumps(dict(array=size,M=M,phase=phase,cycles=plan['cycles'],array_cycles=total)),flush=True)
    numbers=[numerical(M) for M in (1,4,32)]
    r=dict(schema='w2w.npu-independent-reference.v1',passed=True,source_commit=revision(),reference_commit=pin,
        reference_files={str(p.relative_to(source)):file_sha(p) for p in (source/'scalesim/compute/systolic_compute_os.py',source/'scalesim/scale_config.py')},
        kernels=rows,numerical=numbers,wall_seconds=time.monotonic()-begin,
        scope='All requested full H/I expert microkernel shapes. SCALE-Sim comparison covers array core cycles and weight reads, '
            'not WoW DRAM/NoC timing, local broadcast, banking, FP8 conversion or partial reduction; those are explicitly charged and audited separately.')
    if output.exists():raise ValueError('Never overwrite validation evidence')
    write_json(output,r)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reference-source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.reference_source,a.output)
