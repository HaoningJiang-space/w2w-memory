"""A known future release while every externally interacting resource is idle.

No Native cycle, refresh or BookSim state transition is replaced: their existing
advance methods execute the complete interval at the resume boundary. This
reduces only host wakeups in otherwise inactive deployed pipeline stages.
"""
def next_idle_boundary(e,quantum,max_ps):
    if (e.requests or e.packet_info or e.reading or e.active_edges or e.cache_waiting
            or e.memory_candidates or e.ready_tasks or any(e.outstanding.values())
            or any(e.mc_pool_slots.values()) or any(e.mc_slots.values())):return None
    safe=getattr(e.native,'compute_epoch_quiescent',None)
    if safe is None or not safe() or not e.network.drained():return None
    limits=[]
    if e.engine:
        model=getattr(e,'npu_model',None)
        if model is None or model.evidence!='epochs':return None
        for tile,keys in e.engine.items():
            if any(key not in model.kernels for key in keys):return None
            key=model.owners.get(tile)
            if key is None or key not in keys:return None
            finish=e.state[key]['finish_ps']
            if finish is None or finish<=e.now or model.cursors[key]!=model.plans[key]['cycles']:return None
            limits.append(finish)
    frontier=[key for key in e.unallocated if all(e.state[p].get('done',False) for p in e.predecessors[key])]
    if frontier:
        release=min(e.tasks[key].release_ps for key in frontier)
        if release<=e.now:return None
        limits.append(release)
    if e.window_final_ps is not None and e.window_final_ps>e.now:limits.append(e.window_final_ps)
    if not limits:return None
    limit=min(limits)
    at=((limit+quantum-1)//quantum)*quantum
    if at>max_ps or at<=e.now+max(e.spec.noc_period_ps,e.spec.dram_period_ps):return None
    return at
