"""Audit registered service/ILP experiments without test-dependent selection."""
import argparse,hashlib,json
from math import comb
from pathlib import Path
from collections import defaultdict
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def analyze(source,output,figures):
    root=Path(source);read=lambda name:json.loads((root/name).read_text())
    manifest=read('manifest.json');designs=read('designs.json');selection=read('selection.json');ilps=read('ilp_certificates.json')
    payload=(root/'records.jsonl').read_bytes();assert hashlib.sha256(payload).hexdigest()==manifest['records_sha256']
    rows=[json.loads(line) for line in payload.splitlines()];assert len(rows)==manifest['records']
    seeds=[set(manifest[k]) for k in ['train_seeds','validation_seeds','test_seeds']]
    assert not seeds[0]&seeds[1] and not seeds[0]&seeds[2] and not seeds[1]&seeds[2]
    ds={d['id']:d for d in designs};residual=0.
    for d in designs:
        shares=np.array(read(d['id']+'.shares.json'))
        assert shares.min()>=-1e-9 and np.allclose(shares.sum(axis=1),1,atol=1e-7)
        assert max(shares.sum(axis=0)*4)<=.5+1e-7
        assert hashlib.sha256(shares.astype('<f8').tobytes()).hexdigest()==d['layout_hash']
        assert d['certificate']['feasible'] and d['certificate']['minimum_tb_s']>=d['floor']-1e-7
        assert sum(d['widths'])<=32000
        if d['kind'] in ('service_layout','service_exposure'):
            search=d['search'];assert search['final_score']+1e-8>=search['initial_score']
            assert abs(search['final_score']-d['training_mean'])<1e-7
    for s in selection:
        eligible=[d for d in designs if d['floor']==s['floor'] and d['cost']['bank_port_connections']<=s['edges'] and d['cost']['wire_mm']<=s['wire']+1e-8]
        best=min(eligible,key=lambda d:(-round(d['validation_mean'],9),d['cost']['wire_mm'],sum(d['widths']),d['id']))
        assert best['id']==s['id']
    for result in ilps:
        assert result['continuous']==0 and result['binary']>0 and result['integer']==result['variables']
        assert result['primary']['bound']>=result['primary']['objective']-1e-8
    groups=defaultdict(list)
    for row in rows:
        assert row['seed'] in seeds[2]
        assert row['layout_hash']==ds[row['id']]['layout_hash']
        t=row['throughput'];o=row['oracle'];c=row['common']
        assert t['minimum_tb_s']>=row['floor']-1e-7
        assert t['total_tb_s']<=o['total_tb_s']+1e-7<=36+2e-7
        for r in [t,o,c]:residual=max(residual,r['constraint_residual'])
        groups[row['id'],row['pattern'],row['fraction']].append(row)
    summary=[]
    for (identifier,pattern,fraction),rs in sorted(groups.items()):
        bw=np.array([r['throughput']['tb_s_per_active'] for r in rs])
        summary.append(dict(id=identifier,pattern=pattern,fraction=fraction,seeds=len(rs),mean_bw=float(bw.mean()),
            sample_standard_error=float(bw.std(ddof=1)/np.sqrt(len(bw))),
            common_bw=float(np.mean([r['common']['tb_s_per_active'] for r in rs])),
            minimum_service=min(r['throughput']['minimum_tb_s'] for r in rs),
            mean_p5=float(np.mean([r['throughput']['p5_tb_s'] for r in rs])),
            worst_sample_bw=float(bw.min()),oracle_bw=float(np.mean([r['oracle']['tb_s_per_active'] for r in rs]))))
    # Exact finite-population references are independent of the sampled test set.
    # For a perfect disjoint pairing, common rate is 2 iff no pair is co-active.
    analytic=[]
    for active in (9,18,27,36):
        no_collision=2**active*comb(18,active)/comb(36,active) if active<=18 else 0.
        analytic.append(dict(active=active,paired_clients=36,
            mean_per_active=1+(36-active)/35,
            mean_common=1+no_collision,
            probability_no_coactive_pair=no_collision,
            mean_normalized_fluid_phase_duration=1-no_collision/2))
    compact=[]
    for d in designs:
        compact.append({k:v for k,v in d.items() if k not in ('certificate','mask')}|dict(full_load_certificate=True))
    result=dict(manifest=manifest,verification=dict(designs=len(designs),records=len(rows),max_residual=residual,
        checks='Unique bytes/storage, layout hashes, disjoint train/validation/test, validation-only selection, monotonic exact acceptance, ILP variable types/bounds and service caps'),
        designs=compact,selection=selection,ilp_certificates=ilps,perfect_pair_analytic_reference=analytic,summary=summary)
    Path(output).write_text(json.dumps(result,indent=2,allow_nan=False))
    figs=Path(figures);figs.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none'})
    fig,axs=plt.subplots(2,2,figsize=(12,8),layout='constrained')
    ax=axs[0,0]
    for floor in [.9,1.]:
        selected=[s for s in selection if s['floor']==floor]
        ax.plot([s['edges'] for s in selected],[ds[s['id']]['validation_mean'] for s in selected],marker='o',label=f'Floor {floor:g}')
    ax.set(xlabel='Bank-port edge budget (wire budget varies too)',ylabel='Validation TB/s / active',title='Registered budget selections');ax.legend()
    ax=axs[0,1]
    ids=['k2_23_base_h1.0','k3_23_cardinality_h1.0','ilp_e96_h1.0','full5_pairs_base_h1.0']
    for identifier in ids:
        rr=[r for r in summary if r['id']==identifier and r['pattern']=='uniform']
        ax.plot([r['fraction']*100 for r in rr],[r['mean_bw'] for r in rr],marker='o',label=identifier.replace('_h1.0','').replace('_base',''))
    ax.set(xlabel='Active compute (%)',ylabel='Test TB/s / active',title='Fresh 20-seed random activity');ax.legend(fontsize=8)
    ax=axs[1,0]
    ss=[d for d in designs if d['kind']=='service_layout' and d['floor']==.9]
    for d in ss:
        b=ds[d['id'].replace('_slp_','_base_')]
        ax.scatter(d['training_mean']-b['training_mean'],d['validation_mean']-b['validation_mean'],s=50)
        ax.annotate(d['id'].replace('_slp_h0.9',''),(d['training_mean']-b['training_mean'],d['validation_mean']-b['validation_mean']),fontsize=7)
    ax.axhline(0,color='k',lw=.7);ax.axvline(0,color='k',lw=.7)
    ax.set(xlabel='Training gain (TB/s / active)',ylabel='Validation gain',title='Does direct service optimization generalize?')
    ax=axs[1,1]
    for kind,marker in [('baseline','o'),('service_layout','x'),('service_exposure','^'),('pair_baseline','s'),('gurobi_ilp','D')]:
        pts=[d for d in designs if d['kind']==kind and d['floor']==.9]
        ax.scatter([d['cost']['wire_mm'] for d in pts],[d['validation_mean'] for d in pts],marker=marker,label=kind)
    ax.set(xlabel='Memory-side wire proxy (mm)',ylabel='Validation TB/s / active',title='Graph + data + cost');ax.legend(fontsize=8)
    fig.suptitle('Service-driven search and an exact restricted-family ILP',fontsize=14)
    for ext in ['png','svg']:fig.savefig(figs/('service_driven.'+ext),dpi=160)
    plt.close(fig)
    for svg in figs.glob('*.svg'):svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
    print(json.dumps(result['verification'],indent=2))
    print('SELECTION',json.dumps(selection))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('input');p.add_argument('--output',default='service_driven_results.json');p.add_argument('--figures',default='research_figures/service_driven')
    a=p.parse_args();analyze(a.input,a.output,a.figures)
