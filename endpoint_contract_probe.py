"""Endpoint contract microbenchmark, not a wafer architecture speedup model.

Each output carries COMPLETE bytes for a fixed requester/address class. Native
bank service mu=1 is never replicated. M-direct selects one output at its actual
wire rate; M-buffered serializes native service into independently draining FIFOs.
"""
import argparse
import json
import platform
import subprocess
from pathlib import Path
import numpy as np
from scipy.optimize import linprog


def solve(contract,alpha,active_count,efficiency=1.,endpoints=4):
    if contract not in ('F','E','M_direct','M_buffered'):raise ValueError('Unknown contract')
    if not 0<alpha<=1 or not 0<efficiency<=1 or not 1<=active_count<=endpoints:raise ValueError('Invalid parameters')
    # Variables: per-endpoint rates f, time allocations t, common rate r.
    s=endpoints;n=2*s+1;ub=[];rhs=[];eq=[]
    row=np.zeros(n);row[:s]=1;ub.append(row);rhs.append(1.)  # native parent
    peak=1/s if contract=='F' else alpha
    for e in range(s):
        row=np.zeros(n);row[e]=1;ub.append(row);rhs.append(peak)
        row=np.zeros(n);row[e]=1
        if e<active_count:row[-1]=-1
        eq.append(row)
    if contract.startswith('M_'):
        row=np.zeros(n);row[s:2*s]=1;ub.append(row);rhs.append(efficiency)
        for e in range(s):
            row=np.zeros(n);row[e]=1
            row[s+e]=-(alpha if contract=='M_direct' else 1.)
            ub.append(row);rhs.append(0.)
    cost=np.zeros(n);cost[-1]=-1
    result=linprog(cost,A_ub=np.array(ub),b_ub=rhs,A_eq=np.array(eq),b_eq=np.zeros(s),
                   bounds=[(0,None)]*n,method='highs')
    if not result.success:raise RuntimeError(result.message)
    residual=max(0.,float(np.max(np.array(ub)@result.x-rhs)),float(np.max(np.abs(np.array(eq)@result.x))))
    assert residual<1e-9
    expected=(min(peak,1/active_count) if contract in ('F','E') else
              (efficiency*alpha/active_count if contract=='M_direct' else min(alpha,efficiency/active_count)))
    assert abs(result.x[-1]-expected)<1e-9
    return dict(contract=contract,alpha=alpha,active_outputs=active_count,efficiency=efficiency,
        common_per_output=float(result.x[-1]),total=float(result.x[:s].sum()),
        times=result.x[s:2*s].tolist(),residual=residual,
        provisioned_output_capacity=(1. if contract=='F' else s*alpha))


def complete_word_rate(reachable,parts=4):
    # One completed word requires every fixed bit fraction, not any chosen bits.
    n=parts+1;eq=np.zeros((parts,n))
    for e in range(parts):eq[e,e]=1;eq[e,-1]=-1/parts
    result=linprog(np.r_[np.zeros(parts),-1.],A_eq=eq,b_eq=np.zeros(parts),
        A_ub=np.array([np.r_[np.ones(parts),0.]]),b_ub=[1.],
        bounds=[(0,1.) if e in reachable else (0,0) for e in range(parts)]+[(0,None)],method='highs')
    assert result.success
    return float(result.x[-1])


def run(path):
    if subprocess.check_output(['git','status','--porcelain'],text=True).strip():raise RuntimeError('Clean source commit required')
    rows=[solve(contract,float(alpha),count,efficiency)
          for contract in ('F','E','M_direct','M_buffered')
          for alpha in np.linspace(.25,1,31) for count in (1,2,4)
          for efficiency in ((1.,.9) if contract.startswith('M_') else (1.,))]
    assert complete_word_rate({0})==0 and abs(complete_word_rate(set(range(4)))-1)<1e-9
    out=dict(commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),host=platform.node(),
        scope='Normalized single-bank service contract only; complete-byte outputs, static address classes; no wafer performance or measured circuit parameter',
        mu=1.,endpoints=4,alpha_steps=31,rows=rows,
        word_assembly=dict(one_of_four_reachable=complete_word_rate({0}),all_four_reachable=complete_word_rate(set(range(4)))))
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,indent=2)+'\n')
    print('VERIFIED',len(rows),'contract LPs; word assembly counterexample; max residual',max(v['residual'] for v in rows))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args();run(args.output)
