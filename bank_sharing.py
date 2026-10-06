"""Bounded repeated bank-port fabrics and frozen address-layout service bounds.

No inter-reticle forwarding, replication, migration, or per-test layout repair.
Costs are circuit connection/Manhattan wire proxies, not synthesized area.
"""
from dataclasses import dataclass
from itertools import combinations
import hashlib
import json
import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix
from memory_model import MemoryFabric, construct_memory_system
from VerticalConnector import VerticalConnector

BANKS = 32
PORTS = 4
PAGES = 128
DATA_GIB = 4.0
PAGE_GIB = DATA_GIB / PAGES
BANK_GIB = 16.0 / BANKS
BANK_BW = 1.0 / BANKS


def geometry(method, diameter=300):
    """Same 36C/36M and 4 TB/s endpoint budgets for every main placement."""
    if method not in ('aligned', 'half_shifted_x', 'half_shifted'):
        raise ValueError('Resource-matched placements only')
    system = construct_memory_system(dict(wafer_diameter=diameter, method=method),
                                     dict(reticle_size=(26.,33.)))
    for wafer in system.wafers:
        for reticle in wafer.reticles:
            reticle.vertical_connectors = [
                VerticalConnector(reticle.x + (col-.5)*13.,
                                  reticle.y + (row-.5)*16.5, 13., 16.5)
                for row in range(2) for col in range(2)]
    return MemoryFabric(system)


