"""Finite balanced-circulation search for static sparse byte layouts.

Sensitivity only ranks proposals. Every accepted move is evaluated with the
fixed-byte service LP; this is a heuristic, not a convex/global certificate.
"""
import hashlib
import numpy as np
from scipy.optimize import linprog
from sparse_pooling import FixedLayoutService
from cycle_configurations import enumerate_cycles,primal_audit,geometry_contract

DENOMINATOR=60


def units(a):
    q=np.rint(np.asarray(a)*DENOMINATOR).astype(np.int16)
    if not np.allclose(q/DENOMINATOR,a,atol=1e-10,rtol=0):
        raise ValueError('Initial layout not on registered fraction grid')
    return q


def digest(a):return hashlib.sha256(np.asarray(a,dtype=float).tobytes()).hexdigest()


class Evaluation(FixedLayoutService):
    def __init__(self,p,a):
        super().__init__(p,a)
        self.paths=[];ports={}
        for e in p.edges:
            for key in [('c',e['c'],e['cp']),('m',e['m'],e['mp'])]:
                if key not in ports:ports[key]=self.n+len(p.edges)+len(ports)
        for i,e in enumerate(p.edges):
            self.paths.append((e['c'],e['m'],[e['m'],self.n+i,
                ports['c',e['c'],e['cp']],ports['m',e['m'],e['mp']]]))
        assert self.loads.shape[0]==self.n+len(p.edges)+len(ports)

    def batch(self,activity,sensitivity=False,audit=False):
        activity=np.asarray(activity,bool)
        if activity.ndim!=2 or activity.shape[1]!=self.n or not activity.any(axis=1).all():
            raise ValueError('Nonempty activity rows required')
        rates=[];common=[];gradient=np.zeros_like(self.a)
        for active in activity:
            result=linprog(-active.astype(float)/active.sum(),A_ub=self.loads,b_ub=self.caps,
                bounds=[(1.,4.) if a else (0.,0.) for a in active],method='highs',
                options={'primal_feasibility_tolerance':1e-9,'dual_feasibility_tolerance':1e-9})
            if not result.success:raise RuntimeError(result.message)
            r=result.x;rates.append(r)
            usage=self.loads@active.astype(float);positive=usage>0
            rate=min(4.,float(np.min(self.caps[positive]/usage[positive])));common.append(rate)
            if audit:
                primal_audit(self.p,self.a,r,np.flatnonzero(active))
                primal_audit(self.p,self.a,active*rate,np.flatnonzero(active))
            if sensitivity:
                for c,m,rows in self.paths:
                    gradient[c,m]+=r[c]*result.ineqlin.marginals[rows].sum()
        rates=np.array(rates);common=np.array(common)
        residual=max(0.,float(np.max(rates@self.loads.T-self.caps)),
            float(np.max(activity-rates)),float(np.max(rates-4)),float(np.max(np.abs(rates[~activity]),initial=0)))
        assert residual<1e-8
        means=rates.sum(axis=1)/activity.sum(axis=1)
        return dict(mean=float(means.mean()),means=means,common=common,rates=rates,
            gradient=gradient/len(activity),residual=residual)


