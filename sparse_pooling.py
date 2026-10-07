"""Static sparse pooling probes; matching count is not support degree.

The rate-only LP eliminates unique C-M flows algebraically. It retains memory,
edge, compute-port and memory-port capacities, and rejects parallel C-M paths.
ReticleService remains the independent explicit-flow validation reference.
"""
from collections import Counter
from math import comb
from types import SimpleNamespace
import itertools
import numpy as np
import networkx as nx
from scipy.optimize import linear_sum_assignment, linprog
from matching_placement import bipartite, perfect, mixture
from cycle_configurations import primal_audit


def factor_certificate(n, edges, degree):
    edges=sorted(set(edges));flow_graph=nx.DiGraph()
    for c in range(n):flow_graph.add_edge('s',c,capacity=degree)
    for c,m in edges:flow_graph.add_edge(c,n+m,capacity=1)
    for m in range(n):flow_graph.add_edge(n+m,'t',capacity=degree)
    value,flow=nx.maximum_flow(flow_graph,'s','t')
    cut,(left,right)=nx.minimum_cut(flow_graph,'s','t')
    crossing=[(u,v,data['capacity']) for u,v,data in flow_graph.edges(data=True) if u in left and v in right]
    assert sum(cap for _,_,cap in crossing)==cut==value
    support={(c,m) for c,m in edges if flow[c].get(n+m,0)}
    assert len(support)==value
    matchings=[]
    if value==n*degree:
        assert all(v==degree for v in dict(bipartite(n,support).degree()).values())
        for _ in range(degree):
            matching=perfect(n,support);assert matching is not None
            matchings.append(matching);support.difference_update(enumerate(matching))
        assert not support
    return dict(degree=degree,flow=int(value),required=n*degree,feasible=value==n*degree,
        cut_capacity=int(cut),source_side=sorted(left,key=str),cut_edges=crossing,
        matchings=matchings)


def complete_blocks(n,edges,degree):
    graph=bipartite(n,edges);count=0
    for cs in itertools.combinations(range(n),degree):
        common=set.intersection(*(set(graph[c]) for c in cs))
        if len(common)>=degree:count+=comb(len(common),degree)
    return count


def pool_expectation(degree,n=36,active=9,edge_capacity=.8,controller=4.):
    """Uniform fixed K_d,d blocks, conditional on the focal compute active.

    An attainable geometry-relaxed construction, NOT a degree-d global bound.
    """
    terms=[]
    for k in range(1,degree+1):
        probability=(comb(degree-1,k-1)*comb(n-degree,active-k)/comb(n-1,active-1)
                     if 0<=active-k<=n-degree else 0.)
        rate=min(degree/k,edge_capacity*degree,controller)
        terms.append(dict(active_in_pool=k,probability=probability,rate=rate))
    assert abs(sum(t['probability'] for t in terms)-1)<1e-12
    return dict(degree=degree,expectation=sum(t['probability']*t['rate'] for t in terms),terms=terms)


def block_physical(degree):
    # Five reserved 0.8-TB/s ports per reticle, same total 4-TB/s ledger.
    return SimpleNamespace(compute=[SimpleNamespace(vertical_connectors=list(range(5))) for _ in range(degree)],
        memory=[SimpleNamespace(vertical_connectors=list(range(5))) for _ in range(degree)],
        edges=[dict(c=c,m=m,cp=m,mp=c) for c in range(degree) for m in range(degree)],
        edge_bandwidth=lambda e:.8)


def matching_candidates(p,seeds=range(8)):
    """Geometry-only greedy expansion; no test or training activity is read.

    Start from verified home/reciprocal pair matchings. Additional PMs maximize
    new edges first, reduce squared multiplicity second, then break ties by a
    registered design seed. PMs can overlap; do not label them d-factors.
    """
    n=len(p.compute);edges={(e['c'],e['m']) for e in p.edges}
    base=[list(range(n)),[c^1 for c in range(n)]]
    assert all((c,m) in edges for matching in base for c,m in enumerate(matching))
    outputs=[];seen={}
    for seed in seeds:
        rng=np.random.default_rng(seed);matchings=[v.copy() for v in base]
        counts=mixture(matchings,[.5,.5])*2
        for count in (3,4):
            cost=np.full((n,n),np.inf)
            for c,m in sorted(edges):
                cost[c,m]=1000*(counts[c,m]>0)+(2*counts[c,m]+1)+rng.random()/(10*n)
            cs,ms=linear_sum_assignment(cost)
            assert np.isfinite(cost[cs,ms]).all()
            matchings.append(ms.tolist());counts[cs,ms]+=1
            layout=mixture(matchings,[1/count]*count)
            primal_audit(p,layout,np.ones(n),range(n))
            key=(count,layout.tobytes())
            if key in seen:continue
            seen[key]=True;layout.setflags(write=False)
            outputs.append(dict(name=f'mixture{count}_seed{seed}',terms=count,seed=seed,
                matchings=[v.copy() for v in matchings],layout=layout))
    return outputs


class FixedLayoutService:
    def __init__(self,p,layout):
        self.p=p;self.a=np.array(layout,copy=True);self.n=len(p.compute)
        primal_audit(p,self.a,np.ones(self.n),range(self.n))
        if len({(e['c'],e['m']) for e in p.edges})!=len(p.edges):
            raise ValueError('Parallel C-M paths require explicit-flow LP')
        rows=list(self.a.T.copy());caps=[1.]*self.n;ports={}
        for e in p.edges:
            c,m=e['c'],e['m'];row=np.zeros(self.n);row[c]=self.a[c,m]
            rows.append(row);caps.append(p.edge_bandwidth(e))
            for key,q in [(('c',c,e['cp']),4/len(p.compute[c].vertical_connectors)),
                          (('m',m,e['mp']),4/len(p.memory[m].vertical_connectors))]:
                if key not in ports:ports[key]=(np.zeros(self.n),q)
                ports[key][0][c]+=row[c]
        for row,q in ports.values():rows.append(row);caps.append(q)
        self.loads=np.array(rows);self.caps=np.array(caps);self.a.setflags(write=False)

    def solve(self,active):
        active=np.asarray(active,bool)
        if active.shape!=(self.n,) or not active.any():raise ValueError('Nonempty boolean activity required')
        result=linprog(-active.astype(float),A_ub=self.loads,b_ub=self.caps,
            bounds=[(1.,4.) if a else (0.,0.) for a in active],method='highs',
            options={'primal_feasibility_tolerance':1e-9,'dual_feasibility_tolerance':1e-9})
        if not result.success:raise RuntimeError(result.message)
        r=result.x;usage=self.loads@active.astype(float);positive=usage>0
        common=min(4.,float(np.min(self.caps[positive]/usage[positive])))
        residual=primal_audit(self.p,self.a,r,np.flatnonzero(active))
        primal_audit(self.p,self.a,active*common,np.flatnonzero(active))
        return dict(mean=float(r[active].mean()),common=common,minimum=float(r[active].min()),
            p5=float(np.percentile(r[active],5)),rates=r.tolist(),residual=residual)


def layout_summary(a):
    return dict(support_edges=int(np.count_nonzero(a)),
        compute_degree=dict(Counter(np.count_nonzero(a,axis=1).tolist())),
        memory_degree=dict(Counter(np.count_nonzero(a,axis=0).tolist())),
        largest_byte_fraction=float(a.max()))
