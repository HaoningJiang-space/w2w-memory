"""Core fixed-byte service LP; endpoint behavior enters as a value envelope."""
from copy import copy
import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix, hstack, vstack
from w2w.service.resources import bind_resource_ledger


class FixedService:
    def __init__(self, fabric, layout, envelope=None):
        self.source_fabric=fabric;self.layout=layout;self.envelope=envelope
        self.missing=np.zeros(fabric.nc)
        er=[];ec=[];ed=[];row=0;nvar=fabric.nc;routes=[]
        for c in range(fabric.nc):
            for b in np.flatnonzero(layout.shares[c]):
                er.append(row);ec.append(c);ed.append(-layout.shares[c,b])
                paths=fabric.paths.get((c,int(b)),[])
                if not paths:self.missing[c]+=layout.shares[c,b]
                for eidx in paths:
                    er.append(row);ec.append(nvar);ed.append(1.)
                    routes.append((nvar,c,int(b),eidx));nvar+=1
                row+=1
        self.route_variables=routes
        self.ledger=bind_resource_ledger(fabric,routes,nvar,envelope)
        self.ub=self.ledger.matrix
        self.eq=coo_matrix((ed,(er,ec)),shape=(row,nvar)).tocsr();self.nvar=nvar
        self.fabric=copy(fabric)
        self.fabric.labels=list(self.ledger.labels);self.fabric.row=self.ledger.row
        self.fabric.limits=self.ledger.capacities

    def with_delivered_caps(self, caps):
        from w2w.domain.endpoint import EndpointEnvelope
        envelope=(self.envelope or EndpointEnvelope()).with_delivered_caps(caps)
        return FixedService(self.source_fabric,self.layout,envelope)

    def audit_rates(self, rates):
        """Validate fixed-byte routing using this solver's canonical ledger."""
        rates=np.asarray(rates,dtype=float)
        witness=np.zeros(self.nvar);witness[:self.fabric.nc]=rates
        for col,c,bank,edge in self.route_variables:
            if len(self.source_fabric.paths[c,bank])!=1:
                raise ValueError('Rate-only audit requires unique paths; provide routing for multipath')
            witness[col]=self.layout.shares[c,bank]*rates[c]
        return max(self.ledger.residual(witness),float(np.max(np.abs(self.eq@witness))),
                   float(np.max(rates-self.fabric.channels.controller_tb_s)),float(max(0.,-rates.min())))

    def solve(self,demand,minimum=1.,objective='throughput'):
        f=self.fabric;demand=np.asarray(demand,dtype=float);active=demand>0
        if demand.shape!=(f.nc,) or not np.isfinite(demand).all() or (demand<0).any() or minimum<0:
            raise ValueError('Invalid demand or service floor')
        lower=np.minimum(demand,minimum);upper=np.minimum(demand,f.channels.controller_tb_s)
        if np.any(lower>upper):return dict(feasible=False,status='Service floor exceeds controller capacity')
        bounds=[(float(lo),float(hi)) for lo,hi in zip(lower,upper)]+[(0,None)]*(self.nvar-f.nc)
        if objective=='throughput':ub=self.ub;eq=self.eq;cost=np.r_[-np.ones(f.nc),np.zeros(self.nvar-f.nc)]
        elif objective in ('common','common_then_throughput'):
            ub=hstack([self.ub,np.zeros((self.ub.shape[0],1))],format='csr')
            eq=hstack([self.eq,np.zeros((self.eq.shape[0],1))],format='csr')
            rows=np.repeat(np.arange(f.nc),2)
            cols=np.column_stack([np.arange(f.nc),np.full(f.nc,self.nvar)]).ravel()
            vals=np.column_stack([np.ones(f.nc),-demand]).ravel()
            equal=coo_matrix((vals,(rows,cols)),shape=(f.nc,self.nvar+1)).tocsr()
            eq=vstack([eq,equal],format='csr');bounds.append((0,1));cost=np.r_[np.zeros(self.nvar),-1.]
        else:raise ValueError('Unknown objective')
        result=linprog(cost,A_ub=ub,b_ub=f.limits,A_eq=eq,b_eq=np.zeros(eq.shape[0]),bounds=bounds,method='highs')
        if not result.success:
            if result.status==2:return dict(feasible=False,status=result.message)
            raise RuntimeError(result.message)
        alpha=float(result.x[-1]) if objective!='throughput' else None
        if objective=='common_then_throughput':
            new_bounds=[(max(float(lo),float(alpha*d)-1e-9),float(hi)) for lo,hi,d in zip(lower,upper,demand)]+[(0,None)]*(self.nvar-f.nc)
            ub=self.ub;eq=self.eq
            result=linprog(np.r_[-np.ones(f.nc),np.zeros(self.nvar-f.nc)],A_ub=ub,b_ub=f.limits,
                           A_eq=eq,b_eq=np.zeros(eq.shape[0]),bounds=new_bounds,method='highs')
            if not result.success:raise RuntimeError(result.message)
        served=result.x[:f.nc]
        residual=max(0.,float(np.max(ub@result.x-f.limits)),float(np.max(np.abs(eq@result.x))),float(np.max(lower-served)),float(np.max(served-upper)))
        if residual>1e-7:raise RuntimeError('Service constraints violated')
        duals=result.ineqlin.marginals
        important=np.argsort(duals)[:8]
        return dict(feasible=True,total_tb_s=float(served.sum()),tb_s_per_active=float(served.sum()/max(1,active.sum())),
            served_tb_s=served.tolist(),minimum_tb_s=float(min(served[active])) if active.any() else 0.,
            p5_tb_s=float(np.percentile(served[active],5)) if active.any() else 0.,common_fraction=alpha,
            constraint_residual=residual,missing_byte_fraction=float(self.missing[active].mean()) if active.any() else 0.,
            bottlenecks=[dict(resource=list(f.labels[int(i)]),dual=float(duals[i]),slack=float(result.ineqlin.residual[i])) for i in important if duals[i]<-1e-9])

    def full_load_certificate(self,minimum=1.):
        solved=self.solve(np.full(self.fabric.nc,minimum),minimum)
        return dict(**solved,registered_floor_tb_s=minimum,layout_hash=self.layout.sha256,
                    subset_guarantee='Feasible full-load flows restrict to any active subset; no runtime layout changes',
                    bank_load_at_floor_tb_s=(self.layout.shares.sum(axis=0)*minimum).tolist())
