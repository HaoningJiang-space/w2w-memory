import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    d=json.loads(Path('artifacts/results/endpoint/endpoint_bridge_results.json').read_text())
    depths=[0,1,2,8];x=list(range(4))
    fig,axes=plt.subplots(1,3,figsize=(13,4))
    def row(bits,depth,scenario,policy='round_robin'):
        return next(r for r in d['wafer'] if (r['bits'],r['depth'],r['scenario'],r['policy'])==(bits,depth,scenario,policy))
    for bits,color in [(128,'#d97706'),(192,'#2563eb'),(256,'#15803d')]:
        mean=[(27*row(bits,v,'single')['executed_tb_s']+8*row(bits,v,'one_pair')['executed_tb_s'])/35 for v in depths]
        axes[0].plot(x,mean,'o-',color=color,label=f'alpha = {bits/256:g}')
        axes[1].plot(x,[row(bits,v,'full')['executed_tb_s'] for v in depths],'o-',color=color)
    for policy,color in [('round_robin','#2563eb'),('ordered','#d97706')]:
        values=[next(r['total_per_native'] for r in d['micro'] if
                    (r['output_bits'],r['depth'],len(r['active']),r['policy'])==(128,v,2,policy)) for v in depths]
        axes[2].plot(x,values,'o-',label=policy.replace('_',' '),color=color)
    for ax in axes:
        ax.set_xticks(x,depths);ax.set_xlabel('Word slots per output (0 = direct)');ax.grid(alpha=.2)
    axes[0].set_title('Exact random 9-of-36 expectation');axes[0].set_ylabel('TB/s per active compute');axes[0].legend()
    axes[1].set_title('All 36 compute active');axes[1].set_ylabel('TB/s per compute')
    axes[2].set_title('Two busy outputs, alpha = 0.5');axes[2].set_ylabel('Completed service / native bank rate');axes[2].legend()
    fig.suptitle('Same geometry and static pairs; explicit complete-word endpoint execution',fontsize=13)
    fig.tight_layout(rect=(0,.06,1,.94))
    fig.text(.5,.01,'Specified digital model, not measured DRAM. Ordered policy uses eight-word destination bursts.\n'
        'Depth includes active serialization storage; direct still has one shared word register.',ha='center',fontsize=9)
    out=Path('artifacts/figures/endpoint_bridge');out.mkdir(parents=True,exist_ok=True)
    plt.rcParams['svg.fonttype']='none'
    fig.savefig(out/'execution.svg',bbox_inches='tight');fig.savefig(out/'execution.png',dpi=160,bbox_inches='tight')


if __name__ == '__main__':
    main()
