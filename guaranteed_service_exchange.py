"""Static object striping and reciprocal bank exposure with explicit channel widths.

A separate functional experiment mode: original bank_sharing gate is unchanged.
All TB/s are decimal. Cost units are wire-bit-mm and configured storage/selector
proxies, not silicon area, energy, routing completion, or timing signoff.
"""
from dataclasses import dataclass
from math import ceil, comb
import hashlib
import numpy as np
from scipy.optimize import linprog, linear_sum_assignment
from scipy.sparse import coo_matrix, hstack, vstack
from shapely.geometry import Point, Polygon
from Reticle import create_reticle
from Wafer import Wafer
from System import System
from memory_model import MemoryFabric
from bank_sharing import BANKS, BANK_BW, BANK_GIB, DATA_GIB, PAGES, Scenario

STRIPES = 256  # 128 KiB per stripe of a 32 MiB logical object.
OPPOSITE = {1:4, 4:1, 2:3, 3:2}


def contoured_geometry():
    wafers=[]
    for typ,shape,ports in [('compute','H','corner-center'),('memory','plus','edge-center')]:
        reticles=[create_reticle((col-2.5)*25.6,(row-2.5)*33+(col%2-.5)*16.5,
                                26.,33.,typ,shape,.4,ports,(.4,8.25))
                  for row in range(6) for col in range(6)]
        wafers.append(Wafer(reticles,300,typ,'contoured_matched'))
    return MemoryFabric(System(wafers,'memory_and_logic',300,'rectangular',
                        'contoured_matched','direct_only','analytical','synthetic'))


