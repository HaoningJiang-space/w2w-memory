"""Complete captured 94-layer serving replay on explicit replicated V3 stages.

All stack execution uses the existing SystemExecution/Ramulator/BookSim kernel.
The serving coordinator passes completed activation/link tickets, not estimated
layer times. Missing values/arrivals/embedding IDs are separate stated models.
"""
import argparse,fcntl,gzip,json,os,subprocess,sys,time
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from w2w.architecture.presets.recipes import from_recipe
from w2w.architecture.compiler import compile_machine
from w2w.architecture.npu_profile import reference_profile
from w2w.architecture.llm_deployment import LLMProfile,context_catalog,deployment
from w2w.workloads.patterns_adapter import load_corpus
from w2w.workloads.moe_trace import file_sha
from w2w.experiments.run_real_moe import select_cohort,paired_batches
from w2w.mapping.llm_context import lower_context
from w2w.mapping.llm_boundary import add_boundaries
from w2w.domain.execution import ExecutionGraph,DataEdge,ControlEdge
from w2w.system.kv_runtime import KVRuntimeWindows
from w2w.serving.requests import ServingRequest,RequestLifecycle
from w2w.serving.pipeline import PipelineLinks
from w2w.common.io import write_json
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.provenance import revision


def atomic(path,value):
    path=Path(path);temp=path.with_suffix(f'.{os.getpid()}.tmp');write_json(temp,value);temp.replace(path)


def ticket(root,stage,index):return root/'tickets'/f's{stage:02d}-w{index:04d}.json'


def await_ticket(root,stage,index):
    path=ticket(root,stage,index)
    while not path.exists():
        if (root/'stop.json').exists():raise RuntimeError('Serving coordinator stopped, no forced completion')
        time.sleep(1)
    value=json.loads(path.read_text())
    if index:
        ack=root/'notices'/f'ack-s{stage:02d}-w{index-1:04d}.json'
        while not ack.exists():
            if (root/'stop.json').exists():raise RuntimeError('Serving coordinator stopped')
            time.sleep(1)
        value['committed_ps']=max(value['committed_ps'],json.loads(ack.read_text())['source_release_ps'])
    return value,file_sha(path)


class ServingWindows(KVRuntimeWindows):
    def __init__(self,*args,study,stage,slot,**kwargs):
        super().__init__(*args,**kwargs);self.study=study;self.stage=stage;self.slot=slot

    def start(self,e):
        super().start(e)
        # Explicit external double buffers consume existing SRAM.
        extra=2*32*self.catalog['llm_profile']['hidden']*2+2*64*16
        self.reserved['c15']+=extra;e._sram('c15',extra,'kv-residency')

    def checkpoint(self,e,makespan,quantum,advance):
        super().checkpoint(e,makespan,quantum,advance)
        row=self.rows[-1];meta=self.metadata
        atomic(self.study/'notices'/f's{self.stage:02d}-w{row["index"]:04d}.json',dict(stage=self.stage,index=row['index'],
            makespan_ps=makespan,drained_ps=e.now,window_sha256=row['sha256'],decoded_sha256=row['decoded_sha256'],
            input_ticket_sha256=meta['input_ticket_sha256'],release_ps=meta['release_ps'],heads=meta['heads'],
            phase=meta['calls'][0]['phase'],decode_step=meta['calls'][0]['decode_step'],
            tokens=len(meta['calls'][0]['token_ids'])))
        fcntl.flock(self.slot,fcntl.LOCK_UN);self.slot.close();self.slot=None

    def final_boundary(self,now):
        path=self.study/'notices'/f'ack-s{self.stage:02d}-w{len(self.rows)-1:04d}.json'
        while not path.exists():
            if (self.study/'stop.json').exists():raise RuntimeError('Output transmission was interrupted')
            time.sleep(1)
        return max(now,json.loads(path.read_text())['source_release_ps'])


def acquire_slot(root):
    while True:
        for i in range(2):
            f=(root/f'worker-slot-{i}.lock').open('a')
            try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);return f
            except BlockingIOError:f.close()
        if (root/'stop.json').exists():raise RuntimeError('Serving study stopped')
        time.sleep(1)


