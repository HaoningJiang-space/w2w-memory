"""Service-driven static layout updates and repeated bank-exposure proposals.

The joint layout/rate problem is bilinear. A sequential LP linearizes a[c,b]*r[w,c]
around the current *exact* service solution. Only exact-LP improvements are
accepted. No convexity/global optimality or linearized-bound claim is made.
"""
from collections import defaultdict
import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix
from bank_sharing import BANKS, BANK_GIB, DATA_GIB
from guaranteed_service_exchange import FixedService, ExposureFabric, Channels, bank_coordinates
from memory_fabric_dse import FractionalLayout


def evaluate_layout(fabric, layout, phases, floor=.9, details=False):
    problem=FixedService(fabric,layout)
    results=[problem.solve(s.demand,minimum=floor) for s in phases]
    if not all(r['feasible'] for r in results):return dict(feasible=False)
    return dict(feasible=True,score=float(np.mean([r['tb_s_per_active'] for r in results])),
                rates=np.array([r['served_tb_s'] for r in results]),
                results=results if details else None)


def layout_step(fabric, layout, phases, rates, floor=.9, share_radius=.5/32, rate_radius=.5):
    """Linearized joint LP, including an exact full-load floor certificate.

    Each scenario keeps an independent routing flow but shares ONE data layout.
    The full-load certificate is another flow block at the requested design rate.
    Its service floor is a registered tradeoff variable, not fixed universally.
    """
    if floor<=0:raise ValueError('Use a positive design floor for this local solver')
    pairs=sorted(fabric.paths);idx={pair:i for i,pair in enumerate(pairs)}
    if any(layout.shares[c,b]>1e-10 and (c,int(b)) not in idx
           for c in range(fabric.nc) for b in np.flatnonzero(layout.shares[c])):
        return None,dict(status='Initial layout contains inaccessible bytes')
    by_compute=defaultdict(list)
    for pair in pairs:by_compute[pair[0]].append(pair)
    bounds=[];cost=[]
    for c,b in pairs:
        a=layout.shares[c,b]
        bounds.append((max(0.,a-share_radius),min(1.,a+share_radius)));cost.append(0.)
    er=[];ec=[];ev=[];rhs_eq=[];ur=[];uc=[];uv=[];rhs_ub=[]
    def equality(columns,values,rhs):
        row=len(rhs_eq);rhs_eq.append(rhs);er.extend([row]*len(columns));ec.extend(columns);ev.extend(values)
    # Per-client unique bytes and per-bank storage capacity.
    for c in range(fabric.nc):
        columns=[idx[pair] for pair in by_compute[c]]
        equality(columns,[1.]*len(columns),1.)
    storage_rows={}
    for b in range(fabric.nm*BANKS):storage_rows[b]=len(rhs_ub);rhs_ub.append(BANK_GIB/DATA_GIB)
    for c,b in pairs:ur.append(storage_rows[b]);uc.append(idx[c,b]);uv.append(1.)
    rvars={}
    for w,phase in enumerate(phases):
        active=np.flatnonzero(phase.demand);denom=len(active)*len(phases)
        for c in active:
            r0=rates[w,c];rvars[w,int(c)]=len(bounds)
            bounds.append((max(floor,r0-rate_radius),min(float(phase.demand[c]),fabric.channels.controller_tb_s,r0+rate_radius)))
            cost.append(-1./denom)
    # Training scenarios followed by the full-load certificate block.
    for w in range(len(phases)+1):
        certificate=w==len(phases)
        active=range(fabric.nc) if certificate else np.flatnonzero(phases[w].demand)
        resource_offset=len(rhs_ub);rhs_ub.extend(fabric.limits.tolist())
        for c in active:
            for _,b in by_compute[c]:
                columns=[idx[c,b]];values=[-floor if certificate else -rates[w,c]]
                rhs=0.
                if not certificate:
                    a0=layout.shares[c,b];columns.append(rvars[w,int(c)]);values.append(-a0)
                    rhs=-a0*rates[w,c]
                for edge in fabric.paths[c,b]:
                    fvar=len(bounds);bounds.append((0,None));cost.append(0.)
                    columns.append(fvar);values.append(1.)
                    resources=fabric.resources(b,edge)
                    ur.extend([resource_offset+i for i in resources]);uc.extend([fvar]*len(resources));uv.extend([1.]*len(resources))
                equality(columns,values,rhs)
    n=len(bounds)
    eq=coo_matrix((ev,(er,ec)),shape=(len(rhs_eq),n)).tocsr()
    ub=coo_matrix((uv,(ur,uc)),shape=(len(rhs_ub),n)).tocsr()
    result=linprog(cost,A_ub=ub,b_ub=rhs_ub,A_eq=eq,b_eq=rhs_eq,bounds=bounds,method='highs')
    if not result.success:
        if result.status==2:return None,dict(status=result.message)
        raise RuntimeError(result.message)
    a=np.zeros_like(layout.shares)
    for (c,b),i in idx.items():a[c,b]=result.x[i]
    return FractionalLayout(a),dict(predicted_score=float(-result.fun),variables=n,
        constraints=len(rhs_eq)+len(rhs_ub),status='linearized LP; not a performance bound')


