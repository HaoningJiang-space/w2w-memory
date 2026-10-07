"""Open, geometry-constrained memory-fabric exploration.

Repeated x[b,p], port widths q[p], geometry and an offline static layout are
independent variables. Finite seeds + local edge/width moves are a heuristic,
not a global optimum. Fluid data fractions are explicitly a continuous limit.
"""
import hashlib
import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix, hstack, vstack
from w2w.constants import BANKS,BANK_GIB,DATA_GIB
from w2w.service.guaranteed_service_exchange import ExposureFabric


class FractionalLayout:
    """Unique static bytes in a continuous striping limit; no test-time remap."""
    def __init__(self,shares):
        shares=np.asarray(shares,dtype=float)
        if shares.ndim!=2 or not np.isfinite(shares).all() or shares.min()<-1e-9 or not np.allclose(shares.sum(axis=1),1,atol=1e-7):
            raise ValueError('Invalid static byte proportions')
        self.shares=shares.copy();self.shares[np.abs(self.shares)<1e-12]=0;self.shares.setflags(write=False)
        self.bank_storage_gib=self.shares.sum(axis=0)*DATA_GIB
        if max(self.bank_storage_gib)>BANK_GIB+1e-7:raise ValueError('Static storage exceeded')
        self.sha256=hashlib.sha256(self.shares.astype('<f8').tobytes()).hexdigest()


def activity_affinity(training,n):
    active=np.array([s.demand>0 for s in training],dtype=float)
    # Conditional opposite activity, not the product of marginal frequencies.
    # c borrowing m is valuable when c is active and m is idle.
    return (active.T@(1-active))/np.maximum(1,active.sum(axis=0))[:,None]


def project_static_layout(fabric,training,floor=.9,activity_aware=True):
    """L1-project a complementary-access target onto static full-load capacity.

    The requested floor guides layout construction, not final acceptance. The
    service evaluator separately reports feasibility and the performance/loss
    frontier. This is a constructive LP, not a solution to the nonconvex joint
    layout/rate objective. All observed activity comes from training only.
    """
    if not 0<floor<=fabric.channels.controller_tb_s:raise ValueError('Invalid layout design floor')
    pairs=sorted(fabric.paths)
    if len({c for c,b in pairs})!=fabric.nc:return None
    pair_index={pair:i for i,pair in enumerate(pairs)};nf=sum(len(fabric.paths[pair]) for pair in pairs);npairs=len(pairs)
    ur=[];uc=[];ud=[];er=[];ec=[];ed=[];pr=[];pc=[];pd=[]
    objective=np.zeros(nf+npairs)
    affinity=activity_affinity(training,fabric.nc) if activity_aware else np.zeros((fabric.nc,fabric.nm))
    target=np.zeros(npairs)
    for c in range(fabric.nc):
        accessible=[(i,b) for i,(cc,b) in enumerate(pairs) if cc==c]
        weights=np.array([1+2*affinity[c,b//BANKS] for i,b in accessible])
        weights/=weights.sum()
        for (i,b),weight in zip(accessible,weights):target[i]=weight*floor
    var=0
    for c,b in pairs:
        for e in fabric.paths[c,b]:
            resources=fabric.resources(b,e)
            ur.extend(resources);uc.extend([var]*len(resources));ud.extend([1.]*len(resources))
            er.append(c);ec.append(var);ed.append(1.)
            pr.append(pair_index[c,b]);pc.append(var);pd.append(1.);var+=1
    limits=fabric.limits.copy()
    for m in range(fabric.nm):
        for b in range(BANKS):
            i=fabric.row['bank',m,b];limits[i]=min(limits[i],floor*BANK_GIB/DATA_GIB)
    resources=coo_matrix((ud,(ur,uc)),shape=(len(limits),nf+npairs)).tocsr()
    conservation=coo_matrix((ed,(er,ec)),shape=(fabric.nc,nf+npairs)).tocsr()
    flow_per_pair=coo_matrix((pd,(pr,pc)),shape=(npairs,nf)).tocsr()
    minus_identity=coo_matrix((-np.ones(npairs),(np.arange(npairs),np.arange(npairs))),shape=(npairs,npairs)).tocsr()
    ub=vstack([resources,hstack([flow_per_pair,minus_identity]),hstack([-flow_per_pair,minus_identity])],format='csr')
    rhs=np.r_[limits,target,-target];objective[nf:]=1
    result=linprog(objective,A_ub=ub,b_ub=rhs,A_eq=conservation,b_eq=np.full(fabric.nc,floor),bounds=(0,None),method='highs')
    if not result.success:
        if result.status==2:return None
        raise RuntimeError(result.message)
    shares=np.zeros((fabric.nc,fabric.nm*BANKS));values=flow_per_pair@result.x[:nf]/floor
    for (c,b),value in zip(pairs,values):shares[c,b]=value
    return FractionalLayout(shares)


def mutate_mask(mask,physical,limit=8):
    """Short-wire additions/removals; nonuniform degree is allowed.

    Changes repeat across all memory reticles. No home edge is sacred here,
    though removing all outputs of a bank is excluded from this seed family.
    """
    from w2w.service.guaranteed_service_exchange import bank_coordinates
    xy=bank_coordinates();r=physical.memory[0]
    options=[]
    for b,ports in enumerate(mask):
        for p,v in enumerate(r.vertical_connectors):
            present=p in ports
            if present and len(ports)==1:continue
            distance=abs(xy[b,0]-(v.x-r.x))+abs(xy[b,1]-(v.y-r.y))
            new=list(mask);new[b]=tuple(sorted(set(ports)-{p} if present else set(ports)|{p}))
            options.append((distance if not present else -distance,b,p,tuple(new)))
    # Include both adding short connections and removing expensive ones.
    removals=sorted([x for x in options if x[2] in mask[x[1]]])[:limit//2]
    additions=sorted([x for x in options if x[2] not in mask[x[1]]])[:limit-len(removals)]
    return [x[3] for x in removals+additions]


def bandwidth_moves(widths,quantum=1000):
    """Conserve total provisioned HB bandwidth while changing directions."""
    for src,w in enumerate(widths):
        if w<quantum:continue
        for dst in range(len(widths)):
            if dst==src:continue
            q=list(widths);q[src]-=quantum;q[dst]+=quantum
            yield tuple(q)
