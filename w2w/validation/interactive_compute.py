"""Independent service-interval decoder/audit, with no execution imports."""
from collections import defaultdict
from copy import deepcopy


MARKER_FIELDS = {'kind', 'schema', 'time_ps', 'task', 'tile', 'cycles',
                 'period_ps', 'weight_bytes', 'macs', 'tie_runs'}
INTERVAL_FIELDS = {'task', 'tile', 'start_ps', 'cycles', 'period_ps', 'weight_bytes',
                   'macs', 'consumed_before', 'consumed_after', 'committed_prefix_bytes',
                   'transport_live', 'reads_live', 'native_live'}


def expand_interactive_compute(record):
    result = deepcopy(record)
    tasks = {r['id']: r for r in result['graph']['tasks']}
    tiles = {r['id']: r for r in result['spec']['tiles']}
    ordinary, compressed = defaultdict(list), {}
    for row in result['events']:
        if row['kind'] != 'interactive_compute_epoch':
            ordinary[row['time_ps']].append(row)
            continue
        if set(row) != MARKER_FIELDS or row['schema'] != 1 or row['task'] not in tasks:
            raise ValueError('Invalid interactive epoch marker')
        task = tasks[row['task']]; rule = task['stream']
        if rule is None or task['tile'] != row['tile']:
            raise ValueError('Interactive epoch changes task identity')
        period = tiles[row['tile']]['compute_period_ps']
        reuse = rule['macs']//rule['weight_data_bytes']
        rate = min(rule['weight_read_bytes_per_cycle'], rule['macs_per_cycle']//reuse)
        if (any(type(row[k]) is not int or row[k] < 1 for k in
                ('cycles', 'time_ps', 'period_ps', 'weight_bytes', 'macs'))
                or row['time_ps'] % period or row['period_ps'] != period
                or row['weight_bytes'] != rate or row['macs'] != rate*reuse):
            raise ValueError('Interactive epoch changes compute service')
        ties = row['tie_runs']
        if (not isinstance(ties,list) or not ties or any(not isinstance(t, list) or len(t) != 2
                or any(type(v) is not int or v < 0 for v in t) for t in ties)
                or ties[0][0] != 0
                or any(a[0] >= b[0] for a, b in zip(ties, ties[1:]))
                or ties[-1][0] >= row['cycles']):
            raise ValueError('Invalid equal-time service insertion order')
        pointer = 0
        for ordinal in range(row['cycles']):
            if pointer+1 < len(ties) and ties[pointer+1][0] == ordinal:
                pointer += 1
            at = row['time_ps']+ordinal*period
            if at >= result['drained_ps'] or at in compressed:
                raise ValueError('Overlapping or undrained interactive service')
            compressed[at] = (ties[pointer][1], dict(kind='stream_compute', time_ps=at,
                task=row['task'], tile=row['tile'], weight_bytes=rate, scale_bytes=0, macs=rate*reuse))
    events = []
    for at in sorted(ordinary.keys() | compressed.keys()):
        rows = ordinary[at]
        if at in compressed:
            before, service = compressed[at]
            if before > len(rows):
                raise ValueError('Interactive service refers to missing same-time events')
            rows.insert(before, service)
        events.extend(rows)
    result['events'] = events
    return result


def audit_interactive_compute(raw):
    result = expand_interactive_compute(raw)
    meta = raw.get('interactive_compute')
    markers = [e for e in raw['events'] if e['kind'] == 'interactive_compute_epoch']
    if meta is None:
        if markers:raise ValueError('Interactive marker without contract')
        return dict(intervals=0, batched_compute_cycles=0, weight_services=sum(
            e['kind']=='stream_compute' and e['weight_bytes']>0 for e in result['events']),
            arithmetic_updates=None, overlapping_intervals=0, partial_prefix_intervals=0)
    if (set(meta) != {'schema','evidence','intervals','ordinary_weight_updates','batch_updates',
                     'batched_compute_cycles','compute_service_visits','contract'}
            or meta['schema'] != 1 or meta['evidence'] not in ('full','compact')
            or result['compute_execution']['contexts_per_cluster'] != 1
            or result['operand_readiness']['policy'] != 'contiguous_prefix'):
        raise ValueError('Unsupported interactive compute contract')
    tasks = {r['id']: r for r in result['graph']['tasks']}
    tiles = {r['id']: r for r in result['spec']['tiles']}
    chunks, ready, consumed, services = defaultdict(set), defaultdict(int), defaultdict(int), {}
    fragment = result['spec']['memory_request_bytes']
    for row in result['events']:
        key = row.get('task')
        if row['kind'] == 'stream_operand_ready':
            rule = tasks[key]['stream']; offset = row['object_offset']
            if offset < rule['weight_data_bytes']:
                chunks[key].add(offset)
                while ready[key] in chunks[key]:
                    ready[key] = min(ready[key]+fragment, rule['weight_data_bytes'])
                    if ready[key] == rule['weight_data_bytes']:break
        elif row['kind'] == 'stream_compute' and row['weight_bytes']:
            identity = (key,row['time_ps'])
            if identity in services:raise ValueError('Repeated interactive service')
            services[identity] = (consumed[key], ready[key], row)
            consumed[key] += row['weight_bytes']
    total = 0; covered = set(); overlap = 0; partial = 0
    intervals = meta['intervals']
    for interval in intervals:
        if set(interval) != INTERVAL_FIELDS or interval['task'] not in tasks:
            raise ValueError('Invalid interactive interval')
        task = tasks[interval['task']]; rule = task['stream']; period = tiles[task['tile']]['compute_period_ps']
        n, start = interval['cycles'], interval['start_ps']
        if (rule is None or type(n) is not int or n < 1 or interval['tile'] != task['tile']
                or interval['period_ps'] != period or start % period
                or any(type(interval[k]) is not bool for k in ('transport_live','reads_live','native_live'))):
            raise ValueError('Invalid interactive time/context identity')
        reuse = rule['macs']//rule['weight_data_bytes']
        rate = min(rule['weight_read_bytes_per_cycle'], rule['macs_per_cycle']//reuse)
        if (interval['weight_bytes'] != rate or interval['macs'] != rate*reuse
                or interval['consumed_after'] != interval['consumed_before']+n*rate
                or not interval['consumed_after'] < rule['weight_data_bytes']
                or interval['consumed_after'] > interval['committed_prefix_bytes']):
            raise ValueError('Interactive interval crosses committed frontier or task tail')
        for ordinal in range(n):
            identity = (task['id'],start+ordinal*period)
            if identity in covered or identity not in services:raise ValueError('Missing/overlapping interval service')
            before, prefix, row = services[identity]; covered.add(identity)
            if (before != interval['consumed_before']+ordinal*rate or row['weight_bytes'] != rate
                    or row['scale_bytes'] or row['tile'] != task['tile'] or row['macs'] != rate*reuse
                    or ordinal == 0 and prefix != interval['committed_prefix_bytes']):
                raise ValueError('Interactive interval differs from causal service ledger')
        # Independent overlap witness: a later descriptor commits during the
        # service interval. This requires actual continued cross-component work.
        end = start+(n-1)*period
        overlap += any(e['kind']=='stream_operand_ready' and e['task']==task['id']
                       and start < e['time_ps'] <= end for e in result['events'])
        partial += interval['committed_prefix_bytes'] < rule['weight_data_bytes']
        total += n
    if (total != meta['batched_compute_cycles'] or total != meta['compute_service_visits']
            or len(intervals) != meta['batch_updates']
            or len(services)-total != meta['ordinary_weight_updates']):
        raise ValueError('Interactive update count differs from actual services')
    if meta['evidence']=='full' and markers or meta['evidence']=='compact' and len(markers)!=len(intervals):
        raise ValueError('Interactive evidence mode differs from interval count')
    if meta['evidence']=='compact':
        for marker, interval in zip(sorted(markers,key=lambda r:r['time_ps']), intervals):
            if any(marker[a]!=interval[b] for a,b in (
                ('time_ps','start_ps'),('task','task'),('tile','tile'),('cycles','cycles'),
                ('period_ps','period_ps'),('weight_bytes','weight_bytes'),('macs','macs'))):
                raise ValueError('Marker differs from execution interval')
    return dict(intervals=len(intervals), batched_compute_cycles=total, weight_services=len(services),
        arithmetic_updates=meta['ordinary_weight_updates']+meta['batch_updates'],
        overlapping_intervals=overlap, partial_prefix_intervals=partial)
