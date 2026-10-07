"""Finite mathematical checks; no new wafer/architecture experiment."""
import itertools
import json
from math import comb
from pathlib import Path
import numpy as np
from scipy.optimize import linprog
from analyze_matching_placement import independent_sets


def main():
    probabilities=[.1,.25,.5,1.]
    results=[];cases=0;max_error=0.
    for n in [2,3,4,6]:
        a=.5*(np.eye(n)+np.roll(np.eye(n),1,axis=1))
        expected={p:0. for p in probabilities}
        for state in itertools.product([0,1],repeat=n):
            active=np.flatnonzero(state)
            if len(active)==0:continue
            result=linprog(-np.ones(n),A_ub=a.T,b_ub=np.ones(n),
                bounds=[(1,1.6) if state[c] else (0,0) for c in range(n)],method='highs')
            assert result.success;cases+=1
            if state[0]:
                for p in probabilities:
                    expected[p]+=p**sum(state)*(1-p)**(n-sum(state))*result.x[0]/p
        for p in probabilities:
            formula=1+.6*(1-p)**(1 if n==2 else 2)
            max_error=max(max_error,abs(expected[p]-formula))
            results.append(dict(cycle_compute_count=n,p=p,enumerated_conditional_mean=expected[p],formula=formula))
    for n in [2,3,4,6,8]:
        counts=[0]*(n+1)
        for state in itertools.product([0,1],repeat=n):
            if all(not(state[i] and state[(i+1)%n]) for i in range(n)):counts[sum(state)]+=1
        assert all(independent_sets([n],k)==counts[k] for k in range(n+1))
    exact=[]
    for n in [2,3,4,6,9,12,18,36]:
        rivals=1 if n==2 else 2
        exact.append(dict(cycle_compute_count=n,
            mean=1+.6*comb(35-rivals,8)/comb(35,8),
            common_mean=1+.6*independent_sets([n]*(36//n),9)/comb(36,9)))
    a=.5*(np.eye(6)+np.roll(np.eye(6),1,axis=1));counterexample=[]
    for floor in [1,0]:
        r=linprog(-np.ones(6),A_ub=a.T,b_ub=np.ones(6),
            bounds=[(floor,1.6) if i<3 else (0,0) for i in range(6)],method='highs')
        assert r.success
        counterexample.append(dict(floor=floor,rates=r.x.tolist(),total=float(sum(r.x))))
    assert abs(counterexample[0]['total']-3)<1e-10
    assert abs(counterexample[1]['total']-3.6)<1e-10
    assert max_error<1e-10
    output=dict(scope='Abstract cycle model; not additional physical layouts',
        lp_cases=cases+2,maximum_conditional_expectation_error=max_error,
        iid=results,fixed_9_of_36=exact,fairness_counterexample=counterexample)
    Path(__file__).with_name('matching_theory_checks.json').write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps({k:v for k,v in output.items() if k not in ('iid','fixed_9_of_36')},indent=2))


if __name__=='__main__':main()
