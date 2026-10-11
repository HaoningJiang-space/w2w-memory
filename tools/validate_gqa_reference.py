"""Independent upstream array core and numerical grouped GQA/KV reference."""
import argparse,json,subprocess,time
from pathlib import Path
import numpy as np
from validate_npu_reference import reference,bf16
from w2w.architecture.npu_profile import reference_profile
from w2w.system.npu_kernel import program
from w2w.common.io import write_json
from w2w.provenance import revision


def numerical(length):
    rng=np.random.default_rng(20261011+length);P=min(3,length);D=128
    q=bf16(rng.normal(0,.125,(P,64,D)).astype(np.float32));k=bf16(rng.normal(0,.125,(length,4,D)).astype(np.float32));v=bf16(rng.normal(0,.125,(length,4,D)).astype(np.float32))
    positions=np.arange(length-P,length);independent=[];grouped=[]
    for h in range(64):
        scores=q[:,h]@k[:,h//16].T/np.float32(np.sqrt(D));scores=np.where(np.arange(length)[None,:]<=positions[:,None],scores,-np.inf)
        probabilities=np.exp(scores-scores.max(axis=1,keepdims=True));probabilities=bf16(probabilities/probabilities.sum(axis=1,keepdims=True))
        independent.append(bf16(probabilities@v[:,h//16]))
    for h in range(4):
        rows=q[:,h*16:(h+1)*16].reshape(P*16,D);scores=rows@k[:,h].T/np.float32(np.sqrt(D))
        scores=np.where(np.arange(length)[None,:]<=np.repeat(positions,16)[:,None],scores,-np.inf)
        probabilities=np.exp(scores-scores.max(axis=1,keepdims=True));probabilities=bf16(probabilities/probabilities.sum(axis=1,keepdims=True))
        padded=np.pad(probabilities,((0,0),(0,(-length)%16)));values=np.pad(v[:,h].T,((0,0),(0,(-length)%16)))
        grouped.append(bf16(padded@values.T).reshape(P,16,D))
    a=np.stack(independent,axis=1);b=np.concatenate(grouped,axis=1);error=float(np.max(np.abs(a-b)))
    if error>2**-10:raise ValueError('Grouped query rows, causal mask, V transpose or zero padding changes GQA math')
    return dict(length=length,prefill_rows=P,query_heads=64,kv_heads=4,head_dim=D,maximum_absolute_error=error,
        scope='Synthetic BF16 inputs, independent per-head vs grouped causal GQA; not captured tensors or full Qwen numerical inference.')


def run(source,output):
    rows=[];start=time.monotonic();p=reference_profile()
    for M in (1,16,32,512):
        for length in (1,2,46,174):
            for kind,N,K in (('qk',length,128),('pv',128,length)):
                _,plan=program(M,N,K,'BF16',p);cycles=sum(max(reference(p.rows,p.columns,t['M'],t['N'],t['K'])['cycles'] for t in wave) for wave in plan['waves'])
                elements=sum(reference(p.rows,p.columns,t['M'],t['N'],t['K'])['filter_reads'] for wave in plan['waves'] for t in wave)
                if cycles!=plan['array_cycles'] or elements!=sum(t['N']*t['K'] for wave in plan['waves'] for t in wave):
                    raise ValueError('Unequal BF16 K word/tail schedule differs from upstream SCALE-Sim core')
                rows.append(dict(M=M,N=N,K=K,kind=kind,array_core_cycles=cycles,weight_elements=elements))
    write_json(output,dict(passed=True,source_commit=revision(),reference_commit=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip(),
        rows=rows,numerical=[numerical(n) for n in (1,2,46,174)],wall_seconds=time.monotonic()-start,
        scope='Independent BF16/GQA shape and array-core reference, not Native timing or silicon/port calibration.'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reference-source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.reference_source,a.output)