class CirculationSearch:
    def __init__(self,p,activity,edge_budget=126,degree_budget=4):
        geometry_contract(p)  # One physical edge per port; full-load edge bounds suffice.
        self.p=p;self.activity=np.asarray(activity,bool);self.n=len(p.compute)
        self.edge_budget=edge_budget;self.degree_budget=degree_budget;self.cache={}
        self.limit=np.zeros((self.n,self.n),dtype=np.int16)
        for e in p.edges:
            self.limit[e['c'],e['m']]=int(np.floor(p.edge_bandwidth(e)*DENOMINATOR+1e-9))
        self.moves=[]
        for cycle in enumerate_cycles(p,4):
            cs=np.array(cycle[::2]);ms=np.array(cycle[1::2])-self.n
            self.moves.append((tuple(cycle),cs*self.n+ms,cs*self.n+np.roll(ms,1)))

    def valid(self,q):
        support=q>0
        return bool(q.shape==self.limit.shape and np.all(q>=0) and np.all(q<=self.limit)
            and np.all(q.sum(axis=0)==DENOMINATOR) and np.all(q.sum(axis=1)==DENOMINATOR)
            and np.count_nonzero(q)<=self.edge_budget
            and np.max(support.sum(axis=0))<=self.degree_budget
            and np.max(support.sum(axis=1))<=self.degree_budget)

    def evaluate(self,q):
        if not self.valid(q):raise ValueError('Invalid balanced sparse layout')
        key=q.tobytes()
        if key not in self.cache:
            self.cache[key]=Evaluation(self.p,q/DENOMINATOR).batch(self.activity,sensitivity=True)
        return self.cache[key]

    def proposals(self,q,gradient,fixed_support=False):
        if not self.valid(q):raise ValueError('Invalid starting layout')
        original=q>0;flat=q.ravel();limit=self.limit.ravel();grad=gradient.ravel();seen=set();out=[]
        for cycle,pos,neg in self.moves:
            for sign in (1,-1):
                add,subtract=(pos,neg) if sign==1 else (neg,pos)
                bound=int(min(np.min(flat[subtract]),np.min(limit[add]-flat[add])))
                if bound<=0:continue
                for step in sorted({min(5,bound),min(10,bound),bound}):
                    proposal=q.copy();v=proposal.ravel();v[add]+=step;v[subtract]-=step
                    if fixed_support and not np.array_equal(proposal>0,original):continue
                    if not self.valid(proposal):continue
                    key=proposal.tobytes()
                    if key in seen:continue
                    seen.add(key)
                    score=float(step/DENOMINATOR*(grad[add].sum()-grad[subtract].sum()))
                    out.append(dict(q=proposal,cycle=list(cycle),sign=sign,step=step,predicted_gain=score))
        return sorted(out,key=lambda v:-v['predicted_gain'])

    def run(self,start,fixed_support=False,rounds=4,seed=0):
        q=units(start);initial=self.evaluate(q);trajectory=[];trace=[];rng=np.random.default_rng(seed)
        for iteration in range(rounds):
            current=self.evaluate(q);proposals=self.proposals(q,current['gradient'],fixed_support)
            if not proposals:break
            chosen=list(range(min(8,len(proposals))))
            remaining=list(range(len(chosen),len(proposals)))
            if remaining:chosen+=rng.choice(remaining,min(4,len(remaining)),replace=False).tolist()
            best=None;tests=[]
            for index in chosen:
                proposal=proposals[index];value=self.evaluate(proposal['q'])['mean']
                tests.append({**{k:v for k,v in proposal.items() if k!='q'},'training_mean':value,
                              'layout_sha256':digest(proposal['q']/DENOMINATOR)})
                if value>current['mean']+1e-7 and (best is None or value>best[0]+1e-12):best=(value,proposal)
            record=dict(iteration=iteration,starting_mean=current['mean'],feasible_proposals=len(proposals),tested=tests,accepted=best is not None)
            if best is not None:
                q=best[1]['q'];a=q/DENOMINATOR;a.setflags(write=False)
                primal_audit(self.p,a,np.ones(self.n),range(self.n))
                trajectory.append(a)
                record.update(training_mean=best[0],layout_sha256=digest(a),
                    move={k:v for k,v in best[1].items() if k!='q'})
            trace.append(record)
            print('SEARCH', 'ratios' if fixed_support else 'joint',iteration,
                  current['mean'],best[0] if best is not None else None,
                  'proposals',len(proposals),'evaluated',len(chosen),flush=True)
            if best is None:break
        return dict(initial_mean=initial['mean'],final_mean=self.evaluate(q)['mean'],
                    layout=q/DENOMINATOR,trajectory=trajectory,trace=trace)
