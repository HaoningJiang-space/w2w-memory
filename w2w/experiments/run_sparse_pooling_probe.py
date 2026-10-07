"""Registered small sparse-pooling probe; construction checks precede service."""
import argparse
import hashlib
import json
import platform
import subprocess
import time
from pathlib import Path
import numpy as np
from w2w.service.matching_placement import contoured,ReticleService,mixture
from w2w.synthesis.cycle_configurations import catalog,coefficients,solve_cover,assemble
from w2w.workloads.reticle import activity_sets,KINDS
from w2w.synthesis.sparse_pooling import factor_certificate,complete_blocks,pool_expectation,matching_candidates,FixedLayoutService,layout_summary

TRAIN=range(110000,110128)
TEST=range(310000,311024)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    args=parser.parse_args();start=time.time()
    commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    if subprocess.check_output(['git','status','--porcelain'],text=True).strip():raise RuntimeError('Clean source commit required')
    # Scientific checks, not merely import/implementation checks, gate the run.
    subprocess.run([__import__('sys').executable,'-m','unittest','tests.test_sparse_pooling','tests.test_matching_placement'],check=True)
    p=contoured();p.validate_geometry();edges={(e['c'],e['m']) for e in p.edges}
    certs=[factor_certificate(36,edges,d) for d in (2,3,4)]
    assert [v['flow'] for v in certs]==[72,106,126]
    blocks={d:complete_blocks(36,edges,d) for d in (2,3,4)}
    candidates=matching_candidates(p)
    training=activity_sets(TRAIN);testing=activity_sets(TEST);configs=catalog(p)
    out=dict(commit=commit,host=platform.node(),train_seeds=[TRAIN.start,TRAIN.stop-1],
        test_seeds=[TEST.start,TEST.stop-1],factor_certificates=certs,complete_block_counts=blocks,
        ideal_block_references=[pool_expectation(d) for d in (2,3,4)],
        geometry=dict(compute=36,memory=36,physical_edges=len(edges),memory_service=1.,
            reticle_hb_budget=4.,ports_per_reticle=5,edge_capacity=.8,controller=4.),
        candidate_catalog=[dict(name=v['name'],terms=v['terms'],seed=v['seed'],
            matchings=v['matchings'],layout_summary=layout_summary(v['layout'])) for v in candidates],
        designs=[],comparisons=[])
    explicit=ReticleService(p)
    for kind in KINDS:
        scored=[]
        for candidate in candidates:
            service=FixedLayoutService(p,candidate['layout'])
            value=float(np.mean([service.solve(active)['mean'] for active in training[kind]]))
            scored.append(dict(name=candidate['name'],terms=candidate['terms'],value=value))
        print('TRAIN',kind,scored,flush=True)
        choices=[q.optimize(v) for q,v in zip(configs,coefficients(configs,training[kind]))]
        cover=solve_cover(configs,[v['value'] for v in choices]);assert cover['feasible']
        cycle_layout=assemble(configs,choices,cover['selected'])
        layouts=[('pair',mixture([list(range(36)),[c^1 for c in range(36)]],[.5,.5]),None),
                 ('cycle_up_to4',cycle_layout,dict(solver=cover,
                    selected=[dict(cycle=list(configs[j].cycle),ratio=choices[j]['ratio']) for j in cover['selected']]))]
        for terms in (3,4):
            best=max((v for v in scored if v['terms']==terms),key=lambda v:v['value'])
            candidate=next(v for v in candidates if v['name']==best['name'])
            layouts.append((f'mixture{terms}',candidate['layout'],dict(selected=best,training_scores=scored)))
        for name,a,selection in layouts:
            a.setflags(write=False);digest=hashlib.sha256(a.tobytes()).hexdigest()
            service=FixedLayoutService(p,a);results=[service.solve(active) for active in testing[kind]]
            full=service.solve(np.ones(36,bool));assert abs(full['common']-1)<1e-8
            checks=[]
            for idx in list(range(0,len(TEST),64))+[-1]:
                active=testing[kind][idx] if idx>=0 else np.ones(36,bool)
                result=results[idx] if idx>=0 else full
                errors=[]
                for objective,key in [('throughput','mean'),('common','common')]:
                    reference=explicit.solve(a,np.flatnonzero(active),objective,floor=1)
                    assert reference['feasible']
                    error=abs(reference['mean']-result[key]);assert error<1e-8
                    errors.append(error)
                checks.append(dict(index=idx,errors=errors))
            assert digest==hashlib.sha256(a.tobytes()).hexdigest() and not a.flags.writeable
            means=np.array([v['mean'] for v in results]);common=np.array([v['common'] for v in results])
            record=dict(kind=kind,name=name,selection=selection,layout=a.tolist(),layout_sha256=digest,
                layout_summary=layout_summary(a),test_mean=float(means.mean()),common_mean=float(common.mean()),
                worst_sample_mean=float(means.min()),minimum_service=min(v['minimum'] for v in results),
                p5_mean=float(np.mean([v['p5'] for v in results])),
                max_resource_residual=max(v['residual'] for v in results),full_load_common=full['common'],
                test_means=means.tolist(),test_common=common.tolist(),explicit_lp_checks=checks)
            out['designs'].append(record)
            print('TEST',kind,name,record['test_mean'],record['common_mean'],record['layout_summary'],flush=True)
        rows=[r for r in out['designs'] if r['kind']==kind]
        for row in rows[1:]:
            delta=np.array(row['test_means'])-np.array(rows[0]['test_means'])
            half=1.96*delta.std(ddof=1)/np.sqrt(len(delta))
            out['comparisons'].append(dict(kind=kind,name=row['name'],delta=float(delta.mean()),
                paired_ci95=[float(delta.mean()-half),float(delta.mean()+half)],
                fraction_worse=float(np.mean(delta < -1e-8))))
        # Save checkpoints only to the ignored, explicit output directory.
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(out,indent=2)+'\n')
    out['elapsed_s']=time.time()-start
    Path(args.output).write_text(json.dumps(out,indent=2)+'\n')
    print('DONE',out['elapsed_s'],flush=True)


if __name__=='__main__':main()
