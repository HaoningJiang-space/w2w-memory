"""Run fresh-seed experiments only after a complete same-commit certificate."""
from w2w.workloads.reticle import activity_sets,KINDS
from w2w.validation.resources import batch_resource_check
import argparse
import hashlib
import json
import platform
import subprocess
import time
from collections import Counter
from pathlib import Path
import numpy as np
from w2w.service.matching_placement import contoured,ReticleService
from w2w.workloads.reticle import scenarios
from w2w.synthesis.cycle_configurations import catalog,catalog_hash,coefficients,solve_cover,assemble,primal_audit

TRAIN=range(110000,111024)
TEST=range(210000,214096)







def main():
    parser=argparse.ArgumentParser();parser.add_argument('--certificate',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();start=time.time()
    commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    if subprocess.check_output(['git','status','--porcelain'],text=True).strip():raise RuntimeError('Clean committed code required')
    cert=json.loads(Path(args.certificate).read_text())
    assert cert['passed'] and not cert['smoke'] and not cert['dirty'] and cert['commit']==commit
    assert cert['catalog_hash']==catalog_hash(catalog(contoured()))
    assert all(x['exhaustively_checked']==x['configurations'] for x in cert['geometries'])
    training=activity_sets(TRAIN);testing=activity_sets(TEST)
    out=dict(commit=commit,host=platform.node(),certificate_sha256=hashlib.sha256(Path(args.certificate).read_bytes()).hexdigest(),
        train_seeds=[TRAIN.start,TRAIN.stop-1],test_seeds=[TEST.start,TEST.stop-1],designs=[],comparisons=[])
    for pitch in (25.6,25.7):
        physical=contoured(pitch);configs=catalog(physical);service=ReticleService(physical)
        for kind in KINDS:
            coefs=coefficients(configs,training[kind]);choices=[q.optimize(v) for q,v in zip(configs,coefs)]
            for maximum in (2,3,4):
                eligible=[j for j,q in enumerate(configs) if len(q.compute)<=maximum]
                cover=solve_cover([configs[j] for j in eligible],[choices[j]['value'] for j in eligible])
                assert cover['feasible']
                selected=[eligible[j] for j in cover['selected']]
                layout=assemble(configs,choices,selected);frozen_hash=hashlib.sha256(layout.tobytes()).hexdigest()
                train_rates=sum((configs[j].predict(choices[j]['ratio'],training[kind]) for j in selected),start=np.zeros(training[kind].shape))
                train_mean=float(np.mean(train_rates.sum(axis=1)/training[kind].sum(axis=1)))
                assert abs(train_mean-1-cover['value'])<1e-8
                test_rates=sum((configs[j].predict(choices[j]['ratio'],testing[kind]) for j in selected),start=np.zeros(testing[kind].shape))
                resource_error=batch_resource_check(physical,layout,test_rates,testing[kind])
                totals=test_rates.sum(axis=1)/testing[kind].sum(axis=1)
                common=np.where(testing[kind],test_rates,np.inf).min(axis=1)
                p5=np.array([np.percentile(row[act],5) for row,act in zip(test_rates,testing[kind])])
                checks=[]
                # Fixed 16 test indices plus full load; neither selects a design.
                for idx in list(range(0,4096,256))+[-1]:
                    active=np.flatnonzero(testing[kind][idx]).tolist() if idx>=0 else list(range(36))
                    expected=test_rates[idx] if idx>=0 else np.ones(36)
                    lp=service.solve(layout,active,floor=1);fair=service.solve(layout,active,'common',floor=1)
                    assert lp['feasible'] and fair['feasible']
                    error=float(np.max(np.abs(np.array(lp['rates'])-expected)))
                    assert error<1e-8 and abs(fair['mean']-min(expected[active]))<1e-8
                    checks.append(dict(index=idx,max_rate_error=error,common_error=abs(fair['mean']-min(expected[active]))))
                assert hashlib.sha256(layout.tobytes()).hexdigest()==frozen_hash and not layout.flags.writeable
                record=dict(pitch=pitch,kind=kind,maximum=maximum,catalog_size=len(eligible),
                    selected=[dict(cycle=list(configs[j].cycle),compute=list(configs[j].compute),memory=list(configs[j].memory),ratio=choices[j]['ratio'],training_value=choices[j]['value']) for j in selected],
                    component_counts=dict(Counter(len(configs[j].compute) for j in selected)),solver=cover,
                    training_mean=train_mean,test_mean=float(totals.mean()),common_mean=float(common.mean()),
                    worst_sample_mean=float(totals.min()),minimum_service=float(test_rates[testing[kind]].min()),p5_mean=float(p5.mean()),
                    layout_sha256=frozen_hash,resource_residual=resource_error,lp_checks=checks,
                    test_means=totals.tolist(),test_common=common.tolist())
                out['designs'].append(record)
                print('RESULT',pitch,kind,maximum,record['component_counts'],record['test_mean'],record['common_mean'],flush=True)
            rows=[d for d in out['designs'] if d['pitch']==pitch and d['kind']==kind]
            for d in rows[1:]:
                differences=np.array(d['test_means'])-np.array(rows[0]['test_means'])
                mean=float(differences.mean());half=float(1.96*differences.std(ddof=1)/np.sqrt(len(differences)))
                out['comparisons'].append(dict(pitch=pitch,kind=kind,maximum=d['maximum'],delta=mean,relative_gain=d['test_mean']/rows[0]['test_mean']-1,paired_approx_ci95=[mean-half,mean+half]))
    out['elapsed_s']=time.time()-start
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,indent=2)+'\n')
    print('DONE',len(out['designs']),'designs',out['elapsed_s'],'seconds',flush=True)


if __name__=='__main__':main()
