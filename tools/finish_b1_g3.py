"""Read-only scoped B1 G3 finisher; never launch a physical experiment."""
import argparse,gzip,json,time
from pathlib import Path
from collections import Counter

from tools.analyze_b1_mechanism import run as mechanism
from w2w.analysis.moe_mechanism import compare_cases
from w2w.analysis.real_moe import analyze_case
from w2w.analysis.runtime_windows import audit_window_chain
from w2w.validation.context_projections import audit_projection_call
from w2w.architecture.compiler import compile_machine
from w2w.architecture.presets.recipes import from_recipe
from w2w.architecture.llm_deployment import context_catalog,LLMProfile
from w2w.workloads.patterns_adapter import load_corpus,observations
from w2w.serving.batcher import group
from w2w.common.io import write_json
from w2w.workloads.moe_trace import file_sha
from w2w.provenance import revision


def observe(path):
    try:return json.loads(path.read_text())
    except (FileNotFoundError,json.JSONDecodeError):return {}


def worker_identity(pid,study):
    root=Path('/proc')/str(pid)
    try:
        if root.joinpath('stat').read_text().split(') ',1)[1][0]=='Z':return None
        args=[v.decode() for v in root.joinpath('cmdline').read_bytes().split(b'\0') if v]
    except FileNotFoundError:return None
    if 'w2w.experiments.run_real_moe' not in args or 'B1-phase_split' not in args or str(study) not in args:
        raise ValueError('Do not follow a reused/unrelated physical worker PID')
    return args


def projection_readback(root,corpus,output):
    receipt=observe(root/'receipt.json')
    if receipt.get('passed') is not True or receipt.get('context_projection_policy')!='output_sharded':
        raise ValueError('Accepted sharded Native qualification required')
    if file_sha(root/'result.json.gz')!=receipt['result_sha256']:raise ValueError('Qualification result changed')
    capture=next(iter(load_corpus(corpus)))
    if capture['raw_sha256']!=receipt['raw_sha256']:raise ValueError('Qualification capture differs')
    machine=compile_machine(from_recipe('configs/machine/v3-small.json','distributed'))
    catalog=context_catalog(machine,capture['shape'],('0','1'),'up_local',LLMProfile(),context_projection_policy='output_sharded')
    summary=json.load(gzip.open(root/'result.json.gz','rt'));projections=[];cost=Counter()
    def visit(raw,row):
        for layer in ('0','1'):
            batch=group(f'qualification/{row["index"]}/L{layer}',(observations(capture,'prefill',layer)[row['index']],))
            projections.append(audit_projection_call(raw,batch,catalog,f'W{row["index"]:04d}/L{layer}/'))
        for assembly in raw['runtime_metadata']['projection_assemblies']:
            for node in assembly['input_copies']:
                cost['copy_nodes']+=1;spec=raw['npu_execution']['auxiliary'][node['task']]
                for field in ('activation_sram_bytes','output_sram_bytes','vector_ops'):cost['copy_'+field]+=spec[field]
            cost['gather_nodes']+=1;spec=raw['npu_execution']['auxiliary'][assembly['task']]
            for field in ('activation_sram_bytes','output_sram_bytes','vector_ops'):cost['gather_'+field]+=spec[field]
    proof=audit_window_chain(summary,root/'windows',visit=visit)
    if proof!=receipt['proof']:raise ValueError('Independent sharded resource proof differs')
    value=dict(passed=True,analysis_source=revision(),sources={str(p):file_sha(p) for p in (root/'receipt.json',root/'result.json.gz')},
        proof=proof,projection_math=projections,paid_auxiliary_work=dict(cost),
        scope='Independent current full-window resource/projection audits for the first two actual prefill tokens in two true layers. Copy/gather work is paid absolute auxiliary service, not net overhead versus a matched baseline. It qualifies legality, not speedup or complete application serving.')
    write_json(output,value);return value


def reuse_projection_readback(path,qualification,output):
    """Reuse a complete independent readback only for unchanged physical files."""
    value=observe(path);receipt=observe(qualification/'receipt.json')
    expected={str(p):file_sha(p) for p in (qualification/'receipt.json',qualification/'result.json.gz')}
    if (value.get('passed') is not True or receipt.get('passed') is not True
            or value.get('sources')!=expected or value.get('proof')!=receipt.get('proof')
            or receipt.get('context_projection_policy')!='output_sharded'):
        raise ValueError('Independent projection readback does not bind the current qualification')
    write_json(output,value)
    return value


