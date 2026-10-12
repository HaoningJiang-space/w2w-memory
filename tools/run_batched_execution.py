"""P3: pre-registered real batches, best legal placement baseline, paid policies."""
import argparse,gzip,json,os,shutil,subprocess,sys,time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from w2w.architecture.compiler import compile_machine
from w2w.architecture.npu_profile import reference_profile
from w2w.architecture.presets.recipes import from_recipe
from w2w.architecture.resources import inventory
from w2w.backends.booksim.adapter import factory
from w2w.backends.ramulator import VerticalRWDL
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.common.io import write_json
from w2w.domain.execution import ControlEdge,DataEdge,ExecutionGraph
from w2w.experiments.run_real_moe import paired_batches
from w2w.mapping.moe_batch_lowering import BASELINES,full_catalog,lower_batch
from w2w.provenance import revision
from w2w.serving.batcher import group
from w2w.system.kernel import execute_system
from w2w.system.operand_streaming import StreamingKernelModel,reprogram_streaming_graph
from w2w.system.row_mapping import RowMappingKernelModel,reprogram_graph
from w2w.system.runtime_windows import RuntimeWindows
from w2w.system.weight_cache import WeightCacheConfig
from w2w.validation.moe_runtime import audit_moe_call
from w2w.workloads.patterns_adapter import observations
from w2w.workloads.moe_trace import file_sha


def batches(cohort,horizon):
    if horizon=='complete_request':yield from paired_batches(cohort,('0','1'),32);return
    if horizon!='selected_windows':raise ValueError('Unknown actual trace horizon')
    for step in (0,1,2):
        yield tuple(group(f'decode/S{step}/L{layer}',tuple(observations(c,'decode',layer,step)[0] for c in cohort)) for layer in ('0','1'))


def windows(cohort,machine,catalog,p,policy,horizon):
    for index,calls in enumerate(batches(cohort,horizon)):
        tasks=[];data=[];control=[];kernels={};aux={};metadata=[];previous=[]
        for batch in calls:
            prefix=f'W{index:04d}/L{batch.layer_id}/'
            graph,ks,meta=lower_batch(batch,machine,catalog,p,prefix=prefix)
            if policy=='streaming_os':graph=reprogram_streaming_graph(graph,ks,p)
            else:graph=reprogram_graph(graph,ks,p,policy)
            inputs=[prefix+f't{t}/input' for t in range(batch.token_count)]
            if previous:
                control.extend(ControlEdge(a,b) for a in previous for b in inputs)
                data.extend(DataEdge(prefix+f'layer_activation/{t}',a,b,catalog['shape']['hidden']*2) for t,(a,b) in enumerate(zip(previous,inputs)))
            tasks.extend(graph.tasks);data.extend(graph.data);control.extend(graph.control);kernels.update(ks);aux.update(meta['auxiliary'])
            metadata.append({k:meta[k] for k in ('batch_id','layer_id','token_ids','token_to_experts','expert_token_counts','expert_macs',
                'router_macs','router_vector_ops','finish_tasks','router_visibility','scratch_policy')})
            previous=meta['finish_tasks']
        graph=ExecutionGraph(tuple(tasks),catalog['objects'],tuple(data),tuple(control))
        yield graph,kernels,dict(index=index,calls=metadata,npu_kernels={k:asdict(v) for k,v in kernels.items()},auxiliary=aux,
            expert_macs=sum(c['expert_macs'] for c in metadata),router_macs=sum(c['router_macs'] for c in metadata))


