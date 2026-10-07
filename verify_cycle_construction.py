"""Independent enumeration, exhaustive local service and adversarial audits."""
import argparse
import copy
import itertools
import json
import platform
import subprocess
import time
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import networkx as nx
import scipy
from matching_placement import contoured,bipartite,ReticleService
from cycle_configurations import (canonical,enumerate_cycles,catalog,catalog_hash,
    Configuration,geometry_contract,primal_audit,solve_cover,assemble)


def audit_config(p,q,ratio,counters,full=True):
    k=len(q.compute);local=q.local_physical(p);service=ReticleService(local)
    layout=q.matrix(ratio,36)[np.ix_(q.compute,q.memory)]
    for x in (q.lower,(q.lower+q.upper)/2,q.upper):
        aa=q.matrix(x,36)[np.ix_(q.compute,q.memory)]
        counters['resource_residual']=max(counters['resource_residual'],primal_audit(local,aa,np.ones(k),range(k)))
    states=list(itertools.product([False,True],repeat=k))
    for state in states:
        activity=np.zeros((1,36),bool);activity[0,list(q.compute)]=state
        expected=q.predict(ratio,activity)[0,list(q.compute)]
        active=np.flatnonzero(state).tolist()
        counters['resource_residual']=max(counters['resource_residual'],primal_audit(local,layout,expected,active))
        h=np.array(state,float)
        np.testing.assert_allclose(1-layout.T@h,layout.T@(1-h),atol=1e-12)
        counters['activity_states']+=1
        if not active:continue
        actual=service.solve(layout,active,floor=1)
        assert actual['feasible']
        error=float(np.max(np.abs(expected-np.array(actual['rates']))))
        counters['max_rate_error']=max(counters['max_rate_error'],error)
        assert error<1e-8
        counters['throughput_lp']+=1
        if len(active) in (1,k) or (full and tuple(state)==tuple(i%2==0 for i in range(k))):
            common=service.solve(layout,active,'common',floor=1)
            assert common['feasible'] and abs(common['mean']-min(expected[active]))<1e-8
            counters['common_lp']+=1


