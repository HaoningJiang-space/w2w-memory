"""Independent shape/word/partial conservation and shared-array ownership audit."""
from collections import Counter,defaultdict
from math import ceil
from bisect import bisect_right


def audit_npu_result(result):
    npu=result['npu_execution'];p=npu['profile'];tasks={t['id']:t for t in result['graph']['tasks']}
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
        segments=defaultdict(list);weight_words=0;input_words=0;tile_macs=0;core_cycles=0
        for wave in plan['waves']:
            if not 0<len(wave)<=p['arrays']:raise ValueError('Too many physical arrays in a wave')
            inp=Counter();core_cycles+=max(t['K'] for t in wave)+p['rows']+p['columns']-2
            for t in wave:
                if (t['M']>p['rows'] or t['N']>p['columns'] or min(t['M'],t['N'],t['K'])<1
                        or not 0<=t['m']<t['m']+t['M']<=M or not 0<=t['n']<t['n']+t['N']<=N):
                    raise ValueError('Illegal array tile dimensions')
                segments[t['m'],t['n'],t['M'],t['N']].append((t['k'],t['k']+t['K']))
                tile_macs+=t['M']*t['N']*t['K']
                weight_words+=t['N']*ceil(t['K']*bpp/p['word_bytes'])
                for r in range(t['m'],t['m']+t['M']):
                    for word in range(t['k']*2//p['word_bytes'],ceil((t['k']+t['K'])*2/p['word_bytes'])):
                        inp[r,word]+=1
            input_words+=sum(ceil(v/p['input_broadcast_fanout']) for v in inp.values())
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
            accumulator_register_bytes=8*M*N*K,
            activation_delivery_bytes=2*M*K*ceil(N/p['columns']))
        if dict(service[key])!=expected or plan['service']!=expected:raise ValueError('Operand/partial service conservation differs')
        buffers=p['arrays']*(p['rows']*p['columns']*4+(p['rows']+p['columns'])*p['word_bytes']+32)+4*M*N*split
        if tasks[key]['scratch_bytes']<buffers:raise ValueError('Uncharged array register/word/partial state')
    for tile,windows in intervals.items():
        ordered=sorted(windows)
        if any(b[0]<a[1] for a,b in zip(ordered,ordered[1:])):raise ValueError('Physical array ownership duplicated')
        for a,b,key in ordered:
            if not starts[key]<=a<b==finishes[key]:raise ValueError('Output released outside completed array interval')
        begin=[a for a,_,_ in ordered]
        for e in result['events']:
            if e['kind'] not in ('compute_service','stream_compute','npu_cycle'):continue
            if e['tile']!=tile:continue
            index=bisect_right(begin,e['time_ps'])-1
            if index>=0:
                a,b,key=ordered[index]
                if a<=e['time_ps']<b and e['task']!=key:raise ValueError('Shared arithmetic grant used inside an owned array interval')
    return dict(passed=True,kernels=len(npu['kernels']),macs=sum(macs.values()),
        array_service_cycles=sum(seen.values()),precision='BF16 activations, FP8/BF16 weights, ordered FP32 K partials',
        scope='Independent shape/word/fanout/partial/port/ownership audit; array-core cycle calibration is a separate SCALE-Sim receipt. No silicon or real numerical-inference claim.')
