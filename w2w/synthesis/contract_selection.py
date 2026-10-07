"""Exact finite-catalog selection over verified endpoint bridge implementations.

Geometry, exposure mask, A, arbitration and physical paths are frozen. Costs are
separate hardware counters, not an uncalibrated weighted area score. Population
expectations average all uniform K-of-N activity sets analytically; execution
rates remain measurements of the specified complete-word implementation.
"""
from math import comb


def population_rates(single, paired, k, n=36):
    if n % 2 or not 1 <= k <= n or single < paired - 1e-12:
        raise ValueError('Requires disjoint pairs and single >= paired service')
    isolated = (n-k)/(n-1)
    no_pair = comb(n//2,k)*2**k/comb(n,k) if k <= n//2 else 0.
    return dict(mean=paired+(single-paired)*isolated,
                common=paired+(single-paired)*no_pair, full_load=paired)


def catalog(bridge):
    traces={(v['output_bits'],v['depth'],len(v['active'])):v for v in bridge['micro']
            if v['policy']=='round_robin'}
    out=[]
    for bits in (64,128,192,256):
        for depth in (0,1,2,8):
            t1=traces[bits,depth,1];t2=traces[bits,depth,2]
            alpha=bits/256
            out.append(dict(id=f'w{bits}_d{depth}',bits=bits,depth=depth,
                costs=dict(export_lane_bits=32*3*bits,
                           storage_bits=32*256 if depth==0 else 32*3*depth*256),
                # The first selector ignores whether egress can drain independently.
                rates=dict(optimistic=(2*alpha,min(1.,2*alpha)),
                           fluid=(2*alpha,alpha if depth==0 else min(1.,2*alpha)),
                           executed=(2*t1['rate_per_native'][0],
                                     2*min(t2['rate_per_native'])))))
    return out


def evaluate(config,model,distribution):
    scores=[(weight,population_rates(*config['rates'][model],k)) for k,weight in distribution]
    if abs(sum(w for w,_ in scores)-1)>1e-10:raise ValueError('Weights must sum to one')
    return {metric:sum(w*v[metric] for w,v in scores) for metric in ('mean','common','full_load')}


def choose(configs,budget,distribution,model,floor=0):
    feasible=[c for c in configs if all(c['costs'][key]<=cap for key,cap in budget.items())
              and evaluate(c,model,distribution)['full_load']>=floor-1e-10]
    if not feasible:return None
    # Fixed tie rule: lower storage, then lanes, then ID. Never use test execution
    # values to break ties for optimistic/fluid selectors.
    return min(feasible,key=lambda c:(-round(evaluate(c,model,distribution)['mean'],12),
                                      c['costs']['storage_bits'],c['costs']['export_lane_bits'],c['id']))


def study(bridge):
    configs=catalog(bridge)
    distributions={'random9':[(9,1.)],'random18':[(18,1.)],'full':[(36,1.)],
                   'registered_mix':[(9,.5),(18,.25),(36,.25)]}
    rows=[]
    for lane in (6144,12288,18432,24576):
        for storage in (8192,24576,49152,196608):
            budget=dict(export_lane_bits=lane,storage_bits=storage)
            for floor in (0,1):
                for name,dist in distributions.items():
                    best=choose(configs,budget,dist,'executed',floor)
                    for model in ('optimistic','fluid','executed'):
                        chosen=choose(configs,budget,dist,model,floor)
                        row=dict(budget=budget,floor=floor,workload=name,selector=model,
                                 selected=None if chosen is None else chosen['id'],
                                 executed_best=None if best is None else best['id'])
                        if chosen:
                            actual=evaluate(chosen,'executed',dist)
                            valid=actual['full_load']>=floor-1e-10
                            row.update(predicted=evaluate(chosen,model,dist),actual=actual,
                                       actual_floor_feasible=valid,
                                       regret=(evaluate(best,'executed',dist)['mean']-actual['mean'])
                                       if best and valid else None)
                        rows.append(row)
    # Componentwise frontier in two resource counters and mean throughput.
    frontier={}
    for name,dist in distributions.items():
        frontier[name]=[c['id'] for c in configs if not any(
            all(other['costs'][k]<=c['costs'][k] for k in c['costs']) and
            evaluate(other,'executed',dist)['mean']>=evaluate(c,'executed',dist)['mean']-1e-12 and
            (any(other['costs'][k]<c['costs'][k] for k in c['costs']) or
             evaluate(other,'executed',dist)['mean']>evaluate(c,'executed',dist)['mean']+1e-12)
            for other in configs)]
    return dict(scope='16 fixed-geometry/fixed-residency implementations; exact catalog enumeration, not whole-fabric synthesis',
                reference_commit=bridge['commit'],layout_hash=bridge['layout_hash'],
                unchanged_physical_cost=bridge['physical_cost'],
                cost_boundary='Lane and storage counters only; wire/exposure fixed; no calibrated area or energy',
                rates_boundary='Exact K-of-36 activity expectation of finite measured rates, not exact DRAM performance',
                strong_references=dict(home_only_service=1.,wide_pair_random9=1+27/35),
                distributions=distributions,catalog=configs,frontier=frontier,selections=rows)
