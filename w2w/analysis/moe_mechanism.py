"""Read-only phase accounting and witnessed completion chains from real events.

A chain follows the latest completed mathematical predecessor at each task.
Its task spans do not overlap. It is one observed completion witness, not a
unique critical path, an exclusive resource attribution or removable stalls.
"""
from collections import Counter,defaultdict
from math import ceil

from .npu_competition import competition

INTERVALS=('eligible_to_admit_ps','admit_to_operands_ps','operands_to_start_ps',
    'start_to_first_grant_ps','first_grant_to_finish_ps')
EVENTS={'task_allocate','task_start','task_finish','data_deliver','read_issue','read_deliver',
    'cache_operands_ready','npu_cached_operands_ready','fetch_context_acquire','fetch_context_release',
    'npu_epoch','npu_cycle','compute_service'}


def read_mechanism_input(path,expected_sha256,*,extra_events=()):
    """Project task events from a complete hash-bound, previously audited file.

    The original byte SHA binds every event, including unprojected NoC/Native
    events. This is an analysis projection, not a replacement physical archive
    or another full decoded-canonical audit. Keep original event order.
    """
    import base64,gzip,json
    from w2w.common.event_archive import _read_integers
    from w2w.workloads.moe_trace import file_sha
    selected=EVENTS|set(extra_events)
    if file_sha(path)!=expected_sha256:raise ValueError('Complete original archive hash changed')
    stored=json.load(gzip.open(path,'rt'))
    if 'events_codec' not in stored:
        stored['events']=[e for e in stored['events'] if e['kind'] in selected]
        return stored
    codec=stored['events_codec']
    if codec['schema']!='w2w.lossless-event-columns.v1':raise ValueError('Unknown complete archive format')
    groups={}
    for i,column in enumerate(codec['columns']):
        if column['kind'] not in selected:continue
        rows=[dict(kind=column['kind']) for _ in range(column['count'])]
        for field,values in column['fields'].items():
            n=values['count'];present=_read_integers(values['present'],n) if 'present' in values else range(len(rows))
            if values['encoding'] in ('delta-integers','strings'):
                data=_read_integers(values['values'],n)
                if values['encoding']=='strings':data=[codec['strings'][v] for v in data]
            elif values['encoding']=='json':data=values['values']
            else:raise ValueError('Unknown projected field encoding')
            if len(present)!=len(data):raise ValueError('Projected event fields lost alignment')
            for at,value in zip(present,data):rows[at][field]=value
        groups[i]=rows
    # Streaming order IDs avoid a host-memory expansion proportional to all
    # unneeded link/descriptor observer events in large prefill windows.
    events=[];cursor=Counter();count=0;n=shift=last=0
    for byte in base64.b64decode(codec['order'],validate=True):
        n|=(byte&127)<<shift
        if byte&128:shift+=7;continue
        last+=n//2 if n%2==0 else -(n//2)-1;n=shift=0;count+=1
        if not 0<=last<len(codec['columns']):raise ValueError('Invalid original event order')
        if last in groups:
            if cursor[last]>=len(groups[last]):raise ValueError('Projected event repeated')
            events.append(groups[last][cursor[last]]);cursor[last]+=1
    if shift or count!=codec['count'] or any(cursor[i]!=len(rows) for i,rows in groups.items()):
        raise ValueError('Original or projected event order incomplete')
    raw={k:v for k,v in stored.items() if k!='events_codec'};raw['events']=events
    raw['analysis_event_projection']=dict(complete_archive_sha256=expected_sha256,
        original_decoded_sha256=codec['decoded_sha256'],original_events=codec['count'],projected_events=len(events),
        scope='Task/operand/service event projection for analysis; prior complete physical/resource audit remains authoritative.')
    return raw


def distribution(values):
    values=sorted(values)
    if not values:return dict(count=0)
    return dict(count=len(values),minimum=values[0],mean=sum(values)/len(values),
        **{f'p{p}':values[max(0,ceil(p*len(values)/100)-1)] for p in (50,90,99)},maximum=values[-1])


