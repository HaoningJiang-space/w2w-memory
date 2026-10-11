"""Actual complete-cohort views and output-shard array reference, not timing."""
import argparse,gzip,json,sys,subprocess,time
from dataclasses import asdict
from collections import Counter
from pathlib import Path
from tools.validate_npu_reference import reference
from w2w.architecture.presets.recipes import from_recipe
from w2w.architecture.compiler import compile_machine
from w2w.architecture.llm_deployment import LLMProfile,context_catalog
from w2w.architecture.npu_profile import reference_profile
from w2w.experiments.run_real_moe import paired_batches
from w2w.mapping.llm_context import lower_context
from w2w.system.builder import SystemBuilder
from w2w.system.npu_kernel import NPUKernelModel
from w2w.system.weight_cache import WeightCacheConfig
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.common.io import write_json
from w2w.workloads.moe_trace import file_sha
from w2w.provenance import revision


def run(cohort_path,config,policy,reference_source=None):
    begin=time.monotonic();cohort=json.load(gzip.open(cohort_path,'rt'))
    p=LLMProfile.from_config(json.loads(config.read_text()));m=compile_machine(from_recipe('configs/machine/v3-small.json','distributed'));npu=reference_profile()
    if policy=='whole_matrix_local':catalog=context_catalog(m,cohort[0]['shape'],('0','1'),'up_local',p)
    else:catalog=context_catalog(m,cohort[0]['shape'],('0','1'),'up_local',p,context_projection_policy=policy)
    batches=list(paired_batches(cohort,('0','1'),32));pref=[(i,b) for i,b in enumerate(batches) if b[0].observations[0].phase=='prefill']
    dec=[(i,b) for i,b in enumerate(batches) if b[0].observations[0].phase=='decode']
    views={'first_prefill':pref[0],'tail_prefill':pref[-1],'first_decode':dec[0],'last_decode':dec[-1]};rows=[];shapes={}
    cache=WeightCacheConfig();base=cache.data_bytes_per_cluster+cache.metadata_bytes_per_cluster+136+64
    budgets={t.id:t.sram_bytes-base for t in m.tiles}
    for local in range(2):
        for h in range(p.kv_heads):budgets[f'c{local*p.kv_heads+h}']-=len(cohort)*(4*p.head_dim*p.kv_tokens_per_request+128)
    budgets['c15']-=2*32*p.hidden*2+2*64*16
    for view,(index,bs) in views.items():
        for batch in bs:
            state={(batch.layer_id,r.request_id):r.token_position for r in reversed(batch.observations)}
            prefix=f'W{index:04d}/L{batch.layer_id}/';g,k,meta=lower_context(batch,m,catalog,npu,state,prefix=prefix)
            builder=SystemBuilder(m).validate_graph(g);model=NPUKernelModel(npu,k,auxiliary=meta['auxiliary']);model.validate(m,g)
            intrinsic={t.id:builder.footprint[t.id]-(sum(r.size_bytes for r in t.reads) if t.id in k else 0) for t in g.tasks}
            excess=[t.id for t in g.tasks if intrinsic[t.id]>budgets[t.tile]]
            if excess:raise ValueError(f'Actual graph exceeds unchanged SRAM/KV/endpoint budget: {excess[:3]}')
            if policy=='output_sharded':
                from w2w.validation.context_projections import audit_projection_call
                audit_projection_call(dict(graph=asdict(g),npu_execution=model.record(),runtime_metadata=meta),batch,catalog,prefix)
                for assembly in meta['projection_assemblies']:
                    for shard in assembly['shards']:
                        kernel=k[shard['task']];shapes[kernel.M,kernel.N,kernel.K]=model.plans[shard['task']]
            rows.append(dict(view=view,window=index,layer=batch.layer_id,phase=batch.observations[0].phase,tokens=batch.token_count,
                decode_step=batch.observations[0].decode_step,graph_sha256=digest(asdict(g)),kernels_sha256=digest({s:asdict(v) for s,v in k.items()}),
                metadata_sha256=digest(meta),largest_noncache_task=max(intrinsic,key=intrinsic.get),largest_noncache_bytes=max(intrinsic.values()),
                minimum_intrinsic_headroom_bytes=min(budgets[t.tile]-intrinsic[t.id] for t in g.tasks),kernel_macs=sum(v.macs for v in k.values())))
    arrays=[];pin=None
    if policy=='output_sharded':
        pin=subprocess.check_output(['git','-C',str(reference_source),'rev-parse','HEAD'],text=True).strip()
        if pin!='f79d7bc39a80a21fc35bc667967b76a15b311f49':raise ValueError('Pinned array reference required')
        sys.path.insert(0,str(reference_source.resolve()))
        import scalesim.compute.systolic_compute_os as primary
        if Path(primary.__file__).resolve()!=(reference_source/'scalesim/compute/systolic_compute_os.py').resolve():raise ValueError('Unexpected loaded array reference')
        for (M,N,K),plan in sorted(shapes.items()):
            cycles=sum(max(reference(npu.rows,npu.columns,t['M'],t['N'],t['K'])['cycles'] for t in w) for w in plan['waves'])
            reads=sum(reference(npu.rows,npu.columns,t['M'],t['N'],t['K'])['filter_reads'] for w in plan['waves'] for t in w)
            if cycles!=plan['array_cycles'] or reads!=plan['service']['weight_sram_bytes']:raise ValueError('Output-shard core differs from primary reference')
            arrays.append(dict(M=M,N=N,K=K,array_cycles=cycles,service_cycles=plan['cycles'],program_sha256=plan['program_sha256']))
    return dict(passed=True,source_commit=revision(),policy=policy,cohort_sha256=file_sha(cohort_path),model_config_sha256=file_sha(config),
        catalog_sha256=digest([asdict(o) for o in catalog['objects']]),catalog_bytes=sum(o.size_bytes for o in catalog['objects']),
        rows=rows,array_reference=arrays,reference_commit=pin,wall_seconds=time.monotonic()-begin,
        scope='Actual complete-cohort first/tail prefill and first/last decode compiler views at full H/I, two real layers. Intrinsic SRAM includes unchanged cache, reserved KV and endpoint state; dynamic progress still requires Native execution. Default hashes support exact source regression; output shards form complete original hidden reductions with paid copies/gathers. No application latency, captured numerical tensors or new hardware claim.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('cohort','config','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--policy',choices=('whole_matrix_local','output_sharded'),required=True);p.add_argument('--reference-source',type=Path)
    a=p.parse_args()
    if a.output.exists():raise ValueError('Retain prior compiler evidence')
    write_json(a.output,run(a.cohort,a.config,a.policy,a.reference_source))
