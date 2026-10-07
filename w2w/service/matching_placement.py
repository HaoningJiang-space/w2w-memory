"""Matching structure and capacitated *reticle-level* static service relaxation.

This does not synthesize a bank exposure circuit. Memory reticle service is
explicitly 1 TB/s (not scaled by contour area); each port has 4/P TB/s.
"""
from w2w.workloads.reticle import scenarios
import numpy as np
import networkx as nx
from scipy.optimize import linprog
from scipy.sparse import lil_matrix
from Reticle import create_reticle
from Wafer import Wafer
from System import System
from w2w.geometry.memory_model import MemoryFabric


def contoured(pitch=25.6, stagger=16.5):
    wafers=[]
    for typ,shape,ports in [('compute','H','corner-center'),('memory','plus','edge-center')]:
        reticles=[create_reticle((col-2.5)*pitch,(row-2.5)*33+(col%2-.5)*stagger,
                                26.,33.,typ,shape,.4,ports,(.4,8.25))
                  for row in range(6) for col in range(6)]
        wafers.append(Wafer(reticles,300,typ,'matching_contoured'))
    return MemoryFabric(System(wafers,'memory_and_logic',300,'rectangular',
                        'matching_contoured','direct_only','analytical','synthetic'))


def bipartite(n, edges):
    g=nx.Graph();g.add_nodes_from(range(2*n))
    g.add_edges_from((c,n+m) for c,m in sorted(edges))
    return g


def perfect(n, edges):
    g=bipartite(n,edges)
    result=nx.bipartite.maximum_matching(g,top_nodes=set(range(n)))
    return [result[c]-n for c in range(n)] if len(result)==2*n else None


def packing(n, edges):
    """Maximum number of edge-disjoint PMs via integral k-factor max flow.

    Removing greedy PMs alone is not a correct maximum packing algorithm.
    """
    es=sorted(set(edges));g=bipartite(n,es);best=[]
    for k in range(1,min(dict(g.degree()).values(),default=0)+1):
        f=nx.DiGraph()
        for c in range(n):f.add_edge('s',c,capacity=k)
        for c,m in es:f.add_edge(c,n+m,capacity=1)
        for m in range(n):f.add_edge(n+m,'t',capacity=k)
        value,flow=nx.maximum_flow(f,'s','t')
        if value!=n*k:break
        support={(c,m) for c,m in es if flow[c].get(n+m,0)}
        best=[]
        for _ in range(k):
            p=perfect(n,support)
            assert p is not None
            best.append(p);support.difference_update(enumerate(p))
    return best


def audit(n, edges, force_check=False):
    es=set(edges);p=perfect(n,es)
    if p is None:
        return dict(edges=len(es),perfect=False,allowed_edges=0,unique=False,
                    max_disjoint=0,pack=[])
    owner={m:c for c,m in enumerate(p)}
    directed=nx.DiGraph();directed.add_nodes_from(range(n))
    directed.add_edges_from((c,owner[m]) for c,m in es)
    components=list(nx.strongly_connected_components(directed))
    label={c:i for i,s in enumerate(components) for c in s}
    allowed={(c,m) for c,m in es if label[c]==label[owner[m]]}
    if force_check:
        # Independent force-edge check: delete both endpoints, then match n-1.
        for c,m in es:
            g=bipartite(n,es);g.remove_nodes_from([c,n+m])
            result=nx.bipartite.maximum_matching(g,top_nodes=set(range(n))-{c})
            assert ((c,m) in allowed)==(len(result)==2*(n-1))
    packs=packing(n,es)
    dim=len(allowed)-2*n+nx.number_connected_components(bipartite(n,allowed))
    return dict(edges=len(es),perfect=True,allowed_edges=len(allowed),
                unique=len(allowed)==n,balanced_layout_dimension=dim,
                alternating_component_sizes=sorted(map(len,components)),
                max_disjoint=len(packs),pack=packs)


