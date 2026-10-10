"""Conservative active-array coordination; never guesses a native completion."""
from math import gcd


class CausalBoundary:
    def __init__(self):
        self.intervals=[]
        self.attempts=0

    def plan(self,e,max_ps):
        run=e.interactive_compute.live
        if (run is None or run.last_seen!=e.now or e.event_observer is not None
                or e.weight_cache is not None or e.ready_tasks or e.reading or e.active_edges
                or e.memory_candidates or len(e.engine)!=1
                or e.engine.get(run.tile)!=[run.task]):return None
        network=e.network
        if (not getattr(network,'native_idle',False) or network.future or network.ready_packets
                or any(network.receiver_waiters.values())):return None
        quantum=gcd(e.spec.noc_period_ps,e.spec.dram_period_ps,
            *(t.compute_period_ps for t in e.spec.tiles))
        limit=min(max_ps//quantum*quantum,run.start+run.count*run.period)
        for key in e.unallocated:
            release=e.tasks[key].release_ps
            if release<=e.now:return None
            limit=min(limit,(release+quantum-1)//quantum*quantum)
        native=e.native
        method=getattr(native,'first_callback_boundary',None)
        if (method is None or any(native.queues.values()) or any(native.aggregate.values())
                or native.ready or native.native_events or not native.backend.pending):return None
        if native.future:limit=min(limit,(native.future[0][0]+quantum-1)//quantum*quantum)
        if limit<=e.now:return None
        self.attempts+=1
        stop=method(e.now,limit)
        if stop is None:return None
        if not e.now<stop<=limit or stop%quantum:
            raise RuntimeError('Native returned an uncertified system boundary')
        first=run.last_seen+run.period
        last=min(run.start+(run.count-1)*run.period,((stop-1)//run.period)*run.period)
        n=max(0,(last-first)//run.period+1)
        if n:
            if e.interactive_compute.evidence=='full':
                e.events.extend(dict(kind='stream_compute',time_ps=first+i*run.period,
                    task=run.task,tile=run.tile,weight_bytes=run.rate,scale_bytes=0,macs=run.rate*run.reuse)
                    for i in range(n))
            else:
                ordinal=(first-run.start)//run.period
                if not run.tie_runs or run.tie_runs[-1][1]!=0:run.tie_runs.append([ordinal,0])
            run.last_seen=last
            e.interactive_compute.bulk_services+=n
        self.intervals.append(dict(start_ps=e.now,resume_ps=stop,limit_ps=limit,task=run.task,
            first_service_ps=first,bulk_services=n,active_array=True))
        return stop

    def record(self):
        return dict(schema=1,attempts=self.attempts,intervals=self.intervals,
            bulk_services=sum(r['bulk_services'] for r in self.intervals),
            contract='active array only; NoC idle; no frontend queues; first native callback/known frontend/release/prefix/deadline; no input before resumption')