def completion_chain(graph,ledger,origin,makespan):
    tasks={t['id']:t for t in graph['tasks']};rows=ledger['tasks'];parents=defaultdict(set)
    if set(tasks)!=set(rows):raise ValueError('Completion chain has missing/extra physical tasks')
    for edge in (*graph['control'],*graph['data']):parents[edge['consumer']].add(edge['producer'])
    if max(r['completed_ps'] for r in rows.values())!=makespan:raise ValueError('No actual task witnesses the makespan')
    target=max(rows,key=lambda k:(rows[k]['completed_ps'],k));key=target;chain=[];seen=set()
    while True:
        if key in seen:raise ValueError('Cyclic completion witness')
        seen.add(key);row=rows[key];r=row['dependency_ready_ps'];c=row['completed_ps']
        latest=max(parents[key],key=lambda k:(rows[k]['completed_ps'],k)) if parents[key] else None
        expected=max(origin,tasks[key]['release_ps'],rows[latest]['completed_ps'] if latest else origin)
        if r!=expected or c<r or sum(row['observed_intervals_ps'].values())!=c-r:
            raise ValueError('Completion witness cannot close dependency release and elapsed time')
        chain.append(row)
        if latest is None or rows[latest]['completed_ps']<r:break
        key=latest
    chain.reverse();base=chain[0]['dependency_ready_ps']-origin
    totals=Counter({f:0 for f in INTERVALS})
    for row in chain:totals.update(row['observed_intervals_ps'])
    if base<0 or base+sum(totals.values())!=makespan-origin:
        raise ValueError('Nonoverlapping witnessed chain does not reconstruct window completion')
    capacity=dict(fetch_full_before_admit_ps=sum(r.get('fetch_full_before_admit_ps',0) for r in chain),
        compute_context_full_before_start_ps=sum(r.get('compute_context_full_before_start_ps',0) for r in chain))
    if (capacity['fetch_full_before_admit_ps']>totals['eligible_to_admit_ps']
            or capacity['compute_context_full_before_start_ps']>totals['operands_to_start_ps']):
        raise ValueError('Observed capacity intersection exceeds its witnessed interval')
    return dict(target=target,initial_release_ps=base,interval_totals_ps=dict(totals),
        capacity_intersections_ps=capacity,
        arithmetic_service_on_chain_ps=sum(r['arithmetic_service_ps'] for r in chain),tasks=chain,
        scope='One latest-predecessor completion witness. Grant-to-finish includes scalar gaps; admission/operand waits include competing resources and transfers. No exclusive cause or counterfactual savings.')


