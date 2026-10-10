"""Independent omitted-clock/service accounting; no execution imports."""
from w2w.validation.interactive_compute import expand_interactive_compute


def audit_causal_boundary(raw):
    result=expand_interactive_compute(raw);meta=raw.get('causal_boundary')
    if meta is None:return dict(intervals=0,omitted_boundaries=0,bulk_services=0)
    if set(meta)!={'schema','attempts','intervals','bulk_services','contract'} or meta['schema']!=1:
        raise ValueError('Unknown causal boundary contract')
    tasks={t['id']:t for t in result['graph']['tasks']};tiles={t['id']:t for t in result['spec']['tiles']}
    periods={result['spec']['noc_period_ps'],result['spec']['dram_period_ps'],
             *(t['compute_period_ps'] for t in tiles.values())}
    services={(e['task'],e['time_ps']) for e in result['events'] if e['kind']=='stream_compute' and e['weight_bytes']}
    total=0;omitted=set();previous=-1
    for row in meta['intervals']:
        if set(row)!={'start_ps','resume_ps','limit_ps','task','first_service_ps','bulk_services','active_array',
                     'native_cycle','native_callbacks'}:
            raise ValueError('Invalid coordination interval')
        start,stop=row['start_ps'],row['resume_ps']
        if row['task'] not in tasks:raise ValueError('Unknown coordinated task')
        period=tiles[tasks[row['task']]['tile']]['compute_period_ps']
        n=len(range(start+period,stop,period))
        dram=result['spec']['dram_period_ps'];callbacks=row['native_callbacks'];cycle=row['native_cycle']
        if (not previous<=start<stop<=row['limit_ps']<=result['drained_ps']
                or start%period or stop%result['quantum_ps'] or row['first_service_ps']!=start+period
                or row['bulk_services']!=n or row['active_array'] is not True):
            raise ValueError('Coordination crosses time/service bounds')
        if (type(callbacks) is not int or callbacks<0 or type(cycle) is not int or cycle<0
                or callbacks and stop!=cycle*dram
                or not callbacks and (stop!=row['limit_ps'] or cycle!=stop//dram)):
            raise ValueError('Resume differs from first callback or certified cap')
        for at in range(start+period,stop,period):
            if (row['task'],at) not in services:raise ValueError('Missing bulk compute service')
        quantum=result['quantum_ps']
        if any(start<((t['release_ps']+quantum-1)//quantum)*quantum<stop for t in tasks.values()):
            raise ValueError('Coordination crosses external release')
        for p in periods:omitted.update(range((start//p+1)*p,stop,p))
        total+=n;previous=stop
    if total!=meta['bulk_services'] or len(meta['intervals'])>meta['attempts']:
        raise ValueError('Wrong coordination accounting')
    if total!=raw.get('interactive_compute',{}).get('bulk_services',0):
        raise ValueError('Compute bulk evidence differs from scheduler accounting')
    return dict(intervals=len(meta['intervals']),omitted_boundaries=len(omitted),bulk_services=total)