def optimize_layout(fabric, initial, phases, floor=.9, iterations=4):
    """Monotonic TRAINING-only acceptance; finite iterations and backtracking."""
    current=FractionalLayout(initial.shares);trace=[]
    incumbent=evaluate_layout(fabric,current,phases,floor)
    if not incumbent['feasible']:raise ValueError('Initial layout not feasible at design floor')
    initial_score=incumbent['score']
    for iteration in range(iterations):
        proposed,step=layout_step(fabric,current,phases,incumbent['rates'],floor)
        if proposed is None:
            trace.append(dict(iteration=iteration,accepted=False,**step));break
        trials=[];best=None
        for fraction in (1.,.5,.25,.125):
            candidate=FractionalLayout((1-fraction)*current.shares+fraction*proposed.shares)
            evaluation=evaluate_layout(fabric,candidate,phases,floor)
            score=evaluation.get('score')
            trials.append(dict(fraction=fraction,feasible=evaluation['feasible'],score=score))
            if evaluation['feasible'] and score>incumbent['score']+1e-7 and (best is None or score>best[0]):
                best=(score,candidate,evaluation,fraction)
        trace.append(dict(iteration=iteration,before=incumbent['score'],accepted=best is not None,
                          trials=trials,**step))
        if best is None:break
        _,current,incumbent,_=best
    if incumbent['score']+1e-8<initial_score:raise RuntimeError('Nonmonotonic exact service')
    return current,dict(initial_score=initial_score,final_score=incumbent['score'],trace=trace,
                        layout_hash=current.sha256)


def structural_width_cap(fabric, quantum=250):
    """Safely remove width that cannot be used by ANY bank-limited route flow.

    Bound every port/edge by all banks that could traverse it, including overlap
    fractions and both endpoints. These conservative bounds preserve all feasible
    route flows, not just training flows. Only reduce existing widths.
    """
    required=np.zeros(fabric.nports)
    for p in range(fabric.nports):
        required[p]=sum(p in ports for ports in fabric.mask)/BANKS
    compute_banks=defaultdict(set)
    for edge in fabric.edges:
        banks={edge['m']*BANKS+b for b,ports in enumerate(fabric.mask) if edge['mp'] in ports}
        compute_banks[edge['c'],edge['cp']].update(banks)
        for port,fraction in [(edge['cp'],edge['compute_port_fraction']),(edge['mp'],edge['memory_port_fraction'])]:
            if fraction>0:required[port]=max(required[port],len(banks)/BANKS/fraction)
    for (c,p),banks in compute_banks.items():required[p]=max(required[p],len(banks)/BANKS)
    target=np.ceil(required*8000/fabric.channels.clock_ghz/quantum-1e-10)*quantum
    widths=tuple(int(min(old,new)) for old,new in zip(fabric.channels.port_bits,target))
    return ExposureFabric(fabric.physical,fabric.mask,Channels(widths,
        clock_ghz=fabric.channels.clock_ghz,bank_link_bits=fabric.channels.bank_link_bits,
        controller_tb_s=fabric.channels.controller_tb_s,hb_budget_tb_s=fabric.channels.hb_budget_tb_s))