def render_pair(reference,candidate,pair,output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    phases=('prefill','decode');policies=(reference,candidate)
    fig,axes=plt.subplots(1,3,figsize=(12,3.7),constrained_layout=True)
    for p,offset,color,label in zip(policies,(-.18,.18),('#3479a8','#d28429'),('Reference','Phase-Split')):
        axes[0].bar([i+offset for i in range(2)],[p['phases'][f]['execution_latency_ps']/1e9 for f in phases],width=.36,label=label,color=color)
    axes[0].set(xticks=[0,1],xticklabels=['Prefill','Decode'],ylabel='Sum of window completion (ms)');axes[0].legend(fontsize=8)
    decode=[w for w in pair['windows'] if w['phase']=='decode']
    axes[1].plot([w['decode_step'] for w in decode],[w['delta_ps']/1e6 for w in decode],color='#3479a8');axes[1].axhline(0,color='grey',linewidth=.7)
    axes[1].set(xlabel='Original decode step',ylabel='Reference − Phase-Split (µs)',title='Signed per-step benefit; negative retained')
    names=('both_zero_native','both_with_native','mixed_native')
    axes[2].bar(range(3),[pair['phase_and_cache_groups'][n]['delta_ps']/1e9 for n in names],color=['#258256','#d28429','#8665a8'])
    axes[2].axhline(0,color='grey',linewidth=.7);axes[2].set(xticks=range(3),xticklabels=['Both zero','Both read','Mixed'],ylabel='Sum of decode benefit (ms)',title='Matched observed Native-read classes')
    fig.savefig(output/'B1-phase-comparison.png',dpi=180);plt.close(fig)


def run(study,pid,corpus,qualification,reference,shapes,output,projection_readback_path=None):
    output.mkdir(parents=True,exist_ok=False);source=revision();initial=worker_identity(pid,study)
    if initial is None and not observe(study/'cases/B1-phase_split/completion.json').get('complete'):
        raise ValueError('Specific Phase-Split worker ended without a complete result')
    write_json(output/'launch.json',dict(analysis_source=source,phase_worker_pid=pid,phase_worker_args=initial,
        study=str(study),reference_mechanism=str(reference),shape_readback=str(shapes),scope='Only readbacks of frozen B1 Reference/Phase-Split and already executed sharded qualification. No physical launch, retry, source/status mutation or G4/G5 promotion.'))
    try:
        projection=(reuse_projection_readback(projection_readback_path,qualification,output/'sharded-resource-readback.json')
            if projection_readback_path else None)
        while True:
            if projection is None and observe(qualification/'receipt.json').get('passed'):
                projection=projection_readback(qualification,corpus,output/'sharded-resource-readback.json')
            r=observe(reference/'mechanism.json');s=observe(shapes/'receipt.json')
            accepted_reference=observe(study/'cases/B1-reference/analysis.json')
            completion=observe(study/'cases/B1-phase_split/completion.json')
            write_json(output/'status.json',dict(state='waiting_complete_B1',analysis_source=source,
                G3_1=bool(accepted_reference.get('passed')),G3_2=bool(completion.get('complete')),G3_3=bool(projection),
                G3_4=False,G3_5=False,reference_mechanism_ready=bool(r.get('passed')),physical_shape_readback=bool(s.get('passed'))))
            if completion.get('complete') and r.get('passed') and projection and s.get('passed'):break
            if not completion.get('complete') and worker_identity(pid,study)!=initial:
                raise ValueError('Specific Phase-Split worker ended or changed without complete evidence')
            time.sleep(30)
        # Re-audit the entire Phase-Split physical/carry/routing horizon using
        # the existing independent analyzer; preserve the frozen controller files.
        a=analyze_case(study,'B1-phase_split');write_json(output/'phase-split-physical-analysis.json',a)
        c=mechanism(study,'B1-phase_split',output/'phase-split-mechanism',output/'phase-split-physical-analysis.json')
        pair=compare_cases(r,c);write_json(output/'paired-mechanism.json',pair);render_pair(r,c,pair,output)
        value=dict(passed=True,complete_scoped_B1_G3=True,complete_original_12_case_campaign=False,analysis_source=source,
            gates={f'G3.{i}':True for i in range(1,6)},sources={str(p):file_sha(p) for p in (reference/'mechanism.json',shapes/'receipt.json',
                output/'sharded-resource-readback.json',output/'phase-split-physical-analysis.json',output/'phase-split-mechanism/mechanism.json',output/'paired-mechanism.json')},
            signed_phase_and_cache_comparison=pair['phase_and_cache_groups'],
            scope='Only the user-frozen B1 G3 scope is accepted. Both captured phases, actual per-step routes, shape/service budgets, full physical audits and sharded legality are closed. No new hardware, strongest-baseline or full Transformer claim; original B4/16/32 and G4/G5 remain deferred.')
        write_json(output/'receipt.json',value);write_json(output/'status.json',dict(state='complete_scoped_B1_G3',**value))
    except Exception as error:
        write_json(output/'status.json',dict(state='reader_failed',reason=str(error),analysis_source=source,
            physical_jobs_mutated=False,no_automatic_experiment_retry=True));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','corpus','qualification','reference','shapes','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--projection-readback',type=Path)
    p.add_argument('--phase-worker-pid',type=int,required=True);a=p.parse_args()
    run(a.study,a.phase_worker_pid,a.corpus,a.qualification,a.reference,a.shapes,a.output,a.projection_readback)
