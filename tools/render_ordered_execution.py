"""Read-only figures from accepted ordered receipts, with explicit P3 horizon."""
import argparse,json
from collections import Counter
from pathlib import Path

from w2w.common.io import write_json
from w2w.provenance import revision
from w2w.workloads.moe_trace import file_sha


def render(ordered,p1,output,require_p3=False):
    output.mkdir(parents=True,exist_ok=False);sources={}
    def accepted(path):
        value=json.loads(path.read_text())
        if value.get('passed') is not True:raise ValueError('Incomplete figure prerequisite: '+str(path))
        sources[str(path)]=file_sha(path);return value
    prior=accepted(p1/'receipt.json');analysis=json.loads((p1/'analysis.json').read_text())
    if file_sha(p1/'analysis.json')!=prior['analysis_sha256']:raise ValueError('P1 analysis changed')
    sources[str(p1/'analysis.json')]=prior['analysis_sha256']
    row=accepted(ordered/'p2a/receipt.json');stream=accepted(ordered/'p2b/receipt.json')
    refs=json.loads((ordered/'p2a/reference.json').read_text())
    if file_sha(ordered/'p2a/reference.json')!=row['reference_sha256']:raise ValueError('Independent numerical/core references changed')
    sources[str(ordered/'p2a/reference.json')]=row['reference_sha256']
    if stream['P2A_receipt_sha256']!=file_sha(ordered/'p2a/receipt.json') or row['P1_receipt_sha256']!=file_sha(p1/'receipt.json'):
        raise ValueError('Figure prerequisites do not form the accepted ordered chain')
    for group,root in ((row['resident_native'],ordered/'p2a'),(stream['rows'],ordered/'p2b')):
        for entry in group:
            if file_sha(root/entry['file'])!=entry['sha256']:raise ValueError('Accepted microkernel raw file changed')
    host=ordered/'p2b/host-index/receipt.json';accepted(host)
    if file_sha(host)!=stream['host_index_equivalence_sha256']:raise ValueError('Host equivalence qualification changed')
    p3=None
    if require_p3 or (ordered/'p3/receipt.json').exists():
        final=accepted(ordered/'receipt.json');p3=accepted(ordered/'p3/receipt.json')
        if not final['complete_all_four_steps'] or final['completed']['p3']['sha256']!=file_sha(ordered/'p3/receipt.json'):
            raise ValueError('Final ordered acceptance missing')
        for name,entry in p3['completed'].items():
            receipt=Path(entry['receipt']);accepted(receipt)
            if file_sha(receipt)!=entry['sha256']:raise ValueError('P3 accepted case receipt changed')
            case=json.loads(receipt.read_text())
            if file_sha(receipt.parent/'result.json.gz')!=case['result_sha256']:raise ValueError('P3 accepted summary changed')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    decode=[w for w in analysis['paired_windows'] if w['phase']=='decode']
    signed=Counter()
    for w in decode:signed.update(w['interval_delta_ps'])
    fig,axes=plt.subplots(1,3,figsize=(12,3.6),constrained_layout=True)
    keys=('eligible_to_admit_ps','admit_to_operands_ps','operands_to_start_ps','start_to_first_grant_ps','first_grant_to_finish_ps')
    axes[0].bar(range(5),[signed[k]/1e9 for k in keys],color='#3479a8')
    axes[0].set(xticks=range(5),xticklabels=['Admission','Operand','Context','First grant','Service'],ylabel='Signed witness difference (ms)',title='Observed positions; no exclusive causes')
    axes[0].tick_params(axis='x',labelrotation=25)
    for offset,policy,color,label in ((-.18,'reference','#3479a8','Reference'),(.18,'phase_split','#d28429','Phase-Split')):
        values=analysis['witness_latest_operand_sources_ps'][policy+'/decode']
        axes[1].bar([offset,1+offset],[values.get(k,0)/1e9 for k in ('native','activation')],width=.35,label=label,color=color)
    axes[1].set(xticks=[0,1],xticklabels=['Native last-ready','Activation last-ready'],ylabel='Witnessed operand interval (ms)');axes[1].legend(fontsize=8)
    axes[2].scatter([w['delta_gateway_bound_ps']/1e6 for w in decode],[w['delta_ps']/1e6 for w in decode],
        c=['#af3a35' if w['delta_ps']<0 else '#3479a8' for w in decode],s=15,alpha=.7)
    axes[2].axhline(0,color='grey',linewidth=.7);axes[2].set(xlabel='Decrease in busiest-Gateway payload bound (µs)',ylabel='Actual signed Decode benefit (µs)',title='All steps; regressions in red')
    fig.savefig(output/'B1-benefit-sources.png',dpi=180);plt.close(fig)
    fig,axes=plt.subplots(1,3,figsize=(12,3.6),constrained_layout=True)
    for axis,kind in zip(axes,('gate','up','down')):
        for policy,color,label in (('best_os','#3479a8','Best legal OS'),('row_auto','#d28429','Paid row mapping')):
            cases=[v for v in refs['cases'] if v['kind']==kind and v['policy']==policy]
            axis.plot([v['M'] for v in cases],[v['plan']['cycles'] for v in cases],'-o',color=color,label=label,markersize=3)
        axis.set(xlabel='Actual expert token count M',ylabel='Paid kernel service cycles',title=kind.capitalize()+'; pinned subgroup reference')
        axis.set_xscale('log',base=2);axis.set_xticks([1,2,4,8,16,32],labels=['1','2','4','8','16','32'])
    axes[0].legend(fontsize=8);fig.savefig(output/'resident-row-shapes.png',dpi=180);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(9,3.6),constrained_layout=True);xs=np.arange(3)
    for shift,field,color,label in ((-.18,'best_os_ps','#3479a8','Best legal OS'),(.18,'streaming_ps','#d28429','Coordinate streaming')):
        axes[0].bar(xs+shift,[v[field]/1e6 for v in stream['comparisons']],width=.36,color=color,label=label)
    axes[0].set(xticks=xs,xticklabels=['Gate','Up','Down'],ylabel='Cold output completion (µs)',ylim=(0,25));axes[0].legend(fontsize=8)
    axes[1].bar(xs-.18,[v['early_start_ps']/1e6 for v in stream['comparisons']],width=.36,label='Earlier context start',color='#d28429')
    axes[1].bar(xs+.18,[v['signed_benefit_ps']/1e6 for v in stream['comparisons']],width=.36,label='Earlier final output',color='#3479a8')
    axes[1].set(xticks=xs,xticklabels=['Gate','Up','Down'],ylabel='Observed difference (µs)',title='Starting early is not finishing early');axes[1].legend(fontsize=8)
    fig.savefig(output/'cold-coordinate-streaming.png',dpi=180);plt.close(fig)
    if p3:
        fig,axes=plt.subplots(1,2,figsize=(10,3.7),constrained_layout=True)
        for placement,color in (('reference','#3479a8'),('phase_split','#d28429'),('up_local','#258256')):
            axes[0].plot([4,16,32],[p3['completed'][f'B{b}-{placement}-best_os']['makespan_ps']/1e9 for b in (4,16,32)],'-o',label=placement,color=color)
        axes[0].set(xlabel='Real independent-request batch B',ylabel='Three-window completion (ms)',title='Every legal OS placement retained');axes[0].legend(fontsize=8)
        for shift,policy,color in ((-.18,'row_auto','#d28429'),(.18,'streaming_os','#3479a8')):
            values=[next(v for v in p3['comparisons'] if v['B']==b and v['policy']==policy) for b in (4,16,32)]
            axes[1].bar(xs+shift,[100*v['signed_benefit_ps']/v['best_os_ps'] for v in values],width=.36,label=policy,color=color)
        axes[1].axhline(0,color='grey',linewidth=.7);axes[1].set(xticks=xs,xticklabels=['4','16','32'],xlabel='Real batch B',ylabel='Signed completion reduction (%)',title='Same strongest measured placement per B');axes[1].legend(fontsize=8)
        fig.suptitle('Conditional captured Decode 0/1/2; empty initial cache, continuous state; true layers 0/1' if p3['horizon']=='selected_windows' else
            'Complete captured Prefill + 128 Decode steps; continuous two-layer MoE',fontsize=10)
        fig.savefig(output/'real-batched-comparison.png',dpi=180);plt.close(fig)
    write_json(output/'receipt.json',dict(passed=True,analysis_source=revision(),complete_all_four_steps=p3 is not None,
        sources=sources,figures={path.name:file_sha(path) for path in output.glob('*.png')},
        scope='Read-only figures of accepted saved cases. Core curves are reference-qualified declared-model programs; M1 resident and cold output times are actual physical fixtures. P3, when present, is only its explicit conditional three-window horizon. Signed regressions retained; no equal-PPA or full Transformer claim.'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('ordered','p1','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--require-p3',action='store_true');a=p.parse_args();render(a.ordered,a.p1,a.output,a.require_p3)
