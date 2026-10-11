"""Re-audit full registered cohorts against every original ranked routing row."""
import gzip,json
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from .runtime_windows import audit_window_chain
from .energy_edp import activity
from w2w.workloads.moe_trace import file_sha
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.experiments.run_real_moe import paired_batches


def analyze_case(root,case):
    root=Path(root);reg=json.loads((root/'registration.json').read_text());choice=reg['cases'][case]
    directory=root/'cases'/case;completion=json.loads((directory/'completion.json').read_text())
    path=directory/'result.json.gz'
    if file_sha(path)!=completion['result_sha256']:raise ValueError('Final raw result changed')
    result=json.load(gzip.open(path,'rt'))
    if result['registration_sha256']!=file_sha(root/'registration.json') or result['source_commit']!=reg['source_commit']:
        raise ValueError('Frozen experiment identity changed')
    c=reg['cohorts'][str(choice['B'])];cp=root/'cohorts'/c['file']
    if file_sha(cp)!=c['sha256']:raise ValueError('Original complete cohort changed')
    cohort=json.load(gzip.open(cp,'rt'));expected=iter(paired_batches(cohort,reg['layers'],reg['prefill_microbatch']))
    calls=Counter();assignments=0;counts=Counter();windows=[];experts=[];service=Counter();npu_macs=0;cycles=0
    def visit(r,row):
        nonlocal assignments,npu_macs,cycles
        batches=next(expected,None)
        if batches is None or len(batches)!=len(r['runtime_metadata']['calls']):raise ValueError('Extra/missing layer or token window')
        if digest(r['spec'])!=reg['machine_sha256'] or digest(r['graph']['objects'])!=choice['catalog_sha256']:
            raise ValueError('Hardware or complete independent catalog changed')
        if r['npu_execution']['profile']!=reg['npu_profile'] or r['weight_cache']['data_bytes_per_cluster']!=reg['cache']['data_bytes_per_cluster']:
            raise ValueError('NPU/cache resource budget changed')
        starts={e['task']:e['time_ps'] for e in r['events'] if e['kind']=='task_start'}
        ends={e['task']:e['time_ps'] for e in r['events'] if e['kind']=='task_finish'}
        issues={}
        for e in r['events']:
            if e['kind']=='read_issue':issues.setdefault(e['task'],e['time_ps'])
        for batch,meta in zip(batches,r['runtime_metadata']['calls']):
            prefix=f'W{row["index"]:04d}/L{batch.layer_id}/'
            from w2w.validation.moe_runtime import audit_moe_call
            audit_moe_call(r,batch,prefix)
            wanted=dict(batch_id=batch.id,layer_id=batch.layer_id,
                token_ids=[list(x.token_id) for x in batch.observations],
                token_to_experts=[list(x.expert_ids) for x in batch.observations],
                expert_token_counts={str(e):len(ts) for e,ts in batch.expert_to_tokens})
            if any(meta[k]!=v for k,v in wanted.items()):raise ValueError('Actual request/token/layer/rank/group changed')
            router_done=ends[prefix+'router_done'];packed=[];finish=[]
            for expert,tokens in batch.expert_to_tokens:
                ids=[prefix+f'e{expert}/b{block}/{phase}' for block in range(12) for phase in ('gate','up','down')]
                for key in ids:
                    k=r['npu_execution']['kernels'][key]
                    if k['M']!=len(tokens) or (k['N'],k['K'])!=((4096,128) if key.endswith('/down') else (128,4096)):
                        raise ValueError('Expert GEMM uses average rather than actual token count')
                    if key in issues and issues[key]<router_done:raise ValueError('Future route used before modeled router completion')
                pack=ends[prefix+f'e{expert}/pack'];scatter=ends[prefix+f'e{expert}/scatter']
                packed.append(pack);finish.append(scatter)
                experts.append(dict(window=row['index'],layer=batch.layer_id,expert=expert,M=len(tokens),
                    dispatch_pack_ps=pack-router_done,expert_completion_ps=scatter-pack,
                    last_projection_ps=max(ends[k] for k in ids)))
            expected_macs=3*batch.token_count*8*4096*1536
            if meta['expert_macs']!=expected_macs:raise ValueError('MoE mathematical work changed')
            assignments+=8*batch.token_count;phase=batch.observations[0].phase;calls[phase]+=1
            for t in range(batch.token_count):
                combine=prefix+f't{t}/combine'
                for expert in batch.observations[t].expert_ids:
                    if starts[combine]<ends[prefix+f'e{expert}/scatter']:raise ValueError('Combine ran before a selected expert output')
        a=activity(r);counts.update(a['counts'])
        plans=r['npu_execution']['plans'];npu_macs+=sum(v['macs'] for v in plans.values());cycles+=sum(v['cycles'] for v in plans.values())
        for plan in plans.values():service.update(plan['service'])
        windows.append(dict(index=row['index'],phase=batches[0].observations[0].phase,
            decode_step=batches[0].observations[0].decode_step,begin_ps=row['begin_ps'],end_ps=row['makespan_ps'],
            duration_ps=row['makespan_ps']-row['begin_ps'],native_bytes=row['native_bytes'],cache_stats=row['cache_stats'],
            npu_service_cycles=sum(v['cycles'] for v in plans.values()),macs=sum(v['macs'] for v in plans.values()),
            noc_byte_um=a['counts']['noc_data_bit_mm']*125,gateway_bytes=r['native']['gateway_bytes']))
    proof=audit_window_chain(result,directory/'windows',visit=visit)
    if next(expected,None) is not None:raise ValueError('Registered complete trace was truncated')
    total_tokens=c['prefill_tokens']+choice['B']*c['decode_steps']
    if assignments!=total_tokens*8*len(reg['layers']):raise ValueError('Complete routing work not conserved')
    decode=[w for w in windows if w['phase']=='decode'];late=decode[len(decode)//2:]
    if len(decode)!=128 or c['omitted_execution_tokens']!=0:raise ValueError('Incomplete captured lifecycle')
    return dict(schema='w2w.real-npu-moe-analysis.v1',passed=True,case=case,source_commit=reg['source_commit'],
        registration_sha256=file_sha(root/'registration.json'),result_sha256=file_sha(path),cohort_sha256=c['sha256'],
        original_request_hashes=c['original_request_hashes'],proof=proof,B=choice['B'],baseline=choice['baseline'],
        full_captured_lifecycle=True,executed_layers=reg['layers'],omitted_execution_layers=92,
        token_expert_assignments=assignments,prefill_window_time_ps=sum(w['duration_ps'] for w in windows if w['phase']=='prefill'),
        decode_window_time_ps=sum(w['duration_ps'] for w in decode),late_window_time_ps=sum(w['duration_ps'] for w in late),
        npu_macs=npu_macs,npu_service_cycles=cycles,npu_mac_utilization=npu_macs/(16384*cycles),npu_service=dict(service),
        activity_counts=dict(counts),windows=windows,experts=experts,wall_seconds=completion['wall_seconds'],
        scope='Complete original cohort lifecycle in two actual adjacent MoE layers. Not a full Transformer TTFT/TPOT; no numerical routing coefficients or activations supplied by capture.')
