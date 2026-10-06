"""Audit joint-DSE output and summarize registered selections, without retuning."""
import argparse,hashlib,json
from pathlib import Path
from collections import defaultdict, Counter
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def analyze(source,output,figures):
    root=Path(source);read=lambda name:json.loads((root/name).read_text())
    manifest=read('manifest.json');candidates=read('candidates.json');choices=read('selection.json')
    data=(root/'records.jsonl').read_bytes();assert hashlib.sha256(data).hexdigest()==manifest['records_sha256']
    records=[json.loads(x) for x in data.splitlines()];assert len(records)==manifest['records']
    assert not set(manifest['train_seeds'])&set(manifest['test_seeds'])
    catalog={c['id']:c for c in candidates};layouts={};max_residual=0
    for c in candidates:
        assert sum(c['widths'])==32000
        assert c['cost']['bank_port_connections']==sum(c['bank_degree'])
        for p in c['profiles']:
            if not p['feasible']:continue
            key=p['layout_id']
            if key not in layouts:
                a=np.array(read(key+'.shares.json'))
                assert np.allclose(a.sum(axis=1),1,atol=1e-7) and a.min()>=-1e-9
                assert max(a.sum(axis=0)*4)<=.5+1e-7
                layouts[key]=hashlib.sha256(a.astype('<f8').tobytes()).hexdigest()
            assert layouts[key]==p['layout_hash']
    for choice in choices:
        eligible=[(c,p) for c in candidates if (choice['scope']=='joint' or c['method']==choice['scope']) and c['cost']['wire_mm']<=choice['wire']+1e-9 and c['cost']['bank_port_connections']<=choice['connections']
                  for p in c['profiles'] if p['feasible'] and p['floor']==choice['floor']]
        assert bool(eligible)==choice['feasible']
        if eligible:
            c,p=min(eligible,key=lambda x:(-round(x[1]['training_mean'],9),x[0]['cost']['wire_mm'],x[0]['cost']['bank_port_connections'],x[0]['id'],x[1]['mode']))
            assert c['id']==choice['id'] and p['layout_id']==choice['layout_id']
    groups=defaultdict(list)
    for r in records:
        t=r['throughput'];o=r['oracle'];common=r['common']
        assert r['seed'] in manifest['test_seeds']
        assert layouts[r['layout_id']]==r['layout_hash']
        assert t['minimum_tb_s']>=r['floor']-1e-7
        assert t['total_tb_s']<=o['total_tb_s']+1e-7<=r['demand_limited_pool_bound_tb_s']+2e-7
        for metric in (t,o,common,r['full_load_service']):max_residual=max(max_residual,metric['constraint_residual'])
        groups[r['id'],r['layout_id'],r['floor'],r['pattern'],r['fraction']].append(r)
    summary=[]
    for (identifier,layout_id,floor,pattern,fraction),rs in sorted(groups.items()):
        summary.append(dict(id=identifier,method=catalog[identifier]['method'],layout_id=layout_id,floor=floor,pattern=pattern,fraction=fraction,
            mean_bw=float(np.mean([r['throughput']['tb_s_per_active'] for r in rs])),
            common_bw=float(np.mean([r['common']['tb_s_per_active'] for r in rs])),
            min_service=min(r['throughput']['minimum_tb_s'] for r in rs),
            mean_p5=float(np.mean([r['throughput']['p5_tb_s'] for r in rs])),
            worst_sample_mean=min(r['throughput']['tb_s_per_active'] for r in rs),
            oracle_bw=float(np.mean([r['oracle']['tb_s_per_active'] for r in rs])),
            full_load_bw=rs[0]['full_load_service']['tb_s_per_active'],
            full_load_min=rs[0]['full_load_service']['minimum_tb_s'],
            unrecovered_bound_tb_s=float(np.mean([r['unrecovered_bound_tb_s'] for r in rs])),
            fixed_layout_gap_tb_s=float(np.mean([r['fixed_layout_gap_tb_s'] for r in rs])),
            reported_bottleneck_counts=dict(Counter(b['resource'][0] for r in rs for b in r['throughput']['bottlenecks']))))
    for row in summary:
        pooled_per_active=min(4.,36/round(36*row['fraction']))
        row['gain_recovery_global_pool']=(row['mean_bw']-1)/(pooled_per_active-1) if pooled_per_active>1 else None
        row['gain_recovery_same_fabric']=(row['mean_bw']-1)/(row['oracle_bw']-1) if row['oracle_bw']>1+1e-9 else None
    compact=[{k:v for k,v in c.items() if k!='mask'} for c in candidates]
    result=dict(manifest=manifest,verification=dict(records=len(records),candidates=len(candidates),layouts=len(layouts),max_residual=max_residual,
        checks='Source hash, fixed byte/storage conservation, layout hashes, seed separation, training-only selections, per-record floors and oracle bounds'),
        candidates=compact,selection=choices,summary=summary)
    Path(output).write_text(json.dumps(result,indent=2,allow_nan=False))
    figdir=Path(figures);figdir.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none'})
    fig,axs=plt.subplots(2,2,figsize=(12,8),layout='constrained')
    colors=dict(aligned='C0',half_shifted_x='C1',half_shifted='C2',contoured='C3')
    ax=axs[0,0]
    for method,color in colors.items():
        pts=[(c,p) for c in candidates if c['method']==method for p in c['profiles'] if p['feasible'] and p['floor']==.9]
        ax.scatter([c['cost']['wire_mm'] for c,p in pts],[p['training_mean'] for c,p in pts],s=20,alpha=.4,color=color,label=method)
    ax.set(xlabel='Memory-side wire proxy (mm)',ylabel='Training mean TB/s / active',title='All static/fixed candidates, floor 0.9');ax.legend(fontsize=8)
    ax=axs[0,1]
    for floor in (0.,.9,1.):
        sel=[s for s in choices if s['scope']=='joint' and s['floor']==floor and s['connections']==64 and s['feasible']]
        ax.plot([s['wire'] for s in sel],[s['training_mean'] for s in sel],marker='o',label=f'Floor {floor:g}')
    ax.set(xlabel='Wire budget (mm), <=64 bank-port edges',ylabel='Training mean TB/s / active',title='Registered service-cost frontier');ax.legend(fontsize=8)
    ax=axs[1,0];names=[];values=[];commons=[];oracles=[]
    for method in colors:
        sel=next(s for s in choices if s['scope']==method and s['floor']==.9 and s['connections']==64 and s['wire']==1000)
        if not sel['feasible']:continue
        rs=[r for r in summary if r['id']==sel['id'] and r['layout_id']==sel['layout_id'] and r['floor']==.9 and r['pattern']=='uniform' and r['fraction']==.25]
        r=rs[0];names.append(method.replace('half_shifted','shift'));values.append(r['mean_bw']);commons.append(r['common_bw']);oracles.append(r['oracle_bw'])
    xx=np.arange(len(names));ax.bar(xx-.25,values,.25,label='Static throughput');ax.bar(xx,commons,.25,label='Common');ax.bar(xx+.25,oracles,.25,label='Free residency')
    ax.set_xticks(xx,names);ax.set(ylabel='Test TB/s / active',title='25% random: per-placement trained winner');ax.legend(fontsize=8)
    ax=axs[1,1]
    sel=next(s for s in choices if s['scope']=='joint' and s['floor']==.9 and s['connections']==64 and s['wire']==1000)
    for layout_id,label in [(sel['layout_id'],'Selected static'),(sel['id']+'_fixed_home','Fixed home')]:
        rs=[r for r in summary if r['id']==sel['id'] and r['layout_id']==layout_id and r['floor']==.9 and r['pattern']=='uniform']
        if rs:ax.plot([r['fraction']*100 for r in rs],[r['mean_bw'] for r in rs],marker='o',label=label)
    ax.set(xlabel='Active compute (%)',ylabel='Test TB/s / active',title='Identical fabric: isolate static layout');ax.legend(fontsize=8)
    fig.suptitle('Open memory-fabric DSE: finite seeds + local moves, no global-optimum claim',fontsize=14)
    for ext in ('svg','png'):fig.savefig(figdir/('dse_frontier.'+ext),dpi=160)
    plt.close(fig)
    for svg in figdir.glob('*.svg'):
        svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
    print(json.dumps(result['verification'],indent=2))
    print('PRIMARY',json.dumps(sel))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('input');p.add_argument('--output',default='memory_fabric_dse_results.json');p.add_argument('--figures',default='research_figures/memory_fabric_dse');a=p.parse_args();analyze(a.input,a.output,a.figures)
