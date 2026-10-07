"""Independent constraint/closed-form audit and reproducible research figure."""
import json
from collections import defaultdict
from math import comb
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matching_placement import contoured, mixture


def independent_sets(cycle_sizes, count):
    polynomial=[1]
    for n in cycle_sizes:
        assert n>=2
        # Independent sets of size j in a cycle; also valid for a 2-node pair.
        terms=[1]+[n*comb(n-j,j)//(n-j) for j in range(1,n//2+1)]
        out=[0]*(len(polynomial)+len(terms)-1)
        for i,a in enumerate(polynomial):
            for j,b in enumerate(terms):out[i+j]+=a*b
        polynomial=out
    return polynomial[count] if count<len(polynomial) else 0


def main():
    root=Path(__file__).resolve().parent
    raw=json.loads((root/'matching_placement_results.json').read_text())
    assert raw['dirty'] is False
    by_placement={(p['pitch_mm'],p['stagger_mm']):p for p in raw['placements'] if p['legal']}
    physical={key:contoured(*key) for key in by_placement}
    residual=0.;rate_error=0.;groups=defaultdict(list)
    for t in raw['tests']:
        key=(t['pitch_mm'],t['stagger_mm']);p=physical[key];entry=by_placement[key]
        selected=next(c for c in entry['candidates'] if c['family']==t['family'] and np.allclose(c['weights'],t['weights']))
        a=mixture(selected['matchings'],t['weights'])
        assert np.allclose(a.sum(axis=0),1) and np.allclose(a.sum(axis=1),1)
        assert np.max(4*a.sum(axis=0))<=16  # 4 GiB/client, 16 GiB/memory.
        paths={(e['c'],e['m']):e for e in p.edges}
        assert len(paths)==len(p.edges), 'Audit assumes one physical link per C-M pair'
        for objective in ['throughput','common']:
            r=np.array(t[objective]['rates']);flows=a*r[:,None]
            limits=[np.max(a.T@r-1),np.max(r-4),-np.min(r),1-np.min(r[t['active']])]
            inactive=sorted(set(range(36))-set(t['active']))
            if inactive:limits.append(np.max(np.abs(r[inactive])))
            cp=defaultdict(float);mp=defaultdict(float)
            for c,m in zip(*np.nonzero(flows)):
                assert (c,m) in paths
                e=paths[c,m];f=flows[c,m]
                limits.append(f-p.edge_bandwidth(e))
                cp[c,e['cp']]+=f;mp[m,e['mp']]+=f
            limits.extend(v-.8 for v in list(cp.values())+list(mp.values()))
            if objective=='common':limits.append(np.ptp(r[t['active']]))
            residual=max(residual,*limits)
        # Independent closed form for the 50/50 layout at full overlap:
        # an active client can exceed 1 iff neither memory has another active
        # resident client. Its solo cap is 2*0.8=1.6. No LP used here.
        if key==(25.6,16.5) and np.allclose(t['weights'],[.5,.5]):
            sharing=(a>0).astype(int)@(a>0).T
            predicted=np.zeros(36);active=set(t['active'])
            for c in active:
                rivals=set(np.flatnonzero(sharing[c]))-{c}
                predicted[c]=1. if rivals&active else 1.6
            rate_error=max(rate_error,float(np.max(np.abs(predicted-np.array(t['throughput']['rates'])))))
            assert abs(t['common']['mean']-min(predicted[t['active']]))<1e-8
        groups[t['pitch_mm'],t['design'],t['kind']].append(t)
    assert residual<1e-8 and rate_error<1e-8
    aggregated=[]
    for (pitch,design,kind),ts in sorted(groups.items()):
        aggregated.append(dict(pitch_mm=pitch,design=design,kind=kind,n=len(ts),
            mean=float(np.mean([t['throughput']['mean'] for t in ts])),
            common_mean=float(np.mean([t['common']['mean'] for t in ts])),
            worst_sample_mean=min(t['throughput']['mean'] for t in ts),
            minimum_service=min(t['throughput']['minimum'] for t in ts),
            p5_mean=float(np.mean([t['throughput']['p5'] for t in ts]))))
    exact=[]
    base=by_placement[25.6,16.5]
    for c in base['candidates']:
        if c['weights']!=[.5,.5]:continue
        sizes=c['alternating_cycle_compute_sizes']
        # Given client active, remaining eight are drawn from 35 clients.
        mean=1+.6*sum(n*comb(35-(1 if n==2 else 2),8)/comb(35,8) for n in sizes)/36
        common=1+.6*independent_sets(sizes,9)/comb(36,9)
        exact.append(dict(family=c['family'],cycle_sizes=sizes,random25_mean=mean,random25_common_mean=common))
    report=dict(source_commit=raw['commit'],test_cases=len(raw['tests']),
        legal_placements=len(by_placement),candidate_layouts=sum(len(p.get('candidates',[])) for p in raw['placements']),
        independently_reconstructed_constraint_violation=residual,
        independent_closed_form_rate_error=rate_error,exact_random25=exact,aggregated=aggregated)
    (root/'matching_placement_summary.json').write_text(json.dumps(report,indent=2)+'\n')
    fig,axes=plt.subplots(1,2,figsize=(11,4.4),layout='constrained')
    pitches=[25.6,25.7,25.8,25.9]
    rows=[next(x for x in aggregated if x['pitch_mm']==p and x['design']=='training_selected' and x['kind']=='random25') for p in pitches]
    axes[0].plot(pitches,[x['mean'] for x in rows],'o-',label='Held-out mean (20 sets)')
    axes[0].plot(pitches,[1+(s-1)*27/35 for s in [1.6,1.4,1.2,1]],'s--',label='Exact random-subset expectation')
    axes[0].plot(pitches,[x['common_mean'] for x in rows],'^:',label='Held-out common service')
    axes[0].set(title='Same 146 allowed edges; different usable capacity',xlabel='Horizontal center pitch (mm)',ylabel='TB/s per active compute',ylim=(.96,1.63))
    axes[0].set_xticks(pitches);axes[0].legend(fontsize=8)
    selected=[x for x in exact if x['family'] in ['home_reciprocal_pairs','packed_two']]
    x=np.arange(2);width=.33
    axes[1].bar(x-width/2,[s['random25_mean']-1 for s in selected],width,label='Mean throughput')
    axes[1].bar(x+width/2,[s['random25_common_mean']-1 for s in selected],width,label='Common service')
    axes[1].set_xticks(x,['18 reciprocal pairs','Cycles: 3, 3, 6, 8, 16'])
    axes[1].set(title='Two matchings each: exact 9-of-36 expectation',ylabel='Additional TB/s above unit service',ylim=(0,.63))
    axes[1].legend(fontsize=8)
    for ax in axes:ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    directory=root/'research_figures/matching';directory.mkdir(parents=True,exist_ok=True)
    fig.savefig(directory/'matching.svg');fig.savefig(directory/'matching.png',dpi=150)
    print(json.dumps({k:v for k,v in report.items() if k!='aggregated'},indent=2))


if __name__=='__main__':main()
