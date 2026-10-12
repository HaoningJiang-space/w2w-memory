"""Independent shape/word/partial conservation and shared-array ownership audit."""
from collections import Counter,defaultdict
from math import ceil
from bisect import bisect_right


def audit_npu_result(result):
    if result['npu_execution'].get('execution_policy')=='row_mapping_v1':
        from .row_mapping import audit_row_result
        return audit_row_result(result,_audit_reference_npu_result)
    return _audit_reference_npu_result(result)


def _audit_reference_npu_result(result):
    npu=result['npu_execution'];p=npu['profile'];tasks={t['id']:t for t in result['graph']['tasks']}
    objects={o['id']:o for o in result['graph']['objects']};incoming=Counter();outgoing=Counter()
    for e in result['graph']['data']:
        incoming[e['consumer']]+=e['size_bytes'];outgoing[e['producer']]+=e['size_bytes']
    if p['rows']*p['columns']*p['arrays']!=16384:raise ValueError('Array peak changed original compute budget')
    intervals=defaultdict(list);cycles=defaultdict(list);seen={};macs=Counter();service=defaultdict(Counter)
    starts={e['task']:e['time_ps'] for e in result['events'] if e['kind']=='task_start'}
    finishes={e['task']:e['time_ps'] for e in result['events'] if e['kind']=='task_finish'}
    periods={t['id']:t['compute_period_ps'] for t in result['spec']['tiles']}
    fields=('weight_sram_bytes','scale_sram_bytes','activation_sram_bytes','output_sram_bytes','vector_ops',
            'accumulator_register_bytes','activation_delivery_bytes')
    def check_peak(row):
        if (row.get('macs',0)>p['rows']*p['columns']*p['arrays'] or
                row.get('weight_sram_bytes',0)+row.get('scale_sram_bytes',0)>p['weight_read_bytes_per_cycle'] or
                row.get('activation_sram_bytes',0)>p['activation_read_bytes_per_cycle'] or
                row.get('output_sram_bytes',0)>p['output_write_bytes_per_cycle'] or
                row.get('vector_ops',0)>p['vector_ops_per_cycle'] or
                row.get('activation_delivery_bytes',0)>p['activation_read_bytes_per_cycle'] or
                max(row.get('bank_peak_weight_bytes',0),row.get('bank_peak_activation_bytes',0))>p['bank_port_bytes_per_cycle']):
            raise ValueError('Array/SRAM/bank/conversion/fanout port overbooked')
    for e in result['events']:
        if e['kind'] not in ('npu_cycle','npu_epoch'):continue
        key=e['task'];plan=npu['plans'][key];tile=e['tile'];period=periods[tile]
        if e['time_ps']%period or tasks[key]['tile']!=tile:raise ValueError('Off-clock array service')
        if e['kind']=='npu_epoch':
            if key in seen or e['end_ps']-e['time_ps']!=plan['cycles']*period or e['cycles']!=plan['cycles']:
                raise ValueError('Invalid/duplicated array interval')
            if e['program_sha256']!=plan['program_sha256'] or e['service']!=plan['service']:raise ValueError('Internal array program identity changed')
            # Independent total and per-cycle checks below cover physical budget;
            # combined weight+scale peak is checked on separate program phases.
            peak=dict(e['peak_service']);peak['weight_sram_bytes']=max(peak['weight_sram_bytes'],peak.pop('scale_sram_bytes'))
            check_peak(peak)
            intervals[tile].append((e['time_ps'],e['end_ps'],key));seen[key]=e['cycles']
            service[key].update(e['service']);macs[key]+=e['macs']
        else:
            if e['program_cycle']!=len(cycles[key]):raise ValueError('Array cycle skipped or repeated')
            check_peak(e);cycles[key].append(e);macs[key]+=e['macs']
            service[key].update({f:e[f] for f in fields})
    for key,k in npu['kernels'].items():
        plan=npu['plans'][key];M,N,K=k['M'],k['N'],k['K'];split=plan['k_partitions']
        if key in cycles:
            es=cycles[key];seen[key]=len(es)
            intervals[tasks[key]['tile']].append((es[0]['time_ps'],es[-1]['time_ps']+periods[tasks[key]['tile']],key))
            if any(b['time_ps']-a['time_ps']!=periods[tasks[key]['tile']] for a,b in zip(es,es[1:])):
                raise ValueError('Reference nonpreemptive register ownership interrupted')
        if seen.get(key)!=plan['cycles'] or plan['cycles']!=tasks[key]['compute_cycles'] or macs[key]!=M*N*K:
            raise ValueError('Actual shape/cycle/MAC work differs')
        bpp=1 if k['weight_dtype']=='FP8_E4M3FN' else 2
        padded_input=M*ceil(K*2/32)*32
        virtual=k['weight_object'] not in objects
        if incoming[key]!=padded_input+(N*ceil(K*bpp/32)*32 if virtual else 0):raise ValueError('GEMM operand/word-padding storage differs from actual shape')
        segments=defaultdict(list);weight_words=0;input_words=0;tile_macs=0;core_cycles=0
        for wave in plan['waves']:
            if not 0<len(wave)<=p['arrays']:raise ValueError('Too many physical arrays in a wave')
            inp=Counter();core_cycles+=max(t['K'] for t in wave)+p['rows']+p['columns']-2
            for t in wave:
                if (t['M']>p['rows'] or t['N']>p['columns'] or min(t['M'],t['N'],t['K'])<1
                        or not 0<=t['m']<t['m']+t['M']<=M or not 0<=t['n']<t['n']+t['N']<=N):
                    raise ValueError('Illegal array tile dimensions')
                segments[t['m'],t['n'],t['M'],t['N']].append((t['k'],t['k']+t['K']))
                alignment=128 if bpp==1 else 16
                if t['k']%alignment or t['k']+t['K']<K and (t['k']+t['K'])%alignment:
                    raise ValueError('K partition breaks original FP8 scale/BF16 word contract')
                tile_macs+=t['M']*t['N']*t['K']
                weight_words+=t['N']*ceil(t['K']*bpp/p['word_bytes'])
                for r in range(t['m'],t['m']+t['M']):
                    for word in range(t['k']*2//p['word_bytes'],ceil((t['k']+t['K'])*2/p['word_bytes'])):
                        inp[r,word]+=1
            input_words+=sum(ceil(v/p['input_broadcast_fanout']) for v in inp.values())
        expected_tiles={(m,n,min(p['rows'],M-m),min(p['columns'],N-n)) for m in range(0,M,p['rows']) for n in range(0,N,p['columns'])}
        if set(segments)!=expected_tiles:raise ValueError('Missing/overlapping output tile coverage')
        area=0
        for (m,n,a,b),ranges in segments.items():
            at=0
            for x,y in sorted(ranges):
                if x!=at:raise ValueError('Missing/overlapping hidden-reduction range')
                at=y
            if at!=K or len(ranges)!=split:raise ValueError('Incomplete K reduction')
            area+=a*b
        if area!=M*N or tile_macs!=M*N*K or plan['array_cycles']!=core_cycles:
            raise ValueError('Array output/reduction coverage differs')
        expected=dict(weight_sram_bytes=weight_words*p['word_bytes'],
            scale_sram_bytes=4*ceil(N/128)*ceil(K/128) if bpp==1 else 0,
            activation_sram_bytes=input_words*p['word_bytes']+(4*M*N*split if split>1 else 0),
            output_sram_bytes=4*M*N*split+(4*M*N if split>1 else 0),
            vector_ops=(ceil(M/p['rows'])*N*K if bpp==1 else 0)+M*N*(split-1),
            accumulator_register_bytes=8*M*N*K+(8*M*N*split if split>1 else 0),
            activation_delivery_bytes=2*M*K*ceil(N/p['columns']))
        if dict(service[key])!=expected or plan['service']!=expected:raise ValueError('Operand/partial service conservation differs')
        if split>1:
            expected_reduction=ceil(M*N*4/p['activation_read_bytes_per_cycle'])+(split-1)*max(
                ceil(M*N*4/p['activation_read_bytes_per_cycle']),ceil(M*N/p['vector_ops_per_cycle']))+ceil(M*N*4/p['output_write_bytes_per_cycle'])
            scale_cycles=ceil(expected['scale_sram_bytes']/p['weight_read_bytes_per_cycle'])
            partial_cycles=sum(ceil(sum(t['M']*t['N']*4 for t in w)/p['output_write_bytes_per_cycle']) for w in plan['waves'])
            if plan['cycles']!=core_cycles+plan['bank_stall_cycles']+scale_cycles+partial_cycles+expected_reduction:
                raise ValueError('Ordered K additions or final output store did not pay their causal cycles')
        buffers=p['arrays']*(p['rows']*p['columns']*4+(p['rows']+p['columns'])*p['word_bytes']+32)+4*M*N*split
        if tasks[key]['scratch_bytes']<buffers:raise ValueError('Uncharged array register/word/partial state')
    aux=npu.get('auxiliary',{});done=defaultdict(Counter);aux_ticks=Counter();expected_aux={}
    limits=dict(weight_sram_bytes=p['weight_read_bytes_per_cycle'],activation_sram_bytes=p['activation_read_bytes_per_cycle'],
        output_sram_bytes=p['output_write_bytes_per_cycle'],vector_ops=p['vector_ops_per_cycle'],activation_delivery_bytes=p['activation_read_bytes_per_cycle'])
    for key,work in aux.items():
        phases=work.get('phases') or (dict(work,cycles_floor=1),);code=[]
        if any(sum(v.get(f,0) for v in phases)!=work.get(f,0) for f in limits):raise ValueError('Vector phase work changed')
        for v in phases:
            count=max(v.get('cycles_floor',1),max(ceil(v.get(f,0)/limit) for f,limit in limits.items()))
            if tasks[key]['scratch_bytes']+outgoing[key]<v.get('output_sram_bytes',0):raise ValueError('Vector output storage was not owned before production')
            for tick in range(count):
                row={f:min(max(0,v.get(f,0)-tick*limit),limit) for f,limit in limits.items()}
                first=count-ceil(v.get('output_sram_bytes',0)/limits['output_sram_bytes'])
                row['output_sram_bytes']=min(max(0,v.get('output_sram_bytes',0)-max(0,tick-first)*limits['output_sram_bytes']),limits['output_sram_bytes']) if tick>=first else 0
                code.append(row)
        expected_aux[key]=code
    for e in result['events']:
        if e['kind']=='compute_service' and e['task'] in aux:
            key=e['task'];tick=aux_ticks[key];aux_ticks[key]+=1
            if (e['tile']!=tasks[key]['tile'] or e['time_ps']%periods[e['tile']]
                    or not starts[key]<=e['time_ps']<finishes[key] or e['cycles']!=1):
                raise ValueError('Vector service escaped its physical task/clock/grant')
            if tick>=len(expected_aux[key]):raise ValueError('Repeated vector phase grant')
            for field in limits:
                expected=expected_aux[key][tick][field]
                if e.get(field)!=expected:raise ValueError('Vector/SRAM operation exceeded or omitted its actual grant')
                done[key][field]+=e[field]
    for key,work in aux.items():
        if any(done[key][f]!=work.get(f,0) for f in limits) or aux_ticks[key]!=tasks[key]['compute_cycles'] or aux_ticks[key]!=len(expected_aux[key]):raise ValueError('Vector/KV/transpose service not closed')
    grants=defaultdict(list)
    for e in result['events']:
        if e['kind'] in ('compute_service','stream_compute','npu_cycle'):grants[e['tile']].append(e)
    for tile,es in grants.items():
        if len({e['time_ps'] for e in es})!=len(es):raise ValueError('Repeated shared compute grant at one physical clock')
    for tile,windows in intervals.items():
        ordered=sorted(windows)
        if any(b[0]<a[1] for a,b in zip(ordered,ordered[1:])):raise ValueError('Physical array ownership duplicated')
        for a,b,key in ordered:
            if not starts[key]<=a<b==finishes[key]:raise ValueError('Output released outside completed array interval')
        begin=[a for a,_,_ in ordered]
        for e in grants[tile]:
            index=bisect_right(begin,e['time_ps'])-1
            if index>=0:
                a,b,key=ordered[index]
                if a<=e['time_ps']<b and e['task']!=key:raise ValueError('Shared arithmetic grant used inside an owned array interval')
    return dict(passed=True,kernels=len(npu['kernels']),macs=sum(macs.values()),
        array_service_cycles=sum(seen.values()),precision='BF16 activations, FP8/BF16 weights, ordered FP32 K partials',
        scope='Independent shape/word/fanout/partial/port/ownership audit; array-core cycle calibration is a separate SCALE-Sim receipt. No silicon or real numerical-inference claim.')