def prepare(root,corpus,config,B,gate_receipts,context_projection_policy='whole_matrix_local'):
    captures=tuple(load_corpus(corpus));cohort=select_cohort(captures,B);p=LLMProfile.from_config(json.loads(config.read_text()))
    machine=compile_machine(from_recipe('configs/machine/v3-small.json','distributed'));plan=deployment(machine,cohort[0]['shape'],p,
        context_projection_policy=context_projection_policy)
    for receipt in gate_receipts:
        if json.loads(receipt.read_text()).get('passed') is not True:raise ValueError('Full LLM requires accepted NPU/context gates')
    if len(gate_receipts)<6:raise ValueError('Shape/compute/Native/carry/equivalence/context gates required')
    if not any(json.loads(x.read_text()).get('mode')=='idle-boundary' for x in gate_receipts):
        raise ValueError('Full deployed stages require a passed inactive-release Native/BookSim event equivalence receipt')
    root.mkdir(parents=True,exist_ok=False)
    for name in ('tickets','notices','stages'):(root/name).mkdir()
    with gzip.open(root/'cohort.json.gz','wt') as f:json.dump(cohort,f)
    write_json(root/'deployment.json',plan)
    windows=list(paired_batches(cohort,('0','1'),32));schedule=[]
    for index,batches in enumerate(windows):
        b=batches[0];schedule.append(dict(index=index,phase=b.observations[0].phase,decode_step=b.observations[0].decode_step,tokens=b.token_count))
    write_json(root/'registration.json',dict(schema='w2w.full-llm-serving-study.v1',source_commit=revision(),B=B,
        cohort_sha256=file_sha(root/'cohort.json.gz'),model_config_sha256=file_sha(config),deployment_sha256=file_sha(root/'deployment.json'),
        gate_receipts=[dict(path=str(x.resolve()),sha256=file_sha(x)) for x in gate_receipts],schedule=schedule,
        windows=len(schedule),profile=asdict(p),machine_sha256=digest(asdict(machine)),shape=cohort[0]['shape'],
        npu_profile=asdict(reference_profile()),baseline='up_local',context_projection_policy=context_projection_policy,prefill_microbatch=32,max_ps=100000000000000,
        embedding_address_policy='Modeled SHA256(request_id,phase,token_position,decode_step) modulo vocabulary; never presented as captured token IDs.',
        arrivals='Modeled simultaneous admission at zero; prompt lengths use captured prefill row count as a declared assumption.',
        request_completion='Captured prefill plus all 128 decode steps over all 94 real layers, not EOS/text validation.',
        scope='Conditional mixed-fidelity serving: full local Native/NPU/NoC execution, materialized GQA and finite SRAM KV; declared point-to-point inter-stack ports. No calibrated silicon/numerical LLM claim.'))