def private_owner(bank):
    return (bank//4//4)*2 + (bank%4//2)


def templates(k):
    """Candidate repeated masks, exact degree and equal connection count.

    k=2 explores pair, cyclic, chain, geometry-nearest and balanced-mix graphs.
    These are heuristics/candidate families, not a global synthesis optimum.
    """
    owners=[private_owner(b) for b in range(BANKS)]
    if k==1:return [('private', tuple((o,) for o in owners))]
    if k==4:return [('full', tuple(tuple(range(PORTS)) for _ in owners))]
    if k!=2:raise ValueError('With four HB regions k must be 1, 2, or 4')
    candidates=[]
    def add(name,seconds):
        mask=tuple(tuple(sorted((o,int(p)))) for o,p in zip(owners,seconds))
        if any(len(set(ports))!=2 for ports in mask):raise ValueError('Degree not two')
        if mask not in [m for _,m in candidates]:candidates.append((name,mask))
    for delta in (1,2,3):add('xor_'+str(delta),[o^delta for o in owners])
    # Include high-fan-in stars so the conventional-home comparison is not
    # artificially limited to balanced graphs. All candidates have 64 edges.
    for hub in range(PORTS):
        add('star_'+str(hub),[hub if o!=hub else o^1 for o in owners])
    ring=[0,1,3,2]
    for step in (1,-1):add('cyclic_'+str(step),[ring[(ring.index(o)+step)%4] for o in owners])
    ranks={o:0 for o in range(PORTS)}; chain=[];near=[];mix=[]
    for b,o in enumerate(owners):
        rank=ranks[o];ranks[o]+=1
        chain.append(1 if o==0 else 2 if o==3 else o+(-1 if rank%2 else 1))
        x,y=(b%4-1.5)*6.5,(b//4-3.5)*4.125
        near.append(min((p for p in range(PORTS) if p!=o),
                        key=lambda p:(abs(x-(p%2-.5)*13)+abs(y-(p//2-.5)*16.5),p)))
        mix.append((o+1+rank%3)%PORTS)
    add('chain',chain);add('geometry_nearest',near);add('balanced_mix',mix)
    for seed in range(4):
        rng=np.random.default_rng(seed);seconds=[]
        permutations={o:rng.permutation([1,1,1,2,2,2,3,3]) for o in range(PORTS)}
        ranks={o:0 for o in range(PORTS)}
        for o in owners:
            seconds.append((o+int(permutations[o][ranks[o]]))%PORTS);ranks[o]+=1
        # Balanced-mix inspired, not a proven expander; fan-in explicitly reported.
        add('mixed_seed_'+str(seed),seconds)
    return candidates


def validate_mask(mask):
    if len(mask)!=BANKS:raise ValueError('One port set per bank is required')
    for b,ports in enumerate(mask):
        if not ports or len(set(ports))!=len(ports) or private_owner(b) not in ports or any(p not in range(PORTS) for p in ports):
            raise ValueError('Invalid bank-port connectivity')
    return tuple(tuple(ports) for ports in mask)


def circuit_cost(mask):
    mask=validate_mask(mask)
    total_wire=extra_wire=0.
    for b,ports in enumerate(mask):
        x,y=(b%4-1.5)*6.5,(b//4-3.5)*4.125
        for p in ports:
            px,py=(p%2-.5)*13.,(p//2-.5)*16.5
            length=abs(x-px)+abs(y-py)
            total_wire+=length
            if p!=private_owner(b):extra_wire+=length
    fanin=[sum(p in ports for ports in mask) for p in range(PORTS)]
    return dict(k=max(map(len,mask)),bank_port_connections=sum(map(len,mask)),
                extra_connections=sum(map(len,mask))-BANKS,port_fanin=fanin,
                wire_mm=total_wire,extra_wire_mm=extra_wire,
                data_wire_bit_mm_256bit=total_wire*256,
                hb_regions_per_reticle=PORTS,controller_ports=PORTS,
                hb_total_tb_s_per_reticle=4.,
                cost_model='Per-reticle memory-side digital selection/arbitration and Manhattan routing proxy; not synthesized mm2')


@dataclass
class Scenario:
    pattern: str
    fraction: float
    seed: int
    demand: np.ndarray
    weights: np.ndarray

    def serializable(self):
        return dict(pattern=self.pattern, fraction=self.fraction, seed=self.seed,
                    demand_tb_s=self.demand.tolist(), page_weights=self.weights.tolist())


def scenarios(fabric, seeds, fractions=(.25,.5,.75,1.), patterns=('uniform','hotspot','clustered','correlated')):
    coordinates=np.array([(r.x,r.y) for r in fabric.compute])
    distance=np.sqrt(((coordinates[:,None]-coordinates[None,:])**2).sum(axis=2))
    kernel=np.exp(-distance**2/(2*45**2))
    n=len(coordinates); output=[]
    for pattern_id,pattern in enumerate(patterns):
        for fraction in fractions:
            for seed in seeds:
                rng=np.random.default_rng(np.random.SeedSequence([seed,pattern_id,round(100*fraction)]))
                count=max(1,round(n*fraction))
                if pattern in ('uniform','hotspot'):
                    active=rng.choice(n,count,replace=False)
                elif pattern=='clustered':
                    center=int(rng.integers(n));active=np.argsort(distance[center]+rng.uniform(0,.01,n))[:count]
                elif pattern=='correlated':
                    active=np.argsort(kernel@rng.normal(size=n))[-count:]
                else: raise ValueError('Unknown demand pattern')
                demand=np.zeros(n);demand[active]=4.
                weights=np.full(PAGES,1/PAGES)
                if pattern=='hotspot':
                    weights[:16]=.8/16;weights[16:]=.2/(PAGES-16)
                output.append(Scenario(pattern,fraction,seed,demand,weights))
    return output


class LayoutCapacityError(ValueError):
    """A layout heuristic exhausted reachable storage; not a proof of infeasibility."""


class BankFabric:
    def __init__(self, physical, mask):
        self.physical=physical
        self.mask=validate_mask(mask)
        self.nc=len(physical.compute);self.nm=len(physical.memory)
        self.edges=physical.edges
        self.paths={}
        for i,e in enumerate(self.edges):
            for b in range(BANKS):
                if e['mp'] in self.mask[b]:
                    self.paths.setdefault((e['c'],e['m']*BANKS+b),[]).append(i)
        self.candidates=[sorted(g for c,g in self.paths if c==i) for i in range(self.nc)]
        # Full bank and HB resource capacities, invariant across sharing degree.
        self.limits=np.r_[np.full(self.nm*BANKS,BANK_BW),
                          [physical.edge_bandwidth(e) for e in self.edges]]

    def plan_layout(self, mode, training=()):
        """Place unique logical pages once; no duplicate data; finite bank slots.

        home_striped is identical physical bank mapping for every placement/k.
        static_interleaved uses geometry, but no workload observations.
        static_train_greedy uses training-only access frequencies.
        """
        layout=np.full((self.nc,PAGES),-1,dtype=np.int32)
        if mode=='home_striped':
            if self.nc!=self.nm:raise ValueError('Home mapping requires equal counts')
            layout[:]=np.arange(self.nc)[:,None]*BANKS + np.arange(PAGES)[None,:]%BANKS
        elif mode in ('static_interleaved','static_train_greedy'):
            if mode=='static_train_greedy' and not training:
                raise ValueError('Training data required')
            freq=(np.mean([s.demand[:,None]*s.weights for s in training],axis=0)
                  if mode=='static_train_greedy' else np.ones((self.nc,PAGES)))
            slots=np.zeros(self.nm*BANKS,dtype=int)
            load=np.zeros(self.nm*BANKS)
            client_used=np.zeros((self.nc,self.nm*BANKS),dtype=int)
            mem_used=np.zeros((self.nc,self.nm),dtype=int)
            # Low-reachability clients first; then hot pages. Deterministic ties.
            order=sorted(range(self.nc),key=lambda c:(len(self.candidates[c]),c))
            page_order={c:np.argsort(-freq[c],kind='stable') for c in order}
            for rank in range(PAGES):
                for c in order:
                    page=int(page_order[c][rank])
                    possible=np.array([g for g in self.candidates[c] if slots[g] < int(round(BANK_GIB/PAGE_GIB))])
                    if len(possible)==0:raise LayoutCapacityError('Greedy layout cannot fit; no silent capacity overflow')
                    if mode=='static_interleaved':
                        # Even bank striping with deterministic address hash tiebreak.
                        score=1000*client_used[c,possible]+10*slots[possible]+mem_used[c,possible//BANKS]/PAGES
                    else:
                        score=load[possible]/BANK_BW+freq[c,page]/BANK_BW+client_used[c,possible]*.02+mem_used[c,possible//BANKS]*.002
                    tie=((possible*1103515245+(c+1)*12345)%2147483647)/2147483647
                    chosen=int(possible[np.argmin(score+tie*1e-6)])
                    layout[c,page]=chosen;slots[chosen]+=1;load[chosen]+=freq[c,page]
                    client_used[c,chosen]+=1;mem_used[c,chosen//BANKS]+=1
        else:raise ValueError('Unknown fixed layout')
        self.validate_layout(layout)
        return layout

    def validate_layout(self,layout):
        if layout.shape!=(self.nc,PAGES) or not np.issubdtype(layout.dtype,np.integer):
            raise ValueError('Layout must map every logical page exactly once')
        if (layout<0).any() or (layout>=self.nm*BANKS).any():raise ValueError('Invalid physical bank')
        used=np.bincount(layout.ravel(),minlength=self.nm*BANKS)*PAGE_GIB
        if max(used)>BANK_GIB+1e-10:raise ValueError('Bank storage capacity exceeded')
        return used

    @staticmethod
    def layout_hash(layout):
        return hashlib.sha256(np.asarray(layout,dtype='<i4').tobytes()).hexdigest()

    def compile(self,layout=None,weights=None):
        return ServiceProblem(self,layout,weights)


class ServiceProblem:
    """Maximize completed-stream rate, preserving each stream's byte mix.

    A page without a path forces that client's *entire* stream rate to zero.
    It is never discarded while counting its reachable pages as completed work.
    layout=None is a free-bank-service relaxation, not a physical data placement.
    """
    def __init__(self,fabric,layout,weights):
        self.fabric=fabric; nc=fabric.nc
        if layout is not None:
            fabric.validate_layout(layout)
            weights=np.asarray(weights,dtype=float)
            if weights.shape!=(PAGES,) or (weights<0).any() or not np.isclose(weights.sum(),1):
                raise ValueError('Invalid fixed request mixture')
        groups=[]
        self.missing=np.zeros(nc)
        for c in range(nc):
            if layout is None:
                groups.append((c,1.,[(g,e) for g in fabric.candidates[c] for e in fabric.paths[c,g]]))
            else:
                shares=np.bincount(layout[c],weights=weights,minlength=fabric.nm*BANKS)
                for g in np.flatnonzero(shares>0):
                    paths=[(int(g),e) for e in fabric.paths.get((c,int(g)),[])]
                    groups.append((c,float(shares[g]),paths))
                    if not paths:self.missing[c]+=shares[g]
        ur=[];uc=[];ud=[];er=[];ec=[];ed=[]
        nvar=nc
        for row,(c,share,paths) in enumerate(groups):
            er.append(row);ec.append(c);ed.append(-share)
            for g,edge in paths:
                er.append(row);ec.append(nvar);ed.append(1.)
                ur.extend([g,fabric.nm*BANKS+edge]);uc.extend([nvar,nvar]);ud.extend([1.,1.])
                nvar+=1
        self.ub=coo_matrix((ud,(ur,uc)),shape=(len(fabric.limits),nvar)).tocsr()
        self.eq=coo_matrix((ed,(er,ec)),shape=(len(groups),nvar)).tocsr()
        self.cost=np.r_[-np.ones(nc),np.zeros(nvar-nc)]
        self.nvar=nvar

    def solve(self,demand,objective="throughput"):
        fabric=self.fabric;demand=np.asarray(demand,dtype=float)
        if demand.shape!=(fabric.nc,) or not np.isfinite(demand).all() or (demand<0).any():
            raise ValueError('Invalid per-compute demand')
        bounds=[(0,min(4.,d)) for d in demand]+[(0,None)]*(self.nvar-fabric.nc)
        if objective=='throughput':
            costs=self.cost;ub=self.ub;eq=self.eq
        elif objective=='common':
            from scipy.sparse import hstack,vstack
            ub=hstack([self.ub,np.zeros((self.ub.shape[0],1))],format='csr')
            eq=hstack([self.eq,np.zeros((self.eq.shape[0],1))],format='csr')
            rows=np.repeat(np.arange(fabric.nc),2)
            cols=np.ravel(np.column_stack([np.arange(fabric.nc),np.full(fabric.nc,self.nvar)]))
            vals=np.ravel(np.column_stack([np.ones(fabric.nc),-demand]))
            common=coo_matrix((vals,(rows,cols)),shape=(fabric.nc,self.nvar+1)).tocsr()
            eq=vstack([eq,common],format='csr')
            costs=np.r_[np.zeros(self.nvar),-1.];bounds.append((0,1))
        else:raise ValueError('Unknown objective')
        res=linprog(costs,A_ub=ub,b_ub=fabric.limits,
                    A_eq=eq,b_eq=np.zeros(eq.shape[0]),bounds=bounds,method='highs')
        if not res.success:raise RuntimeError(res.message)
        error=max(0.,float(np.max(ub@res.x-fabric.limits)),float(np.max(np.abs(eq@res.x))))
        if error>1e-7:raise RuntimeError('Service constraints violated')
        served=res.x[:fabric.nc];active=demand>0
        return dict(total_tb_s=float(served.sum()),served_tb_s=served.tolist(),
                    tb_s_per_active=float(served.sum()/max(1,active.sum())),
                    unreachable_demand_fraction=float(np.dot(self.missing,demand)/max(1.,demand.sum())),
                    blocked_active_clients=int(np.count_nonzero(active & (self.missing>1e-10))),
                    min_served_fraction=float(np.min(served[active]/demand[active])) if active.any() else 0.,
                    p5_tb_s=float(np.percentile(served[active],5)) if active.any() else 0.,
                    common_completion=float(res.x[-1]) if objective=="common" else None,
                    constraint_residual=error)


def search_templates(physical,k,layout_mode,training,frozen_layout=None):
    """Select using only training scenarios; hardware is frozen for all test sets.

    Exact selection within the declared repeated-template candidate family.
    static_train_greedy creates one offline mapping per candidate from training;
    static_interleaved uses a supplied *fixed ideal-connectivity* address mapping.
    """
    trials=[];best=None
    for name,mask in templates(k):
        fabric=BankFabric(physical,mask)
        layout_trials=[]
        if layout_mode=='static_train_greedy':
            ideal=BankFabric(physical,templates(4)[0][1])
            choices=[]
            for planner, target, mode in [('train_greedy',fabric,layout_mode),
                                          ('mask_interleaved',fabric,'static_interleaved'),
                                          ('geometry_interleaved',ideal,'static_interleaved'),
                                          ('home_striped',fabric,'home_striped')]:
                try:
                    choices.append((planner,target.plan_layout(mode,training)))
                except LayoutCapacityError as error:
                    layout_trials.append(dict(planner=planner,heuristic_failure=str(error)))
        else:
            layout=(None if layout_mode=='oracle' else frozen_layout if frozen_layout is not None
                    else fabric.plan_layout(layout_mode,training))
            choices=[(layout_mode,layout)]
        chosen=None
        for planner,layout in choices:
            compiled={};values=[]
            for scenario in training:
                key='oracle' if layout is None else scenario.weights.tobytes()
                if key not in compiled:compiled[key]=fabric.compile(layout,scenario.weights)
                values.append(compiled[key].solve(scenario.demand)['tb_s_per_active'])
            score=float(np.mean(values))
            layout_trials.append(dict(planner=planner,training_score=score))
            if chosen is None or score>chosen[0]+1e-10:chosen=(score,layout,planner)
        score,layout,planner=chosen
        cost=circuit_cost(mask)
        trial=dict(name=name,mask=[list(p) for p in mask],training_mean_tb_s_per_active=score,cost=cost,
                   planner=planner,layout_trials=layout_trials)
        trials.append(trial)
        key=(round(score,10),-cost['extra_wire_mm'],name)
        if best is None or key>best[0]:best=(key,fabric,layout,trial)
    return best[1],best[2],dict(selected=best[3],candidates=trials)


def periodic_reference(physical):
    """A mathematical torus, NOT wires across the physical wafer boundary."""
    import copy
    result=copy.deepcopy(physical)
    xs=sorted({r.x for r in result.compute});ys=sorted({r.y for r in result.compute})
    width=len(xs)*26.;height=len(ys)*33.
    def key(x,y):return (round(x%width,6),round(y%height,6))
    port_map={key(v.x,v.y):(m,p) for m,r in enumerate(result.memory) for p,v in enumerate(r.vertical_connectors)}
    edges=[]
    for c,r in enumerate(result.compute):
        for cp,v in enumerate(r.vertical_connectors):
            m,mp=port_map[key(v.x,v.y)]
            edges.append(dict(c=c,m=m,cp=cp,mp=mp,overlap_mm2=v.w*v.h,
                              compute_port_fraction=1.,memory_port_fraction=1.))
    result.edges=edges
    return result


def interior_compute_ids():
    """Common 25-node interior; retain all 36 memory reticles as reservoirs."""
    p=geometry('half_shifted')
    return [c for c in range(len(p.compute)) if len({e['cp'] for e in p.edges if e['c']==c})==PORTS]


def interior_scenario(s,physical):
    """Same phase seed/pattern, active candidates restricted to common interior."""
    allowed=interior_compute_ids()
    sub=type('Coordinates',(),dict(compute=[physical.compute[c] for c in allowed]))()
    restricted=scenarios(sub,[s.seed],fractions=(s.fraction,),patterns=(s.pattern,))[0]
    demand=np.zeros(len(physical.compute));demand[allowed]=restricted.demand
    return Scenario(s.pattern,s.fraction,s.seed,demand,s.weights.copy())


class PoolingNetwork:
    """Exact max-flow/min-cut certificate for free-bank-service relaxation.

    This bound ignores fixed data mixture; it cannot certify fixed-layout service.
    Repeated bank-port mask and every bank/HB/controller service cap are retained.
    """
    def __init__(self,fabric):
        import networkx as nx
        self.fabric=fabric
        self.graph=nx.DiGraph()
        for c in range(fabric.nc):self.graph.add_edge(('source',),('c',c),capacity=0.)
        for e in fabric.edges:
            u=('c',e['c']);v=('p',e['m'],e['mp'])
            cap=fabric.physical.edge_bandwidth(e)
            old=self.graph.get_edge_data(u,v,{}).get('capacity',0.)
            self.graph.add_edge(u,v,capacity=old+cap)
        for m in range(fabric.nm):
            for b in range(BANKS):
                for p in fabric.mask[b]:self.graph.add_edge(('p',m,p),('b',m,b),capacity=1e4)
                self.graph.add_edge(('b',m,b),('sink',),capacity=BANK_BW)

    def evaluate(self,demand):
        import networkx as nx
        from collections import deque
        demand=np.asarray(demand,dtype=float)
        for c,d in enumerate(demand):self.graph[('source',)][('c',c)]['capacity']=min(4.,float(d))
        residual=nx.algorithms.flow.preflow_push(self.graph,('source',),('sink',))
        flow=float(residual.graph['flow_value'])
        reached={('source',)};queue=deque(reached)
        while queue:
            u=queue.popleft()
            for v,a in residual[u].items():
                if v not in reached and a['capacity']-a['flow']>1e-8:
                    reached.add(v);queue.append(v)
        cut={'controller_or_demand':0.,'hb':0.,'bank_service':0.}
        for u in reached:
            for v,a in self.graph[u].items():
                if v in reached:continue
                kind='controller_or_demand' if u[0]=='source' else 'hb' if u[0]=='c' else 'bank_service' if u[0]=='b' else 'invalid'
                if kind=='invalid':raise RuntimeError('Infinite bank-port edge in min cut')
                cut[kind]+=a['capacity']
        if abs(sum(cut.values())-flow)>1e-7:raise RuntimeError('Invalid min-cut certificate')
        active=set(np.flatnonzero(demand>0).tolist())
        neighbors={e['m'] for e in self.fabric.edges if e['c'] in active}
        banks={g for c in active for g in self.fabric.candidates[c]}
        global_bound=min(float(np.minimum(demand,4).sum()),float(self.fabric.nm))
        served=[float(residual.get_edge_data(('source',),('c',c),{}).get('flow',0.))
                for c in range(self.fabric.nc)]
        subset=[c for c in active if ('c',c) in reached]
        subset_neighbors={e['m'] for e in self.fabric.edges if e['c'] in subset}
        return dict(oracle_tb_s=flow,min_cut_tb_s=sum(cut.values()),cut_components=cut,
                    served_tb_s=served,global_pooling_bound_tb_s=global_bound,
                    pooling_efficiency=flow/global_bound if global_bound else 0.,
                    stranded_vs_global_bound_tb_s=global_bound-flow,
                    neighbor_memory_count=len(neighbors),neighbor_bank_count=len(banks),
                    neighbor_bank_service_tb_s=len(banks)*BANK_BW,
                    memory_expansion=len(neighbors)/max(1,len(active)),
                    cut_active_subset=sorted(subset),cut_subset_neighbor_count=len(subset_neighbors))
