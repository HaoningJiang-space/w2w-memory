"""Three-way data split and frozen-layout evaluation of circulation search."""
import argparse
import json
import platform
import subprocess
import sys
import time
from pathlib import Path
import numpy as np
from w2w.service.matching_placement import contoured,mixture,ReticleService
from w2w.synthesis.cycle_configurations import catalog,coefficients,solve_cover,assemble,primal_audit
from w2w.synthesis.sparse_pooling import matching_candidates,layout_summary
from w2w.synthesis.nonuniform_pooling import CirculationSearch,Evaluation,units,digest,DENOMINATOR
from w2w.workloads.reticle import activity_sets,KINDS

TRAIN=range(410000,410256)
VALIDATION=range(420000,420256)
TEST=range(510000,511024)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    parser.add_argument('--mixed',action='store_true',help='One static fabric trained on an equal mixture of all four distributions')
    args=parser.parse_args();start=time.time();path=Path(args.output)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    if subprocess.check_output(['git','status','--porcelain'],text=True).strip():raise RuntimeError('Clean committed source required')
    subprocess.run([sys.executable,'-m','unittest','tests.test_nonuniform_pooling','tests.test_sparse_pooling','tests.test_matching_placement'],check=True)
    p=contoured();p.validate_geometry();configs=catalog(p)
    train_range=range(430000,430064) if args.mixed else TRAIN
    validation_range=range(440000,440064) if args.mixed else VALIDATION
    test_range=range(610000,611024) if args.mixed else TEST
    train=activity_sets(train_range);validation=activity_sets(validation_range)
    design_kinds=('mixed',) if args.mixed else KINDS
    if args.mixed:
        train={'mixed':np.concatenate([train[k] for k in KINDS])}
        validation={'mixed':np.concatenate([validation[k] for k in KINDS])}
    # Do not even generate test scenarios until all four designs are frozen.
    out=dict(commit=commit,host=platform.node(),mixed=args.mixed,train_seeds=[train_range.start,train_range.stop-1],
        validation_seeds=[validation_range.start,validation_range.stop-1],test_seeds=[test_range.start,test_range.stop-1],
        denominator=DENOMINATOR,edge_budget=126,degree_budget=4,designs=[],results=[])
    frozen=[]
    for kind in design_kinds:
        search=CirculationSearch(p,train[kind]);choices=[q.optimize(v) for q,v in zip(configs,coefficients(configs,train[kind]))]
        cover=solve_cover(configs,[v['value'] for v in choices]);assert cover['feasible']
        baseline=[dict(name='pair',layout=mixture([list(range(36)),[c^1 for c in range(36)]],[.5,.5])),
                  dict(name='cycle_up_to4',layout=assemble(configs,choices,cover['selected']))]
        baseline += [dict(name=v['name'],layout=v['layout']) for v in matching_candidates(p)]
        for v in baseline:
            v['layout']=units(v['layout'])/DENOMINATOR
            v['training_mean']=search.evaluate(units(v['layout']))['mean']
        initial=max(baseline,key=lambda v:v['training_mean'])
        print('START',kind,initial['name'],initial['training_mean'],flush=True)
        ratios=search.run(initial['layout'],fixed_support=True,seed=700)
        joint=search.run(ratios['layout'],fixed_support=False,seed=701)
        ratio_candidates=[dict(name=f'ratios_step{i+1}',layout=a) for i,a in enumerate(ratios['trajectory'])]
        joint_candidates=[dict(name=f'joint_step{i+1}',layout=a) for i,a in enumerate(joint['trajectory'])]
        all_candidates=baseline+ratio_candidates+joint_candidates
        validated={}
        for v in all_candidates:
            a=v['layout'];key=digest(a)
            if key not in validated:validated[key]=Evaluation(p,a).batch(validation[kind])['mean']
            v['validation_mean']=validated[key]
            v['training_mean']=search.evaluate(units(a))['mean']
        def best(vs):
            # Stable tie breaking prefers the earlier, simpler fallback candidate.
            return max(vs,key=lambda v:v['validation_mean'])
        selections=[('pair',baseline[0]),('cycle_up_to4',baseline[1]),
            ('equal3',best([v for v in baseline if v['name'].startswith('mixture3')])),
            ('equal4',best([v for v in baseline if v['name'].startswith('mixture4')])),
            ('baseline_selected',best(baseline)),
            ('ratios_selected',best(baseline+ratio_candidates)),
            ('joint_selected',best(all_candidates))]
        selected=[]
        for label,v in selections:
            a=v['layout'].copy();a.setflags(write=False);primal_audit(p,a,np.ones(36),range(36))
            selected.append(dict(label=label,name=v['name'],layout=a.tolist(),layout_sha256=digest(a),
                training_mean=v['training_mean'],validation_mean=v['validation_mean'],layout_summary=layout_summary(a)))
            frozen.append((kind,label,a))
        out['designs'].append(dict(kind=kind,starting_candidate=initial['name'],
            training_layouts_evaluated=len(search.cache),
            candidates=[dict(name=v['name'],layout=v['layout'].tolist(),layout_sha256=digest(v['layout']),
                training_mean=v['training_mean'],validation_mean=v['validation_mean']) for v in all_candidates],
            ratios_trace=ratios['trace'],joint_trace=joint['trace'],selections=selected,
            cycle_solver=cover))
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,indent=2)+'\n')
        print('FROZEN',kind,[(v['label'],v['name'],v['validation_mean']) for v in selected],flush=True)
    print('ALL_DESIGNS_FROZEN_BEFORE_TEST',flush=True)
    testing=activity_sets(test_range);explicit=ReticleService(p);cache={}
    evaluated=frozen if not args.mixed else [(kind,label,a) for _,label,a in frozen for kind in KINDS]
    for kind,label,a in evaluated:
        key=(kind,digest(a))
        if key not in cache:cache[key]=Evaluation(p,a).batch(testing[kind],audit=True)
        result=cache[key];checks=[]
        for idx in list(range(0,len(test_range),128))+[-1]:
            active=testing[kind][idx] if idx>=0 else np.ones(36,bool)
            for objective,key_name in [('throughput','means'),('common','common')]:
                reference=explicit.solve(a,np.flatnonzero(active),objective,floor=1)
                assert reference['feasible']
                target=result[key_name][idx] if idx>=0 else 1.
                error=abs(reference['mean']-target);assert error<1e-8
                checks.append(dict(index=idx,objective=objective,error=error))
        assert digest(a)==key[1] and not a.flags.writeable
        rates=result['rates'];activity=testing[kind]
        out['results'].append(dict(kind=kind,label=label,layout_sha256=digest(a),
            test_mean=result['mean'],common_mean=float(result['common'].mean()),
            test_means=result['means'].tolist(),test_common=result['common'].tolist(),
            minimum_service=float(rates[activity].min()),worst_sample_mean=float(result['means'].min()),
            p5_mean=float(np.mean([np.percentile(r[x],5) for r,x in zip(rates,activity)])),
            resource_residual=result['residual'],explicit_checks=checks))
        print('TEST',kind,label,result['mean'],float(result['common'].mean()),flush=True)
        path.write_text(json.dumps(out,indent=2)+'\n')
    out['elapsed_s']=time.time()-start
    path.write_text(json.dumps(out,indent=2)+'\n');print('DONE',out['elapsed_s'],flush=True)


if __name__=='__main__':main()