def window_mechanism(raw):
    ledger=competition(raw);origin=raw['runtime_window_begin_ps'];end=raw['makespan_ps']
    calls=raw['runtime_metadata']['calls'];token=calls[0]['token_ids'][0]
    reads=defaultdict(list);cache={};delivered={}
    array_cycles=Counter();array_macs=Counter();array_service=defaultdict(Counter)
    for event in raw['events']:
        kind=event['kind'];key=event.get('task')
        if kind in ('read_issue','read_deliver'):reads[key].append(event)
        elif kind in ('cache_operands_ready','npu_cached_operands_ready'):cache[key]=event['time_ps']
        elif kind=='data_deliver':delivered[event['edge']]=event['time_ps']
        elif kind in ('npu_epoch','npu_cycle'):
            array_cycles[key]+=event.get('cycles',1);array_macs[key]+=event['macs']
            work=event['service'] if kind=='npu_epoch' else {f:event[f] for f in raw['npu_execution']['plans'][key]['service']}
            array_service[key].update(work)
    kernels=raw['npu_execution']['kernels'];plans=raw['npu_execution']['plans']
    if set(array_cycles)!=set(kernels) or any(array_cycles[k]!=plans[k]['cycles'] or array_macs[k]!=plans[k]['macs'] or dict(array_service[k])!=plans[k]['service'] for k in kernels):
        raise ValueError('Observed array grants do not close actual shapes/service programs')
    chain=completion_chain(raw['graph'],ledger,origin,end);inputs=defaultdict(list)
    for edge in raw['graph']['data']:inputs[edge['consumer']].append(edge)
    for row in chain['tasks']:
        key=row['task'];o=row['operands_committed_ps'];witness=[]
        issued=sum(e['bytes'] for e in reads[key] if e['kind']=='read_issue')
        if row['admitted_ps']==o:witness.append('admission')
        if cache.get(key)==o:witness.append('cache_lookup_ready')
        last=max((e['time_ps'] for e in reads[key] if e['kind']=='read_deliver'),default=None)
        if last==o:witness.append('native_supply_chain_ready')
        witness.extend('tensor:'+e['id'] for e in inputs[key] if delivered.get(e['id'])==o)
        if not witness:raise ValueError('Operand readiness lacks an observed source boundary')
        row.update(operand_readiness_witness=witness,native_weight_bytes=issued)
    all_service=Counter()
    for values in array_service.values():all_service.update(values)
    expert_keys=[k for k in kernels if k.endswith(('/gate','/up','/down'))]
    profile=raw['npu_execution']['profile'];peak=profile['rows']*profile['columns']*profile['arrays']
    cycles=sum(array_cycles.values());macs=sum(array_macs.values());ec=sum(array_cycles[k] for k in expert_keys);em=sum(array_macs[k] for k in expert_keys)
    gateway=raw['native']['gateway_bytes'];native=sum(gateway.values())
    groups=[dict(layer=c['layer_id'],token_count=len(c['token_ids']),
        ordered_token_to_experts=c['token_to_experts'],expert_token_counts=c['expert_token_counts']) for c in calls]
    issue_times=[e['time_ps'] for events in reads.values() for e in events if e['kind']=='read_issue']
    delivery_times=[e['time_ps'] for events in reads.values() for e in events if e['kind']=='read_deliver']
    return dict(index=raw['runtime_metadata']['index'],phase=token[1],decode_step=token[-1],
        begin_ps=origin,makespan_ps=end,drained_ps=raw['drained_ps'],duration_ps=end-origin,
        groups=groups,expert_token_counts=[n for g in groups for n in g['expert_token_counts'].values()],
        cache_stats=raw['weight_cache']['stats'],native_bytes=native,gateway_bytes=gateway,
        maximum_gateway_bytes=max(gateway.values(),default=0),
        maximum_gateway_share=max(gateway.values())/native if native else None,
        supply_observation=dict(first_descriptor_issue_ps=min(issue_times) if issue_times else None,
            last_descriptor_delivery_ps=max(delivery_times) if delivery_times else None,
            scope='Observed complete supply-chain endpoints, including Native/Gateway/NoC service; not exclusive DRAM busy or additive stalls.'),
        array_macs=macs,array_service_cycles=cycles,array_service=dict(all_service),
        array_service_efficiency=macs/(peak*cycles),expert_array_macs=em,expert_array_service_cycles=ec,
        expert_array_service_efficiency=em/(peak*ec),shared_compute_service_ps=sum(raw['compute_busy_ps'].values()),
        sram_peak_bytes=raw['sram_peak_bytes'],completion_witness=chain,
        clusters=ledger['clusters'])


