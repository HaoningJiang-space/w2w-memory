"""Conservative exact compute epochs inside the existing system kernel.

Only one running streaming context with fully committed operands and quiescent
transport qualifies. Native DRAM still advances every internal cycle (refresh
included) at the resume barrier. No active network or memory service is skipped.
"""
from math import gcd


def advance_compute_epoch(execution, max_ps):
    e = execution
    if (e.event_observer is not None or e.weight_cache is not None
            or e.requests or e.packet_info or e.reading or e.active_edges or e.cache_waiting
            or e.memory_candidates or e.ready_tasks or any(e.outstanding.values())
            or any(e.mc_pool_slots.values()) or any(e.mc_slots.values())):
        return None
    live = [(tile, key) for tile, keys in e.engine.items() for key in keys]
    if len(live) != 1:
        return None
    tile, key = live[0]
    task, state = e.tasks[key], e.state[key]
    stream = task.stream
    period = e.builder.tiles[tile].compute_period_ps
    if (stream is None or period != e.spec.noc_period_ps or e.now % period
            or state['finish_ps'] is not None or not state.get('stream_scale_consumed')
            or not state['issued_all'] or e.compute_service_tick.get(tile) != e.now
            or state['read_bytes'] != sum(r.size_bytes for r in task.reads)
            or state.get('stream_weight_delivered', 0) != stream.weight_data_bytes
            or e._available_weights(key) != stream.weight_data_bytes-state.get('stream_consumed', 0)):
        return None
    safe = getattr(e.native, 'compute_epoch_quiescent', None)
    if safe is None or not safe() or not e.network.drained():
        return None
    quantum = gcd(e.spec.noc_period_ps, e.spec.dram_period_ps,
                  *(t.compute_period_ps for t in e.spec.tiles))
    limit = max_ps//quantum*quantum
    for candidate in e.unallocated:
        release = e.tasks[candidate].release_ps
        # Even dependency-blocked releases remain conservative barriers.
        if release <= e.now:
            return None
        limit = min(limit, (release+quantum-1)//quantum*quantum)
    reuse = stream.macs//stream.weight_data_bytes
    rate = min(stream.weight_read_bytes_per_cycle, stream.macs_per_cycle//reuse)
    remaining = stream.weight_data_bytes-state.get('stream_consumed', 0)
    # Leave the final, possibly short, service and completion to ordinary code.
    count = min((remaining-1)//rate, max(0, (limit-1-e.now)//period))
    if count < 2:
        return None
    start, last = e.now+period, e.now+count*period
    resume = min(last+period, limit)
    before = state.get('stream_consumed', 0)
    state['stream_consumed'] = before+count*rate
    state['stream_tick'] = last
    e.compute_service_tick[tile] = last
    e.busy_ps[tile] += count*period
    # One context: the ordinary round-robin successor remains zero.
    e.context_cursor[tile] = 0
    marker = dict(kind='compute_epoch', schema=1, time_ps=start, task=key, tile=tile,
                  period_ps=period, cycles=count, weight_bytes=rate, macs=rate*reuse)
    if e.compute_epoch_evidence == 'full':
        e.events.extend(dict(kind='stream_compute', time_ps=start+i*period,
            task=key, tile=tile, weight_bytes=rate, scale_bytes=0, macs=rate*reuse)
            for i in range(count))
    else:
        e.events.append(marker)
    e.compute_epochs.append(dict(start_ps=start, last_service_ps=last, resume_ps=resume,
        task=key, cycles=count, consumed_before=before, consumed_after=state['stream_consumed']))
    return resume
