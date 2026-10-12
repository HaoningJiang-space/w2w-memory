"""Independent folded-coordinate, work, storage and physical-grant conservation."""
from collections import Counter,defaultdict
from math import ceil


def row_work(kernel,plan,p):
    M,N,K=(kernel[f] for f in ('M','N','K'));row=plan['row_mapping']
    if plan.get('source_scale_bytes')!=4*ceil(N/128)*ceil(K/128):raise ValueError('Original source scale identity changed')
    fold=row['groups'];height=row['rows_per_group'];split=plan['k_partitions']
    if (p['rows'],p['columns'],p['arrays'])!=(16,16,64) or fold not in (2,4) or height*fold!=16:
        raise ValueError('Folded physical geometry changed')
    if kernel['weight_dtype']!='FP8_E4M3FN' or (N,K) not in ((128,4096),(4096,128)):
        raise ValueError('Unregistered folded precision/shape')
    if row['group_phase_skew_cycles']!=1:raise ValueError('Unqualified group phase policy')
    segments=defaultdict(list);weight_words=input_words=core=scale_routes=group_count=partial_values=0
    peak_partials=0
    for wave in plan['waves']:
        owners=set();inputs=Counter();owned=0
        core+=max(g['start_tick']+g['K']+height+p['columns']-2 for g in wave)
        for g in wave:
            a,q=g['array'],g['row_group'];m,n,k,x,y,z=(g[f] for f in ('m','n','k','M','N','K'))
            if not 0<=a<p['arrays'] or not 0<=q<fold or (a,q) in owners or g['start_tick']!=q:
                raise ValueError('Duplicated physical row owner or unqualified phase skew')
            owners.add((a,q))
            if not 0<x<=height or not 0<y<=p['columns'] or min(z,k+1)<1:
                raise ValueError('Logical tile does not fit its physical row group')
            if not 0<=m<m+x<=M or not 0<=n<n+y<=N or not 0<=k<k+z<=K or k%128 or z%128:
                raise ValueError('Coordinate or original scale-group coverage changed')
            segments[m,n,x,y].append((k,k+z));owned+=x*y;group_count+=1;partial_values+=x*y
            weight_words+=y*ceil(z/p['word_bytes']);scale_routes+=4*ceil(z/128)
            for token in range(m,m+x):
                for word in range(k*2//p['word_bytes'],(k+z)*2//p['word_bytes']):
                    inputs[token,word,g['start_tick']]+=1
        if owned>p['rows']*p['columns']*p['arrays']:raise ValueError('Live FP32 partials exceed physical accumulator cells')
        peak_partials=max(peak_partials,owned)
        input_words+=sum(ceil(v/p['input_broadcast_fanout']) for v in inputs.values())
    area=macs=0
    for (m,n,x,y),ranges in segments.items():
        end=0
        for a,b in sorted(ranges):
            if a!=end:raise ValueError('Missing or overlapping original K coordinates')
            end=b;macs+=x*y*(b-a)
        if end!=K or len(ranges)!=split:raise ValueError('Incomplete ordered K partials')
        area+=x*y
    expected={(0,n,M,min(16,N-n)) for n in range(0,N,16)}
    if set(segments)!=expected or area!=M*N or macs!=M*N*K or core!=plan['array_cycles']:
        raise ValueError('Folded output/math/core schedule does not close')
    cfg=p['arrays']*fold*32;word_buffers=p['arrays']*(p['rows']+p['columns']*fold)*p['word_bytes']
    scale_regs=max(sum(4*ceil(g['K']/128) for g in w) for w in plan['waves'])
    scratch=p['arrays']*(p['rows']*p['columns']*4+32)+word_buffers+cfg+scale_regs+M*N*split*4
    if row['configuration_bytes']!=cfg or row['word_buffer_bytes']!=word_buffers or row['scale_register_bytes']!=scale_regs or plan['scratch_bytes']!=scratch:
        raise ValueError('Unpaid row configuration/word/scale/partial storage')
    if row['independent_fp8_weight_lanes']!=p['arrays']*fold*p['columns'] or row['added_weight_lanes']!=p['arrays']*(fold-1)*p['columns']:
        raise ValueError('Row weight-injection capability is not declared')
    expected_work=dict(weight_sram_bytes=weight_words*p['word_bytes'],
        scale_sram_bytes=4*ceil(N/128)*ceil(K/128)+scale_routes,
        activation_sram_bytes=input_words*p['word_bytes']+cfg*len(plan['waves'])+(4*M*N*split if split>1 else 0),
        output_sram_bytes=4*partial_values+(4*M*N if split>1 else 0)+cfg*len(plan['waves'])+scale_routes,
        vector_ops=N*K+5*group_count+scale_routes//4+M*N*(split-1),
        accumulator_register_bytes=8*M*N*K+(8*M*N*split if split>1 else 0),
        activation_delivery_bytes=2*M*K*ceil(N/16))
    if plan['service']!=expected_work:raise ValueError('Folded operand/routing/reduction service not conserved')
    return expected_work


def audit_row_result(result,reference_audit):
    npu=result['npu_execution'];p=npu['profile'];plans=npu['plans'];kernels=npu['kernels']
    folded={k for k,v in plans.items() if 'row_mapping' in v}
    ordinary=dict(result);ordinary['npu_execution']=dict(npu,
        plans={k:v for k,v in plans.items() if k not in folded},kernels={k:v for k,v in kernels.items() if k not in folded})
    ordinary['events']=[e for e in result['events'] if not (e['kind'] in ('npu_epoch','npu_cycle') and e['task'] in folded)]
    base=reference_audit(ordinary)
    tasks={t['id']:t for t in result['graph']['tasks']}
    starts={e['task']:e['time_ps'] for e in result['events'] if e['kind']=='task_start'}
    finishes={e['task']:e['time_ps'] for e in result['events'] if e['kind']=='task_finish'}
    incoming=Counter()
    for edge in result['graph']['data']:incoming[edge['consumer']]+=edge['size_bytes']
    intervals=defaultdict(list);observed=defaultdict(list)
    for event in result['events']:
        if event['kind'] in ('npu_epoch','npu_cycle'):observed[event['task']].append(event)
    def peaks(value):
        if (value.get('macs',0)>16384 or max(value.get('weight_sram_bytes',0),value.get('scale_sram_bytes',0))>p['weight_read_bytes_per_cycle']
                or value.get('activation_sram_bytes',0)>p['activation_read_bytes_per_cycle']
                or value.get('output_sram_bytes',0)>p['output_write_bytes_per_cycle']
                or value.get('vector_ops',0)>p['vector_ops_per_cycle']
                or value.get('activation_delivery_bytes',0)>p['activation_read_bytes_per_cycle']
                or max(value.get('bank_peak_weight_bytes',0),value.get('bank_peak_activation_bytes',0))>p['bank_port_bytes_per_cycle']):
            raise ValueError('Folded shared MAC/word/bank/conversion grant exceeded')
    for key in folded:
        plan=plans[key];kernel=kernels[key];work=row_work(kernel,plan,p);task=tasks[key];es=observed[key]
        if task['scratch_bytes']<plan['scratch_bytes'] or task['compute_cycles']!=plan['cycles']:
            raise ValueError('Folded task context not funded')
        if incoming[key]!=kernel['M']*ceil(kernel['K']*2/32)*32:raise ValueError('Folded input storage identity differs')
        if not es:raise ValueError('No actual folded array grants')
        if es[0]['kind']=='npu_epoch':
            e=es[0]
            if len(es)!=1 or e['program_sha256']!=plan['program_sha256'] or e['service']!=work or e['cycles']!=plan['cycles'] or e['macs']!=plan['macs']:
                raise ValueError('Folded epoch does not execute its complete program')
            if e.get('source_scale_bytes')!=plan['source_scale_bytes']:raise ValueError('Folded epoch repeated or omitted original source scales')
            if e['end_ps']-e['time_ps']!=plan['cycles']*p['period_ps']:raise ValueError('Folded epoch timing changed')
            peaks(e['peak_service']);end=e['end_ps']
        else:
            if len(es)!=plan['cycles'] or sum(e['macs'] for e in es)!=plan['macs'] or any(e['program_cycle']!=i for i,e in enumerate(es)):
                raise ValueError('Folded cycles skipped/repeated mathematical work')
            if any(b['time_ps']-a['time_ps']!=p['period_ps'] for a,b in zip(es,es[1:])):raise ValueError('Nonpreemptive folded registers interrupted')
            for e in es:peaks(e)
            if (es[0]['phase']!='scale_load' or sum(e.get('source_scale_bytes',-1) for e in es)!=plan['source_scale_bytes']
                    or any(e.get('source_scale_bytes')!=(e['scale_sram_bytes'] if e['phase']=='scale_load' else 0) for e in es)):
                raise ValueError('Original scales and internal routing reads were conflated')
            if {f:sum(e[f] for e in es) for f in work}!=work:raise ValueError('Observed folded service differs')
            end=es[-1]['time_ps']+p['period_ps']
        if not starts[key]<=es[0]['time_ps']<end==finishes[key] or any(e['tile']!=task['tile'] or e['time_ps']%p['period_ps'] for e in es):
            raise ValueError('Folded owner/output escaped actual task clocks')
    for key,es in observed.items():
        if not es:continue
        end=es[0]['end_ps'] if es[0]['kind']=='npu_epoch' else es[-1]['time_ps']+p['period_ps']
        intervals[tasks[key]['tile']].append((es[0]['time_ps'],end,key))
    for tile,spans in intervals.items():
        spans.sort()
        if any(b[0]<a[1] for a,b in zip(spans,spans[1:])):raise ValueError('Row mapping creates a second free array owner')
        for e in result['events']:
            if e.get('tile')!=tile or e['kind'] not in ('compute_service','stream_compute'):continue
            if any(a<=e['time_ps']<b and e['task']!=key for a,b,key in spans):raise ValueError('Scalar grant overlaps folded array ownership')
    return dict(base,passed=True,kernels=len(kernels),macs=sum(v['macs'] for v in plans.values()),
        array_service_cycles=sum(v['cycles'] for v in plans.values()),folded_kernels=len(folded),
        scope='Actual Native/NoC execution plus folded coordinate, scale, MAC, shared-port, funded-state and nonpreemptive ownership audits. Row steering/injection is an explicit uncalibrated candidate capability; no equal-PPA or silicon claim.')