def phase_summary(rows):
    output={}
    for phase in ('prefill','decode'):
        selected=[r for r in rows if r['phase']==phase]
        if not selected:raise ValueError('Both captured phases required')
        cache=Counter();service=Counter();intervals=Counter();capacity=Counter();gateways=Counter();counts=[];active=[]
        macs=cycles=expert_macs=expert_cycles=initial_release=0
        for r in selected:
            cache.update(r['cache_stats']);service.update(r['array_service']);gateways.update(r['gateway_bytes'])
            intervals.update(r['completion_witness']['interval_totals_ps'])
            capacity.update(r['completion_witness']['capacity_intersections_ps'])
            initial_release+=r['completion_witness']['initial_release_ps']
            counts.extend(r['expert_token_counts']);active.extend(len(g['expert_token_counts']) for g in r['groups'])
            macs+=r['array_macs'];cycles+=r['array_service_cycles'];expert_macs+=r['expert_array_macs'];expert_cycles+=r['expert_array_service_cycles']
        peak=16384
        output[phase]=dict(windows=len(selected),tokens=sum(r['groups'][0]['token_count'] for r in selected),
            execution_latency_ps=sum(r['duration_ps'] for r in selected),drain_overhead_ps=sum(r['drained_ps']-r['makespan_ps'] for r in selected),
            duration_ps=distribution([r['duration_ps'] for r in selected]),active_experts_per_layer_invocation=distribution(active),
            tokens_per_active_expert=distribution(counts),cache_stats=dict(cache),native_bytes=sum(r['native_bytes'] for r in selected),
            gateway_bytes=dict(gateways),array_macs=macs,array_service_cycles=cycles,array_service=dict(service),
            array_service_efficiency=macs/(peak*cycles),expert_array_service_efficiency=expert_macs/(peak*expert_cycles),
            witnessed_interval_totals_ps=dict(intervals),witnessed_initial_release_ps=initial_release,
            witnessed_capacity_intersections_ps=dict(capacity),
            scope='Phases reported separately; expert distribution samples actual groups in bounded layer/microbatch invocations. Array efficiency uses observed reserved array cycles, not whole-machine duty or silicon utilization. Witnessed intervals partition completion chains, not all parallel task waits.')
    return output


def compare_cases(reference,candidate):
    if not reference.get('passed') or not candidate.get('passed'):raise ValueError('Completed accepted mechanisms required')
    for field in ('registration_sha256','cohort_sha256','machine_sha256','npu_profile','cache_budget'):
        if reference[field]!=candidate[field]:raise ValueError('Matched trace or hardware budget changed')
    left=reference['windows'];right=candidate['windows']
    if len(left)!=len(right):raise ValueError('Window horizons differ')
    pairs=[]
    for a,b in zip(left,right):
        if (a['index'],a['phase'],a['decode_step'],a['groups'],a['array_macs'],a['array_service_cycles'],a['array_service'])!=(b['index'],b['phase'],b['decode_step'],b['groups'],b['array_macs'],b['array_service_cycles'],b['array_service']):
            raise ValueError('Matched route groups or NPU arithmetic/service work changed')
        pairs.append(dict(index=a['index'],phase=a['phase'],decode_step=a['decode_step'],
            delta_ps=a['duration_ps']-b['duration_ps'],reference_ps=a['duration_ps'],candidate_ps=b['duration_ps'],
            reference_native_bytes=a['native_bytes'],candidate_native_bytes=b['native_bytes'],
            cache_class='both_zero_native' if a['native_bytes']==b['native_bytes']==0 else ('both_with_native' if a['native_bytes'] and b['native_bytes'] else 'mixed_native'),
            reference_gateway_bytes=a['gateway_bytes'],candidate_gateway_bytes=b['gateway_bytes'],
            reference_witness_intervals_ps=a['completion_witness']['interval_totals_ps'],
            candidate_witness_intervals_ps=b['completion_witness']['interval_totals_ps']))
    summaries={}
    for name in ('prefill','decode','both_zero_native','both_with_native','mixed_native'):
        selected=[p for p in pairs if p['phase']==name or p['phase']=='decode' and p['cache_class']==name]
        summaries[name]=dict(windows=len(selected),delta_ps=sum(p['delta_ps'] for p in selected),
            reference_ps=sum(p['reference_ps'] for p in selected),candidate_ps=sum(p['candidate_ps'] for p in selected))
    return dict(passed=True,phase_and_cache_groups=summaries,windows=pairs,
        scope='Signed paired deltas on identical actual routes and NPU work; observed cache traffic may differ. A witnessed-chain change is not a unique resource cause or counterfactual saving. Negative Phase-Split results are retained.')
