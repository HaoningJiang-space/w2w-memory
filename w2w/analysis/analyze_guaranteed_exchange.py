"""Verify independent invariants, summarize held-out results, draw static figures."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from w2w.service.guaranteed_service_exchange import STRIPES


def analyze(path,output,figures):
    root=Path(path);out=Path(output);figdir=Path(figures);figdir.mkdir(parents=True,exist_ok=True)
    read=lambda name:json.loads((root/name).read_text())
    manifest=read('manifest.json');designs=read('designs.json');selection=read('selection.json')
    payload=(root/'records.jsonl').read_bytes()
    assert hashlib.sha256(payload).hexdigest()==manifest['records_sha256']
    records=[json.loads(x) for x in payload.splitlines()]
    assert len(records)==manifest['records']
    assert not set(manifest['train_seeds'])&set(manifest['test_seeds'])
    residual=0.;models={d['id']:d for d in designs}
    for d in designs:
        counts=np.array(read(d['id']+'.layout.json'),dtype=np.int32)
        assert (counts>=0).all() and (counts.sum(axis=1)==STRIPES).all()
        assert (counts.sum(axis=0)/STRIPES*4<=.5+1e-9).all()
        assert hashlib.sha256(counts.astype('<i4').tobytes()).hexdigest()==d['layout_hash']
        c=d['certificate']
        if c['feasible']:
            assert c['minimum_tb_s']>=1-1e-7
            assert max(c['bank_load_at_floor_tb_s'])<=1/32+1e-9
            residual=max(residual,c['constraint_residual'])
        assert sum(d['cost']['port_tb_s'])<=4+1e-9
    for choice in selection:
        eligible=[d for d in designs if d['kind'] in ('home','reciprocal') and d['training_mean'] is not None and d['cost']['wire_mm']<=choice['wire_budget_mm']+1e-9 and sum(d['cost']['port_bits'])<=choice['port_budget_bits']]
        best=min(eligible,key=lambda d:(-round(d['training_mean'],10),d['cost']['wire_mm'],sum(d['cost']['port_bits']),d['beta'] or 0,d['id']))
        assert choice['design']==best['id']
    groups=defaultdict(list)
    for r in records:
        assert r['seed'] in manifest['test_seeds']
        t=r['throughput'];assert t['feasible']
        assert t['total_tb_s']<=36+1e-7
        residual=max(residual,t['constraint_residual'])
        if not r.get('oracle_only'):
            assert r['layout_hash']==models[r['id']]['layout_hash']
            assert t['minimum_tb_s']>=1-1e-7
            assert t['total_tb_s']<=r['oracle']['total_tb_s']+1e-7
            assert r['common']['total_tb_s']<=t['total_tb_s']+1e-7
            residual=max(residual,r['oracle']['constraint_residual'],r['common']['constraint_residual'])
        groups[r['id'],r['pattern'],r['fraction']].append(r)
    rows=[]
    for (identifier,pattern,fraction),rs in sorted(groups.items()):
        row=dict(id=identifier,pattern=pattern,fraction=fraction,samples=len(rs),
            mean_bw=float(np.mean([r['throughput']['tb_s_per_active'] for r in rs])),
            worst_sample_mean_bw=min(r['throughput']['tb_s_per_active'] for r in rs),
            minimum_service=min(r['throughput']['minimum_tb_s'] for r in rs),
            mean_p5=float(np.mean([r['throughput']['p5_tb_s'] for r in rs])))
        if not rs[0].get('oracle_only'):
            row.update(common_bw=float(np.mean([r['common']['tb_s_per_active'] for r in rs])),
                same_fabric_oracle_bw=float(np.mean([r['oracle']['tb_s_per_active'] for r in rs])),
                gain_recovery_fraction=(sum(r['throughput']['tb_s_per_active']-1 for r in rs)/sum(r['oracle']['tb_s_per_active']-1 for r in rs)) if sum(r['oracle']['tb_s_per_active']-1 for r in rs)>1e-9 else None)
        rows.append(row)
    compact=[]
    for d in designs:
        compact.append({k:v for k,v in d.items() if k not in ('mask','certificate')}|dict(certified=d['certificate']['feasible']))
    probe=read('locked_probe.json');probe_summary=[]
    for pattern in ('uniform','hotspot','clustered','correlated'):
        rs=[r for r in probe if r['pattern']==pattern and r['fraction']==.25]
        probe_summary.append(dict(pattern=pattern,mean_bw=float(np.mean([r['throughput']['tb_s_per_active'] for r in rs])),common_bw=float(np.mean([r['common']['tb_s_per_active'] for r in rs]))))
    summary=dict(manifest=manifest,verification=dict(records=len(records),designs=len(designs),certified=sum(d['certificate']['feasible'] for d in designs),max_residual=residual,
        checks='Hashes, unique stripe/storage conservation, full-load certificate, all test floors/caps, oracle bounds, disjoint seeds and training-only winner recomputation'),
        designs=compact,selection=selection,summary=rows,layout_limits=read('layout_limits.json'),
        exact=read('exact_expectations.json'),coactivity=read('coactivity.json'),locked_probe=probe_summary)
    out.write_text(json.dumps(summary,indent=2,allow_nan=False))
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none'})
    fig,axes=plt.subplots(2,2,figsize=(12,8.4),layout='constrained')
    selected_id=next(s['design'] for s in selection if s['wire_budget_mm']==950 and s['port_budget_bits']==16000)
    names=['contoured_home',selected_id,'r23_b0.5_w4000','r1234_b0.5_w2000']
    labels=['Home-only','Training-selected','2-peer half/half','4-peer half/half']
    ax=axes[0,0]
    for identifier,label in zip(names,labels):
        rr=[r for r in rows if r['id']==identifier and r['pattern']=='uniform']
        ax.plot([r['fraction']*100 for r in rr],[r['mean_bw'] for r in rr],marker='o',label=label)
    ax.set(xlabel='Active compute (%)',ylabel='TB/s per active compute',title='Held-out random subsets (10 seeds)');ax.legend(fontsize=8)
    ax=axes[0,1];patterns=['uniform','hotspot','clustered','correlated'];xx=np.arange(4)
    rr=[next(r for r in rows if r['id']==selected_id and r['pattern']==pat and r['fraction']==.25) for pat in patterns]
    ax.bar(xx-.17,[r['mean_bw'] for r in rr],.34,label='Throughput objective')
    ax.bar(xx+.17,[r['common_bw'] for r in rr],.34,label='Common completion objective')
    ax.set_xticks(xx,patterns);ax.set(ylabel='TB/s per active compute',title='Selected design, 25% activity');ax.legend(fontsize=8)
    ax=axes[1,0]
    for beta in (.125,.25,.5):
        ds=sorted([d for d in designs if d['id'].startswith('r23_b'+str(beta)+'_') and d['certificate']['feasible']],key=lambda d:d['cost']['port_bits'][2])
        ax.plot([d['cost']['port_bits'][2] for d in ds],[d['training_mean'] for d in ds],marker='o',label=f'Peer fraction {beta:g}')
    ax.set(xlabel='Bits per shared port at 1 GHz',ylabel='Training mean TB/s per active',title='Finite width + frozen data fractions');ax.legend(fontsize=8)
    ax=axes[1,1]
    for dirs,col in [('14','C0'),('23','C1'),('1234','C2')]:
        ds=[d for d in designs if d['id'].startswith('r'+dirs+'_') and d['certificate']['feasible']]
        ax.scatter([d['cost']['wire_mm'] for d in ds],[d['training_mean'] for d in ds],s=[sum(d['cost']['port_bits'])/180 for d in ds],alpha=.4,color=col,label='Directions '+dirs)
    ax.axvline(784,color='k',ls='--',label='Old X wire proxy 784 mm')
    ax.set(xlabel='Bank-to-port centerline wire (mm)',ylabel='Training mean TB/s per active',title='Cost frontier (bubble area = port width)');ax.legend(fontsize=8)
    fig.suptitle('Guaranteed reciprocal exposure: fluid service, not application speedup',fontsize=14)
    for ext in ('svg','png'):fig.savefig(figdir/('service_cost.'+ext),dpi=160)
    plt.close(fig)
    fig,ax=plt.subplots(figsize=(11,5));ax.set(xlim=(0,11),ylim=(0,5));ax.axis('off')
    def box(x,y,w,h,text,color):
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.06',facecolor=color,edgecolor='#345'))
        ax.text(x+w/2,y+h/2,text,ha='center',va='center',fontsize=10)
    box(.3,3.8,10.4,.8,'Repeated memory reticle: 32 banks, 1 TB/s total\nEach bank retains HOME + one SHARED output (256 bits each)','#e1ebf5')
    for x,label,width in [(1,'Shared P2\n16 banks','4000 bits / 0.5 TB/s'),(4.4,'Home P0\n32 banks','8000 bits / 1 TB/s'),(7.8,'Shared P3\n16 banks','4000 bits / 0.5 TB/s')]:
        box(x,2,2.2,1,label+'\n'+width,'#dceee1')
        ax.annotate('',xy=(x+1.1,3.02),xytext=(x+1.1,3.8),arrowprops=dict(arrowstyle='->',lw=2))
        ax.annotate('',xy=(x+1.1,.95),xytext=(x+1.1,2),arrowprops=dict(arrowstyle='->',lw=2))
    ax.axhline(1.55,color='#735',ls='--');ax.text(.1,1.6,'HB',color='#735')
    box(.3,.2,10.4,.75,'Reciprocal neighbor / home / reciprocal neighbor compute controllers (4 TB/s each)\nStatic unique stripes; boundary groups without a partner remain home-only','#f4e9d9')
    ax.set_title('One k=2 candidate: width-accounted parallel aggregation before HB\nAt 1 GHz; conceptual ports and wire proxies, not a routed implementation')
    for ext in ('svg','png'):fig.savefig(figdir/('architecture.'+ext),dpi=160,bbox_inches='tight')
    plt.close(fig)
    for svg in figdir.glob('*.svg'):
        svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
    print(json.dumps(dict(verification=summary['verification'],selected=selected_id,probe=probe_summary),indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('input');p.add_argument('--output',default='artifacts/results/exchange/guaranteed_exchange_results.json');p.add_argument('--figures',default='artifacts/figures/guaranteed_exchange')
    a=p.parse_args();analyze(a.input,a.output,a.figures)
