"""Independent event-ledger checks, without calling router or kernel accounting helpers."""
from collections import Counter


def audit_system_result(result):
    if result['schema'] not in ('w2w.system-execution.v2','w2w.system-execution.v3'):
        raise ValueError('Incompatible result scope')
    spec, graph = result['spec'], result['graph']
    links = {l['id']: l for l in spec['links']}
    tasks = {t['id']: t for t in graph['tasks']}
    capacities = {t['id']: t['sram_bytes'] for t in spec['tiles']}
    edge_bytes = {e['id']: e['size_bytes'] for e in graph['data']}
    starts, finishes, packets, delivered, requests = {}, {}, {}, set(), {}
    stages = {kind: set() for kind in ('mc_accept', 'native_accept', 'native_ready', 'mc_release', 'read_deliver')}
    sram, sram_peak, data, read, link_count, packet_flits = Counter(), Counter(), Counter(), Counter(), Counter(), Counter()
    slots = set()
    last = -1
    stream_ready,stream_scale,stream_consumed,stream_macs,stream_ticks=Counter(),Counter(),Counter(),Counter(),set()
    last_compute={}
    scale_consumed=Counter()
    for event in result['events']:
        at, kind = event['time_ps'], event['kind']
        if at < last: raise ValueError('Nonmonotonic event ledger')
        last = at
        if kind == 'packet_accept':
            key = event['packet']
            if key in packets: raise ValueError('Packet accepted twice')
            packets[key] = event
        elif kind == 'packet_deliver':
            key = event['packet']
            if key not in packets or key in delivered: raise ValueError('Unknown/duplicate delivery')
            for field in ('payload_bytes', 'traffic_class', 'src', 'dst'):
                if event[field] != packets[key][field]: raise ValueError('Packet identity changed')
            delivered.add(key)
        elif kind == 'link_send':
            key, link = event['packet'], links[event['link']]
            slot = event['resource'], at
            if slot in slots: raise ValueError('Two flits consumed the same physical link slot')
            slots.add(slot)
            if at % link['period_ps'] or key not in packets: raise ValueError('Invalid flit send')
            if event['resource'] != link['resource_id']: raise ValueError('Wrong physical resource')
            packet_flits[key, link['id'], event['flit']] += 1
            if packet_flits[key, link['id'], event['flit']] != 1: raise ValueError('Duplicated flit')
            link_count[link['id']] += 1
        elif kind == 'sram_change':
            tile = event['tile']; sram[tile] += event['bytes']
            if not 0 <= sram[tile] <= capacities[tile]: raise ValueError('SRAM capacity/lifetime violation')
            sram_peak[tile] = max(sram_peak[tile], sram[tile])
        elif kind == 'data_deliver':
            data[event['edge']] += event['bytes']
        elif kind == 'read_issue':
            if event['request'] in requests: raise ValueError('Repeated read issue')
            requests[event['request']] = event
        elif kind in stages:
            key = event['request']
            if key not in requests or key in stages[kind]: raise ValueError('Repeated/unknown transaction event')
            order = ('mc_accept', 'native_accept', 'native_ready', 'mc_release', 'read_deliver')
            index = order.index(kind)
            if index and key not in stages[order[index-1]]: raise ValueError('Transaction lifecycle reordered')
            stages[kind].add(key)
            if kind == 'read_deliver':
                issued = requests[key]
                for field in ('task', 'memory', 'bank', 'word_address', 'bytes'):
                    if event[field] != issued[field]: raise ValueError('Read address identity changed')
                read[event['task']] += event['bytes']
        elif kind == 'stream_operand_ready':
            task=tasks[event['task']];rule=task['stream']
            if event['object']!=rule['weight_object']:raise ValueError('Wrong streamed weight object')
            if event['object_offset']>=rule['weight_data_bytes']:stream_scale[event['task']]+=event['bytes']
            else:stream_ready[event['task']]+=event['bytes']
        elif kind == 'stream_compute':
            key=event['task'];rule=tasks[key]['stream']
            tick=(event['tile'],at)
            if key not in starts or key in finishes or tick in stream_ticks:raise ValueError('Invalid streamed engine service')
            stream_ticks.add(tick);last_compute[key]=at
            scale_consumed[key]+=event['scale_bytes']
            if (event['macs']>rule['macs_per_cycle'] or event['weight_bytes']>rule['weight_read_bytes_per_cycle']
                    or event['macs']*rule['weight_data_bytes']!=event['weight_bytes']*rule['macs']):
                raise ValueError('Streamed compute exceeds arithmetic/SRAM service')
            stream_consumed[key]+=event['weight_bytes'];stream_macs[key]+=event['macs']
            if (stream_consumed[key]>stream_ready[key] or stream_scale[key]!=rule['scale_bytes']
                    or scale_consumed[key]>rule['scale_bytes'] or
                    event['scale_bytes']+event['weight_bytes']>rule['weight_read_bytes_per_cycle']):
                raise ValueError('Streamed arithmetic consumed unavailable operands')
        elif kind == 'task_start':
            key = event['task']
            if key in starts: raise ValueError('Task started twice')
            for edge in graph['data']:
                if edge['consumer'] == key and data[edge['id']] != edge['size_bytes']:
                    raise ValueError('Consumer started before tensor delivery')
            for edge in graph['control']:
                if edge['consumer'] == key and edge['producer'] not in finishes:
                    raise ValueError('Control predecessor incomplete')
            if not tasks[key].get('stream') and read[key] != sum(r['size_bytes'] for r in tasks[key]['reads']):
                raise ValueError('Compute started before memory delivery')
            if tasks[key].get('stream') and stream_scale[key]!=tasks[key]['stream']['scale_bytes']:
                raise ValueError('Streamed GEMM started before scale delivery')
            for other in starts:
                if tasks[other]['tile'] == event['tile'] and other not in finishes:
                    raise ValueError('Compute engine overallocated')
            starts[key] = at
        elif kind == 'task_finish':
            key = event['task']
            period = next(t['compute_period_ps'] for t in spec['tiles'] if t['id'] == tasks[key]['tile'])
            rule=tasks[key].get('stream')
            if rule:
                if (stream_consumed[key]!=rule['weight_data_bytes'] or stream_macs[key]!=rule['macs']
                        or scale_consumed[key]!=rule['scale_bytes']
                        or read[key]!=sum(r['size_bytes'] for r in tasks[key]['reads']) or at!=last_compute[key]+period):
                    raise ValueError('Invalid streamed GEMM completion')
            elif key not in starts or at != starts[key]+tasks[key]['compute_cycles']*period:
                raise ValueError('Invalid compute duration')
            finishes[key] = at
    if (set(packets) != delivered or set(finishes) != set(tasks) or any(sram.values())
            or any(set(requests) != ids for ids in stages.values()) or dict(data) != edge_bytes):
        raise ValueError('Final byte/transaction/storage ledger did not drain')
    network = result['network']
    if network.get('event_level') == 'transaction':
        if (network['kind'] != 'native_boundary_booksim' or not network['drained']
                or network['accepted_packets'] != len(packets)
                or network['delivered_packets'] != len(delivered)
                or network['accepted_bytes'] != network['delivered_bytes']):
            raise ValueError('Native packet/byte ledger did not drain')
        # Fine channel slot checks run online from native per-flit observations.
        # Full flit histories are optional; transaction checks above remain independent.
        for key, count in network['link_flits'].items():
            if key not in links or count > result['drained_ps']//links[key]['period_ps']+1:
                raise ValueError('Native physical capacity exceeded')
        link_count = Counter(network['link_flits'])
    if dict(link_count) != network['link_flits'] or dict(sram_peak) != result['sram_peak_bytes']:
        raise ValueError('Recorded resource totals disagree with events')
    return dict(passed=True, packets=len(packets), read_descriptors=len(requests),
                read_words=sum(r['bytes']//32 for r in requests.values()), data_bytes=sum(data.values()),
                physical_link_flits=sum(link_count.values()), tasks=len(tasks))
