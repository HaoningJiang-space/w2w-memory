"""Registered finite-candidate synthesis with untouched legacy Gate semantics."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from w2w.service.bank_sharing import geometry,templates
from w2w.workloads.bank import scenarios
from w2w.service.guaranteed_service_exchange import contoured_geometry,balanced_assignment,Channels,ExposureFabric,StripedLayout,FixedService,FreePlacementService,maximum_nonhome_layout,exact_uniform_pair_mean,complementary_phases
from w2w.provenance import provenance

TRAIN_SEEDS=list(range(200,204))
TEST_SEEDS=list(range(2000,2010))
DIAGNOSTIC_SEEDS=list(range(1000,1010))


def run(output):
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    if (out/'manifest.json').exists():raise ValueError('Use a fresh output directory')
    start=time.monotonic()
    manifest=dict(provenance=provenance(),train_seeds=TRAIN_SEEDS,test_seeds=TEST_SEEDS,
        diagnostic_seeds=DIAGNOSTIC_SEEDS,registered_minimum_tb_s=1.,stripes_per_object=256,
        stripe_kib=128,logical_object_mib=32,objects_per_compute=128,
        demand='4 TB/s per active compute; uniform within each logical object',
        resource_budget='36C+36M; 1 TB/s and 16 GiB per memory; HB <=4 TB/s and controller 4 TB/s each',
        selection='Training throughput only among full-load-certified candidates within wire and width budgets; ties prefer smaller wire, width, beta, ID',
        scope='Functional fluid rates and physical proxies, not application speedup or PPA',
        cost_budgets=dict(wire_mm=[784,850,950],total_port_bits=[8000,12000,16000,32000]))
    def save(name,data):(out/name).write_text(json.dumps(data,indent=2,allow_nan=False))
    save('manifest.json',manifest)
    p=contoured_geometry();training=scenarios(p,TRAIN_SEEDS,fractions=(.25,.5))
    heldout=scenarios(p,TEST_SEEDS)
    save('scenarios.json',dict(training=[s.serializable() for s in training],heldout=[s.serializable() for s in heldout]))
    diagnostics=[]
    for method,k,name in [('half_shifted_x',2,'xor_1'),('half_shifted_x',4,'full'),
                          ('half_shifted',2,'star_0'),('half_shifted',4,'full'),('half_shifted',2,'xor_3')]:
        f=ExposureFabric(geometry(method),dict(templates(k))[name],Channels((8000,)*4))
        for floor in (.8,.9,.95,.99,1.):
            diagnostics.append(dict(method=method,k=k,template=name,**maximum_nonhome_layout(f,floor)))
    save('layout_limits.json',diagnostics)
    designs=[];models={};layouts={}
    def add(identifier,physical,mask,widths,beta=None,kind='reciprocal',assignment='minimum_wire',train=True):
        f=ExposureFabric(physical,mask,Channels(tuple(widths)))
        layout=StripedLayout.home(f) if beta is None else StripedLayout.reciprocal(f,beta)
        model=FixedService(f,layout);certificate=model.full_load_certificate()
        cost=f.cost()
        row=dict(id=identifier,kind=kind,beta=beta,assignment=assignment,mask=[list(x) for x in mask],
            cost=cost,layout_hash=layout.sha256,certificate=certificate,training_mean=None)
        if certificate['feasible'] and train:
            row['training_mean']=float(np.mean([model.solve(s.demand)['tb_s_per_active'] for s in training]))
        designs.append(row);models[identifier]=model;layouts[identifier]=layout
        save(identifier+'.layout.json',layout.counts.tolist())
        print('CANDIDATE',identifier,certificate['feasible'],row['training_mean'],flush=True)
        return row
    add('contoured_home',p,tuple((0,) for _ in range(32)),(8000,0,0,0,0),kind='home')
    # Strengthened home mapping. No per-test data changes; blocked mappings are
    # reported, not repaired. The continuous relaxation above proves why a
    # strictly protected cross-home layout cannot rescue the one-way cases.
    for method,k,name in [('aligned',1,'private'),('aligned',4,'full'),
                          ('half_shifted_x',2,'xor_1'),('half_shifted_x',4,'full'),
                          ('half_shifted',2,'star_0'),('half_shifted',4,'full')]:
        add(method+'_'+name,geometry(method),dict(templates(k))[name],(8000,)*4,kind='legacy_striped_home')
    for dirs in ((1,4),(2,3),(1,2,3,4)):
        mask=balanced_assignment(p,dirs)
        for beta in (.125,.25,.5):
            for width in (256,1000,2000,4000,8000):
                widths=[8000]+[width if port in dirs else 0 for port in range(1,5)]
                if sum(widths)>32000:continue
                add('r'+''.join(map(str,dirs))+'_b'+str(beta)+'_w'+str(width),p,mask,widths,beta)
    # Locked diagnostic reproduces declared 2+1+1 TB/s ports. It never enters
    # candidate selection; lower-width candidates already span its service.
    probe=add('probe_23_original_width',p,balanced_assignment(p,(2,3)),(16000,0,8000,8000,0),.5,kind='locked_probe',train=False)
    cyclic=add('probe_23_cyclic',p,balanced_assignment(p,(2,3),'cyclic'),(8000,0,4000,4000,0),.5,kind='locked_probe',assignment='cyclic',train=False)
    selected=[]
    for wire in manifest['cost_budgets']['wire_mm']:
        for width in manifest['cost_budgets']['total_port_bits']:
            # Baseline and reciprocal candidates share the same contour here;
            # cross-geometry diagnostics are evaluated separately.
            eligible=[d for d in designs if d['kind'] in ('home','reciprocal') and d['training_mean'] is not None
                      and d['cost']['wire_mm']<=wire+1e-9 and sum(d['cost']['port_bits'])<=width]
            best=min(eligible,key=lambda d:(-round(d['training_mean'],10),d['cost']['wire_mm'],sum(d['cost']['port_bits']),d['beta'] or 0,d['id']))
            selected.append(dict(wire_budget_mm=wire,port_budget_bits=width,design=best['id'],training_mean=best['training_mean']))
    save('selection.json',selected)  # frozen BEFORE any held-out service solve
    save('designs.json',designs)
    exact={}
    for identifier in ('r23_b0.5_w4000','r1234_b0.5_w2000'):
        f=models[identifier].fabric
        exact[identifier]={str(a):exact_uniform_pair_mean(f,layouts[identifier],a) for a in (9,18,27,36)}
    save('exact_expectations.json',exact)
    coactivity=[]
    for dirs in ((1,4),(2,3)):
        phases=complementary_phases(p,dirs)
        scores={identifier:float(np.mean([models[identifier].solve(s.demand)['tb_s_per_active'] for s in phases]))
                for identifier in ('r14_b0.5_w4000','r23_b0.5_w4000')}
        coactivity.append(dict(preferred=list(dirs),marginal_activity=[float(x) for x in np.mean([s.demand>0 for s in phases],axis=0)],
                               scores=scores,selected=max(scores,key=scores.get),scope='Synthetic joint-activity mechanism check, not trace generalization'))
    save('coactivity.json',coactivity)
    # Include locked baselines, a priori half/half references, and trained winners.
    ids=sorted({x['design'] for x in selected}|{d['id'] for d in designs if d['kind']!='reciprocal'}|
               {'r14_b0.5_w4000','r23_b0.5_w4000','r1234_b0.5_w2000'})
    count=0
    with (out/'records.jsonl').open('w') as records:
        for identifier in ids:
            model=models[identifier]
            if not next(d for d in designs if d['id']==identifier)['certificate']['feasible']:continue
            oracle=FreePlacementService(model.fabric)
            for phase in heldout:
                result=model.solve(phase.demand);common=model.solve(phase.demand,objective='common')
                bound=oracle.solve(phase.demand)
                if result['total_tb_s']>bound['total_tb_s']+1e-7:raise RuntimeError('Static service exceeds oracle')
                row=dict(id=identifier,pattern=phase.pattern,fraction=phase.fraction,seed=phase.seed,
                    active=int(np.count_nonzero(phase.demand)),layout_hash=layouts[identifier].sha256,
                    throughput=result,common=common,oracle=bound)
                records.write(json.dumps(row,allow_nan=False)+'\n');count+=1
            records.flush();print('TESTED',identifier,count,round(time.monotonic()-start,1),flush=True)
        # Same full bank crossbar for each geometry, no residency: explicitly an
        # additional oracle architecture, not mislabeled k=4 on five ports.
        for method,physical in [('aligned',geometry('aligned')),('half_shifted_x',geometry('half_shifted_x')),
                                ('half_shifted',geometry('half_shifted')),('contoured',p)]:
            nports=len(physical.memory[0].vertical_connectors)
            widths=(8000,)*4 if nports==4 else (16000,4000,4000,4000,4000)
            f=ExposureFabric(physical,tuple(tuple(range(nports)) for _ in range(32)),Channels(widths))
            oracle=FreePlacementService(f)
            for phase in heldout:
                result=oracle.solve(phase.demand,minimum=0.)
                records.write(json.dumps(dict(id=method+'_full_crossbar_oracle',pattern=phase.pattern,fraction=phase.fraction,
                    seed=phase.seed,active=int(np.count_nonzero(phase.demand)),layout_hash=None,throughput=result,
                    oracle_only=True,cost=f.cost()),allow_nan=False)+'\n');count+=1
            records.flush()
    probe_records=[]
    for s in scenarios(p,DIAGNOSTIC_SEEDS,fractions=(.25,1.)):
        probe_records.append(dict(pattern=s.pattern,fraction=s.fraction,seed=s.seed,
            throughput=models[probe['id']].solve(s.demand),common=models[probe['id']].solve(s.demand,objective='common')))
    save('locked_probe.json',probe_records)
    manifest.update(records=count,elapsed_seconds=time.monotonic()-start,
        records_sha256=hashlib.sha256((out/'records.jsonl').read_bytes()).hexdigest(),
        geometry=dict(reticles_per_wafer=36,memory_area_mm2=p.memory[0].get_area(),
            home_edges=sum(e['c']==e['m'] for e in p.edges),reciprocal_pairs=len({tuple(sorted((e['c'],e['m']))) for e in p.edges if e['c']!=e['m']})))
    save('manifest.json',manifest)
    print('COMPLETE',count,'seconds',round(manifest['elapsed_seconds'],1),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    args=parser.parse_args();run(args.output)
