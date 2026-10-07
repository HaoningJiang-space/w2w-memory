"""Separate address permission R from physical recipient reachability Y.

No new fabric synthesis: audit the existing H/plus design, then compare a
two-memory normalization with an explicitly relaxed recipient graph.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import numpy as np
from scipy.optimize import linprog
from w2w.service.guaranteed_service_exchange import contoured_geometry, ExposureFabric, Channels
from w2w.synthesis.service_driven_fabric import paired_layout
from w2w.endpoints.endpoint_execution import execute


def service(y, address='flexible', active=(0,), serial=False):
    """Two C/two M; fixed A_cm=.5 and two equal byte classes within each M.

    y[m,e,c] means physical output e of memory m can reach compute c.
    Source memory and byte class are never substituted. Output peaks are .5,
    native M service is 1, controllers are 4. Common active rate is maximized.
    """
    y=np.asarray(y,dtype=bool)
    if y.shape!=(2,2,2) or address not in ('flexible','unique','striped'):
        raise ValueError('Invalid physical graph or address contract')
    paths=[(c,m,a,e) for c in range(2) for m in range(2) for a in range(2) for e in range(2)]
    n=1+len(paths);ub=[];rhs=[];eq=[];bounds=[(0,4)]
    missing=0
    for c,m,a,e in paths:
        allowed=(address=='flexible' or (address=='striped' and a==e) or
                 (address=='unique' and e==int(np.argmax(y[m,:,c]))))
        bounds.append((0,None) if allowed and y[m,e,c] else (0,0))
    for c in range(2):
        for m in range(2):
            for a in range(2):
                row=np.zeros(n);row[0]=-.25 if c in active else 0
                cols=[j+1 for j,p in enumerate(paths) if p[:3]==(c,m,a)]
                row[cols]=1;eq.append(row)
                if c in active and not any(bounds[j][1]!=0 for j in cols):missing+=1
    for m in range(2):
        row=np.zeros(n)
        for j,p in enumerate(paths):
            if p[1]==m:row[j+1]=1
        ub.append(row);rhs.append(1.)
        if serial:ub.append(row/.5);rhs.append(1.)
        for e in range(2):
            row=np.zeros(n)
            for j,p in enumerate(paths):
                if p[1]==m and p[3]==e:row[j+1]=1
            ub.append(row);rhs.append(.5)
    cost=np.zeros(n);cost[0]=-1
    result=linprog(cost,A_ub=ub,b_ub=rhs,A_eq=eq,b_eq=np.zeros(len(eq)),bounds=bounds,method='highs')
    assert result.success
    residual=max(0.,float(np.max(np.array(ub)@result.x-rhs)),float(np.max(np.abs(np.array(eq)@result.x))))
    assert residual<1e-9
    return dict(rate_per_active=float(result.x[0]),missing_active_byte_classes=missing,
                floor_one_feasible=bool(result.x[0]>=1-1e-9),residual=residual)


def audit():
    p=contoured_geometry()
    f=ExposureFabric(p,tuple((0,2,3) for _ in range(32)),Channels((8000,0,8000,8000,0)))
    layout,pairing=paired_layout(f)
    multiplicity=Counter(Counter((e['c'],e['m']) for e in p.edges).values())
    routes=Counter(len(f.paths[c,int(b)]) for c in range(f.nc) for b in np.flatnonzero(layout.shares[c]))
    assert multiplicity=={1:146} and routes=={1:2304}
    pair=pairing['pairs'][0];y=np.zeros((2,2,2),bool);port_ids=[]
    for mi,m in enumerate(pair):
        edges=[e for e in p.edges if e['m']==m and e['c'] in pair]
        ports=sorted({e['mp'] for e in edges});assert len(ports)==2;port_ids.append(ports)
        for e in edges:y[mi,ports.index(e['mp']),pair.index(e['c'])]=True
    cases=[]
    for address in ('unique','flexible','striped'):
        for relaxed in (False,True):
            for active in ((0,),(0,1)):
                if address=='unique' and relaxed:continue
                cases.append(dict(address=address,physical_relaxation=relaxed,active=list(active),
                    **service(np.ones_like(y) if relaxed else y,address,active)))
    return dict(physical_cm_multiplicity=dict(multiplicity),used_c_bank_routes=dict(routes),
        layout_hash=layout.sha256,example_pair=pair,physical_memory_ports=port_ids,
        physical_y=y.astype(int).tolist(),cases=cases,
        abstract_two_output_complete_word_trace=execute(128,1,active=(0,1)),
        oracle_serial_single=service(np.ones_like(y),'striped',(0,),serial=True),
        scope='Real geometry audit plus physically relaxed aggregation upper reference; no added real HB paths',
        interpretation='R permits bytes at outputs; Y separately determines recipients. Changing R alone does not change Y.')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    if subprocess.check_output(['git','status','--porcelain'],text=True).strip():raise RuntimeError('Clean source required')
    result=audit();result['commit']=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('physical_cm_multiplicity','used_c_bank_routes','cases')},indent=2))


if __name__=='__main__':main()
