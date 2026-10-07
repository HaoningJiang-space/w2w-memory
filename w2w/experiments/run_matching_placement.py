"""Registered small placement/matching probe; see MATCHING_PLACEMENT_METHOD.md."""
import argparse
import itertools
import json
import platform
import subprocess
import time
from pathlib import Path
import numpy as np
import networkx as nx
import scipy
from w2w.service.bank_sharing import geometry
from w2w.service.matching_placement import contoured,audit,perfect,mixture,ReticleService
from w2w.workloads.reticle import scenarios

TRAIN=range(91000,91008)
TEST=range(92000,92020)
WEIGHTS=(.2,.35,.5,.65,.8)


def cycles(p):
    seen=set();lengths=[]
    for c in range(len(p)):
        if c in seen:continue
        length=0;i=c
        while i not in seen:seen.add(i);length+=1;i=p[i]
        lengths.append(length)
    return sorted(lengths)


def candidates(p, a):
    n=len(p.compute);home=list(range(n));es={(e['c'],e['m']) for e in p.edges}
    output=[('home',[home],[1.])]
    capacities={cm:sum(p.edge_bandwidth(e) for e in p.edges if (e['c'],e['m'])==cm) for cm in es}
    def add_pair(name,matchings):
        caps=[min(capacities[c,m] for c,m in enumerate(pm)) for pm in matchings]
        # Equalize the two weakest-link single-client ceilings, in addition to
        # the registered grid. The full resource LP still checks feasibility.
        weights=sorted(set(WEIGHTS+(caps[0]/sum(caps),)))
        for w in weights:output.append((name,matchings,[w,1-w]))
    derangement=perfect(n,{(c,m) for c,m in es if c!=m})
    if derangement is not None:
        add_pair('home_derangement',[home,derangement])
    # A second, independently constructed family: home + reciprocal swaps.
    g=nx.Graph();g.add_nodes_from(range(n))
    for c,m in sorted(es):
        if c<m and (m,c) in es:
            cr,mr=p.compute[c],p.compute[m]
            distance=abs(cr.x-mr.x)+abs(cr.y-mr.y)
            g.add_edge(c,m,weight=-round(distance*1000))
    pairs=nx.max_weight_matching(g,maxcardinality=True)
    if len(pairs)*2==n:
        swap=home.copy()
        for c,m in pairs:swap[c]=m;swap[m]=c
        add_pair('home_reciprocal_pairs',[home,swap])
    if len(a['pack'])>=2:
        add_pair('packed_two',a['pack'][:2])
    return output


def metric(service,layout,active,objective='throughput',floor=1.):
    r=service.solve(layout,active,objective,floor)
    if not r['feasible']:raise RuntimeError('Certified layout lost subset feasibility')
    return {k:v for k,v in r.items() if k!='flow'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
    args=parser.parse_args();started=time.time()
    out=dict(commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        dirty=bool(subprocess.check_output(['git','status','--porcelain'],text=True).strip()),
        host=platform.node(),versions=dict(numpy=np.__version__,scipy=scipy.__version__,networkx=nx.__version__),
        train_seeds=list(TRAIN),test_seeds=list(TEST),audits={},placements=[],tests=[])
    for name in ['aligned','half_shifted_x','half_shifted','contoured']:
        p=contoured() if name=='contoured' else geometry(name)
        a=audit(36,{(e['c'],e['m']) for e in p.edges},force_check=True)
        out['audits'][name]=a
        print('AUDIT',name,a['edges'],a['allowed_edges'],a['max_disjoint'],flush=True)
    training=[(seed,kind,active) for seed in TRAIN for kind,active in scenarios(seed)]
    test=[(seed,kind,active) for seed in TEST for kind,active in scenarios(seed)]
    evaluations=[]
    for pitch,stagger in itertools.product([25.6,25.7,25.8,25.9,26.],[0.,8.25,16.5]):
        entry=dict(pitch_mm=pitch,stagger_mm=stagger);out['placements'].append(entry)
        try:p=contoured(pitch,stagger)
        except ValueError as e:
            entry.update(legal=False,reason=str(e));continue
        a=audit(36,{(e['c'],e['m']) for e in p.edges});service=ReticleService(p)
        entry.update(legal=True,audit=a,reticle_area_mm2=p.memory[0].get_area(),
            ports=5,port_area_mm2=[v.w*v.h for v in p.memory[0].vertical_connectors],
            memory_tb_s=1.,hb_tb_s=4.,controller_tb_s=4.,candidates=[])
        optimum=service.solve(None,range(36),'common')
        entry['best_full_common_relaxation']=optimum['mean']
        for family,matchings,weights in candidates(p,a):
            layout=mixture(matchings,weights)
            certificate=service.solve(layout,range(36),'common')
            record=dict(family=family,matchings=matchings,weights=weights,
                        full_common=certificate['mean'],full_residual=certificate['residual'])
            if len(matchings)==2:
                inverse={m:c for c,m in enumerate(matchings[0])}
                record['alternating_cycle_compute_sizes']=cycles([inverse[m] for m in matchings[1]])
            entry['candidates'].append(record)
            if certificate['mean']<1-1e-8:continue
            scores=[metric(service,layout,active)['mean'] for _,_,active in training]
            record['training_mean']=float(np.mean(scores))
        feasible=[r for r in entry['candidates'] if 'training_mean' in r]
        if feasible:
            selected=max(feasible,key=lambda r:r['training_mean'])
            entry['selected']=selected
            evaluations.append((pitch,stagger,'training_selected',p,selected))
            # Fixed 50/50 probes compare structures without test-time selection.
            for r in entry['candidates']:
                if r['weights']==[.5,.5] and 'training_mean' in r:
                    evaluations.append((pitch,stagger,r['family']+'_half',p,r))
        print('PLACEMENT',pitch,stagger,'full_bound',optimum['mean'],
              'selected',entry.get('selected',{}).get('family'),flush=True)
    # All choices frozen before touching held-out demand sets.
    for pitch,stagger,name,p,r in evaluations:
        service=ReticleService(p);layout=mixture(r['matchings'],r['weights'])
        for seed,kind,active in test+[(None,'full',list(range(36)))]:
            total=metric(service,layout,active)
            common=metric(service,layout,active,'common')
            out['tests'].append(dict(pitch_mm=pitch,stagger_mm=stagger,design=name,
                family=r['family'],weights=r['weights'],seed=seed,kind=kind,active=active,
                throughput=total,common=common))
    out['elapsed_s']=time.time()-started
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(out,indent=2)+'\n')
    print('DONE',len(out['tests']),'test cases',round(out['elapsed_s'],2),'seconds',flush=True)


if __name__=='__main__':main()