def stage_run(root,stage,binary):
    from w2w.backends.ramulator import VerticalRWDL
    from w2w.backends.booksim.adapter import factory
    from w2w.system.kernel import execute_system
    from w2w.system.npu_kernel import NPUKernelModel
    from w2w.system.weight_cache import WeightCacheConfig
    reg=json.loads((root/'registration.json').read_text());plan=json.loads((root/'deployment.json').read_text())
    if revision()!=reg['source_commit'] or file_sha(root/'deployment.json')!=reg['deployment_sha256'] or file_sha(root/'cohort.json.gz')!=reg['cohort_sha256']:
        raise ValueError('Frozen complete serving deployment/cohort changed')
    cohort=tuple(json.load(gzip.open(root/'cohort.json.gz','rt')));p=LLMProfile(**reg['profile'])
    machine=compile_machine(from_recipe('configs/machine/v3-small.json','distributed'));npu=reference_profile();description=plan['stages'][stage]
    catalog=context_catalog(machine,reg['shape'],tuple(description['layers']),reg['baseline'],p,
        embedding=description['embedding'],head=description['lm_head'],context_projection_policy=reg.get('context_projection_policy','whole_matrix_local'))
    if digest([asdict(o) for o in catalog['objects']])!=description['catalog_sha256']:raise ValueError('Resident full model catalog changed')
    directory=root/'stages'/f's{stage:02d}';directory.mkdir(exist_ok=False);holder={};state={}
    def producer():
        for index,batches in enumerate(paired_batches(cohort,catalog['layers'],reg['prefill_microbatch'])):
            incoming,hash_=await_ticket(root,stage,index);slot=acquire_slot(root)
            tasks=[];data=[];control=[];kernels={};aux={};calls=[];appends=[];reads=[];groups=[];previous=[];inputs=[];assemblies=[]
            for batch in batches:
                prefix=f'W{index:04d}/L{batch.layer_id}/'
                g,k,m=lower_context(batch,machine,catalog,npu,state,prefix=prefix);current=m['context_input'];inputs.append(current)
                if previous:
                    for task in previous:control.append(ControlEdge(task,current))
                    for t,task in enumerate(previous):data.append(DataEdge(prefix+f'layer_activation/{t}',task,current,2*p.hidden))
                tasks.extend(g.tasks);data.extend(g.data);control.extend(g.control);kernels.update(k);aux.update(m['auxiliary'])
                appends.extend(m['kv_appends']);reads.extend(m['kv_reads']);previous=m['finish_tasks']
                groups.extend(dict(g,layer=batch.layer_id) for g in m['attention_groups'])
                assemblies.extend(m.get('projection_assemblies',()))
                call={key:m[key] for key in ('batch_id','layer_id','token_ids','token_to_experts','expert_token_counts','expert_macs','router_macs')}
                call.update(phase=batch.observations[0].phase,decode_step=batch.observations[0].decode_step);calls.append(call)
            meta=dict(index=index,calls=calls,context_inputs=inputs,finish_tasks=previous,auxiliary=aux,kv_appends=appends,kv_reads=reads,attention_groups=groups,
                input_ticket_sha256=hash_,release_ps=incoming['committed_ps'])
            if assemblies:meta['projection_assemblies']=assemblies
            g=ExecutionGraph(tuple(tasks),catalog['objects'],tuple(data),tuple(control))
            g,k,meta=add_boundaries(g,kernels,meta,batches,catalog,machine,npu,cohort,index=index,stage=stage,release_ps=incoming['committed_ps'])
            if 'source' in holder:holder['source'].slot=slot
            else:holder['first_slot']=slot
            yield g,k,meta
    gen=producer();graph,kernels,metadata=next(gen)
    source=ServingWindows(directory/'windows',gen,metadata,catalog,[c['request_id'] for c in cohort],
        study=root,stage=stage,slot=holder.pop('first_slot'));source.lengths=state;holder['source']=source
    native=VerticalRWDL(machine,request_control=True,refresh=True,gateway_trace_bin_ps=1000000);start=time.monotonic()
    try:r=execute_system(machine,graph,native=native,max_ps=reg['max_ps'],time_advance='boundaries',compute_contexts=2,
        fetch_contexts=2,read_issue_policy='round_robin',weight_cache=WeightCacheConfig(),operand_readiness='contiguous_prefix',
        activation_sram_read_bytes_per_cycle=machine.rx_write_bytes_per_cycle,npu_model=NPUKernelModel(npu,kernels,auxiliary=metadata['auxiliary']),
        window_source=source,idle_release_boundaries=True,network_factory=factory(binary=binary,directory=directory/'network',ready_router_ids=tuple(r.id for r in machine.routers),ready_slots=16))
    finally:native.close()
    with gzip.open(directory/'result.json.gz','wt') as f:json.dump(r,f)
    from w2w.validation.llm_context import audit_llm_stage
    audit_slot=acquire_slot(root)
    try:proof=audit_llm_stage(r,directory/'windows',cohort,catalog,reg)
    finally:fcntl.flock(audit_slot,fcntl.LOCK_UN);audit_slot.close()
    write_json(directory/'completion.json',dict(passed=True,stage=stage,source_commit=revision(),result_sha256=file_sha(directory/'result.json.gz'),
        proof=proof,wall_seconds=time.monotonic()-start))


