"""Audit every dynamic array tick against committed row-major weight coordinates."""
from collections import Counter,defaultdict
from dataclasses import asdict
from math import ceil
from bisect import bisect_right

from w2w.architecture.npu_profile import NPUProfile
from w2w.system.operand_streaming import streaming_program


def audit_stream_result(result,reference_audit):
    npu=result['npu_execution'];p=NPUProfile(**npu['profile']);plans=npu['plans'];kernels=npu['kernels']
    streamed={k for k,v in plans.items() if 'streaming' in v};codes={};required={}
    tasks={t['id']:t for t in result['graph']['tasks']};input_edges=defaultdict(list)
    for e in result['graph']['data']:input_edges[e['consumer']].append(e['id'])
    for key in streamed:
        k=kernels[key];code,plan,mask=streaming_program(k['M'],k['N'],k['K'],k['weight_dtype'],p)
        if plan!=plans[key] or tasks[key]['compute_cycles']!=plan['cycles'] or tasks[key]['scratch_bytes']<plan['scratch_bytes']:
            raise ValueError('Dynamic program or funded readiness ROM/state changed')
        if result['spec']['memory_request_bytes']!=4096 or result['operand_readiness']['policy']!='contiguous_prefix':
            raise ValueError('Canonical paid descriptor tracking changed')
        codes[key]=code;required[key]=mask
    committed=Counter();scale_bytes=Counter();starts={};finishes={};inputs={};cursors=Counter();waits=Counter();last={};checked=Counter();waiting={}
    body_events=[];body_plans=dict(plans);body_tasks=[]
    for task in result['graph']['tasks']:
        if task['id'] in streamed:body_tasks.append(dict(task,compute_cycles=plans[task['id']]['streaming']['base_plan']['cycles']))
        else:body_tasks.append(task)
    for key in streamed:body_plans[key]=plans[key]['streaming']['base_plan']
    observed=defaultdict(Counter);body_cursor=Counter()
    for e in result['events']:
        key=e.get('task');kind=e['kind'];at=e['time_ps']
        if kind=='data_deliver':inputs[e['edge']]=at
        if kind=='task_start':
            starts[key]=at
            if key in streamed and any(edge not in inputs or inputs[edge]>at for edge in input_edges[key]):
                raise ValueError('Partial array acquisition preceded complete input activation')
        elif kind=='task_finish':finishes[key]=at
        if key not in streamed:
            body_events.append(e);continue
        k=kernels[key];data_bytes=k['N']*k['K'];scales=4*ceil(k['N']/128)*ceil(k['K']/128)
        if kind=='cache_operands_ready':committed[key]=(1<<plans[key]['streaming']['fragments'])-1;scale_bytes[key]=scales
        elif kind=='stream_operand_ready':
            offset,size=e['object_offset'],e['bytes']
            if e['object']!=k['weight_object']:raise ValueError('Streaming validity belongs to a different matrix')
            if offset>=data_bytes:scale_bytes[key]+=size
            else:
                if offset%4096 or size!=min(4096,data_bytes-offset):raise ValueError('Invalid original weight fragment')
                bit=1<<(offset//4096)
                if committed[key]&bit:raise ValueError('Descriptor committed twice')
                committed[key]|=bit
        if key in waiting and kind in ('stream_operand_ready','cache_operands_ready'):
            need=required[key][cursors[key]]
            if need&~committed[key]==0 and waiting[key]['ready_ps'] is None:waiting[key]['ready_ps']=at
        if kind not in ('npu_cycle','npu_operand_wait_start','npu_operand_wait_end'):
            body_events.append(e);continue
        cursor=cursors[key]
        if cursor>=len(codes[key]) or e['program_cycle']!=cursor or at%p.period_ps or e['tile']!=tasks[key]['tile']:
            raise ValueError('Dynamic instruction repeated/skipped or escaped physical clock')
        if key not in starts or at<starts[key] or (kind!='npu_operand_wait_end' and key in last and at-last[key]!=p.period_ps):
            raise ValueError('Unaccounted gap in retained array ownership')
        need=required[key][cursor]
        if kind=='npu_operand_wait_start':
            if not need&~committed[key] or e['required_mask']!=hex(need) or e['committed_mask']!=hex(committed[key]):
                raise ValueError('Operand stall lacks actual missing descriptors')
            if key in waiting:raise ValueError('Nested operand wait')
            waiting[key]=dict(begin_ps=at,ready_ps=None);continue
        if kind=='npu_operand_wait_end':
            span=waiting.pop(key,None)
            if span is None or span['ready_ps'] is None or e['begin_ps']!=span['begin_ps'] or e['cycles']*p.period_ps!=at-span['begin_ps']:
                raise ValueError('Operand wait interval does not conserve its retained clocks')
            if at!=ceil(span['ready_ps']/p.period_ps)*p.period_ps:raise ValueError('Operand wait extends past its actual first-ready clock')
            waits[key]+=e['cycles'];last[key]=at-p.period_ps;continue
        last[key]=at
        if need&~committed[key] or scale_bytes[key]!=scales:raise ValueError('MAC/probe consumed uncommitted original weights/scales')
        row=codes[key][cursor]
        if any(e.get(f)!=v for f,v in asdict(row).items()):raise ValueError('Actual dynamic grant differs from its paid instruction')
        if row.phase=='operand_probe':checked[key]|=need
        elif row.phase=='readiness_rom_build':pass
        else:
            # Independently recover row-major coordinates from the original
            # OS geometry, without accepting a byte prefix as a K tile.
            if row.phase in ('array','array_input_stall'):
                actual=0
                for tile in plans[key]['waves'][row.wave]:
                    for output in range(tile['n'],tile['n']+tile['N']):
                        local_k=row.array_tick-(output-tile['n'])
                        if 0<=local_k<tile['K']:
                            actual|=1<<((output*k['K']+tile['k']+local_k)//4096)
                if actual!=need or actual&~checked[key]:raise ValueError('Coordinate readiness bypassed its paid probe')
            body_events.append(dict(e,program_cycle=body_cursor[key]));body_cursor[key]+=1
        for f in plans[key]['service']:observed[key][f]+=e[f]
        cursors[key]+=1
    for key in streamed:
        plan=plans[key]
        if cursors[key]!=plan['cycles'] or dict(observed[key])!=plan['service'] or last[key]+p.period_ps!=finishes[key]:
            raise ValueError('Dynamic output/service ownership did not close')
        if waits[key]!=npu['operand_wait_cycles'].get(key,0):raise ValueError('Dynamic wait count differs')
    if waiting:raise ValueError('Dynamic result has live operand wait ownership')
    # ROM construction, probes and idle operand clocks own the same physical
    # arrays as the OS body. Removing them below must not create free grants.
    owners=defaultdict(list)
    for key in kernels:owners[tasks[key]['tile']].append((starts[key],finishes[key],key))
    for tile,spans in owners.items():
        spans.sort()
        if any(b[0]<a[1] for a,b in zip(spans,spans[1:])):
            raise ValueError('Streaming startup/probe/wait created overlapping array owners')
        begin=[a for a,_,_ in spans]
        for event in result['events']:
            if event.get('tile')!=tile or event['kind'] not in ('compute_service','stream_compute','npu_cycle','npu_epoch'):continue
            index=bisect_right(begin,event['time_ps'])-1
            if index>=0:
                a,b,key=spans[index]
                if a<=event['time_ps']<b and event['task']!=key:
                    raise ValueError('Other shared compute grant used inside a streaming owner interval')
    body=dict(result,events=body_events,graph=dict(result['graph'],tasks=body_tasks),
        npu_execution=dict(npu,plans=body_plans))
    # Complete native events remain unchanged. Only paid probe/stall records
    # are removed for the separate existing OS work/port/ownership audit.
    reference_audit(body,allow_gaps=True)
    return dict(passed=True,kernels=len(kernels),macs=sum(v['macs'] for v in plans.values()),
        array_service_cycles=sum(v['cycles'] for v in plans.values()),streamed_kernels=len(streamed),operand_wait_cycles=sum(waits.values()),
        scope='All original OS work, ports, words, FP32 partials and owners audited; every probe/MAC checks original committed N/K descriptors/scales and full input. Extra readiness ROM/state/probe service is funded. No free context/cache release, epoch bypass, original-step checkpoint or silicon claim.')
