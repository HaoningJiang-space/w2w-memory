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
