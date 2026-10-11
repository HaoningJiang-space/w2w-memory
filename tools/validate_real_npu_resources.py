"""Full-shape real-token resource qualification, never a complete-study claim."""
import argparse,gzip,json,time
from dataclasses import asdict
from pathlib import Path
from w2w.architecture.presets.recipes import from_recipe
from w2w.architecture.compiler import compile_machine
from w2w.architecture.npu_profile import reference_profile
from w2w.architecture.llm_deployment import LLMProfile,context_catalog
from w2w.workloads.patterns_adapter import load_corpus,observations
from w2w.serving.batcher import group
from w2w.mapping.moe_batch_lowering import full_catalog,lower_batch
from w2w.mapping.llm_context import lower_context
from w2w.domain.execution import ExecutionGraph,DataEdge,ControlEdge
from w2w.system.npu_kernel import NPUKernelModel
from w2w.system.runtime_windows import RuntimeWindows
from w2w.system.kv_runtime import KVRuntimeWindows
from w2w.system.kernel import execute_system
from w2w.system.weight_cache import WeightCacheConfig
from w2w.backends.ramulator import VerticalRWDL
from w2w.backends.booksim.adapter import factory
from w2w.analysis.runtime_windows import audit_window_chain
from w2w.validation.moe_runtime import audit_moe_call
from w2w.common.io import write_json
from w2w.workloads.moe_trace import file_sha
from w2w.provenance import revision


def run(root,corpus,binary,context,context_projection_policy='whole_matrix_local'):
    root.mkdir(parents=True,exist_ok=False);capture=next(iter(load_corpus(corpus)))
    machine=compile_machine(from_recipe('configs/machine/v3-small.json','distributed'));p=reference_profile();layers=('0','1')
    if not context and context_projection_policy!='whole_matrix_local':raise ValueError('Context mapping requires context execution')
    catalog=context_catalog(machine,capture['shape'],layers,'up_local',LLMProfile(),context_projection_policy=context_projection_policy) if context else full_catalog(machine,capture['shape'],layers,'up_local')
    state={};expected={}
    def producer():
        for index in range(2):
            tasks=[];data=[];control=[];kernels={};aux={};calls=[];append=[];reads=[];previous=[];assemblies=[]
            for layer in layers:
                b=group(f'qualification/{index}/L{layer}',(observations(capture,'prefill',layer)[index],))
                prefix=f'W{index:04d}/L{layer}/';expected[index,layer]=b
                if context:g,k,m=lower_context(b,machine,catalog,p,state,prefix=prefix)
                else:g,k,m=lower_batch(b,machine,catalog,p,prefix=prefix)
                current=m['context_input'] if context else prefix+'t0/input'
                for t,key in enumerate(previous):
                    control.append(ControlEdge(key,current));data.append(DataEdge(prefix+f'layer_activation/{t}',key,current,8192))
                tasks.extend(g.tasks);data.extend(g.data);control.extend(g.control);kernels.update(k);aux.update(m['auxiliary']);calls.append(m)
                append.extend(m.get('kv_appends',()));reads.extend(m.get('kv_reads',()));previous=m['finish_tasks']
                assemblies.extend(m.get('projection_assemblies',()))
            meta=dict(index=index,calls=calls,npu_kernels={k:asdict(v) for k,v in kernels.items()},auxiliary=aux,
                kv_appends=append,kv_reads=reads,finish_tasks=previous,heads=[])
            if assemblies:meta['projection_assemblies']=assemblies
            yield ExecutionGraph(tuple(tasks),catalog['objects'],tuple(data),tuple(control)),kernels,meta
    gen=producer();g,ks,meta=next(gen)
    source=KVRuntimeWindows(root/'windows',gen,meta,catalog,(capture['request_id'],)) if context else RuntimeWindows(root/'windows',gen,meta)
    if context:source.lengths=state
    native=VerticalRWDL(machine,request_control=True,refresh=True,gateway_trace_bin_ps=1000000);begin=time.monotonic()
    try:r=execute_system(machine,g,native=native,time_advance='boundaries',max_ps=50000000000,
        compute_contexts=2,fetch_contexts=2,read_issue_policy='round_robin',weight_cache=WeightCacheConfig(),operand_readiness='contiguous_prefix',
        activation_sram_read_bytes_per_cycle=machine.rx_write_bytes_per_cycle,npu_model=NPUKernelModel(p,ks,auxiliary=meta['auxiliary']),window_source=source,
        network_factory=factory(binary=binary,directory=root/'network',ready_router_ids=tuple(r.id for r in machine.routers),ready_slots=16))
    finally:native.close()
    math=[]
    def visit(raw,row):
        for layer in layers:math.append(audit_moe_call(raw,expected[row['index'],layer],f'W{row["index"]:04d}/L{layer}/'))
        if context:
            from w2w.validation.context_projections import audit_projection_call
            for layer in layers:audit_projection_call(raw,expected[row['index'],layer],catalog,f'W{row["index"]:04d}/L{layer}/')
            app=[e for e in raw['events'] if e['kind']=='kv_append'];reads=[e for e in raw['events'] if e['kind']=='kv_read']
            if len(app)!=8 or len(reads)!=16 or any((e['before'],e['after'])!=(row['index'],row['index']+1) for e in app):
                raise ValueError('Actual consecutive tokens did not own contiguous KV history')
            finish={e['task']:e['time_ps'] for e in raw['events'] if e['kind']=='task_finish'}
            for read in reads:
                owned=next(e for e in app if (e['layer'],e['request_id'],e['head'])==(read['layer'],read['request_id'],read['head']))
                if read['length']!=row['index']+1 or read['time_ps']<finish[owned['task']]:raise ValueError('Future KV exposure')
    proof=audit_window_chain(r,root/'windows',visit=visit)
    with gzip.open(root/'result.json.gz','wt') as f:json.dump(r,f)
    write_json(root/'receipt.json',dict(passed=True,source_commit=revision(),context=context,context_projection_policy=context_projection_policy,proof=proof,math=math,
        request_id=capture['request_id'],raw_sha256=capture['raw_sha256'],result_sha256=file_sha(root/'result.json.gz'),wall_seconds=time.monotonic()-begin,
        scope='Directed resource qualification of the first two actual prefill tokens, full H/I and two true layers; deliberately incomplete request, not G3/G4 research performance. Complete registrations must execute all captured tokens.'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--corpus',type=Path,required=True)
    p.add_argument('--booksim-binary',type=Path,required=True);p.add_argument('--context',action='store_true')
    p.add_argument('--context-projection-policy',choices=('whole_matrix_local','output_sharded'),default='whole_matrix_local');a=p.parse_args()
    run(a.root,a.corpus,a.booksim_binary,a.context,a.context_projection_policy)
