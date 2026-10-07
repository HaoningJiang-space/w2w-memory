"""Restricted static cycle configurations with explicit analytic contracts.

Unit reticle service, two positive byte fractions, active floor=1. No bank
circuit claim. Reject shared-port/multipath cases instead of applying a formula
outside its assumptions. Global LP remains the independent service oracle.
"""
from dataclasses import dataclass
from collections import Counter
from types import SimpleNamespace
import hashlib
import json
import numpy as np
import networkx as nx
from scipy.optimize import milp, Bounds, LinearConstraint
from scipy.sparse import csc_matrix
from matching_placement import bipartite


def canonical(cycle):
    v=list(cycle);i=v.index(min(v));v=v[i:]+v[:i]
    return min(tuple(v),tuple([v[0]]+list(reversed(v[1:]))))


def enumerate_cycles(physical, maximum=4):
    """Bounded DFS, independently checked against NetworkX simple_cycles."""
    n=len(physical.compute)
    g=bipartite(n,{(e['c'],e['m']) for e in physical.edges})
    output=set()
    def visit(start,path):
        for v in sorted(g[path[-1]]):
            if v==start:
                if len(path)>=4:output.add(canonical(path))
            elif len(path)<2*maximum and v>start and v not in path:
                visit(start,path+[v])
    for start in range(n):visit(start,[start])
    return sorted(output)


def geometry_contract(p):
    if len(p.compute)!=len(p.memory):raise ValueError('Equal reticle counts required')
    if any(v>1 for v in Counter((e['c'],e['m']) for e in p.edges).values()):
        raise ValueError('Analytic path model does not support parallel C-M links')
    for kind in ('compute','memory'):
        keys=[(e['c'],e['cp']) if kind=='compute' else (e['m'],e['mp']) for e in p.edges]
        if max(Counter(keys).values(),default=0)>1:
            raise ValueError('Shared physical port: use general flow LP, not cycle formula')
    if any(not 0<p.edge_bandwidth(e)<1 for e in p.edges):
        raise ValueError('This strict positive two-path family requires edge capacities in (0,1)')


@dataclass(frozen=True)
class Configuration:
    cycle: tuple
    compute: tuple
    memory: tuple
    a: tuple
    b: tuple
    lower: float
    upper: float
    rivals: tuple

    @classmethod
    def build(cls,p,cycle):
        n=len(p.compute);v=canonical(cycle);k=len(v)//2
        if len(v)%2 or k<2 or len(set(v))!=len(v):raise ValueError('Not a simple alternating cycle')
        cs=tuple(v[::2]);ms=tuple(m-n for m in v[1::2])
        if any(not 0<=i<n for i in cs+ms):raise ValueError('Invalid bipartite node ordering')
        edges={(e['c'],e['m']):e for e in p.edges}
        try:
            a=tuple(p.edge_bandwidth(edges[c,ms[i]]) for i,c in enumerate(cs))
            b=tuple(p.edge_bandwidth(edges[c,ms[i-1]]) for i,c in enumerate(cs))
        except KeyError as e:raise ValueError('Missing physical edge') from e
        lo=max(1-x for x in b);hi=min(a)
        if lo>hi+1e-10:return None
        if not 0<lo<=hi+1e-10<1:raise ValueError('Degenerate zero-fraction cycle unsupported')
        if lo>hi:lo=hi=(lo+hi)/2
        rivals=tuple(tuple(sorted({cs[i-1],cs[(i+1)%k]})) for i in range(k))
        return cls(v,cs,ms,a,b,lo,hi,rivals)

    def matrix(self,ratio,n):
        if not self.lower-1e-10<=ratio<=self.upper+1e-10:raise ValueError('Ratio violates full-load feasibility')
        a=np.zeros((n,n))
        for i,c in enumerate(self.compute):
            a[c,self.memory[i]]=ratio;a[c,self.memory[i-1]]=1-ratio
        return a

    def ceilings(self,ratio,controller=4.):
        return np.minimum(controller,np.minimum(np.array(self.a)/ratio,np.array(self.b)/(1-ratio)))

    def optimize(self,coefficients,controller=4.):
        weights=np.asarray(coefficients,float)
        if weights.shape!=(len(self.compute),) or (weights<0).any():raise ValueError('Nonnegative local weights required')
        if controller<1:raise ValueError('Controller cannot sustain floor')
        points={self.lower,self.upper}
        for a,b in zip(self.a,self.b):
            for x in (a/(a+b),a/controller,1-b/controller):
                if self.lower-1e-12<=x<=self.upper+1e-12:points.add(min(self.upper,max(self.lower,x)))
        values=[(float(weights@(self.ceilings(x,controller)-1)),x) for x in sorted(points)]
        value,ratio=max(values,key=lambda t:t[0])
        return dict(ratio=ratio,value=value,ceilings=self.ceilings(ratio,controller).tolist(),points=sorted(points))

    def predict(self,ratio,activity,floor=1.):
        if floor!=1:raise ValueError('Closed form requires active floor exactly one')
        activity=np.asarray(activity,bool)
        if activity.ndim!=2 or any(c>=activity.shape[1] for c in self.compute):raise ValueError('Invalid activity matrix')
        rates=np.zeros(activity.shape)
        for j,c in enumerate(self.compute):
            alone=~activity[:,self.rivals[j]].any(axis=1)
            rates[:,c]=activity[:,c]*(1+(self.ceilings(ratio)[j]-1)*alone)
        return rates

    def local_physical(self,p):
        cs={c:i for i,c in enumerate(self.compute)};ms={m:i for i,m in enumerate(self.memory)}
        es=[dict(e,c=cs[e['c']],m=ms[e['m']],capacity=p.edge_bandwidth(e)) for e in p.edges if e['c'] in cs and e['m'] in ms]
        return SimpleNamespace(compute=[p.compute[c] for c in self.compute],memory=[p.memory[m] for m in self.memory],
                               edges=es,edge_bandwidth=lambda e:e['capacity'])


