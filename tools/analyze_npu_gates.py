"""Evidence-only figures and architecture decision; never promote pending runs."""
import argparse,json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from w2w.workloads.moe_trace import file_sha
from w2w.common.io import write_json
from w2w.analysis.energy_edp import threshold


def accepted(path):
    value=json.loads(path.read_text())
    if value.get('passed') is not True:raise ValueError(f'Unaccepted evidence: {path}')
    return value


def render(evidence,output,*,study=None,serving=None,final=False):
    output.mkdir(parents=True,exist_ok=False);d=accepted(evidence/'demand-r2.json');n=accepted(evidence/'npu-reference-r2.json')
    sources={name:file_sha(evidence/name) for name in ('demand-r2.json','npu-reference-r2.json')}
    batches=[int(x) for x in d['decode']];counts=[d['decode'][str(b)]['expert_token_counts'] for b in batches]
    fig,ax=plt.subplots(1,2,figsize=(10,3.5),constrained_layout=True)
    for statistic in ('p50','p90','p99','maximum'):ax[0].plot(batches,[c[statistic] for c in counts],marker='o',label=statistic)
    ax[0].set(xlabel='Batch size',ylabel='Tokens per active expert',title='All 256 captured requests / 94 layers / 128 decode steps');ax[0].legend()
    ax[1].plot(batches,[d['decode'][str(b)]['distinct_experts']['mean'] for b in batches],marker='o')
    ax[1].set(xlabel='Batch size',ylabel='Mean active experts',ylim=(0,128),title='Disjoint source-order cohorts, no dropped requests')
    fig.savefig(output/'fig1-real-demand.png',dpi=180);fig.savefig(output/'fig1-real-demand.pdf');plt.close(fig)
    fig,ax=plt.subplots(1,2,figsize=(10,3.5),constrained_layout=True)
    for array in (16,32):
        for phase in ('gate','down'):
            rows=[r for r in n['kernels'] if r['array_size']==array and r['phase']==phase]
            ax[0].plot([r['M'] for r in rows],[r['plan']['cycles'] for r in rows],marker='o',label=f'{array}×{array}, {phase}')
            ax[1].plot([r['M'] for r in rows],[100*r['logical_macs']/(16384*r['plan']['cycles']) for r in rows],marker='o')
    ax[0].set(xlabel='Actual expert token count M',ylabel='Standalone NPU service cycles',title='Full H=4096 / I=1536; equal 16,384 MAC/cycle');ax[0].legend(fontsize=8)
    ax[1].set(xlabel='Actual expert token count M',ylabel='Useful MAC / peak service capacity (%)',title='Model utilization, not silicon utilization')
    fig.savefig(output/'fig2-shape-efficiency.png',dpi=180);fig.savefig(output/'fig2-shape-efficiency.pdf');plt.close(fig)
    cases=[];pending=[]
    if study:
        registration=json.loads((study/'registration.json').read_text());sources['registration']=file_sha(study/'registration.json')
        for name in registration['cases']:
            path=study/'cases'/name/'analysis.json'
            if path.exists():
                case=accepted(path)
                if case['registration_sha256']!=sources['registration']:raise ValueError('Architecture analysis used another registration')
                cases.append(case);sources[name]=file_sha(path)
            else:pending.append(name)
    if final and (len(cases)!=12 or pending or not serving or not (serving/'serving-results.json').exists()):
        raise ValueError('G5 final decision requires every complete G3 case and complete accepted G4 serving evidence')
    decision=dict(status='awaiting_complete_physical_studies',pending_cases=pending,
        new_hardware_justified=False,reason='Trace/shape evidence alone does not establish a new physical structure or calibrated cost advantage.')
    if len(cases)==12:
        bs=(1,4,16,32);policies=('reference','phase_split','up_local');by={(c['B'],c['baseline']):c for c in cases}
        fig,ax=plt.subplots(1,2,figsize=(10,3.5),constrained_layout=True)
        terms=('fixed_gateway_assignment_ps','native_data_bus_ps','shared_compute_ps','executed_channel_data_lane_ps','receiver_write_ps')
        for t in terms:
            ax[0].plot(bs,[sum(w['necessary_service_bounds_ps'][t] for w in by[b,'up_local']['windows'])/1e9 for b in bs],marker='o',label=t.removesuffix('_ps'))
        ax[0].set(xlabel='Real cohort batch size',ylabel='Sum of window necessary work bounds (ms)',title='Overlapping resource bounds; do not add them');ax[0].legend(fontsize=6)
        ax[1].plot(bs,[by[b,'up_local']['proof']['cache_stats'].get('misses',0) for b in bs],marker='o');ax[1].set(xlabel='Batch size',ylabel='Observed matrix cache misses',title='Complete prefill + 128 decode, two real layers')
        fig.savefig(output/'fig3-memory-compute.png',dpi=180);fig.savefig(output/'fig3-memory-compute.pdf');plt.close(fig)
        fig,ax=plt.subplots(1,3,figsize=(12,3.5),constrained_layout=True)
        for policy in policies:
            cs=[by[b,policy] for b in bs];ax[0].plot(bs,[c['proof']['makespan_ps']/1e9 for c in cs],marker='o',label=policy)
            ax[1].plot(bs,[c['activity_counts']['noc_data_bit_mm']*125/1e12 for c in cs],marker='o')
            ax[2].plot(bs,[c['proof']['native_bytes']/1e9 for c in cs],marker='o')
        for a,y in zip(ax,('Completion (ms)','NoC activity (10¹² byte·µm)','Native read bytes (GB)')):a.set(xlabel='Batch size',ylabel=y)
        ax[0].legend();fig.savefig(output/'fig4-physical-comparison.png',dpi=180);fig.savefig(output/'fig4-physical-comparison.pdf');plt.close(fig)
        sensitivity={}
        for b in bs:
            records={p:dict(counts=by[b,p]['activity_counts'],makespan_ps=by[b,p]['proof']['makespan_ps'],drained_ps=by[b,p]['proof']['drained_ps']) for p in policies}
            sensitivity[str(b)]={p:threshold(records['reference'],records[p]) for p in policies[1:]}
        fig,ax=plt.subplots(figsize=(7,3.5),constrained_layout=True)
        for policy in policies[1:]:ax.plot(bs,[sensitivity[str(b)][policy]['candidate_energy_ratio_limit'] for b in bs],marker='o',label=policy)
        ax.axhline(1,color='grey',linestyle='--');ax.set(xlabel='Batch size',ylabel='Maximum total energy ratio for improved EDP',title='Conditional threshold, no measured energy or area');ax.legend()
        fig.savefig(output/'fig5-hardware-opportunity.png',dpi=180);fig.savefig(output/'fig5-hardware-opportunity.pdf');plt.close(fig)
        decision=dict(status='completed_baseline_screen',new_hardware_justified=False,edp_sensitivity=sensitivity,
            reason='These accepted runs compare legal mappings on unchanged hardware. They cannot prove a new structure outperforms the strongest baseline at equal physical cost. Retain this negative design decision until a calibrated costed intervention is accepted.',
            next_hardware_gate='Identify recoverable dependency latency on completed traces, compare a costed physical intervention with the fastest accepted mapping; exclude Oracle routes and array-model artifacts.')
    if serving and (serving/'serving-results.json').exists():
        full=accepted(serving/'serving-results.json');sources['full_serving']=file_sha(serving/'serving-results.json');decision['conditional_full_serving']=full['proof']
    write_json(output/'decision.json',dict(passed=bool(final and len(cases)==12),completed_trace_analysis=True,completed_shape_reference=True,
        sources=sources,decision=decision,limits=['OS model is conservative, not proof of optimal GEMV/WS mapping','Banking, local fanout and ports are declared, not silicon-calibrated','Routing capture lacks values, scores, vocabulary IDs and arrival times','No calibrated area, total energy, thermal or wafer-yield claim']))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--evidence',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--study',type=Path);p.add_argument('--serving',type=Path);p.add_argument('--final',action='store_true');a=p.parse_args();render(a.evidence,a.output,study=a.study,serving=a.serving,final=a.final)