def bank_coordinates():
    return np.array([((b%4-1.5)*6.5,(b//4-3.5)*4.125) for b in range(BANKS)])


def balanced_assignment(physical, directions, mode='minimum_wire'):
    directions=tuple(directions)
    if not directions or BANKS%len(directions) or any(OPPOSITE[p] not in directions for p in directions):
        raise ValueError('Require balanced opposite groups dividing 32 banks')
    r=physical.memory[0]
    ports=np.array([(v.x-r.x,v.y-r.y) for v in r.vertical_connectors])
    xy=bank_coordinates()
    if not all(Polygon(r.shape_points).covers(Point(r.x+x,r.y+y)) for x,y in xy):
        raise ValueError('Bank center outside the memory contour')
    if mode=='cyclic':assigned=np.array([directions[b%len(directions)] for b in range(BANKS)])
    elif mode=='minimum_wire':
        slots=np.repeat(directions,BANKS//len(directions))
        costs=np.abs(xy[:,None,:]-ports[slots][None,:,:]).sum(axis=2)
        rows,cols=linear_sum_assignment(costs)
        assigned=np.zeros(BANKS,dtype=int);assigned[rows]=slots[cols]
    else:raise ValueError('Unknown balanced assignment')
    return tuple((0,int(p)) for p in assigned)


@dataclass(frozen=True)
class Channels:
    port_bits: tuple
    clock_ghz: float = 1.
    bank_link_bits: int = 256
    controller_tb_s: float = 4.
    hb_budget_tb_s: float = 4.
    buffer_depth: int = 2
    pipeline_spacing_mm: float = 2.

    def __post_init__(self):
        if any(int(w)!=w or w<0 for w in self.port_bits) or int(self.bank_link_bits)!=self.bank_link_bits or self.bank_link_bits<=0:
            raise ValueError('Nonnegative integer port widths and positive bank width required')
        if not all(np.isfinite(x) and x>0 for x in (self.clock_ghz,self.pipeline_spacing_mm,self.controller_tb_s,self.hb_budget_tb_s)) or int(self.buffer_depth)!=self.buffer_depth or self.buffer_depth<0:
            raise ValueError('Invalid clock/buffer/pipeline parameters')
        if sum(self.port_bits)*self.clock_ghz/8000>self.hb_budget_tb_s+1e-10:
            raise ValueError('Configured port service exceeds total HB budget')

    def capacity(self, bits):return bits*self.clock_ghz/8000.


class ExposureFabric:
    def __init__(self, physical, mask, channels):
        self.physical=physical;self.mask=tuple(tuple(ps) for ps in mask);self.channels=channels
        self.nc=len(physical.compute);self.nm=len(physical.memory)
        self.nports=len(channels.port_bits)
        if len(mask)!=BANKS or any(not ps or len(ps)!=len(set(ps)) or any(p<0 or p>=self.nports for p in ps) for ps in mask):
            raise ValueError('Invalid repeated bank-port mask')
        if any(len(r.vertical_connectors)!=self.nports for r in physical.compute+physical.memory):
            raise ValueError('Channel vector must match physical interfaces')
        self.edges=physical.edges;self.paths={};self.labels=[];self.limits=[];self.row={}
        def resource(label,cap):
            self.row[label]=len(self.limits);self.labels.append(label);self.limits.append(cap)
        for m in range(self.nm):
            for b in range(BANKS):
                resource(('bank',m,b),BANK_BW)
                for p in self.mask[b]:resource(('bank_output',m,b,p),channels.capacity(channels.bank_link_bits))
            for p,w in enumerate(channels.port_bits):resource(('memory_group_arb',m,p),channels.capacity(w))
        for c in range(self.nc):
            for p,w in enumerate(channels.port_bits):resource(('compute_port',c,p),channels.capacity(w))
        for eidx,e in enumerate(self.edges):
            cap=min(channels.capacity(channels.port_bits[e['cp']])*e['compute_port_fraction'],
                    channels.capacity(channels.port_bits[e['mp']])*e['memory_port_fraction'])
            resource(('hb_edge',eidx),cap)
            if cap>1e-12:
                for b in range(BANKS):
                    if e['mp'] in self.mask[b]:self.paths.setdefault((e['c'],e['m']*BANKS+b),[]).append(eidx)
        self.limits=np.array(self.limits)

    def resources(self, bank, eidx):
        m,b=divmod(bank,BANKS);e=self.edges[eidx]
        return [self.row[('bank',m,b)],self.row[('bank_output',m,b,e['mp'])],
                self.row[('memory_group_arb',m,e['mp'])],self.row[('compute_port',e['c'],e['cp'])],
                self.row[('hb_edge',eidx)]]

    def cost(self):
        xy=bank_coordinates();r=self.physical.memory[0]
        lengths=[];pipeline_bits=0
        for b,ps in enumerate(self.mask):
            for p in ps:
                v=r.vertical_connectors[p];length=float(abs(xy[b,0]-(v.x-r.x))+abs(xy[b,1]-(v.y-r.y)))
                lengths.append(length)
                pipeline_bits+=ceil(length/self.channels.pipeline_spacing_mm)*self.channels.bank_link_bits
        fanin=[sum(p in ps for ps in self.mask) for p in range(self.nports)]
        widths=list(self.channels.port_bits)
        return dict(bank_port_connections=len(lengths),port_fanin=fanin,port_bits=widths,
            port_tb_s=[self.channels.capacity(w) for w in widths],clock_ghz=self.channels.clock_ghz,
            bank_link_bits=self.channels.bank_link_bits,bank_link_tb_s=self.channels.capacity(self.channels.bank_link_bits),
            hb_budget_tb_s=self.channels.hb_budget_tb_s,configured_hb_tb_s=sum(widths)*self.channels.clock_ghz/8000,
            controller_tb_s=self.channels.controller_tb_s,wire_mm=sum(lengths),
            wire_bit_mm=sum(lengths)*self.channels.bank_link_bits,pipeline_register_bits=pipeline_bits,
            buffer_bits=self.channels.buffer_depth*(BANKS*self.channels.bank_link_bits+sum(widths)),
            buffer_depth=self.channels.buffer_depth,selection_bit_inputs=sum(n*w for n,w in zip(fanin,widths)),
            memory_area_mm2=r.get_area(),compute_area_mm2=self.physical.compute[0].get_area(),
            bank_centers='4x8 points; not a bank macro floorplan',
            cost_scope='Per-memory-reticle proxies; parallel aggregation assumed, no PDK, timing, congestion or arbiter implementation')


class StripedLayout:
    """Each logical object uses the same immutable within-object stripe pattern.

    counts[c,b] specifies unique stripes, not replicas; sum is STRIPES per object.
    Demand weights may differ between objects; accesses are uniform within each.
    """
    def __init__(self,counts,nm):
        counts=np.asarray(counts)
        if counts.ndim!=2 or counts.shape[1]!=nm*BANKS or not np.issubdtype(counts.dtype,np.integer) or (counts<0).any() or not np.all(counts.sum(axis=1)==STRIPES):
            raise ValueError('Every object must map each stripe exactly once')
        self.counts=counts.copy();self.counts.setflags(write=False)
        self.shares=counts/STRIPES;self.shares.setflags(write=False)
        self.bank_storage_gib=self.shares.sum(axis=0)*DATA_GIB
        if max(self.bank_storage_gib)>BANK_GIB+1e-10:raise ValueError('Storage capacity exceeded')
        self.sha256=hashlib.sha256(counts.astype('<i4').tobytes()).hexdigest()

    @classmethod
    def home(cls,fabric):
        a=np.zeros((fabric.nc,fabric.nm*BANKS),dtype=int)
        for c in range(fabric.nc):a[c,c*BANKS:(c+1)*BANKS]=STRIPES//BANKS
        return cls(a,fabric.nm)

    @classmethod
    def reciprocal(cls,fabric,peer_fraction=.5):
        amount=STRIPES*peer_fraction/BANKS
        if amount!=round(amount) or not 0<=peer_fraction<=.5:raise ValueError('Stripe fraction not expressible or outside family')
        a=cls.home(fabric).counts.copy();amount=int(round(amount))
        incoming={(e['m'],e['mp']):e['c'] for e in fabric.edges if e['mp']!=0}
        for c in range(fabric.nc):
            for p in sorted({p for ps in fabric.mask for p in ps if p}):
                peer=incoming.get((c,p))
                if peer is None:continue  # no fake boundary connection
                q=OPPOSITE[p]
                if incoming.get((peer,q))!=c:raise ValueError('Nonreciprocal physical connection')
                own=[b for b,ps in enumerate(fabric.mask) if p in ps]
                other=[b for b,ps in enumerate(fabric.mask) if q in ps]
                if len(own)!=len(other):raise ValueError('Unbalanced reciprocal group')
                for b in own:a[c,c*BANKS+b]-=amount
                for b in other:a[c,peer*BANKS+b]+=amount
        return cls(a,fabric.nm)


class FixedService:
    def __init__(self,fabric,layout):
        self.fabric=fabric;self.layout=layout;self.missing=np.zeros(fabric.nc)
        ur=[];uc=[];ud=[];er=[];ec=[];ed=[];row=0;nvar=fabric.nc
        for c in range(fabric.nc):
            for b in np.flatnonzero(layout.shares[c]):
                er.append(row);ec.append(c);ed.append(-layout.shares[c,b])
                routes=fabric.paths.get((c,int(b)),[])
                if not routes:self.missing[c]+=layout.shares[c,b]
                for eidx in routes:
                    er.append(row);ec.append(nvar);ed.append(1.)
                    indices=fabric.resources(int(b),eidx)
                    ur.extend(indices);uc.extend([nvar]*len(indices));ud.extend([1.]*len(indices));nvar+=1
                row+=1
        self.ub=coo_matrix((ud,(ur,uc)),shape=(len(fabric.limits),nvar)).tocsr()
        self.eq=coo_matrix((ed,(er,ec)),shape=(row,nvar)).tocsr();self.nvar=nvar

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


def maximum_nonhome_layout(fabric, floor):
    """Continuous relaxation: fixed proportions maximizing non-home residency.

    Flow at a common rate floor defines a static layout. Includes every modeled
    bandwidth resource and storage capacity. Infeasibility is reported honestly.
    """
    if not np.isfinite(floor) or floor<=0:raise ValueError('Positive finite floor required')
    if floor>fabric.channels.controller_tb_s:return dict(feasible=False,floor=floor)
    variables=[(c,b,e) for (c,b),es in fabric.paths.items() for e in es]
    ur=[];uc=[];ud=[];er=[];ec=[];ed=[];cost=[]
    for i,(c,b,e) in enumerate(variables):
        ids=fabric.resources(b,e);ur.extend(ids);uc.extend([i]*len(ids));ud.extend([1.]*len(ids))
        er.append(c);ec.append(i);ed.append(1.);cost.append(-float(b//BANKS!=c))
    limits=fabric.limits.copy()
    for m in range(fabric.nm):
        for b in range(BANKS):
            row=fabric.row['bank',m,b];limits[row]=min(limits[row],floor*BANK_GIB/DATA_GIB)
    ub=coo_matrix((ud,(ur,uc)),shape=(len(limits),len(variables))).tocsr()
    eq=coo_matrix((ed,(er,ec)),shape=(fabric.nc,len(variables))).tocsr()
    result=linprog(cost,A_ub=ub,b_ub=limits,A_eq=eq,b_eq=np.full(fabric.nc,floor),bounds=(0,None),method='highs')
    if not result.success:
        if result.status==2:return dict(feasible=False,floor=floor)
        raise RuntimeError(result.message)
    layout=np.zeros((fabric.nc,fabric.nm*BANKS))
    for value,(c,b,e) in zip(result.x,variables):layout[c,b]+=value/floor
    return dict(feasible=True,floor=floor,max_mean_nonhome=float(-result.fun/floor/fabric.nc),
                maximum_bank_storage_gib=float(max(layout.sum(axis=0)*DATA_GIB)),
                constraint_residual=max(float(np.max(np.abs(eq@result.x-floor))),float(max(0.,np.max(ub@result.x-limits)))))


def reciprocal_coverage(fabric,layout):
    peers=[];eligible=[]
    for c in range(fabric.nc):
        ps=sorted({b//BANKS for b in np.flatnonzero(layout.shares[c]) if b//BANKS!=c})
        # A private bank share of 1/32 prevents any rate >1.
        if layout.shares[c].max()<BANK_BW-1e-12:eligible.append(c)
        peers.append(ps)
    return peers,eligible


def exact_uniform_pair_mean(fabric,layout,active=9,peer_fraction=.5):
    """For balanced beta=.5, sufficient channel widths and r>=1, bank rows imply
    r_i+r_j<=2; busy peers force r_i=1. Only all-idle peers allow a rate of 2.
    This formula is NOT used for beta<.5 or throttled widths.
    """
    if peer_fraction!=.5:raise ValueError('Formula restricted to half/half layout')
    if not 1<=active<=fabric.nc:raise ValueError('Invalid active count')
    if layout.sha256!=StripedLayout.reciprocal(fabric,.5).sha256:raise ValueError('Formula requires reciprocal half layout')
    widths=fabric.channels
    group_sizes=[sum(p in ps for ps in fabric.mask) for p in range(fabric.nports)]
    if widths.capacity(widths.port_bits[0])<1 or widths.controller_tb_s<2 or widths.capacity(widths.bank_link_bits)<BANK_BW or any(widths.capacity(widths.port_bits[p])+1e-12<group_sizes[p]/BANKS for p in range(1,fabric.nports)):
        raise ValueError('Formula requires sufficient widths')
    peers,eligible=reciprocal_coverage(fabric,layout);n=fabric.nc
    gain=sum((comb(n-1-len(peers[c]),active-1) if n-1-len(peers[c])>=active-1 else 0)/comb(n-1,active-1) for c in eligible)/n
    return dict(mean_tb_s_per_active=1+gain,eligible_clients=eligible,peer_counts=[len(p) for p in peers],
                assumption='half/half, >=1 per active, sufficient widths; exact uniform fixed-cardinality subset expectation')


def complementary_phases(physical,preferred=(2,3)):
    """Two cohorts have the same per-client marginal 1/2, different coactivity."""
    constraints={c:[] for c in range(len(physical.compute))}
    for e in physical.edges:
        if e['c']!=e['m']:constraints[e['c']].append((e['m'],int(e['mp'] in preferred)))
    colors={0:0};todo=[0]
    while todo:
        c=todo.pop()
        for peer,parity in constraints[c]:
            value=colors[c]^parity
            if peer in colors:
                if colors[peer]!=value:raise ValueError('Inconsistent coactivity coloring')
            else:colors[peer]=value;todo.append(peer)
    if len(colors)!=len(physical.compute):raise ValueError('Disconnected coloring')
    out=[]
    for phase in (0,1):
        demand=np.array([4. if colors[c]==phase else 0. for c in range(len(colors))])
        out.append(Scenario('complementary_'+str(preferred),.5,phase,demand,np.full(PAGES,1/PAGES)))
    return out


class FreePlacementService(FixedService):
    """Relaxation with scenario-specific bank service; no fixed data residency.

    Same bank-output, group, HB and controller capacities. This is an upper
    bound only: it ignores stored-byte placement/capacity and object semantics.
    """
    def __init__(self,fabric):
        self.fabric=fabric;self.layout=None;self.missing=np.zeros(fabric.nc)
        ur=[];uc=[];ud=[];er=list(range(fabric.nc));ec=list(range(fabric.nc));ed=[-1.]*fabric.nc
        nvar=fabric.nc
        for (c,b),edges in fabric.paths.items():
            for edge in edges:
                er.append(c);ec.append(nvar);ed.append(1.)
                indices=fabric.resources(b,edge)
                ur.extend(indices);uc.extend([nvar]*len(indices));ud.extend([1.]*len(indices));nvar+=1
        self.ub=coo_matrix((ud,(ur,uc)),shape=(len(fabric.limits),nvar)).tocsr()
        self.eq=coo_matrix((ed,(er,ec)),shape=(fabric.nc,nvar)).tocsr();self.nvar=nvar
