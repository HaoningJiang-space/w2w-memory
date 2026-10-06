"""Create a static scientific comparison from recorded experiment results."""
import argparse
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def summarize(path):
    data=json.loads(Path(path).read_text()); out=Path(path).parent
    records=data['records']; summaries=[]
    for diameter in (200,300):
        fig,axes=plt.subplots(1,2,figsize=(12,4.8),sharey=True,layout='constrained')
        workloads=['single_center','random_0.25','clustered_quarter','random_0.5','full']
        for ax,mode in zip(axes,['partitioned','pooled']):
            for method,label,color in [('aligned','Aligned','#3d5a80'),('half_shifted_x','Half shift X','#ee9b00'),('half_shifted','Half shift XY','#ae2012')]:
                means=[];lo=[];hi=[]
                for workload in workloads:
                    rows=[r for r in records if r['diameter_mm']==diameter and r['method']==method
                          and r['bank_mode']==mode and r['hb_tb_s']==4 and r['controller_tb_s']==4
                          and r['pool_port_fraction']==1 and r['workload']==workload and r['objective']=='throughput']
                    vals=[r['total_tb_s']/r['active'] for r in rows]
                    means.append(float(np.mean(vals)));lo.append(min(vals));hi.append(max(vals))
                    summaries.append(dict(diameter_mm=diameter,bank_mode=mode,method=method,workload=workload,
                                          mean_tb_s_per_active=means[-1],min_tb_s_per_active=lo[-1],max_tb_s_per_active=hi[-1],
                                          mean_total_tb_s=float(np.mean([r['total_tb_s'] for r in rows]))))
                ax.plot(range(5),means,'o-',label=label,color=color)
                ax.fill_between(range(5),lo,hi,color=color,alpha=.12)
            ax.set_title('Local bank groups' if mode=='partitioned' else 'Ideal all-bank access per port')
            ax.set_xticks(range(5),['One\ncompute','Random\n25%','Clustered\n25%','Random\n50%','All\ncompute'])
            ax.set_ylim(0,4.3);ax.grid(axis='y',alpha=.2);ax.legend(fontsize=9)
        axes[0].set_ylabel('Service upper bound per active compute (TB/s)')
        fig.suptitle(f'{diameter} mm: equal counts and endpoint budgets\nHB = controller = 4 TB/s; DRAM = 1 TB/s per memory reticle',fontsize=12)
        fig.savefig(out/f'comparison_{diameter}.png',dpi=180);fig.savefig(out/f'comparison_{diameter}.svg');plt.close(fig)
    (out/'summary.json').write_text(json.dumps(dict(provenance=data['provenance'],rows=summaries),indent=2))
    print('Figures and summary written to',out)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('input');a=p.parse_args();summarize(a.input)