def exposure_proposals(fabric,layout,phases,floor=.9,group_size=4,limit=2):
    """Rank repeated edge additions by unused-bank service x unmet demand.

    This is a proposal heuristic. Added connections only become useful after
    static-layout reoptimization; the score is not a throughput prediction.
    """
    problem=FixedService(fabric,layout);scores=defaultdict(float)
    xy=bank_coordinates();reticle=fabric.physical.memory[0]
    for phase in phases:
        lower=np.minimum(phase.demand,floor);upper=np.minimum(phase.demand,fabric.channels.controller_tb_s)
        result=linprog(np.r_[-np.ones(fabric.nc),np.zeros(problem.nvar-fabric.nc)],
            A_ub=problem.ub,b_ub=fabric.limits,A_eq=problem.eq,b_eq=np.zeros(problem.eq.shape[0]),
            bounds=list(zip(lower,upper))+[(0,None)]*(problem.nvar-fabric.nc),method='highs')
        if not result.success:raise RuntimeError(result.message)
        usage=problem.ub@result.x;unmet=np.maximum(0,phase.demand-result.x[:fabric.nc])
        for edge in fabric.edges:
            c,m,p=edge['c'],edge['m'],edge['mp']
            if unmet[c]<1e-9 or fabric.channels.port_bits[p]==0:continue
            for b,ports in enumerate(fabric.mask):
                if p in ports:continue
                idle=max(0.,1/BANKS-usage[fabric.row['bank',m,b]])
                scores[b,p]+=min(idle,unmet[c])/len(phases)
    candidates=[]
    for p in range(fabric.nports):
        options=[]
        v=reticle.vertical_connectors[p]
        for b in range(BANKS):
            if (b,p) not in scores or scores[b,p]<=1e-10:continue
            length=abs(xy[b,0]-(v.x-reticle.x))+abs(xy[b,1]-(v.y-reticle.y))
            options.append((scores[b,p]/max(length,1.),b,scores[b,p]))
        selected=sorted(options,reverse=True)[:group_size]
        if not selected:continue
        mask=list(fabric.mask)
        for _,b,_ in selected:mask[b]=tuple(sorted(set(mask[b])|{p}))
        candidates.append(dict(mask=tuple(mask),added_port=p,banks=[b for _,b,_ in selected],
                               score=sum(score for _,b,score in selected)))
    return sorted(candidates,key=lambda x:-x['score'])[:limit]


def paired_layout(fabric, phases=(), workload_aware=False):
    """Exact matching within a restricted, statically paired layout family.

    A candidate peer must expose ALL banks bidirectionally, retain home access,
    and sustain 1 TB/s on each used port. Pairing changes unique data residency,
    not the repeated hardware template. Positive weights use training only.
    """
    import networkx as nx
    graph=nx.Graph();graph.add_nodes_from(range(fabric.nc))
    def full_route(c,m):
        return any(e['c']==c and e['m']==m and all(e['mp'] in ps for ps in fabric.mask)
            and fabric.limits[fabric.row['hb_edge',i]]>=1-1e-9
            for i,e in enumerate(fabric.edges))
    if fabric.channels.controller_tb_s<2 or any(not full_route(c,c) for c in range(fabric.nc)):
        raise ValueError('Pair-family formula requires full home service and controller >=2')
    if any(np.any((s.demand>0)&(s.demand<2)) for s in phases):
        raise ValueError('Pair-family formula requires active demand >=2')
    for c in range(fabric.nc):
        for peer in range(c+1,fabric.nc):
            if not full_route(c,peer) or not full_route(peer,c):continue
            if workload_aware:
                if not phases:raise ValueError('Training phases required')
                weight=sum(float((s.demand[c]>0)!=(s.demand[peer]>0))/max(1,np.count_nonzero(s.demand)) for s in phases)/len(phases)
            else:weight=1.
            graph.add_edge(c,peer,weight=weight)
    matching=sorted(tuple(sorted(pair)) for pair in nx.max_weight_matching(graph,maxcardinality=not workload_aware))
    a=np.zeros((fabric.nc,fabric.nm*BANKS))
    for c in range(fabric.nc):a[c,c*BANKS:(c+1)*BANKS]=1/BANKS
    for c,peer in matching:
        for requester,other in [(c,peer),(peer,c)]:
            a[requester,:]=0
            a[requester,requester*BANKS:(requester+1)*BANKS]=.5/BANKS
            a[requester,other*BANKS:(other+1)*BANKS]=.5/BANKS
    layout=FractionalLayout(a)
    if not FixedService(fabric,layout).full_load_certificate()['feasible']:
        raise ValueError('Pairing does not sustain its registered baseline')
    return layout,dict(pairs=[list(pair) for pair in matching],matched_clients=2*len(matching),
        objective='training normalized exclusive-activity probability' if workload_aware else 'maximum cardinality',
        matching_weight=sum(graph[c][peer]['weight'] for c,peer in matching),
        scope='Optimal matching only in the disjoint equal-half full-bank-pair family; not global fabric synthesis')


def exact_pair_expectation(n,matched_clients,active):
    if not 1<=active<=n:raise ValueError('Invalid active count')
    return 1+(matched_clients/n)*(n-active)/(n-1)