def coordinate(root,binary):
    reg=json.loads((root/'registration.json').read_text());plan=json.loads((root/'deployment.json').read_text());N=plan['stack_copies']
    if revision()!=reg['source_commit']:raise ValueError('Frozen serving source changed')
    for receipt in reg['gate_receipts']:
        if file_sha(receipt['path'])!=receipt['sha256']:raise ValueError('Accepted serving gate changed')
    cohort=json.load(gzip.open(root/'cohort.json.gz','rt'));requests=RequestLifecycle(tuple(ServingRequest(c['request_id'],
        c['coverage']['prefill_tokens'],c['coverage']['decode_tokens'],c['raw_sha256']) for c in cohort))
    links=PipelineLinks(LLMProfile(**reg['profile']));workers=[];logs=[];seen=set();finished={};pending=[];prefill_count=sum(s['phase']=='prefill' for s in reg['schedule'])
    atomic(ticket(root,0,0),dict(committed_ps=0,kind='modeled_arrival',source=None,destination=0,payload_bytes=0))
    for stage in range(N):
        log=(root/f's{stage:02d}.log').open('w');logs.append(log)
        workers.append(subprocess.Popen([sys.executable,'-m','w2w.experiments.run_full_llm','--root',str(root),
            '--stage',str(stage),'--booksim-binary',str(binary)],stdout=log,stderr=subprocess.STDOUT,start_new_session=True))
    try:
        while True:
            for stage,w in enumerate(workers):
                if w.poll() not in (None,0):raise RuntimeError(f'Physical serving stage {stage} failed with {w.returncode}; no retry')
            for path in sorted((root/'notices').glob('s??-w????.json')):
                if path.name in seen:continue
                notice=json.loads(path.read_text());s=notice['stage'];i=notice['index'];seen.add(path.name)
                finished[s,i]=notice['drained_ps'];pending.append((s,i,notice,path))
            retained=[]
            for s,i,notice,path in pending:
                destination=s+1 if s<N-1 else 0
                previous=i-1 if s<N-1 else i
                if i and (destination,previous) not in finished:
                    retained.append((s,i,notice,path));continue
                ready=max(notice['drained_ps'],finished.get((destination,previous),0))
                if s<N-1:
                    at=links.transfer(s,s+1,notice['tokens']*reg['profile']['hidden']*2,ready,window=i,kind='activation')
                    links.events[-1]['producer_ready_ps']=notice['drained_ps']
                    atomic(ticket(root,s+1,i),dict(committed_ps=at,source=s,destination=s+1,payload_bytes=notice['tokens']*8192,
                        producer_notice_sha256=file_sha(path)))
                    if s==0 and i+1<prefill_count:
                        atomic(ticket(root,0,i+1),dict(committed_ps=links.tx[s],kind='local_prefill_KV_dependency',producer_notice_sha256=file_sha(path)))
                else:
                    if notice['heads']:
                        at=links.transfer(s,0,4*len(notice['heads']),ready,window=i,kind='token_feedback')
                        links.events[-1]['producer_ready_ps']=notice['drained_ps']
                        for h in notice['heads']:requests.emit(h['request_id'],h['phase'],h['decode_step'],at)
                        if i+1<len(reg['schedule']) and i>=prefill_count-1:
                            atomic(ticket(root,0,i+1),dict(committed_ps=at,kind='autoregressive_feedback',source=s,destination=0,
                                producer_notice_sha256=file_sha(path)))
                atomic(root/'notices'/f'ack-s{s:02d}-w{i:04d}.json',dict(source_release_ps=max(notice['drained_ps'],links.tx[s]),
                    producer_notice_sha256=file_sha(path)))
            pending=retained
            atomic(root/'link-evidence.json',dict(events=links.events))
            atomic(root/'controller-status.json',dict(state='running',completed_stage_windows=len(seen),
                expected_stage_windows=N*reg['windows'],workers=[dict(stage=s,pid=w.pid,returncode=w.poll()) for s,w in enumerate(workers)]))
            if all(w.poll()==0 for w in workers):break
            time.sleep(2)
        if len(seen)!=N*reg['windows'] or pending:raise ValueError('Serving ended without all true 94-layer windows/transfers')
        write_json(root/'link-evidence.json',dict(events=links.events))
        metrics=requests.metrics()
        from w2w.validation.llm_context import audit_serving
        proof=audit_serving(root,reg,plan,metrics,links.events)
        write_json(root/'serving-results.json',dict(passed=True,proof=proof,requests=metrics,scope=reg['scope'],source_commit=revision()))
        atomic(root/'controller-status.json',dict(state='complete',passed=True,proof=proof))
    except Exception as error:
        atomic(root/'stop.json',dict(reason=str(error)));atomic(root/'controller-status.json',dict(state='failed',reason=str(error)))
        for w in workers:
            if w.poll() is None:os.killpg(w.pid,15)
        raise
    finally:
        for log in logs:log.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    mode=p.add_mutually_exclusive_group(required=True);mode.add_argument('--prepare',action='store_true');mode.add_argument('--stage',type=int);mode.add_argument('--coordinate',action='store_true')
    p.add_argument('--corpus',type=Path);p.add_argument('--config',type=Path);p.add_argument('--B',type=int,default=1)
    p.add_argument('--gate-receipts',type=Path,nargs='*',default=());p.add_argument('--booksim-binary',type=Path)
    p.add_argument('--context-projection-policy',choices=('whole_matrix_local','output_sharded'),default='whole_matrix_local');a=p.parse_args()
    if a.prepare:prepare(a.root,a.corpus,a.config,a.B,a.gate_receipts,a.context_projection_policy)
    elif a.coordinate:coordinate(a.root,a.booksim_binary)
    else:stage_run(a.root,a.stage,a.booksim_binary)
