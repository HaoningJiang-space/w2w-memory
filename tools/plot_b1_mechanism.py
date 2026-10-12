"""Plot an accepted B1 event-mechanism readback without running a simulation."""
import argparse,json
from pathlib import Path

from w2w.common.io import write_json
from w2w.workloads.moe_trace import file_sha
from w2w.provenance import revision
from w2w.analysis.moe_mechanism import INTERVALS


def run(source,output):
    value=json.loads(source.read_text())
    if value.get('passed') is not True or value['case']!='B1-reference':
        raise ValueError('Accepted original B1 Reference mechanism required')
    decode=[r for r in value['windows'] if r['phase']=='decode']
    if [r['decode_step'] for r in decode]!=list(range(128)):
        raise ValueError('All original decode steps required')
    output.mkdir(parents=True,exist_ok=False)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(3,1,figsize=(11,8),constrained_layout=True)
    colors=['#3c6fa1','#d78530','#7c68a6','#b45a66','#398b70']
    x=[r['decode_step'] for r in decode]
    for native,label,color in ((False,'Zero Native weight reads','#3c6fa1'),(True,'With Native weight reads','#d78530')):
        chosen=[r for r in decode if bool(r['native_bytes'])==native]
        axes[0].scatter([r['decode_step'] for r in chosen],[r['duration_ps']/1e6 for r in chosen],s=16,label=label,color=color)
    axes[0].set(ylabel='Window completion (µs)',title='Actual two-layer Decode windows');axes[0].legend(fontsize=8)
    axes[1].bar(x,[r['native_bytes']/1e6 for r in decode],color='#d78530',width=.85,label='All gateways')
    axes[1].plot(x,[r['maximum_gateway_bytes']/1e6 for r in decode],color='#3c6fa1',linewidth=.9,label='Most loaded gateway')
    axes[1].set(ylabel='Native payload (MB)',title='Observed supply work; overlaps other service');axes[1].legend(fontsize=8)
    bottom=[r['completion_witness']['initial_release_ps']/1e6 for r in decode]
    labels=('Eligible → admission','Admission → operands','Operands → context start','Start → first grant','First grant → finish')
    for key,label,color in zip(INTERVALS,labels,colors):
        heights=[r['completion_witness']['interval_totals_ps'][key]/1e6 for r in decode]
        axes[2].bar(x,heights,bottom=bottom,width=.85,label=label,color=color)
        bottom=[a+b for a,b in zip(bottom,heights)]
    axes[2].set(xlabel='Original Decode step',ylabel='Witnessed chain time (µs)',title='One nonoverlapping completion witness per window')
    axes[2].legend(fontsize=7,ncol=3,loc='upper right')
    for ax in axes:ax.set_xlim(-1,128)
    fig.savefig(output/'B1-reference-mechanism.png',dpi=180);plt.close(fig)
    receipt=dict(passed=True,analysis_source=revision(),source_sha256=file_sha(source),figure_sha256=file_sha(output/'B1-reference-mechanism.png'),
        scope='Pure plot of the accepted 130-window event-mechanism readback. Supply work is observed traffic; witnessed intervals reconstruct elapsed time without summing parallel tasks. No exclusive bottleneck or recoverable-stall attribution.')
    write_json(output/'receipt.json',receipt);return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.source,a.output)
