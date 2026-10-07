"""Analyze a preregistered real corpus; preserve routing vs execution assumptions."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import time
import numpy as np
from w2w.workloads.patterns_trace import load_requests
from w2w.analysis.patterns_batch import summarize
from w2w.experiments.run_read_workload import load_designs


def run(manifest_path,plan,output):
    start=time.monotonic();path=Path(manifest_path);manifest=json.loads(path.read_text())
    if manifest['revision']!=plan['revision'] or manifest['evidence']!='captured':raise ValueError('Source/revision mismatch')
    if len(manifest['requests'])!=len(plan['subjects'])*plan['requests_per_subject']:raise ValueError('Corpus size mismatch')
    if len({r['sha256'] for r in manifest['requests']})!=len(manifest['requests']):raise ValueError('Duplicate request content')
    base=json.loads(Path('artifacts/provenance/patterns_trace_input/execution.json').read_text())
    base['layers']=[dict(base['layers'][0],key=str(i)) for i in range(plan['layers'])]
    base['batching']['max_decode_steps']=None
    layer_keys=[str(i) for i in plan['analysis_layers']]
    matrices=[];sources=[]
    # Load one request at a time, validate all 94 layers, retain eight sampled layers.
    for index,record in enumerate(manifest['requests']):
        single=dict(manifest,requests=[dict(record,path=str((path.parent/record['path']).resolve()))])
        scratch=Path(output)/'one_manifest.json';scratch.parent.mkdir(parents=True,exist_ok=True)
        scratch.write_text(json.dumps(single))
        req,_=load_requests(scratch,base);req=req[0]
        a=np.zeros((len(req.decode),len(layer_keys),plan['expert_count']),dtype=bool)
        for step,layer_rows in enumerate(req.decode):
            for j,k in enumerate(plan['analysis_layers']):a[step,j,list(layer_rows[k])]=True
        matrices.append(a);sources.append(dict(record,decode_steps=len(req.decode),prefill_tokens=req.source['prefill_tokens']))
        if index%32==31:print('VALIDATED',index+1,flush=True)
    scratch.unlink()
    if len({len(a) for a in matrices})!=1:raise ValueError('Unequal lengths: fixed-cohort vectorized study requires explicit new registration; no padding')
    routes=np.stack(matrices);del matrices
    designs,catalog=load_designs();design=designs[2]
    nb=len(design.exposure.mask);shares=np.array(design.layout.shares).reshape(36,36,nb).sum(axis=2)
    peers={c:int(next(m for m in np.flatnonzero(shares[c]) if m!=c)) for c in range(36)}
    if any(peers[peers[c]]!=c or abs(shares[c,c]-.5)>1e-9 or abs(shares[c,peers[c]]-.5)>1e-9 for c in peers):
        raise ValueError('Archived k3 is not a 50/50 reciprocal cover')
    pairs=[(c,peers[c]) for c in range(36) if c<peers[c]]
    results=[]
    population=np.arange(plan['expert_count'])%36
    for mapping_seed in plan['mapping_seeds']:
        owners=population if mapping_seed is None else np.random.default_rng(mapping_seed).permutation(population)
        for order_seed in plan['order_seeds']:
            order=np.random.default_rng(order_seed).permutation(len(routes))
            for batch_size in plan['batch_sizes']:
                row=summarize(routes,order,batch_size,owners,pairs)
                results.append(dict(mapping_seed=mapping_seed,order_seed=order_seed,batch_size=batch_size,**row))
            print('ANALYZED',mapping_seed,order_seed,flush=True)
    # Each subject alone distinguishes domain concentration from synthetic mixed serving.
    subject_results=[]
    for subject in plan['subjects']:
        indices=[i for i,r in enumerate(sources) if r['id'].split('/')[-2]==subject]
        subset=routes[indices]
        for batch_size in plan['batch_sizes']:
            if batch_size<=len(subset):
                order=np.random.default_rng(plan['order_seeds'][0]).permutation(len(subset))
                subject_results.append(dict(subject=subject,batch_size=batch_size,
                                            **summarize(subset,order,batch_size,population,pairs)))
    # Keep broad and selected-layer capacity accounting separate.
    record=dict(schema='w2w.patterns-batch-study.v1',plan=plan,
        source_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        source_dirty=bool(subprocess.check_output(['git','status','--porcelain'],text=True).strip()),
        manifest_sha256=sha256(path.read_bytes()).hexdigest(),sources=sources,catalog=catalog,
        frozen_pairs=pairs,all_layer_formats_validated=plan['layers'],selected_layers=layer_keys,
        results=results,subject_results=subject_results,
        claim='Real routing; synthetic fixed cohorts and frozen mappings; bank-only bounds omit endpoints, credits, HB and task execution',
        uncertainty='Order/mapping sensitivity is not an independent-request confidence interval; decode tokens are correlated',
        elapsed_seconds=time.monotonic()-start)
    (Path(output)/'summary.json').write_text(json.dumps(record,indent=2,allow_nan=False)+'\n')
    print('DONE',len(results),len(subject_results),record['elapsed_seconds'],flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--manifest',required=True)
    p.add_argument('--plan',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    if Path(a.output).exists():raise ValueError('Use a new output directory')
    run(a.manifest,json.loads(Path(a.plan).read_text()),a.output)


if __name__=='__main__':main()
