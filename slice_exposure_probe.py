"""Minimal endpoint-capacity experiment; no synthesis and no fixed-data claim.

Bank capacity is shared across FOUR endpoint groups. Fixed-share endpoints have
mu/4 capacity; elastic endpoints each support mu but share a parent bank cap mu.
The latter is a hypothesis, not measured DRAM behavior. A/B/C in each hypothesis
have identical bank, endpoint, HB and controller capacities. Only wiring differs.
Maximum flow is a continuous service-envelope LP, not an ILP or workload speedup.
"""
import argparse,json,time
from pathlib import Path
import numpy as np
import networkx as nx
from bank_sharing import geometry,private_owner,BANKS
from run_gate0 import provenance

UNIT=128 # integer flow units per TB/s; exact for registered rectangular geometry


def capacity_units(value):
    result=round(value*UNIT)
    if abs(result/UNIT-value)>1e-9:raise ValueError('Geometry needs a finer exact flow unit')
    return result


def graph(physical,architecture,endpoint_mode):
    if architecture not in ('partitioned','striped','pooled'):raise ValueError('Unknown architecture')
    if endpoint_mode not in ('fixed_share','elastic_bank'):raise ValueError('Unknown endpoint semantics')
    g=nx.DiGraph();mu=UNIT//BANKS;endpoint=mu//4 if endpoint_mode=='fixed_share' else mu
    for m in range(len(physical.memory)):
        for b in range(BANKS):
            bank=('bank',m,b);g.add_edge('source',bank,capacity=mu)
            for s in range(4):
                node=('slice',m,b,s);g.add_edge(bank,node,capacity=endpoint)
                ports=(private_owner(b),) if architecture=='partitioned' else ((s,) if architecture=='striped' else range(4))
                for p in ports:g.add_edge(node,('mp_in',m,p),capacity=endpoint)
        for p in range(4):g.add_edge(('mp_in',m,p),('mp_out',m,p),capacity=UNIT)
    for c in range(len(physical.compute)):
        for p in range(4):
            g.add_edge(('cp_in',c,p),('cp_out',c,p),capacity=UNIT)
            g.add_edge(('cp_out',c,p),('compute',c),capacity=UNIT)
    for e in physical.edges:
        u,v=('mp_out',e['m'],e['mp']),('cp_in',e['c'],e['cp'])
        if g.has_edge(u,v):raise ValueError('Unexpected duplicate physical port link')
        g.add_edge(u,v,capacity=capacity_units(min(e['memory_port_fraction'],e['compute_port_fraction'])))
    return g


def solve(base,demand):
    g=base.copy()
    for c,d in enumerate(demand):g.add_edge(('compute',c),'sink',capacity=capacity_units(min(4.,float(d))))
    value,flow=nx.maximum_flow(g,'source','sink')
    for u,v,a in g.edges(data=True):
        if not 0<=flow[u][v]<=a['capacity']:raise RuntimeError('Flow capacity violated')
    for node in g:
        if node in ('source','sink'):continue
        if sum(flow[u][node] for u in g.predecessors(node))!=sum(flow[node].values()):
            raise RuntimeError('Flow conservation violated')
    served=[flow[('compute',c)]['sink']/UNIT for c in range(len(demand))]
    return dict(total_tb_s=value/UNIT,per_active=value/UNIT/max(1,np.count_nonzero(demand)),served=served)


def run(output):
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    if (out/'results.json').exists():raise ValueError('Use a fresh output directory')
    started=time.monotonic();xy=geometry('half_shifted');n=len(xy.compute)
    interior=min((i for i,r in enumerate(xy.compute) if len({e['m'] for e in xy.edges if e['c']==i})==4),
                 key=lambda i:xy.compute[i].x**2+xy.compute[i].y**2)
    single=np.zeros(n);single[interior]=4
    cases=[('single_interior',single),('full',np.full(n,4.))]
    for seed in range(9000,9004):
        d=np.zeros(n);d[np.random.default_rng(seed).choice(n,9,replace=False)]=4.
        cases.append(('random25_'+str(seed),d))
    rows=[]
    for placement in ('aligned','half_shifted_x','half_shifted'):
        physical=geometry(placement)
        for mode in ('fixed_share','elastic_bank'):
            for architecture in ('partitioned','striped','pooled'):
                base=graph(physical,architecture,mode)
                for name,demand in cases:
                    rows.append(dict(placement=placement,mode=mode,architecture=architecture,case=name,**solve(base,demand)))
                print(placement,mode,architecture,flush=True)
    index={(r['placement'],r['mode'],r['architecture'],r['case']):r['total_tb_s'] for r in rows}
    for p in ('aligned','half_shifted_x','half_shifted'):
        for name,_ in cases:
            assert index[p,'fixed_share','partitioned',name]==index[p,'fixed_share','striped',name]
            assert index[p,'elastic_bank','striped',name]==index[p,'elastic_bank','pooled',name]
            assert index[p,'fixed_share','pooled',name]==index[p,'elastic_bank','pooled',name]
    result=dict(provenance=provenance(),elapsed_seconds=time.monotonic()-started,
        scope='Free byte placement capacity envelope ONLY. No fixed residency, independent row access, implementation cost or application speedup claimed.',
        registration=dict(compute=n,memory=n,banks=32,slices_per_bank=4,bank_tb_s=1/32,
            hb_tb_s=4,controller_tb_s=4,endpoint_modes={'fixed_share':1/128,'elastic_bank':1/32},
            single_client=interior,seeds=list(range(9000,9004)),demands={name:d.tolist() for name,d in cases}),
        rows=rows,verified=dict(flow_conservation=True,bank_caps=True,endpoint_caps=True,hb_caps=True,
            fixed_share_partitioned_equals_striped=True,elastic_striped_equals_pool=True))
    (out/'results.json').write_text(json.dumps(result,indent=2));print('COMPLETE',len(rows),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();run(a.output)
