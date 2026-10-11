"""Read-only full real-layer, KV, residency and finite serving-chain audit."""
import gzip,json
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from w2w.analysis.runtime_windows import audit_window_chain
from w2w.common.fingerprints import digest_read_v1 as digest
from w2w.workloads.moe_trace import file_sha
from w2w.experiments.run_real_moe import paired_batches
from w2w.architecture.llm_deployment import LLMProfile
from w2w.serving.pipeline import PipelineLinks
from w2w.serving.requests import ServingRequest,RequestLifecycle
from .moe_runtime import audit_moe_call


def audit_llm_stage(summary,root,cohort,catalog,registration):
    p=catalog['llm_profile'];expected=iter(paired_batches(cohort,catalog['layers'],registration['prefill_microbatch']))
    kv={};windows=0;assignments=0;attention_macs=0;heads=[];resident=digest([asdict(o) for o in catalog['objects']])
    def visit(r,row):
        nonlocal windows,assignments,attention_macs
        batches=next(expected,None);m=r['runtime_metadata'];windows+=1
        if batches is None or len(batches)!=len(m['calls']):raise ValueError('Missing/extra true context layer window')
        if digest(r['graph']['objects'])!=resident or digest(r['spec'])!=registration['machine_sha256']:
            raise ValueError('Physical machine or complete model residency changed')
        if r['npu_execution']['profile']!=registration['npu_profile']:raise ValueError('NPU budget changed')
        if r['weight_cache']['data_bytes_per_cluster']!=184*1024**2:raise ValueError('KV stole undeclared cache capacity')
        ends={e['task']:e['time_ps'] for e in r['events'] if e['kind']=='task_finish'}
        starts={e['task']:e['time_ps'] for e in r['events'] if e['kind']=='task_start'}
        if any(t['start_ps']<m['release_ps'] for t in r['tasks'].values()):raise ValueError('Stage started before paid input commit')
        append_events=[e for e in r['events'] if e['kind']=='kv_append'];read_events=[e for e in r['events'] if e['kind']=='kv_read']
        if len(append_events)!=len(m['kv_appends']) or len(read_events)!=len(m['kv_reads']):raise ValueError('KV ownership event missing/repeated')
        for batch,call in zip(batches,m['calls']):
            prefix=f'W{row["index"]:04d}/L{batch.layer_id}/'
            wanted=dict(batch_id=batch.id,layer_id=batch.layer_id,token_ids=[list(x.token_id) for x in batch.observations],
                token_to_experts=[list(x.expert_ids) for x in batch.observations],
                expert_token_counts={str(e):len(ts) for e,ts in batch.expert_to_tokens})
            if any(call[k]!=v for k,v in wanted.items()):raise ValueError('Real request/token/layer/rank changed')
            proof=audit_moe_call(r,batch,prefix);assignments+=proof['token_expert_assignments']
            router_done=ends[prefix+'router_done']
            if any(e['time_ps']<router_done for e in r['events'] if e['kind']=='read_issue' and e['task'].startswith(prefix+'e')):
                raise ValueError('Future captured selection exposed before Router completion')
            members={}
            for x in batch.observations:members.setdefault(x.request_id,[]).append(x)
            for rid,observations in members.items():
                before=kv.get((batch.layer_id,rid),0);after=before+len(observations)
                if [x.token_position for x in observations]!=list(range(before,after)) or after>p['kv_tokens_per_request']:
                    raise ValueError('KV position/capacity mismatch or truncated history')
                for h in range(p['kv_heads']):
                    mapping=[x for x in m['attention_groups'] if (x['layer'],x['request_id'],x['kv_head'])==(batch.layer_id,rid,h)]
                    indices=[i for i,x in enumerate(batch.observations) if x.request_id==rid];group=p['query_heads']//p['kv_heads']
                    if len(mapping)!=1 or mapping[0]['query_row_order']!=[[i,q] for i in indices for q in range(h*group,(h+1)*group)]:
                        raise ValueError('Query packing/concat mixes a request, token or head identity')
                    app=[x for x in append_events if (x['layer'],x['request_id'],x['head'])==(batch.layer_id,rid,h)]
                    reads=[x for x in read_events if (x['layer'],x['request_id'],x['head'])==(batch.layer_id,rid,h)]
                    if len(app)!=1 or (app[0]['before'],app[0]['after'],app[0]['bytes'])!=(before,after,4*len(observations)*p['head_dim']):
                        raise ValueError('KV append does not own the actual request history')
                    if app[0]['time_ps']!=ends[app[0]['task']] or len(reads)!=2 or {x['tensor_kind'] for x in reads}!={'K','V_transpose'} or {x['length'] for x in reads}!={after}:
                        raise ValueError('Attention read wrong/uncommitted KV length')
                    if any(x['time_ps']<app[0]['time_ps'] or x['time_ps']!=starts[x['task']] for x in reads):
                        raise ValueError('Future KV became visible before append')
                    for kind,N,K in (('qk',after,p['head_dim']),('pv',p['head_dim'],after)):
                        key=prefix+f'context/{rid}/group{h}/{kind}';kernel=r['npu_execution']['kernels'][key]
                        shape=(len(observations)*(p['query_heads']//p['kv_heads']),N,K)
                        if (kernel['M'],kernel['N'],kernel['K'])!=shape or kernel['weight_dtype']!='BF16':
                            raise ValueError('GQA repeats KV or uses an averaged/incorrect shape')
                        attention_macs+=shape[0]*shape[1]*shape[2]
                    soft=prefix+f'context/{rid}/group{h}/causal_softmax'
                    phases=r['npu_execution']['auxiliary'][soft]['phases']
                    if [x['name'] for x in phases]!=['scale-and-causal-mask','causal-mask-max','shift-exp-sum','normalize-BF16-zero-padding']:
                        raise ValueError('Attention lacks ordered causal softmax/conversion')
                kv[batch.layer_id,rid]=after
        heads.extend(m['heads'])
        if m.get('export_task') and ends[m['export_task']]>r['makespan_ps']:raise ValueError('Stage published before output exported')
    chain=audit_window_chain(summary,root,visit=visit)
    if next(expected,None) is not None or windows!=registration['windows']:raise ValueError('Complete captured lifecycle was not executed')
    for layer in catalog['layers']:
        for c in cohort:
            if kv.get((layer,c['request_id']))!=c['coverage']['prefill_tokens']+c['coverage']['decode_tokens']:
                raise ValueError('KV lifecycle incomplete')
    if catalog['head'] and Counter(h['request_id'] for h in heads)!=Counter({c['request_id']:129 for c in cohort}):
        raise ValueError('Full LM head omitted captured token completions')
    if not catalog['head'] and heads:raise ValueError('Nonfinal stage generated tokens')
    return dict(passed=True,chain=chain,layers=catalog['layers'],assignments=assignments,attention_macs=attention_macs,
        complete_kv_histories=len(kv),head_completions=len(heads),scope=registration['scope'])


def audit_serving(root,registration,plan,metrics,events):
    root=Path(root);N=plan['stack_copies'];schedule=registration['schedule']
    layers=[x for s in plan['stages'] for x in s['layers']]
    if layers!=[str(x) for x in range(94)] or N!=47:raise ValueError('Full model aliases or omits a true layer')
    if file_sha(root/'deployment.json')!=registration['deployment_sha256']:raise ValueError('Deployment changed')
    notices={};completions=[]
    for stage in range(N):
        path=root/'stages'/f's{stage:02d}'/'completion.json';c=json.loads(path.read_text())
        if c.get('passed') is not True or c['source_commit']!=registration['source_commit'] or c['stage']!=stage:
            raise ValueError('Missing independent physical stage acceptance')
        if file_sha(path.parent/'result.json.gz')!=c['result_sha256']:raise ValueError('Accepted stage evidence changed')
        completions.append(dict(stage=stage,sha256=file_sha(path),proof=c['proof']))
        for i in range(registration['windows']):
            notice=root/'notices'/f's{stage:02d}-w{i:04d}.json';v=json.loads(notice.read_text());notices[stage,i]=v
            if (v['phase'],v['decode_step'],v['tokens'])!=(schedule[i]['phase'],schedule[i]['decode_step'],schedule[i]['tokens']):
                raise ValueError('Serving pipeline lost a complete trace window')
            input_path=root/'tickets'/f's{stage:02d}-w{i:04d}.json'
            if file_sha(input_path)!=v['input_ticket_sha256']:raise ValueError('Stage did not execute its accepted input ticket')
    links=PipelineLinks(LLMProfile(**registration['profile']));seen=set()
    for event in events:
        s,d,i=event['source'],event['destination'],event['window'];notice=notices[s,i]
        expected_kind='activation' if s<N-1 else 'token_feedback'
        payload=notice['tokens']*8192 if s<N-1 else len(notice['heads'])*4
        if d!=(s+1 if s<N-1 else 0) or event['kind']!=expected_kind or event['payload_bytes']!=payload or (s,i) in seen:
            raise ValueError('Duplicated/wrong/missing finite inter-stack data')
        previous=i-1 if s<N-1 else i
        earliest=max(notice['drained_ps'],notices[d,previous]['drained_ps'] if i else 0)
        if event['ready_ps']!=earliest or event['producer_ready_ps']!=notice['drained_ps']:
            raise ValueError('Transport used nonexistent output or overlapped active endpoint SRAM')
        links.transfer(s,d,payload,earliest,window=i,kind=expected_kind);actual=links.events[-1]
        if any(event[k]!=v for k,v in actual.items()):raise ValueError('Wire/header/SRAM/port work or ordering changed')
        seen.add((s,i))
        ack=json.loads((root/'notices'/f'ack-s{s:02d}-w{i:04d}.json').read_text())
        if ack['source_release_ps']<event['tx_end_ps']:raise ValueError('Output buffer released before transmission')
        if s<N-1:
            t=json.loads((root/'tickets'/f's{d:02d}-w{i:04d}.json').read_text())
            if t['committed_ps']!=event['committed_ps']:raise ValueError('Stage input not charged to completed link')
    required={(s,i) for s in range(N-1) for i in range(registration['windows'])}
    required|={(N-1,i) for i in range(registration['windows']) if notices[N-1,i]['heads']}
    if seen!=required:raise ValueError('Incomplete physical serving transfers')
    cohort=json.load(gzip.open(root/'cohort.json.gz','rt'));lifecycle=RequestLifecycle(tuple(ServingRequest(c['request_id'],
        c['coverage']['prefill_tokens'],c['coverage']['decode_tokens'],c['raw_sha256']) for c in cohort))
    for e in events:
        if e['kind']=='token_feedback':
            for h in notices[N-1,e['window']]['heads']:lifecycle.emit(h['request_id'],h['phase'],h['decode_step'],e['committed_ps'])
    if lifecycle.metrics()!=metrics:raise ValueError('TTFT/TPOT not derived from complete paid token feedback')
    return dict(passed=True,real_layers=94,physical_stacks=N,complete_stage_windows=N*registration['windows'],
        stage_receipts=completions,transfers=len(events),wire_bytes=sum(e['wire_bytes'] for e in events),
        external_sram_bytes=sum(e['source_sram_read_bytes']+e['destination_sram_write_bytes'] for e in events),
        scope='Conditional timing replay, not real numerical text generation or silicon-calibrated performance; no single 8 GiB full-model claim.')