def mixture(matchings, weights):
    w=np.asarray(weights,float);n=len(matchings[0]);a=np.zeros((n,n))
    if len(w)!=len(matchings) or (w<0).any() or not np.isclose(w.sum(),1):
        raise ValueError('Convex combination required')
    for p,weight in zip(matchings,w):
        if sorted(p)!=list(range(n)):raise ValueError('Not a perfect matching')
        a[np.arange(n),p]+=weight
    return a


class ReticleService:
    """Fixed bytes: sum(flow on C-M edges) = A[c,m] * rate[c].

    Explicit port and overlap capacities. No forwarding/replication/migration.
    All banks inside one M are pooled: a relaxation, not implemented hardware.
    """
    def __init__(self, physical):
        self.p=physical;self.n=len(physical.compute);self.es=physical.edges
        if len(physical.memory)!=self.n:raise ValueError('Equal counts required')
        self.e=len(self.es);groups={}
        def add(key,cap,i):
            if key not in groups:groups[key]=(cap,[])
            groups[key][1].append(i)
        for i,e in enumerate(self.es):
            add(('m',e['m']),1.,i)
            add(('mp',e['m'],e['mp']),4/len(physical.memory[e['m']].vertical_connectors),i)
            add(('cp',e['c'],e['cp']),4/len(physical.compute[e['c']].vertical_connectors),i)
        self.ub=lil_matrix((len(groups),self.e+self.n+1));self.cap=[]
        for row,(cap,indices) in enumerate(groups.values()):
            self.ub[row,indices]=1;self.cap.append(cap)
        self.ub=self.ub.tocsr();self.cap=np.array(self.cap)
        self.edge_caps=[physical.edge_bandwidth(e) for e in self.es]

    def solve(self, layout, active, objective='throughput', floor=0.):
        active=sorted(set(active));n=self.n;nv=self.e+n+1
        if not active:raise ValueError('Nonempty active set required')
        if objective not in ('throughput','common'):raise ValueError('Unknown objective')
        if layout is not None:
            layout=np.asarray(layout,float)
            if layout.shape!=(n,n) or (layout<0).any() or not np.allclose(layout.sum(axis=1),1):
                raise ValueError('Invalid static byte fractions')
            eq=lil_matrix((n*n+len(active),nv))
            for i,e in enumerate(self.es):eq[e['c']*n+e['m'],i]=1
            for c,m in zip(*np.nonzero(layout)):eq[c*n+m,self.e+c]=-layout[c,m]
            offset=n*n
        else:
            # Full-load best common service with free reticle byte distribution.
            eq=lil_matrix((n+len(active),nv))
            for i,e in enumerate(self.es):eq[e['c'],i]=1
            for c in range(n):eq[c,self.e+c]=-1
            offset=n
        if objective=='common':
            for row,c in enumerate(active):
                eq[offset+row,self.e+c]=1;eq[offset+row,-1]=-1
        bounds=[(0,v) for v in self.edge_caps]+[(floor,4) if c in active else (0,0) for c in range(n)]+[(0,4)]
        cost=np.zeros(nv)
        if objective=='common':cost[-1]=-1
        else:cost[self.e:self.e+n]=-1
        result=linprog(cost,A_ub=self.ub,b_ub=self.cap,A_eq=eq.tocsr(),
                       b_eq=np.zeros(eq.shape[0]),bounds=bounds,method='highs',
                       options={'primal_feasibility_tolerance':1e-9,'dual_feasibility_tolerance':1e-9})
        if not result.success:return dict(feasible=False,status=int(result.status))
        rates=result.x[self.e:self.e+n];flow=result.x[:self.e]
        bound_violation=max([max(lo-v,v-hi,0) for v,(lo,hi) in zip(result.x,bounds)])
        residual=max(float(np.max(np.abs(eq@result.x))),float(max(0,np.max(self.ub@result.x-self.cap))),bound_violation)
        return dict(feasible=True,mean=float(rates[active].mean()),minimum=float(rates[active].min()),
                    p5=float(np.percentile(rates[active],5)),rates=rates.tolist(),
                    residual=residual,flow=flow.tolist())