def run_case(root,case,binary):
    reg=json.loads((root/'registration.json').read_text());choice=reg['cases'][case]
    if revision()!=reg['source_commit']:raise ValueError('P3 frozen source changed')
    for path,sha in reg['prerequisites'].items():
        if file_sha(Path(path))!=sha:raise ValueError('P3 qualification changed')
    cohort_path=Path(reg['cohorts'][str(choice['B'])]['path'])
    if file_sha(cohort_path)!=reg['cohorts'][str(choice['B'])]['sha256']:raise ValueError('Original real cohort changed')
    cohort=json.load(gzip.open(cohort_path,'rt'));machine=compile_machine(from_recipe('configs/machine/v3-small.json','distributed'));p=reference_profile()
    if len(cohort)!=choice['B']:raise ValueError('Actual independent-request batch size differs')
    if digest(asdict(machine))!=reg['machine_sha256'] or asdict(p)!=reg['profile']:raise ValueError('P3 resource budget changed')
    catalog=full_catalog(machine,reg['shape'],('0','1'),choice['placement']);directory=root/'cases'/case;directory.mkdir(parents=True,exist_ok=False)
    producer=iter(windows(cohort,machine,catalog,p,choice['policy'],reg['horizon']));graph,kernels,meta=next(producer)
    source=RuntimeWindows(directory/'windows',producer,meta)
    model=StreamingKernelModel(p,kernels,auxiliary=meta['auxiliary']) if choice['policy']=='streaming_os' else RowMappingKernelModel(p,kernels,policy=choice['policy'],auxiliary=meta['auxiliary'])
    native=VerticalRWDL(machine,request_control=True,refresh=True,gateway_trace_bin_ps=1000000);start=time.monotonic()
    try:
        result=execute_system(machine,graph,native=native,network_factory=factory(binary=binary,directory=directory/'network',
            ready_router_ids=tuple(r.id for r in machine.routers),ready_slots=16),max_ps=2000000000000,time_advance='boundaries',
            compute_contexts=2,fetch_contexts=2,read_issue_policy='round_robin',weight_cache=WeightCacheConfig(),
            operand_readiness='contiguous_prefix',activation_sram_read_bytes_per_cycle=machine.rx_write_bytes_per_cycle,
            npu_model=model,window_source=source,indexed_admission=True)
    finally:native.close()
    result.update(source_commit=reg['source_commit'],case=case,registration_sha256=file_sha(root/'registration.json'))
    path=directory/'result.json.gz'
    with gzip.open(path,'wt') as f:json.dump(result,f)
    write_json(directory/'completion.json',dict(complete=True,makespan_ps=result['makespan_ps'],drained_ps=result['drained_ps'],
        windows=len(source.rows),wall_seconds=time.monotonic()-start,result_sha256=file_sha(path),source_commit=reg['source_commit']))
    expected=iter(batches(cohort,reg['horizon']));calls_seen=0;histogram=Counter()
    def visit(raw,row):
        nonlocal calls_seen
        wanted=next(expected,None)
        if wanted is None:raise ValueError('P3 executed extra or fabricated windows')
        if len(wanted)!=len(raw['runtime_metadata']['calls']):raise ValueError('P3 added or omitted a layer invocation')
        if (digest(raw['spec'])!=reg['machine_sha256'] or raw['npu_execution']['profile']!=reg['profile']
                or digest(raw['graph']['objects'])!=digest([asdict(o) for o in catalog['objects']])):
            raise ValueError('P3 physical resources or independent two-layer catalog changed')
        for batch,meta in zip(wanted,raw['runtime_metadata']['calls']):
            if meta['layer_id']!=batch.layer_id or meta['batch_id']!=batch.id:raise ValueError('P3 original layer/batch identity changed')
            if list(map(list,(o.expert_ids for o in batch.observations)))!=meta['token_to_experts'] or [list(o.token_id) for o in batch.observations]!=meta['token_ids']:
                raise ValueError('P3 route/token identities changed')
            if sum(meta['expert_token_counts'].values())!=8*batch.token_count:raise ValueError('Batched expert grouping lost assignments')
            audit_moe_call(raw,batch,f'W{row["index"]:04d}/L{batch.layer_id}/')
            for M in meta['expert_token_counts'].values():histogram[M]+=1
            calls_seen+=1
    from w2w.analysis.runtime_windows import audit_window_chain
    proof=audit_window_chain(result,directory/'windows',visit=visit)
    if next(expected,None) is not None:raise ValueError('P3 selected horizon was truncated')
    target=sum(1 for _ in batches(cohort,reg['horizon']))
    if proof['windows']!=target or calls_seen!=2*target:raise ValueError('P3 horizon incomplete')
    write_json(directory/'receipt.json',dict(passed=True,source_commit=revision(),registration_sha256=file_sha(root/'registration.json'),
        result_sha256=file_sha(path),B=choice['B'],placement=choice['placement'],policy=choice['policy'],proof=proof,
        expert_M_histogram=dict(histogram),window_times_ps=[w['makespan_ps']-w['begin_ps'] for w in source.rows],
        scope=reg['scope']))


