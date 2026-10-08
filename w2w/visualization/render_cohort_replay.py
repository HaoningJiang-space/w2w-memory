"""Export paired finite-task changes; inputs must come from frozen replay."""
import argparse
import json
from pathlib import Path


def render(source,output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    result=json.loads(Path(source).read_text())
    labels=('home','k2','wide','c')
    cases=[f'c{g}_b{b}' for g in range(3) for b in (1,4,16)]
    indexed={(r['case'],r['structure']):r['time_reduction_percent'] for r in result['metrics']}
    values=np.array([[indexed[c,s] for c in cases] for s in labels])
    limit=max(1,float(abs(values).max()))
    fig,ax=plt.subplots(figsize=(10,3.4),constrained_layout=True)
    plot=ax.imshow(values,cmap='RdBu',vmin=-limit,vmax=limit,aspect='auto')
    ax.set_xticks(range(9),[f'G{g+1}\nB{b}' for g in range(3) for b in (1,4,16)])
    ax.set_yticks(range(4),['Home','k2','Wide k3','C'])
    for i in range(4):
        for j in range(9):
            ax.text(j,i,f'{values[i,j]:+.1f}%',ha='center',va='center',
                    color='white' if abs(values[i,j])>.6*limit else 'black',fontsize=9)
    ax.set_title('Same hardware: cold-read completion time reduction after frozen cohort mapping',fontsize=11)
    fig.colorbar(plot,ax=ax,label='Time reduction (%)')
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    for ext in ('pdf','svg'):
        fig.savefig(output.with_suffix('.'+ext))
    plt.close(fig)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source');p.add_argument('--output',required=True)
    a=p.parse_args();render(a.source,a.output)
