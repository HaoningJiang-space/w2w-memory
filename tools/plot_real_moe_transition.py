"""Plot an accepted complete case without promoting an unfinished campaign."""
import argparse
import gzip
import json
from collections import Counter
from pathlib import Path
from statistics import median

from w2w.common.io import write_json
from w2w.provenance import revision
from w2w.workloads.moe_trace import file_sha


def render(study,case,output):
    directory=study/'cases'/case
    analysis=directory/'analysis.json';completion=directory/'completion.json';registration=study/'registration.json'
    a=json.loads(analysis.read_text());c=json.loads(completion.read_text());reg=json.loads(registration.read_text())
    choice=reg['cases'][case];cohort=study/'cohorts'/reg['cohorts'][str(choice['B'])]['file'];raw=directory/'result.json.gz'
    sources={str(path):file_sha(path) for path in (analysis,completion,registration,cohort,raw)}
    if (a.get('passed') is not True or c.get('complete') is not True or not a['full_captured_lifecycle']
            or a['case']!=case or (a['B'],a['baseline'])!=(choice['B'],choice['baseline'])
            or a['source_commit']!=c['source_commit'] or a['source_commit']!=reg['source_commit']
            or a['registration_sha256']!=sources[str(registration)] or a['cohort_sha256']!=sources[str(cohort)]
            or a['result_sha256']!=c['result_sha256'] or a['result_sha256']!=sources[str(raw)]):
        raise ValueError('Completed case evidence is missing or belongs to another registration')
    summary=json.load(gzip.open(raw,'rt'));windows=a['windows'];decode=[w for w in windows if w['phase']=='decode']
    if (a['executed_layers']!=reg['layers'] or [w['index'] for w in windows]!=list(range(c['windows']))
            or summary['runtime_windows']['completed_windows']!=len(windows)
            or [w['decode_step'] for w in decode]!=list(range(128))):
        raise ValueError('Complete original decode horizon required for the transition plot')
    count=reg['cohorts'][str(choice['B'])]
    assignments=(count['prefill_tokens']+128*choice['B'])*8*len(reg['layers'])
    if a['token_expert_assignments']!=assignments:raise ValueError('Original captured routing work changed')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    output.mkdir(parents=True,exist_ok=False)
    steps=[w['decode_step'] for w in decode]
    fig,axes=plt.subplots(2,1,figsize=(10,5.5),sharex=True,constrained_layout=True)
    axes[0].plot(steps,[w['duration_ps']/1e6 for w in decode],color='#222222',linewidth=1.3,label='Observed window completion')
    for term,label,color in [('shared_compute_ps','Shared NPU service bound','#2878b5'),
            ('fixed_gateway_assignment_ps','Assigned gateway payload bound','#d57721'),
            ('receiver_write_ps','Receive-write service bound','#8665a8')]:
        axes[0].plot(steps,[w['necessary_service_bounds_ps'][term]/1e6 for w in decode],color=color,linewidth=1,label=label)
    warm=[w for w in decode if w['native_bytes']==0]
    axes[0].scatter([w['decode_step'] for w in warm],[w['duration_ps']/1e6 for w in warm],s=13,color='#258256',zorder=3,label='Zero Native weight reads')
    axes[0].set(yscale='log',ylabel='Time per two-layer window (µs)',
        title=f'{case}: complete original 128-step decode; service bounds overlap')
    axes[0].legend(fontsize=8,ncol=2);axes[0].grid(axis='y',alpha=.2)
    axes[1].bar(steps,[w['native_bytes']/1024**2 for w in decode],color='#d57721',width=.85)
    axes[1].set(xlabel='Original decode step',ylabel='Native weight reads (MiB)',xlim=(-1,128))
    axes[1].grid(axis='y',alpha=.2)
    fig.savefig(output/'decode-transition.png',dpi=180);plt.close(fig)
    def group(rows):
        winners=Counter(max(w['necessary_service_bounds_ps'],key=w['necessary_service_bounds_ps'].get) for w in rows)
        return dict(windows=len(rows),native_bytes=sum(w['native_bytes'] for w in rows),
            median_duration_ps=median(w['duration_ps'] for w in rows) if rows else None,
            largest_necessary_bound_counts=dict(winners))
    write_json(output/'receipt.json',dict(passed=True,analysis_source=revision(),case=case,sources=sources,
        figure_sha256=file_sha(output/'decode-transition.png'),completed_case=True,complete_campaign=False,
        zero_native_decode=group(warm),with_native_decode=group([w for w in decode if w['native_bytes']]),
        scope='Read-only visualization of one accepted full captured lifecycle in two real MoE layers. Existing raw-event audit is reused by hash; this plot performs source bindings, not another raw-event audit. Resource work bounds overlap and cannot be added as stalls or interpreted as counterfactual savings. Other mappings/batches and full Transformer serving remain separate evidence.'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--study',type=Path,required=True);p.add_argument('--case',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();render(a.study,a.case,a.output)
