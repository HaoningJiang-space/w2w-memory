"""Explain the accepted B1 pair using saved events; never launch Native work."""
import argparse,csv,gzip,json,time
from collections import Counter,defaultdict
from pathlib import Path

from w2w.analysis.moe_mechanism import INTERVALS,compare_cases,distribution,read_mechanism_input
from w2w.analysis.npu_competition import competition
from w2w.common.io import write_json
from w2w.provenance import revision
from w2w.workloads.moe_trace import file_sha


def readiness_and_lifetimes(raw):
    ledger=competition(raw);origin=raw['runtime_window_begin_ps']
    cache={};read=defaultdict(list);issues=defaultdict(list);delivered={};acquired={};released={}
    for e in raw['events']:
        kind=e['kind'];key=e.get('task')
        if kind in ('cache_operands_ready','npu_cached_operands_ready'):cache[key]=e['time_ps']
        elif kind=='read_deliver':read[key].append(e['time_ps'])
        elif kind=='read_issue':issues[key].append(e['time_ps'])
        elif kind=='data_deliver':delivered[e['edge']]=e['time_ps']
        elif kind=='fetch_context_acquire':acquired[key]=e['time_ps']
        elif kind=='fetch_context_release':released[key]=e['time_ps']
    incoming=defaultdict(list)
    for edge in raw['graph']['data']:incoming[edge['consumer']].append(edge['id'])
    tasks={t['id']:t for t in raw['graph']['tasks']};details={};holds=[]
    for key,row in ledger['tasks'].items():
        a=row['admitted_ps'];w=max(cache.get(key,a),max(read[key],default=a));x=max((delivered[e] for e in incoming[key]),default=a)
        ready=max(a,w,x)
        if ready!=row['operands_committed_ps']:raise ValueError('Separate weight/activation boundaries do not close')
        latest=[]
        if w==ready and tasks[key]['reads']:latest.append('cache' if key in cache else 'native')
        if x==ready and incoming[key]:latest.append('activation')
        if a==ready:latest.append('admission')
        details[key]=dict(weight_ready_ps=w-origin,activation_ready_ps=x-origin,latest_ready_sources=latest,
            operand_interval_ps=ready-a,cache_hit=key in cache)
        if key not in acquired:continue
        if key not in released or not acquired[key]<=released[key]:raise ValueError('Unclosed fetch ownership')
        hold=dict(task=key,cache_hit=key in cache,hold_ps=released[key]-acquired[key],
            eligibility_to_admission_ps=row['observed_intervals_ps']['eligible_to_admit_ps'])
        if issues[key]:
            first,last=min(issues[key]),max(issues[key]);final=max(read[key])
            if not acquired[key]<=first<=last<=final==released[key]:raise ValueError('Miss context does not retain complete return ownership')
            hold.update(admission_to_first_issue_ps=first-acquired[key],issue_span_ps=last-first,remaining_return_ps=final-last)
        elif key not in cache:raise ValueError('Fetch owner has neither cache nor Native supply')
        holds.append(hold)
    return details,holds


def signed_accounting(reference,candidate,pair):
    windows=sum(w['delta_ps'] for w in pair['windows'])
    drain=reference['inter_window_drain_ps']-candidate['inter_window_drain_ps']
    total=reference['makespan_ps']-candidate['makespan_ps']
    if windows+drain!=total:raise ValueError('Signed windows plus drain do not close total benefit')
    groups={}
    for name in ('both_zero_native','both_with_native','mixed_native'):
        selected=[w for w in pair['windows'] if w['phase']=='decode' and w['cache_class']==name]
        groups[name]=dict(windows=len(selected),benefit_ps=sum(w['delta_ps'] for w in selected),
            faster=sum(w['delta_ps']>0 for w in selected),slower=sum(w['delta_ps']<0 for w in selected),equal=sum(w['delta_ps']==0 for w in selected),
            reference_native_bytes=sum(w['reference_native_bytes'] for w in selected),candidate_native_bytes=sum(w['candidate_native_bytes'] for w in selected))
    return dict(reference_ps=reference['makespan_ps'],candidate_ps=candidate['makespan_ps'],
        signed_window_sum_ps=windows,signed_inter_window_drain_ps=drain,signed_total_ps=total,
        completion_reduction_fraction=total/reference['makespan_ps'],observed_native_classes=groups)


