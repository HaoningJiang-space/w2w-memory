"""A known future release while every externally interacting resource is idle.

No Native cycle, refresh or BookSim state transition is replaced: their existing
advance methods execute the complete interval at the resume boundary. This
reduces only host wakeups in otherwise inactive deployed pipeline stages.
"""
def next_idle_boundary(e,quantum,max_ps):
    if (e.requests or e.packet_info or e.reading or e.active_edges or e.cache_waiting
            or e.memory_candidates or e.ready_tasks or e.engine or any(e.outstanding.values())
            or any(e.mc_pool_slots.values()) or any(e.mc_slots.values())):return None
    safe=getattr(e.native,'compute_epoch_quiescent',None)
    if safe is None or not safe() or not e.network.drained():return None
    frontier=[key for key in e.unallocated if all(e.state[p].get('done',False) for p in e.predecessors[key])]
    if frontier:
        limit=min(e.tasks[key].release_ps for key in frontier)
        if limit<=e.now:return None
    elif e.window_final_ps is not None and e.window_final_ps>e.now:limit=e.window_final_ps
    else:return None
    at=((limit+quantum-1)//quantum)*quantum
    if at>max_ps or at<=e.now+max(e.spec.noc_period_ps,e.spec.dram_period_ps):return None
    return at