def coordinate(output,study,p2a,p2b,binary,horizon):
    prereqs={str(path.resolve()):file_sha(path) for path in (p2a,p2b)}
    for path in (p2a,p2b):
        if json.loads(path.read_text()).get('passed') is not True:raise ValueError('P3 requires independent completed P2-A/B')
    streaming=json.loads(p2b.read_text());index_receipt=p2b.parent/'host-index/receipt.json'
    if (not streaming['host_index_equivalence']['passed'] or streaming['source_commit']!=revision()
            or file_sha(index_receipt)!=streaming['host_index_equivalence_sha256']):
        raise ValueError('P3 requires exact physical-event qualification of host indexing at the frozen source')
    prereqs[str(index_receipt.resolve())]=file_sha(index_receipt)
    output.mkdir(parents=True,exist_ok=False);(output/'cases').mkdir();old=json.loads((study/'registration.json').read_text())
    machine=compile_machine(from_recipe('configs/machine/v3-small.json','distributed'));p=reference_profile();cohorts={};cases={}
    for B in (4,16,32):
        original=study/'cohorts'/old['cohorts'][str(B)]['file']
        if file_sha(original)!=old['cohorts'][str(B)]['sha256']:raise ValueError('Nested original cohort changed')
        cohorts[str(B)]=dict(path=str(original),sha256=file_sha(original),request_ids=old['cohorts'][str(B)]['request_ids'])
        for placement in BASELINES:
            for policy in ('best_os','row_auto','streaming_os'):
                cases[f'B{B}-{placement}-{policy}']=dict(B=B,placement=placement,policy=policy)
    scope=('Complete captured prefill and all 128 Decode steps in two true layers.' if horizon=='complete_request' else
        'Pre-registered first three consecutive captured Decode steps (0/1/2), all actual B4/16/32 tokens and two true layers. Initial cache is explicitly empty; cache/Native/NoC state persists inside this conditional episode. Captured input activations are unavailable and modeled at the boundary. No claim of original post-prefill residency, full request or Transformer timing.')
    write_json(output/'registration.json',dict(source_commit=revision(),horizon=horizon,profile=asdict(p),machine_sha256=digest(asdict(machine)),
        resources=inventory(machine.stack),cache=asdict(WeightCacheConfig()),prerequisites=prereqs,shape=old['shape'],cohorts=cohorts,cases=cases,
        sampling='Before new performance: nested original B cohorts; selected horizon is steps 0/1/2, not performance-selected samples.',scope=scope,
        placement_selection='All three legal best-OS placements measured for each B. Row/stream comparisons use the fastest measured best-OS placement, retaining all baseline and negative results.',
        hardware_cost='Aggregate resources fixed. Row steering/word/scale state and streaming ROM/probes paid as declared; no equal-PPA assumption.',
        host_concurrency=2,host_optimization='Same qualified indexed admission in every case; unchanged physical lexical ordering and resources.'))
    complete={};start=time.monotonic()
    def execute_cases(names):
        queue=list(names);live={};handles=[]
        try:
            while queue or live:
                while queue and len(live)<2:
                    if shutil.disk_usage(output).free<60*1024**3:raise RuntimeError('Preserve evidence: P3 filesystem headroom below 60 GiB')
                    name=queue.pop(0);log=(output/(name+'.log')).open('xb');handles.append(log)
                    proc=subprocess.Popen([sys.executable,'-m','tools.run_batched_execution','--output',str(output),'--case',name,
                        '--booksim-binary',str(binary)],stdout=log,stderr=subprocess.STDOUT)
                    live[name]=proc
                for name,proc in list(live.items()):
                    code=proc.poll()
                    if code is None:continue
                    if code:raise RuntimeError(f'P3 case {name} failed ({code}); no automatic retry')
                    path=output/'cases'/name/'receipt.json';value=json.loads(path.read_text())
                    if not value.get('passed'):raise ValueError('P3 independent case audit missing')
                    complete[name]=dict(receipt=str(path),sha256=file_sha(path),makespan_ps=value['proof']['makespan_ps']);del live[name]
                write_json(output/'status.json',dict(state='running',completed=complete,live={n:p.pid for n,p in live.items()},queued=queue,wall_seconds=time.monotonic()-start))
                if queue or live:time.sleep(10)
        except Exception:
            for proc in live.values():
                if proc.poll() is None:proc.terminate()
            raise
        finally:
            for log in handles:log.close()
    try:
        execute_cases([f'B{B}-{placement}-best_os' for B in (4,16,32) for placement in BASELINES])
        selected={}
        for B in (4,16,32):
            selected[str(B)]=min(BASELINES,key=lambda placement:(complete[f'B{B}-{placement}-best_os']['makespan_ps'],placement))
        write_json(output/'baseline-selection.json',dict(passed=True,selected=selected,all_measured_baselines=complete.copy()))
        execute_cases([f'B{B}-{selected[str(B)]}-{policy}' for B in (4,16,32) for policy in ('row_auto','streaming_os')])
        comparisons=[]
        for B in (4,16,32):
            placement=selected[str(B)];base=complete[f'B{B}-{placement}-best_os']['makespan_ps']
            for policy in ('row_auto','streaming_os'):
                case=f'B{B}-{placement}-{policy}';value=json.loads(Path(complete[case]['receipt']).read_text());t=value['proof']['makespan_ps']
                comparisons.append(dict(B=B,placement=placement,policy=policy,best_os_ps=base,candidate_ps=t,signed_benefit_ps=base-t,
                    completion_reduction_fraction=(base-t)/base,expert_M_histogram=value['expert_M_histogram'],native_bytes=value['proof']['native_bytes'],
                    reload_bytes=value['proof']['cache_stats'].get('reload_bytes',0)))
        value=dict(passed=True,source_commit=revision(),horizon=horizon,scope=scope,registration_sha256=file_sha(output/'registration.json'),
            completed=complete,selected=selected,comparisons=comparisons,wall_seconds=time.monotonic()-start,
            accepted_cases=len(complete),original_27_registered_policy_cases_executed=False,
            contract='Nine legal placement baselines plus six matched policy cases; all selected horizon windows independently audited. Best baseline selection and all signed regressions retained. This validates the recorded trace episode, not unexecuted full lifecycle or equal-PPA novelty.')
        write_json(output/'receipt.json',value);write_json(output/'status.json',dict(state='complete',**value))
    except Exception as error:
        write_json(output/'status.json',dict(state='failed',reason=str(error),completed=complete,no_automatic_retry=True));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--case')
    parser.add_argument('--study',type=Path);parser.add_argument('--p2a-receipt',type=Path);parser.add_argument('--p2b-receipt',type=Path)
    parser.add_argument('--booksim-binary',type=Path,required=True);parser.add_argument('--horizon',choices=('selected_windows','complete_request'),default='selected_windows')
    args=parser.parse_args()
    if args.case:run_case(args.output,args.case,args.booksim_binary)
    else:
        if not all((args.study,args.p2a_receipt,args.p2b_receipt)):parser.error('Original cohort and P2 receipts required')
        coordinate(args.output,args.study,args.p2a_receipt,args.p2b_receipt,args.booksim_binary,args.horizon)
