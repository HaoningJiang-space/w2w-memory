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
    service_cycles=Counter();contexts=result.get('compute_execution',{}).get('contexts_per_cluster',1)
    incoming={k:[] for k in tasks};control={k:[] for k in tasks}
    for edge in graph['data']:incoming[edge['consumer']].append(edge)
    for edge in graph['control']:control[edge['consumer']].append(edge['producer'])
    engine_slots,context_peak=Counter(),Counter()
    cache=result.get('weight_cache');cache_entries={t:{} for t in capacities}
    cache_valid=set();cache_pins=Counter();cache_lookups={};cache_used=Counter();cache_peak=Counter();cache_stats=Counter()
    cache_lookup_times={};cache_lookup_done=set();cache_seen=set();lookup_live=Counter();last_lookup_at=Counter()
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
            if cache and tasks[event['task']]['stream'] and event['task'] not in cache_lookup_done:
                raise ValueError('Cache miss issued before finite tag lookup')
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
        elif kind in ('cache_initial_resident','cache_lookup','cache_evict','cache_fill'):
            if not cache:raise ValueError('Cache event without a declared finite cache')
            tile,obj=event['tile'],event['object'];identity=(tile,obj);entries=cache_entries[tile]
            if kind=='cache_initial_resident':
                if obj in entries:raise ValueError('Duplicate initial cache object')
                entries[obj]=event['bytes'];cache_used[tile]+=event['bytes'];cache_valid.add(identity)
                cache_stats['initial_bytes']+=event['bytes']
                cache_seen.add(identity)
            elif kind=='cache_lookup':
                key=event['task'];rule=tasks[key]['stream']
                if key in cache_lookups or obj!=rule['weight_object']:raise ValueError('Invalid/repeated cache lookup')
                cache_lookups[key]=identity;cache_pins[identity]+=1
                cache_lookup_times[key]=event['available_ps'];lookup_live[tile]+=1
                if lookup_live[tile]>cache['lookup_slots_per_cluster'] or event['available_ps']<=last_lookup_at[tile]:
                    raise ValueError('Cache tag lookup port/slots overbooked')
                last_lookup_at[tile]=event['available_ps']
                if event['previously_resident']!=(identity in cache_seen):raise ValueError('Cache reload provenance changed')
                cache_seen.add(identity)
                if event['hit']:
                    if identity not in cache_valid or entries[obj]!=event['bytes']:raise ValueError('Cache hit on missing/unfilled data')
                    cache_stats['hit_bytes']+=event['bytes']
                else:
                    if obj in entries:raise ValueError('Duplicate cache fill reservation')
                    entries[obj]=event['bytes'];cache_used[tile]+=event['bytes'];cache_stats['miss_bytes']+=event['bytes']
                    cache_stats['reload_bytes' if event['previously_resident'] else 'compulsory_bytes']+=event['bytes']
            elif kind=='cache_evict':
                if obj not in entries or cache_pins[identity] or identity not in cache_valid:
                    raise ValueError('Eviction removed filling/in-use/unowned data')
                cache_used[tile]-=entries.pop(obj);cache_valid.remove(identity)
                cache_stats['evictions']+=1;cache_stats['evicted_bytes']+=event['bytes']
            else:
                key=event['task']
                if cache_lookups.get(key)!=identity or identity in cache_valid or read[key]!=sum(r['size_bytes'] for r in tasks[key]['reads']):
                    raise ValueError('Cache object marked ready without delivered bytes')
                cache_valid.add(identity)
            cache_peak[tile]=max(cache_peak[tile],cache_used[tile])
            if cache_used[tile]>cache['data_bytes_per_cluster'] or len(entries)>cache['entries_per_cluster']:
                raise ValueError('Finite distributed cache overflow')
        elif kind=='cache_lookup_complete':
            key=event['task']
            if key in cache_lookup_done or cache_lookup_times.get(key)!=at:raise ValueError('Cache tag lookup completed at wrong boundary')
            cache_lookup_done.add(key);lookup_live[event['tile']]-=1
        elif kind=='cache_operands_ready':
            key=event['task'];identity=cache_lookups.get(key);rule=tasks[key]['stream']
            if key not in cache_lookup_done or identity not in cache_valid or event['object']!=rule['weight_object'] or not cache_pins[identity]:
                raise ValueError('Cache operand availability is unowned')
            read[key]+=event['bytes'];stream_ready[key]+=event['weight_bytes'];stream_scale[key]+=event['scale_bytes']
        elif kind == 'stream_operand_ready':
            task=tasks[event['task']];rule=task['stream']
            if event['object']!=rule['weight_object']:raise ValueError('Wrong streamed weight object')
            if event['object_offset']>=rule['weight_data_bytes']:stream_scale[event['task']]+=event['bytes']
            else:stream_ready[event['task']]+=event['bytes']
        elif kind=='compute_service':
            key=event['task'];tick=(event['tile'],at)
            if key not in starts or key in finishes or tick in stream_ticks or event['cycles']!=1:
                raise ValueError('Arithmetic service copied across contexts')
            stream_ticks.add(tick);last_compute[key]=at;service_cycles[key]+=1
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
            for edge in incoming[key]:
                if data[edge['id']] != edge['size_bytes']:
                    raise ValueError('Consumer started before tensor delivery')
            for producer in control[key]:
                if producer not in finishes:
                    raise ValueError('Control predecessor incomplete')
            if not tasks[key].get('stream') and read[key] != sum(r['size_bytes'] for r in tasks[key]['reads']):
                raise ValueError('Compute started before memory delivery')
            if tasks[key].get('stream') and stream_scale[key]!=tasks[key]['stream']['scale_bytes']:
                raise ValueError('Streamed GEMM started before scale delivery')
            engine_slots[event['tile']]+=1;context_peak[event['tile']]=max(context_peak[event['tile']],engine_slots[event['tile']])
            if engine_slots[event['tile']]>contexts:
                raise ValueError('Finite compute contexts overallocated')
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
            elif 'compute_execution' in result and tasks[key]['compute_cycles']:
                if service_cycles[key]!=tasks[key]['compute_cycles'] or at!=last_compute[key]+period:
                    raise ValueError('Invalid shared arithmetic completion')
            elif key not in starts or at != starts[key]+tasks[key]['compute_cycles']*period:
                raise ValueError('Invalid compute duration')
            finishes[key] = at
            engine_slots[event['tile']]-=1
            if key in cache_lookups:cache_pins[cache_lookups[key]]-=1
    if (set(packets) != delivered or set(finishes) != set(tasks) or any(sram.values())
            or any(set(requests) != ids for ids in stages.values()) or dict(data) != edge_bytes):
        raise ValueError('Final byte/transaction/storage ledger did not drain')
    network = result['network']
    if 'compute_execution' in result and dict(context_peak)!=result['compute_execution']['context_peak']:
        raise ValueError('Reported context occupancy differs from event ledger')
    if cache:
        if any(lookup_live.values()) or any(cache_pins.values()) or dict(cache_peak)!=cache['peak_data_bytes'] or dict(cache_used)!=cache['resident_bytes']:
            raise ValueError('Cache lifetime/count record differs from events')
        for key in ('hit_bytes','miss_bytes','evictions','evicted_bytes','reload_bytes','compulsory_bytes'):
            if cache_stats[key]!=cache['stats'].get(key,0):raise ValueError('Cache traffic/eviction counters differ')
        if cache_stats['initial_bytes']!=cache['initial_resident_bytes']:raise ValueError('Warm initial bytes were not accounted')
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
