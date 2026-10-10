"""Independent versioned compute-epoch evidence reader; no kernel imports."""
from copy import deepcopy


FIELDS = {'kind', 'schema', 'time_ps', 'task', 'tile', 'period_ps', 'cycles', 'weight_bytes', 'macs'}


def expand_compute_epochs(record):
    result = deepcopy(record)
    tasks = {r['id']: r for r in result['graph']['tasks']}
    tiles = {r['id']: r for r in result['spec']['tiles']}
    events = []
    for row in result['events']:
        if row['kind'] != 'compute_epoch':
            events.append(row)
            continue
        if set(row) != FIELDS or row['schema'] != 1 or row['task'] not in tasks:
            raise ValueError('Invalid compute epoch evidence')
        task = tasks[row['task']]; stream = task['stream']
        if stream is None or row['tile'] != task['tile']:
            raise ValueError('Compute epoch changes task identity')
        period = tiles[row['tile']]['compute_period_ps']
        reuse = stream['macs']//stream['weight_data_bytes']
        rate = min(stream['weight_read_bytes_per_cycle'], stream['macs_per_cycle']//reuse)
        if (any(type(row[k]) is not int or row[k] < 1 for k in
                ('time_ps', 'period_ps', 'cycles', 'weight_bytes', 'macs'))
                or row['time_ps'] % period or row['period_ps'] != period
                or row['weight_bytes'] != rate or row['macs'] != rate*reuse
                or row['time_ps']+(row['cycles']-1)*period >= result['drained_ps']):
            raise ValueError('Compute epoch violates service bounds')
        events.extend(dict(kind='stream_compute', time_ps=row['time_ps']+i*period,
            task=row['task'], tile=row['tile'], weight_bytes=rate, scale_bytes=0, macs=rate*reuse)
            for i in range(row['cycles']))
    # Preserve insertion order at equal times. The independent system audit
    # checks actual availability, single shared service and completion timing.
    result['events'] = events
    return result


def audit_compute_epoch_intervals(raw):
    """Cross-check efficiency receipts against full service, not their totals."""
    result=expand_compute_epochs(raw)
    metadata=raw.get('compute_epoch')
    if metadata is None:
        if any(e['kind']=='compute_epoch' for e in raw['events']):
            raise ValueError('Epoch evidence has no execution contract')
        return dict(intervals=0,batched_compute_cycles=0,omitted_boundaries=0)
    if metadata.get('schema')!=1 or metadata.get('evidence') not in ('full','compact'):
        raise ValueError('Unknown compute epoch contract')
    intervals=metadata['intervals'];tasks={t['id']:t for t in result['graph']['tasks']}
    tiles={t['id']:t for t in result['spec']['tiles']};consumed={};services={}
    for row in result['events']:
        if row['kind']=='stream_compute':
            key=row['task'];at=row['time_ps']
            if (key,at) in services:raise ValueError('Repeated compute service')
            services[key,at]=(consumed.get(key,0),row)
            consumed[key]=consumed.get(key,0)+row['weight_bytes']
    expected_fields={'start_ps','last_service_ps','resume_ps','task','cycles','consumed_before','consumed_after'}
    total=0;omitted=0;covered=set();markers=[]
    for interval in intervals:
        if set(interval)!=expected_fields or interval['task'] not in tasks:
            raise ValueError('Invalid epoch interval identity')
        task=tasks[interval['task']];rule=task['stream'];tile=task['tile'];period=tiles[tile]['compute_period_ps']
        if rule is None:raise ValueError('Epoch is not a streamed task')
        start,n=interval['start_ps'],interval['cycles'];reuse=rule['macs']//rule['weight_data_bytes']
        rate=min(rule['weight_read_bytes_per_cycle'],rule['macs_per_cycle']//reuse)
        last=start+(n-1)*period;resume=interval['resume_ps']
        if (type(n) is not int or n<2 or start%period or interval['last_service_ps']!=last
                or not last<resume<=last+period
                or interval['consumed_after']!=interval['consumed_before']+n*rate
                or not interval['consumed_after']<rule['weight_data_bytes']):
            raise ValueError('Epoch interval violates tail/time/work bounds')
        for ordinal in range(n):
            identity=(task['id'],start+ordinal*period)
            if identity in covered or identity not in services:raise ValueError('Missing/repeated epoch service')
            before,row=services[identity];covered.add(identity)
            if (before!=interval['consumed_before']+ordinal*rate or row['tile']!=tile
                    or row['scale_bytes']!=0 or row['weight_bytes']!=rate or row['macs']!=rate*reuse):
                raise ValueError('Epoch progress differs from independently expanded service')
        quantum=result['quantum_ps']
        if any(start<=((t['release_ps']+quantum-1)//quantum)*quantum<resume for t in tasks.values()):
            raise ValueError('Epoch crosses an external release')
        periods={result['spec']['noc_period_ps'],result['spec']['dram_period_ps'],
                 *(t['compute_period_ps'] for t in tiles.values())}
        entry=start-period
        omitted+=len({at for p in periods for at in range((entry//p+1)*p,resume,p)})
        markers.append(dict(kind='compute_epoch',schema=1,time_ps=start,task=task['id'],tile=tile,
            period_ps=period,cycles=n,weight_bytes=rate,macs=rate*reuse));total+=n
    if total!=metadata['batched_compute_cycles']:
        raise ValueError('Epoch total differs from actual service intervals')
    actual=[e for e in raw['events'] if e['kind']=='compute_epoch']
    if metadata['evidence']=='compact' and actual!=markers or metadata['evidence']=='full' and actual:
        raise ValueError('Epoch markers differ from declared evidence mode')
    return dict(intervals=len(intervals),batched_compute_cycles=total,omitted_boundaries=omitted)