def run(study,finisher,reference_root,output):
    receipt_path=finisher/'receipt.json';receipt=json.loads(receipt_path.read_text())
    if not receipt.get('passed') or not receipt.get('complete_scoped_B1_G3') or not all(receipt['gates'].values()):
        raise ValueError('Accepted complete B1 G3 receipt required before P1')
    for path,sha in receipt['sources'].items():
        if file_sha(Path(path))!=sha:raise ValueError('Accepted G3 evidence changed')
    paths=(reference_root/'mechanism.json',finisher/'phase-split-mechanism/mechanism.json',finisher/'paired-mechanism.json')
    reference,candidate,pair=(json.loads(p.read_text()) for p in paths)
    if compare_cases(reference,candidate)!=pair:raise ValueError('Independent signed pairing differs from the finisher')
    output.mkdir(parents=True,exist_ok=False);start=time.monotonic();rows=[];chain_sources=defaultdict(Counter);fetches=defaultdict(list)
    physical=json.loads((finisher/'phase-split-physical-analysis.json').read_text())
    reference_physical=json.loads((study/'cases/B1-reference/analysis.json').read_text())
    for policy,mechanism,physical_analysis in (('reference',reference,reference_physical),('phase_split',candidate,physical)):
        for index,window in enumerate(mechanism['windows']):
            path=study/'cases'/mechanism['case']/'windows'/f'window-{index:04d}.json.gz'
            raw=read_mechanism_input(path,window['source_sha256']);details,holds=readiness_and_lifetimes(raw)
            # The independently closed witness has only nonoverlapping spans.
            ledger=competition(raw)
            from w2w.analysis.moe_mechanism import completion_chain
            chain=completion_chain(raw['graph'],ledger,raw['runtime_window_begin_ps'],raw['makespan_ps'])
            sources=Counter()
            for task in chain['tasks']:
                d=details[task['task']];label='+'.join(d['latest_ready_sources'])
                sources[label]+=d['operand_interval_ps']
            if sum(sources.values())!=chain['interval_totals_ps']['admit_to_operands_ps']:
                raise ValueError('Latest-source observation does not partition witnessed operand time')
            phase=window['phase'];chain_sources[policy+'/'+phase].update(sources);fetches[policy+'/'+phase].extend(holds)
            gateway_bound=max(window['gateway_bytes'].values(),default=0)*raw['spec']['noc_period_ps']//32
            if any(g['data_bytes_per_cycle']!=32 for g in raw['spec']['stack']['gateways']):raise ValueError('Gateway resource assumption changed')
            rows.append(dict(policy=policy,index=index,phase=phase,decode_step=window['decode_step'],duration_ps=window['duration_ps'],
                native_bytes=window['native_bytes'],reload_bytes=window['cache_stats'].get('reload_bytes',0),
                maximum_gateway_bytes=max(window['gateway_bytes'].values(),default=0),gateway_payload_bound_ps=gateway_bound,
                noc_byte_um=physical_analysis['windows'][index]['noc_byte_um'],
                witnessed_operand_latest_sources_ps=dict(sources),witnessed_intervals_ps=chain['interval_totals_ps']))
            if index<2 or (index+1)%16==0:write_json(output/'progress.json',dict(policy=policy,completed_windows=index+1,wall_seconds=time.monotonic()-start))
    lifetimes={}
    for key,values in fetches.items():
        lifetimes[key]={}
        for hit in (False,True):
            selected=[v for v in values if v['cache_hit']==hit]
            lifetimes[key]['hit' if hit else 'miss']={field:distribution([v[field] for v in selected if field in v]) for field in
                ('hold_ps','eligibility_to_admission_ps','admission_to_first_issue_ps','issue_span_ps','remaining_return_ps')}
    paired_rows=[]
    for a,b in zip(rows[:130],rows[130:]):
        if a['index']!=b['index']:raise ValueError('P1 event horizon differs')
        paired_rows.append(dict(index=a['index'],phase=a['phase'],decode_step=a['decode_step'],
            delta_ps=a['duration_ps']-b['duration_ps'],delta_native_bytes=a['native_bytes']-b['native_bytes'],
            delta_reload_bytes=a['reload_bytes']-b['reload_bytes'],delta_gateway_bound_ps=a['gateway_payload_bound_ps']-b['gateway_payload_bound_ps'],
            delta_noc_byte_um=a['noc_byte_um']-b['noc_byte_um'],
            interval_delta_ps={f:a['witnessed_intervals_ps'][f]-b['witnessed_intervals_ps'][f] for f in INTERVALS},
            reference=a,candidate=b))
    decode=[w for w in paired_rows if w['phase']=='decode']
    value=dict(passed=True,analysis_source=revision(),sources={str(p):file_sha(p) for p in (*paths,receipt_path)},
        signed_accounting=signed_accounting(reference,candidate,pair),
        witness_latest_operand_sources_ps={k:dict(v) for k,v in chain_sources.items()},fetch_lifetimes=lifetimes,
        paired_windows=paired_rows,largest_benefits=sorted(decode,key=lambda w:w['delta_ps'],reverse=True)[:8],
        largest_regressions=sorted([w for w in decode if w['delta_ps']<0],key=lambda w:w['delta_ps'])[:8],
        original_probe_steps=[w for w in decode if w['decode_step'] in (0,25)],wall_seconds=time.monotonic()-start,
        scope='Accepted full Native/NoC/carry audits reused; all 260 SHA-bound saved windows inspected for actual weight/activation and coupled fetch ownership. Signed total includes drain, negative steps and changed reloads. Latest operand sources and Gateway work bounds are observations, not exclusive causal attribution or removable stalls. No intervention or new physical run.')
    write_json(output/'analysis.json',value)
    fields=('index','phase','decode_step','delta_ps','delta_native_bytes','delta_reload_bytes','delta_gateway_bound_ps','delta_noc_byte_um')
    with (output/'steps.csv').open('x',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows({k:w[k] for k in fields} for w in paired_rows)
    write_json(output/'receipt.json',dict(passed=True,analysis_source=revision(),G3_receipt_sha256=file_sha(receipt_path),
        analysis_sha256=file_sha(output/'analysis.json'),scope=value['scope']))
    return value


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('study','finisher','reference','output'):parser.add_argument('--'+name,type=Path,required=True)
    a=parser.parse_args();run(a.study,a.finisher,a.reference,a.output)
