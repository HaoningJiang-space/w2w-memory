"""Static architecture and experiment figures for the bounded-sharing gate."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle,FancyArrowPatch


def architecture(out):
    fig,ax=plt.subplots(figsize=(12,7));ax.set_xlim(0,12);ax.set_ylim(0,7);ax.axis('off')
    def box(x,y,w,h,text,color='#edf2f7',size=10):
        ax.add_patch(Rectangle((x,y),w,h,facecolor=color,edgecolor='#384860',lw=1))
        if text:ax.text(x+w/2,y+h/2,text,ha='center',va='center',fontsize=size)
    def arrow(x,y,xx,yy):ax.add_patch(FancyArrowPatch((x,y),(xx,yy),arrowstyle='-|>',mutation_scale=12,color='#384860',lw=1.2))
    ax.text(.3,6.75,'One repeated memory-side template, instantiated on 36 reticles',fontsize=16,weight='bold')
    ax.add_patch(Rectangle((.25,2.6),7.6,3.75,facecolor='#f4f7fb',edgecolor='#73829a',lw=1.5))
    ax.text(.45,6.1,'DRAM reticle: 32 banks, 1 TB/s aggregate service',fontsize=12)
    colors=['#d8e8f5','#fce5bc','#ddecd7','#e9dff2']
    for r in range(8):
        for c in range(4):box(.65+c*1.5,4.02+r*.23,1.35,.18,str(r*4+c),colors[(r//4)*2+c//2],7)
    ax.text(7.4,4.7,'Bank\noutputs',ha='center',va='center',fontsize=10)
    arrow(3.85,3.98,3.85,3.65)
    box(.8,3.05,6.1,.58,'Sparse digital selection + arbitration\nRepeated mask: each bank connects to k HB regions','#d7e4ee',11)
    for p,x in enumerate([1.1,2.7,4.3,5.9]):
        arrow(x+.4,3.05,x+.4,2.93);box(x,2.65,.8,.28,f'P{p}',colors[p],10)
        arrow(x+.4,2.6,x+.4,1.7)
    ax.plot([.3,7.8],[2.2,2.2],color='#aa643b',lw=5)
    ax.text(8.,2.2,'HB overlap enables these links\nPlacement decides the receiving reticle',va='center',fontsize=10)
    ax.add_patch(Rectangle((.25,.75),7.6,1.05,facecolor='#eef5e9',edgecolor='#73829a',lw=1.5))
    ax.text(.4,1.65,'Receiving interfaces may belong to different compute reticles',fontsize=8)
    for p,x in enumerate([1.1,2.7,4.3,5.9]):box(x,1.05,.8,.5,f'Ctl {p}',colors[p],10)
    ax.text(.4,.45,'Compute side: 4 TB/s controller cap; 4 TB/s total HB budget per reticle',fontsize=10)
    ax.text(8.3,5.8,'Connectivity cost per template',fontsize=12,weight='bold')
    for i,(k,edges,desc) in enumerate([(1,32,'Local bank group'),(2,64,'Local + one selected region'),(4,128,'All four regions')]):
        y=5.15-i*.65
        ax.text(8.3,y,f'k = {k}: {edges} bank-port edges',fontsize=11)
        ax.text(8.3,y-.25,desc,fontsize=10,color='#53627a')
    ax.text(8.3,.6,'Added circuitry is on the MEMORY side.\nNo inter-reticle memory forwarding.\nWire/fan-in costs are proxies;\nDRAM process/timing not validated.',fontsize=10,linespacing=1.5)
    fig.savefig(out/'architecture.png',dpi=180,bbox_inches='tight');fig.savefig(out/'architecture.svg',bbox_inches='tight');plt.close(fig)


def plot_results(directory):
    out=Path(directory);out.mkdir(parents=True,exist_ok=True);architecture(out)
    if not (out/'records.jsonl').exists():return
    rows=[json.loads(s) for s in (out/'records.jsonl').read_text().splitlines()]
    grouped=defaultdict(list)
    for r in rows:grouped[tuple(r[k] for k in ('scope','method','layout_mode','k','pattern','fraction'))].append(r)
    summary=[]
    for key,items in grouped.items():
        scope,method,mode,k,pattern,fraction=key
        vals=np.array([r['throughput']['tb_s_per_active'] for r in items])
        summary.append(dict(scope=scope,method=method,layout_mode=mode,k=k,pattern=pattern,fraction=fraction,
                            mean_tb_s_per_active=float(vals.mean()),min_tb_s_per_active=float(vals.min()),max_tb_s_per_active=float(vals.max()),
                            mean_pooling_efficiency=float(np.mean([r['pooling_efficiency'] for r in items])),
                            mean_common_fraction=float(np.mean([r['common']['common_completion'] for r in items])),
                            mean_common_p5_tb_s=float(np.mean([r['common']['p5_tb_s'] for r in items])),
                            mean_p5_one_throughput_solution_tb_s=float(np.mean([r['throughput']['p5_tb_s'] for r in items])),
                            mean_blocked_active=float(np.mean([r['throughput']['blocked_active_clients'] for r in items])),
                            mean_oracle_cut_tb_s=float(np.mean([r['cut']['oracle_tb_s'] for r in items]))))
    (out/'summary.json').write_text(json.dumps(summary,indent=2))
    for pattern in ('uniform','clustered'):
        fig,axes=plt.subplots(1,3,figsize=(13,4.4),sharey=True,layout='constrained')
        for ax,mode,title in zip(axes,['home_striped','static_interleaved','static_train_greedy'],
                                ['Home-bank striping','Frozen geometry-aware striping','One offline trained layout']):
            for method,label,color in [('aligned','Aligned','#3d5a80'),('half_shifted_x','X shift','#e49b18'),('half_shifted','XY shift','#a92332')]:
                if not any(r['method']==method for r in summary):continue
                selected=[next(r for r in summary if r['scope']=='finite' and r['method']==method and r['layout_mode']==mode
                               and r['k']==k and r['pattern']==pattern and r['fraction']==.25) for k in (1,2,4)]
                means=np.array([r['mean_tb_s_per_active'] for r in selected]);lo=[r['min_tb_s_per_active'] for r in selected];hi=[r['max_tb_s_per_active'] for r in selected]
                ax.plot([1,2,4],means,'o-',label=label,color=color);ax.fill_between([1,2,4],lo,hi,color=color,alpha=.12)
            upper=next(r for r in summary if r['scope']=='finite' and r['method']=='half_shifted' and r['layout_mode']=='oracle'
                       and r['k']==4 and r['pattern']==pattern and r['fraction']==.25)['mean_tb_s_per_active']
            ax.axhline(upper,ls='--',color='#555',label='XY free-bank upper bound')
            ax.set_xticks([1,2,4]);ax.set_xlabel('Ports per bank k (32k connections)');ax.set_title(title,fontsize=11)
            ax.grid(alpha=.2);ax.set_ylim(0,max(3,upper+.3))
        axes[0].set_ylabel('TB/s per active compute\n(Aligned home-stripe baseline = 1 for uniform)')
        axes[-1].legend(fontsize=8,loc='lower right')
        fig.suptitle(f'25% active, {pattern} demand; masks and data layouts frozen before testing',fontsize=13)
        fig.savefig(out/f'cost_curve_{pattern}.png',dpi=180);fig.savefig(out/f'cost_curve_{pattern}.svg');plt.close(fig)
    diagnostics(out,summary)
    structural_cost(out)
    print('Wrote architecture, cost curves and',len(summary),'summary rows')

def diagnostics(out,summary):
    fig,axes=plt.subplots(1,2,figsize=(12,4.6),layout='constrained')
    scopes=['finite','interior_active','periodic_reference']
    for ax,mode,k,title in [(axes[0],'oracle',1,'Private banks: boundary service loss'),
                            (axes[1],'static_train_greedy',2,'Offline static k=2: same frozen layout')]:
        for i,(method,label,color) in enumerate([('aligned','Aligned','#3d5a80'),('half_shifted_x','X shift','#e49b18'),('half_shifted','XY shift','#a92332')]):
            if not any(r['method']==method for r in summary):continue
            values=[next(r['mean_tb_s_per_active'] for r in summary if r['scope']==scope and r['method']==method and r['layout_mode']==mode and r['k']==k and r['pattern']=='uniform' and r['fraction']==1.) for scope in scopes]
            ax.bar(np.arange(3)+(i-1)*.24,values,width=.24,label=label,color=color)
        ax.set_xticks(range(3),['Finite\n36 active','Interior activity\n25 active','Periodic reference\n36 active']);ax.set_title(title,fontsize=11)
        ax.set_ylabel('TB/s per active compute');ax.set_ylim(0,1.25);ax.grid(axis='y',alpha=.2)
    axes[-1].legend(fontsize=9);fig.suptitle('All eligible clients active; identical bank/HB/controller budgets',fontsize=13)
    fig.savefig(out/'boundary_diagnostic.png',dpi=180);fig.savefig(out/'boundary_diagnostic.svg');plt.close(fig)


def structural_cost(out):
    source=out/'structure_expectations.json'
    if not source.exists():return
    records=json.loads(source.read_text())['records']
    fig,ax=plt.subplots(figsize=(8,4.8),layout='constrained')
    for method,label,color in [('aligned','Aligned','#3d5a80'),('half_shifted_x','X shift','#e49b18'),('half_shifted','XY shift','#a92332')]:
        rows=[r for r in records if r['scope']=='finite' and r['method']==method and r['k']==2 and r['active']==9]
        ax.scatter([r['cost']['extra_wire_mm'] for r in rows],[r['mean_oracle_tb_s_per_active'] for r in rows],label=label,color=color,alpha=.8,s=45)
        best=max(rows,key=lambda r:(r['mean_oracle_tb_s_per_active'],-r['cost']['extra_wire_mm']))
        ax.annotate(best['mask'],(best['cost']['extra_wire_mm'],best['mean_oracle_tb_s_per_active']),xytext=(8,6),textcoords='offset points',fontsize=9,color=color)
    ax.set_xlabel('Added Manhattan wirelength per memory reticle (mm; proxy)')
    ax.set_ylabel('Exact expected oracle TB/s per active compute')
    ax.set_title('Same k=2 / 64 connections: placement and mask tradeoffs\n9 uniformly chosen active clients; data residency relaxed')
    ax.legend();ax.grid(alpha=.2);ax.set_ylim(.8,1.8)
    fig.savefig(out/'structural_cost.png',dpi=180);fig.savefig(out/'structural_cost.svg');plt.close(fig)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory');a=p.parse_args();plot_results(a.directory)