def must_reject(fn):
    try:fn()
    except ValueError:return
    raise AssertionError('Invalid construction was accepted')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--smoke',action='store_true')
    args=parser.parse_args();start=time.time()
    stats=dict(throughput_lp=0,common_lp=0,activity_states=0,max_rate_error=0.,resource_residual=0.)
    output=dict(commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        dirty=bool(subprocess.check_output(['git','status','--porcelain'],text=True).strip()),
        smoke=args.smoke,host=platform.node(),versions=dict(numpy=np.__version__,networkx=nx.__version__,scipy=scipy.__version__),
        geometries=[],checks=stats)
    base=contoured();qs=catalog(base);output['catalog_hash']=catalog_hash(qs)
    independent={canonical(v) for v in nx.simple_cycles(bipartite(36,{(e['c'],e['m']) for e in base.edges}),length_bound=8)}
    assert set(enumerate_cycles(base))==independent
    counts=dict(Counter(len(q.compute) for q in qs));assert counts=={2:95,3:428,4:2091}
    output['enumeration_counts']=counts
    graph=nx.Graph();graph.add_nodes_from(range(36));es={(e['c'],e['m']) for e in base.edges}
    graph.add_edges_from((c,m) for c,m in es if c<m and (m,c) in es)
    assert graph.number_of_edges()==55
    forced=[];g=graph.copy()
    while len(g):
        leaves=[v for v in g if g.degree(v)==1]
        assert leaves, 'Leaf argument did not finish'
        c=min(leaves);m=next(iter(g[c]));forced.append([c,m]);g.remove_nodes_from([c,m])
    assert len(forced)==18
    for edge in forced:
        g=graph.copy();g.remove_edge(*edge)
        assert len(nx.max_weight_matching(g,maxcardinality=True))<18
    pairs=[q for q in qs if len(q.compute)==2]
    feasible=[]
    if not args.smoke:
        for i in range(len(pairs)):
            result=solve_cover(pairs,np.zeros(len(pairs)),forced=i)
            if result['feasible']:feasible.append(i)
        assert len(feasible)==18
        counts_c=Counter(c for i in feasible for c in pairs[i].compute)
        counts_m=Counter(m for i in feasible for m in pairs[i].memory)
        assert counts_c==Counter(range(36)) and counts_m==Counter(range(36))
    output['pair_uniqueness']=dict(home_reciprocal_edges=55,leaf_forced_pairs=forced,
        general_k22_candidates=len(pairs),extendible_k22_indices=feasible,forced_milps=0 if args.smoke else len(pairs))
    for pitch in (25.6,25.7):
        p=contoured(pitch);configs=catalog(p)
        selected=configs if not args.smoke else [next(q for q in configs if len(q.compute)==k) for k in (2,3,4)]
        for j,q in enumerate(selected):
            choice=q.optimize(np.ones(len(q.compute)))
            audit_config(p,q,choice['ratio'],stats)
            if j%500==0:print('AUDIT',pitch,j,'/',len(selected),flush=True)
        output['geometries'].append(dict(pitch=pitch,configurations=len(configs),exhaustively_checked=len(selected)))
    # Heterogeneous capacities, nonuniform value weights, controller switchpoints.
    rng=np.random.default_rng(310000);worst_grid_advantage=0.;synthetic=0
    for case in range(8 if args.smoke else 64):
        k=2+case%3;ca=rng.uniform(.55,.95,k);cb=rng.uniform(.55,.95,k)
        es=[]
        for c in range(k):
            es.extend([dict(c=c,m=c,cp=0,mp=0,capacity=ca[c]),dict(c=c,m=(c-1)%k,cp=1,mp=1,capacity=cb[c])])
        p=SimpleNamespace(compute=[SimpleNamespace(vertical_connectors=[0,1]) for _ in range(k)],
            memory=[SimpleNamespace(vertical_connectors=[0,1]) for _ in range(k)],edges=es,edge_bandwidth=lambda e:e['capacity'])
        geometry_contract(p)
        cycle=tuple(v for c in range(k) for v in (c,k+c));q=Configuration.build(p,cycle)
        weights=rng.random(k);controller=rng.uniform(1,4)
        choice=q.optimize(weights,controller)
        grid=np.linspace(q.lower,q.upper,4001)
        values=np.minimum(controller,np.minimum(ca[:,None]/grid,cb[:,None]/(1-grid)))
        advantage=float(np.max(weights@(values-1))-choice['value'])
        worst_grid_advantage=max(worst_grid_advantage,advantage);assert advantage<1e-10
        # Full LP check at independently chosen interior ratio, not just optimum.
        audit_config(p,q,(q.lower+q.upper)/2,stats,False);synthetic+=1
    output['breakpoints']=dict(cases=synthetic,grid_points=4001,largest_grid_advantage=worst_grid_advantage)
    # Independently enumerate every feasible cover on a small complete 4C+4M
    # graph; verifies BOTH coverage sides and the master objective/assembly.
    tiny=SimpleNamespace(compute=[SimpleNamespace(vertical_connectors=list(range(4))) for _ in range(4)],
        memory=[SimpleNamespace(vertical_connectors=list(range(4))) for _ in range(4)],
        edges=[dict(c=c,m=m,cp=m,mp=c,capacity=.8) for c in range(4) for m in range(4)],
        edge_bandwidth=lambda e:e['capacity'])
    small=catalog(tiny);weights=rng.random(len(small));brute=-1.;covers=0
    for size in (1,2):
        for selected in itertools.combinations(range(len(small)),size):
            cs=Counter(c for j in selected for c in small[j].compute)
            ms=Counter(m for j in selected for m in small[j].memory)
            if cs==Counter(range(4)) and ms==Counter(range(4)):
                brute=max(brute,sum(weights[j] for j in selected));covers+=1
    solved=solve_cover(small,weights,n=4);assert solved['feasible'] and abs(solved['value']-brute)<1e-10
    aa=assemble(small,[dict(ratio=.5) for _ in small],solved['selected'],n=4)
    primal_audit(tiny,aa,np.ones(4),range(4))
    output['master_bruteforce']=dict(catalog_size=len(small),feasible_covers=covers,objective_error=abs(solved['value']-brute))
    # Deliberate counterexamples exercise assumptions rather than mirror outputs.
    pair=next(q for q in qs if len(q.compute)==2);local=pair.local_physical(base)
    a=pair.matrix(.5,36)[np.ix_(pair.compute,pair.memory)]
    bad=a.copy();bad[0]*=1.1;must_reject(lambda:primal_audit(local,bad,[1,1],[0,1]))
    bad=a.copy();bad[0]=[.6,.4];must_reject(lambda:primal_audit(local,bad,[1,1],[0,1]))
    missing=copy.deepcopy(local);missing.edges=missing.edges[1:]
    must_reject(lambda:primal_audit(missing,a,[1,1],[0,1]))
    weak=copy.deepcopy(local);weak.edges[0]['capacity']=.4
    must_reject(lambda:primal_audit(weak,a,[1,1],[0,1]))
    shared=copy.deepcopy(base)
    for e in shared.edges:
        if e['c']==0:e['cp']=0
    must_reject(lambda:geometry_contract(shared))
    must_reject(lambda:pair.predict(.5,np.zeros((1,36),bool),floor=0))
    must_reject(lambda:assemble([pair],[dict(ratio=.5)],[0,0]))
    output['rejected_mutations']=['duplicated_bytes','unbalanced_residency','missing_HB','overcommitted_HB','shared_port_fast_formula','wrong_service_floor','overlapping_components']
    output.update(passed=True,elapsed_s=time.time()-start)
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps(output,indent=2),flush=True)


if __name__=='__main__':main()
