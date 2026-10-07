"""Exact integer reference for static full-bank pairs and repeated exposure.

Binary z[c,j] selects disjoint reciprocal pairs; binary x[b,p] selects repeated
bank-port edges; integer lanes[p] selects 32-bit port widths at 1 GHz. Eliminating
fluid rates analytically makes this restricted family a PURE ILP. General
static-layout/service co-design remains bilinear, not magically an ILP.
"""
import sys
import numpy as np
from w2w.constants import BANKS
from w2w.service.guaranteed_service_exchange import ExposureFabric,Channels,bank_coordinates
from w2w.synthesis.memory_fabric_dse import FractionalLayout


def synthesize_pairs(physical,training,edge_budget=96,wire_budget=1800.,hb_tb_s=4.,
                     gurobi_site=None,time_limit=60):
    if gurobi_site and gurobi_site not in sys.path:sys.path.append(gurobi_site)
    import gurobipy as gp
    n=len(physical.compute);nports=len(physical.memory[0].vertical_connectors)
    # H/plus has a dedicated home port. This exact reference is deliberately
    # restricted; rectangular baselines still use the general service model.
    home=[e for e in physical.edges if e['c']==e['m']]
    if len(home)!=n or any(e['cp']!=0 or e['mp']!=0 for e in home):
        raise ValueError('This integer reference requires one dedicated home port')
    direct={(e['c'],e['m']):e for e in physical.edges}
    pairs=[(c,j) for c in range(n) for j in range(c+1,n) if (c,j) in direct and (j,c) in direct]
    weights={pair:sum(float((s.demand[pair[0]]>0)!=(s.demand[pair[1]]>0))/np.count_nonzero(s.demand)
                     for s in training)/len(training) for pair in pairs}
    if any(np.any((s.demand>0)&(s.demand<2)) for s in training):raise ValueError('Need active demand >=2')
    xy=bank_coordinates();r=physical.memory[0]
    length={(b,p):abs(xy[b,0]-(v.x-r.x))+abs(xy[b,1]-(v.y-r.y))
            for b in range(BANKS) for p,v in enumerate(r.vertical_connectors)}
    with gp.Env(empty=True) as env:
        env.setParam('OutputFlag',0);env.start()
        with gp.Model(env=env) as model:
            model.Params.Threads=2;model.Params.TimeLimit=time_limit;model.Params.MIPGap=1e-8
            model.Params.Seed=0
            z=model.addVars(pairs,vtype=gp.GRB.BINARY,name='pair')
            x=model.addVars(BANKS,nports,vtype=gp.GRB.BINARY,name='bank_port')
            full_port=model.addVars(nports,vtype=gp.GRB.BINARY,name='full_port')
            for b in range(BANKS):
                for p in range(nports):model.addConstr(full_port[p]<=x[b,p])
            lanes=model.addVars(nports,vtype=gp.GRB.INTEGER,lb=0,ub=1000,name='lanes_32bit')
            for c in range(n):model.addConstr(gp.quicksum(z[i,j] for i,j in pairs if c in (i,j))<=1)
            for b in range(BANKS):model.addConstr(x[b,0]==1)
            model.addConstr(lanes[0]>=250)
            for i,j in pairs:
                for e in (direct[i,j],direct[j,i]):
                    model.addConstr(z[i,j]<=full_port[e['mp']])
                    # Need 1 TB/s for half of a 2 TB/s single-client stream.
                    model.addConstr(.004*e['memory_port_fraction']*lanes[e['mp']]>=z[i,j])
                    model.addConstr(.004*e['compute_port_fraction']*lanes[e['cp']]>=z[i,j])
            for b in range(BANKS):
                for p in range(nports):model.addConstr(lanes[p]>=x[b,p])
            edge_count=gp.quicksum(x.values());wire=gp.quicksum(length[b,p]*x[b,p] for b,p in x)
            model.addConstr(edge_count<=edge_budget);model.addConstr(wire<=wire_budget)
            model.addConstr(.004*gp.quicksum(lanes.values())<=hb_tb_s)
            gain=gp.quicksum(weights[pair]*z[pair] for pair in pairs)
            model.setObjective(gain,gp.GRB.MAXIMIZE);model.optimize()
            if model.SolCount==0:return dict(feasible=False,status=model.Status)
            primary=dict(status=model.Status,objective=float(model.ObjVal),bound=float(model.ObjBound),gap=float(model.MIPGap))
            # Preserve the attained primary value, then remove redundant wires,
            # connections and lanes. An interrupted primary solve remains labeled.
            model.addConstr(gain>=primary['objective']-1e-9)
            model.setObjective(wire+.001*gp.quicksum(lanes.values())+.000001*edge_count,gp.GRB.MINIMIZE)
            model.optimize()
            if model.SolCount==0:raise RuntimeError('Cost tie-break lost feasible incumbent')
            chosen=sorted(pair for pair in pairs if z[pair].X>.5)
            mask=tuple(tuple(p for p in range(nports) if x[b,p].X>.5) for b in range(BANKS))
            widths=tuple(32*int(round(lanes[p].X)) for p in range(nports))
            a=np.zeros((n,n*BANKS))
            for c in range(n):a[c,c*BANKS:(c+1)*BANKS]=1/BANKS
            for i,j in chosen:
                for c,peer in ((i,j),(j,i)):
                    a[c,:]=0;a[c,c*BANKS:(c+1)*BANKS]=.5/BANKS;a[c,peer*BANKS:(peer+1)*BANKS]=.5/BANKS
            report=dict(feasible=True,gurobi_version=list(gp.gurobi.version()),primary=primary,
                secondary=dict(status=model.Status,objective=model.ObjVal,bound=model.ObjBound,gap=model.MIPGap),
                variables=model.NumVars,binary=model.NumBinVars,integer=model.NumIntVars,
                constraints=model.NumConstrs,continuous=model.NumVars-model.NumIntVars,
                pairs=[list(pair) for pair in chosen],matched_clients=2*len(chosen),widths=list(widths),mask=[list(ps) for ps in mask],
                training_score=1+sum(weights[pair] for pair in chosen),edge_budget=edge_budget,wire_budget=wire_budget,hb_budget_tb_s=hb_tb_s,
                scope='Exact only in equal-half, disjoint full-bank pair family; all banks repeat x[b,p], no dynamic remapping')
    fabric=ExposureFabric(physical,mask,Channels(widths,hb_budget_tb_s=hb_tb_s))
    return report,fabric,FractionalLayout(a)