def catalog(p,maximum=4):
    geometry_contract(p)
    return [q for cycle in enumerate_cycles(p,maximum) if (q:=Configuration.build(p,cycle)) is not None]


def catalog_hash(configs):
    return hashlib.sha256(json.dumps([q.cycle for q in configs]).encode()).hexdigest()


def coefficients(configs,activity):
    activity=np.asarray(activity,bool);counts=activity.sum(axis=1)
    if (counts==0).any():raise ValueError('Objective undefined for empty active set')
    cache={};result=[]
    for q in configs:
        row=[]
        for c,rivals in zip(q.compute,q.rivals):
            key=(c,rivals)
            if key not in cache:cache[key]=float(np.mean(activity[:,c]*(~activity[:,rivals].any(axis=1))/counts))
            row.append(cache[key])
        result.append(row)
    return result


def solve_cover(configs,values,n=36,forced=None,relaxed=False):
    incidence=np.zeros((2*n,len(configs)))
    for j,q in enumerate(configs):
        incidence[list(q.compute),j]=1;incidence[n+np.array(q.memory),j]=1
    lb=np.zeros(len(configs));ub=np.ones(len(configs))
    if forced is not None:lb[forced]=1
    result=milp(-np.array(values,float),integrality=np.zeros(len(configs)) if relaxed else np.ones(len(configs)),
        bounds=Bounds(lb,ub),constraints=LinearConstraint(csc_matrix(incidence),np.ones(2*n),np.ones(2*n)),
        options={'mip_rel_gap':0.,'time_limit':120.})
    if not result.success:
        if result.status==2:return dict(feasible=False,status=2)
        raise RuntimeError(f'Uncertified cover solve: {result.message}')
    selected=np.flatnonzero(result.x>.5).tolist()
    if not relaxed:
        assert np.max(np.abs(result.x-np.round(result.x)))<1e-7
        assert np.max(np.abs(incidence@np.round(result.x)-1))<1e-7
    return dict(feasible=True,selected=selected,value=float(-result.fun),
        gap=float(getattr(result,'mip_gap',0) or 0),bound=float(-(getattr(result,'mip_dual_bound',None) if getattr(result,'mip_dual_bound',None) is not None else result.fun)))


def assemble(configs,choices,selected,n=36):
    counts_c=Counter(c for j in selected for c in configs[j].compute)
    counts_m=Counter(m for j in selected for m in configs[j].memory)
    if counts_c!=Counter(range(n)) or counts_m!=Counter(range(n)):
        raise ValueError('Components must cover every compute and memory exactly once')
    a=sum((configs[j].matrix(choices[j]['ratio'],n) for j in selected),start=np.zeros((n,n)))
    a.setflags(write=False)
    return a


def primal_audit(p,a,rates,active,floor=1.):
    """Reconstruct bytes and every port load without calling the LP."""
    n=len(p.compute);a=np.asarray(a);r=np.asarray(rates)
    if a.shape!=(n,n) or r.shape!=(n,) or not np.isfinite(a).all() or not np.isfinite(r).all():raise ValueError('Invalid arrays')
    if (a<0).any() or not np.allclose(a.sum(axis=0),1,atol=1e-10,rtol=0) or not np.allclose(a.sum(axis=1),1,atol=1e-10,rtol=0):
        raise ValueError('Layout must conserve bytes and full-load balance')
    if np.max(4*a.sum(axis=0))>16+1e-10:raise ValueError('Data capacity exceeded')
    es={(e['c'],e['m']):e for e in p.edges};active=set(active)
    # Check support even for currently inactive clients.
    if any((c,m) not in es for c,m in zip(*np.nonzero(a))):raise ValueError('Unphysical data path')
    violations=[float(np.max(a.T@r-1)),float(np.max(r-4)),float(-np.min(r))]
    violations.extend((floor-r[c]) if c in active else abs(r[c]) for c in range(n))
    cp=Counter();mp=Counter()
    for c,m in zip(*np.nonzero(a)):
        e=es[c,m];flow=a[c,m]*r[c]
        violations.append(flow-p.edge_bandwidth(e));cp[c,e['cp']]+=flow;mp[m,e['mp']]+=flow
    violations.extend(v-4/len(p.compute[c].vertical_connectors) for (c,_),v in cp.items())
    violations.extend(v-4/len(p.memory[m].vertical_connectors) for (m,_),v in mp.items())
    residual=max(0.,*violations)
    if residual>1e-8:raise ValueError(f'Resource overcommit: {residual}')
    return residual
