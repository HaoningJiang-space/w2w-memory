"""Registered service-driven optimization + Gurobi integer reference."""
import argparse,hashlib,json,time
from pathlib import Path
import numpy as np
from w2w.service.bank_sharing import geometry,templates
from w2w.workloads.bank import scenarios
from w2w.service.guaranteed_service_exchange import contoured_geometry,balanced_assignment,Channels,ExposureFabric,StripedLayout,FixedService,FreePlacementService
from w2w.synthesis.service_driven_fabric import optimize_layout,evaluate_layout,structural_width_cap,exposure_proposals,paired_layout,exact_pair_expectation
from w2w.synthesis.gurobi_pair_synthesis import synthesize_pairs
from w2w.synthesis.memory_fabric_dse import FractionalLayout
from w2w.provenance import provenance


def run(output,gurobi_site):
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    if (out/'manifest.json').exists():raise ValueError('Fresh directory required')
    def save(name,obj):(out/name).write_text(json.dumps(obj,indent=2,allow_nan=False))
    start=time.monotonic();p=contoured_geometry()
    training=scenarios(p,range(500,504),fractions=(.25,.5),patterns=('uniform','clustered','correlated'))
    validation=scenarios(p,range(1500,1504),fractions=(.25,.5),patterns=('uniform','clustered','correlated'))
    testing=scenarios(p,range(7000,7020))
    manifest=dict(provenance=provenance(),train_seeds=list(range(500,504)),validation_seeds=list(range(1500,1504)),
        test_seeds=list(range(7000,7020)),train_cases=len(training),validation_cases=len(validation),test_cases=len(testing),
        floors=[.9,1.],iterations=4,backtracking=[1.,.5,.25,.125],
        selection='Validation mean within each registered cost/floor budget; ties use less wire/width then ID',
        budgets=[dict(edges=64,wire=1000),dict(edges=72,wire=1400),dict(edges=96,wire=2000),dict(edges=160,wire=3600)],
        scope='Fluid service, immutable continuous striping; analytical pair seeds also admit finite stripes; no application/PPA claim')
    save('manifest.json',manifest)
    save('scenarios.json',dict(training=[s.serializable() for s in training],validation=[s.serializable() for s in validation],testing=[s.serializable() for s in testing]))
    designs=[];models={};layouts={};raw_fabrics={}
    def add(identifier,fabric,layout,kind,floor,search=None):
        # Apply SAME safe width reduction to every baseline and new method.
        layout=FractionalLayout(layout.shares)
        trimmed=structural_width_cap(fabric);model=FixedService(trimmed,layout)
        train=evaluate_layout(trimmed,layout,training,floor);valid=evaluate_layout(trimmed,layout,validation,floor)
        if not train['feasible'] or not valid['feasible']:raise RuntimeError('Lost a registered service floor')
        row=dict(id=identifier,kind=kind,floor=floor,cost=trimmed.cost(),original_widths=list(fabric.channels.port_bits),
            mask=[list(ps) for ps in trimmed.mask],widths=list(trimmed.channels.port_bits),layout_hash=layout.sha256,
            training_mean=train['score'],validation_mean=valid['score'],search=search,
            certificate=model.full_load_certificate(floor))
        save(identifier+'.shares.json',layout.shares.tolist());designs.append(row)
        models[identifier]=model;layouts[identifier]=layout;raw_fabrics[identifier]=fabric
        save('designs.json',designs)
        print('DESIGN',identifier,'train',round(train['score'],6),'validation',round(valid['score'],6),flush=True)
        return row
    seeds=[]
    for method in ('aligned','half_shifted_x','half_shifted'):
        f=ExposureFabric(geometry(method),templates(4)[0][1],Channels((8000,)*4))
        seeds.append((method+'_full',f,StripedLayout.home(f)))
    for dirs in ((1,4),(2,3),(1,2,3,4)):
        f=ExposureFabric(p,balanced_assignment(p,dirs),Channels((8000,6000,6000,6000,6000)))
        seeds.append(('k2_'+''.join(map(str,dirs)),f,StripedLayout.reciprocal(f)))
    full=ExposureFabric(p,tuple(tuple(range(5)) for _ in range(32)),Channels((8000,4000,8000,8000,4000)))
    l,matching=paired_layout(full)
    seeds.append(('full5_pairs',full,l))
    for name,fabric,initial in seeds:
        for floor in (.9,1.):
            add(name+'_base_h'+str(floor),fabric,initial,'baseline',floor)
            learned,trace=optimize_layout(fabric,initial,training,floor,iterations=4)
            add(name+'_slp_h'+str(floor),fabric,learned,'service_layout',floor,trace)
    # Service-driven new exposures: select parent using TRAINING only, inherit
    # its full static layout, then reoptimize bytes on added routes.
    parents=[d for d in designs if d['kind']=='service_layout' and d['floor']==.9 and d['id'].startswith('k2_')]
    parent=max(parents,key=lambda d:d['training_mean'])
    fabric=raw_fabrics[parent['id']];layout=layouts[parent['id']]
    for i,proposal in enumerate(exposure_proposals(fabric,layout,training,limit=2)):
        f=ExposureFabric(p,proposal['mask'],fabric.channels)
        learned,trace=optimize_layout(f,layout,training,.9,iterations=3)
        trace.update(parent=parent['id'],proposal={k:v for k,v in proposal.items() if k!='mask'})
        add('exposure_'+str(i),f,learned,'service_exposure',.9,trace)
    # Strong family controls: full-bank k=3 exposure, fixed maximum-cardinality
    # pairing, plus exact training-weighted Gurobi joint x/pair/lane decisions.
    for dirs in ((1,4),(2,3)):
        widths=tuple(8000 if port==0 or port in dirs else 0 for port in range(5))
        f=ExposureFabric(p,tuple((0,)+dirs for _ in range(32)),Channels(widths))
        l,match=paired_layout(f)
        for floor in (.9,1.):add('k3_'+''.join(map(str,dirs))+'_cardinality_h'+str(floor),f,l,'pair_baseline',floor,match)
    ilp=[]
    for edges,wire in ((64,1000),(96,2000)):
        report,f,l=synthesize_pairs(p,training,edges,wire,gurobi_site=gurobi_site)
        # Every Gurobi certificate is independently checked by the fluid LP.
        score=evaluate_layout(f,l,training,1.)['score']
        if abs(score-report['training_score'])>1e-7:raise RuntimeError('Integer objective disagrees with service LP')
        if report['continuous']!=0:raise RuntimeError('Reference was supposed to be an ILP')
        report['exact_uniform_quarter_mean']=exact_pair_expectation(36,report['matched_clients'],9)
        ilp.append(report)
        for floor in (.9,1.):add('ilp_e'+str(edges)+'_h'+str(floor),f,l,'gurobi_ilp',floor,report)
    save('ilp_certificates.json',ilp)
    selection=[]
    for floor in (.9,1.):
        for budget in manifest['budgets']:
            feasible=[d for d in designs if d['floor']==floor and d['cost']['bank_port_connections']<=budget['edges'] and d['cost']['wire_mm']<=budget['wire']+1e-8]
            best=min(feasible,key=lambda d:(-round(d['validation_mean'],9),d['cost']['wire_mm'],sum(d['widths']),d['id']))
            selection.append(dict(floor=floor,**budget,id=best['id']))
    save('selection.json',selection) # never select with test results
    # Predetermined controls plus validation winners, for paired comparisons.
    evaluate_ids={s['id'] for s in selection}|{d['id'] for d in designs if d['kind'] in ('baseline','pair_baseline','gurobi_ilp')}
    for s in selection:
        if '_slp_' in s['id']:evaluate_ids.add(s['id'].replace('_slp_','_base_'))
    count=0
    with (out/'records.jsonl').open('w') as stream:
        for identifier in sorted(evaluate_ids):
            model=models[identifier];floor=next(d['floor'] for d in designs if d['id']==identifier)
            oracle=FreePlacementService(model.fabric)
            for phase in testing:
                t=model.solve(phase.demand,minimum=floor);common=model.solve(phase.demand,minimum=floor,objective='common')
                upper=oracle.solve(phase.demand,minimum=floor)
                if t['total_tb_s']>upper['total_tb_s']+1e-7:raise RuntimeError('Oracle violated')
                stream.write(json.dumps(dict(id=identifier,floor=floor,pattern=phase.pattern,fraction=phase.fraction,seed=phase.seed,
                    layout_hash=layouts[identifier].sha256,throughput=t,common=common,oracle=upper),allow_nan=False)+'\n');count+=1
            stream.flush();print('TEST',identifier,count,round(time.monotonic()-start,1),flush=True)
    manifest.update(records=count,designs=len(designs),elapsed_seconds=time.monotonic()-start,
        records_sha256=hashlib.sha256((out/'records.jsonl').read_bytes()).hexdigest())
    save('manifest.json',manifest);print('COMPLETE',count,round(manifest['elapsed_seconds'],1),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--gurobi-site')
    a=p.parse_args();run(a.output,a.gurobi_site)
