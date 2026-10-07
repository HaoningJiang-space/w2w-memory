"""Export projections of the four-dimensional executed architecture frontier."""
import argparse
import gzip
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def render(source, output):
    raw=Path(source).read_bytes()
    data=json.loads(gzip.decompress(raw) if str(source).endswith('.gz') else raw)
    rows={r['id']:r for r in data['search']['catalog']}
    colors=dict(home='#27865c',k2='#2670b7',k3='#d16c28')
    markers=dict(home='D',k2='o',k3='^')
    axes_keys=[('export_lane_bits','Export lanes (kbit)'),
               ('endpoint_storage_bits','Endpoint storage (kbit)'),
               ('access_wire_bit_mm','Access wire (10³ bit-mm)')]
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(2,3,figsize=(13,7),sharey=True)
    for i,workload in enumerate(('random9','clustered9')):
        frontier=[rows[k] for k in data['frontiers'][workload]['global_primary']]
        for j,(key,label) in enumerate(axes_keys):
            ax=axes[i,j]
            for structure in ('home','k2','k3'):
                points=sorted({(r['cost'][key]/1000,r['scores'][workload]) for r in frontier
                               if r['structure']==structure})
                if points:
                    ax.scatter(*zip(*points),s=38,c=colors[structure],marker=markers[structure],
                               label=structure,edgecolor='white',linewidth=.5,zorder=3)
            ax.axhline(1,color='#999999',linewidth=.8,linestyle='--')
            ax.grid(alpha=.18)
            ax.set_xlabel(label)
            ax.set_title(('Uniform 9-of-36' if i==0 else 'Clustered 3×3 / 16 windows'))
            ax.set_ylim(.98,1.84)
            if j==0:
                ax.set_ylabel('Executed TB/s per active compute')
    handles,labels=axes[0,0].get_legend_handles_labels()
    fig.legend(handles,labels,ncol=3,loc='upper center',frameon=False,bbox_to_anchor=(.5,1.01))
    fig.suptitle('Architecture competition: projections of the 4D Pareto frontier',y=1.055,fontsize=13)
    fig.text(.5,.005,'Fixed H/plus · native always-ready · full-load floor = 1 · bank-side serialization\n'
             'Points are jointly nondominated in performance, lanes, endpoint storage and access wire; counters are not PPA.',
             ha='center',fontsize=9,color='#555555')
    fig.tight_layout(rect=(0,.075,1,1))
    path=Path(output)
    path.parent.mkdir(parents=True,exist_ok=True)
    for extension in ('svg','pdf','png'):
        fig.savefig(path.with_suffix('.'+extension),bbox_inches='tight',dpi=160)
    plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('input')
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    render(args.input,args.output)
