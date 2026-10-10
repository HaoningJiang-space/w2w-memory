"""Deferred exact compute service while native transport remains active.

The host does NOT jump time. A committed prefix funds a finite service interval;
ordinary native arrival, credit, commit and admission phases still run. Only the
single context's repeated arithmetic-state updates are deferred. A read of
available operands includes service already performed, never future service.
"""
from dataclasses import dataclass, field


class OrderedEvidence(list):
    """Compact evidence retains insertion order at equal physical times."""
    def __init__(self):
        super().__init__()
        self.at_time = {}

    def append(self, event):
        super().append(event)
        if event['kind'] != 'interactive_compute_epoch':
            at = event['time_ps']
            self.at_time[at] = self.at_time.get(at, 0) + 1

    def extend(self, events):
        for event in events:
            self.append(event)


@dataclass
class ServiceInterval:
    task: str
    tile: str
    start: int
    period: int
    count: int
    rate: int
    reuse: int
    before: int
    ready: int
    transport_live: bool
    reads_live: bool
    native_live: bool
    last_seen: int | None = None
    tie_runs: list = field(default_factory=list)

    @property
    def served(self):
        return 0 if self.last_seen is None else (self.last_seen-self.start)//self.period+1


class InteractiveCompute:
    def __init__(self, evidence):
        self.evidence = evidence
        self.live = None
        self.intervals = []
        self.ordinary_updates = 0
        self.batch_updates = 0
        self.service_visits = 0
        self.bulk_services = 0

    def deferred_bytes(self, key):
        run = self.live
        return run.served*run.rate if run is not None and run.task == key else 0

    def materialize(self, e):
        """Restore ordinary state at the last executed compute boundary."""
        run = self.live
        if run is None:
            return
        n = run.served
        if n:
            state = e.state[run.task]
            state['stream_consumed'] = run.before+n*run.rate
            state['stream_tick'] = run.last_seen
            e.compute_service_tick[run.tile] = run.last_seen
            e.context_cursor[run.tile] = 0
            e.busy_ps[run.tile] += n*run.period
            self.batch_updates += 1
            self.intervals.append(dict(task=run.task, tile=run.tile, start_ps=run.start,
                cycles=n, period_ps=run.period, weight_bytes=run.rate, macs=run.rate*run.reuse,
                consumed_before=run.before, consumed_after=state['stream_consumed'],
                committed_prefix_bytes=run.ready, transport_live=run.transport_live,
                reads_live=run.reads_live, native_live=run.native_live))
            if self.evidence == 'compact':
                e.events.append(dict(kind='interactive_compute_epoch', schema=1,
                    time_ps=run.start, task=run.task, tile=run.tile, cycles=n,
                    period_ps=run.period, weight_bytes=run.rate, macs=run.rate*run.reuse,
                    tie_runs=run.tie_runs))
        self.live = None

    def _recognize(self, e, tile, key):
        state, task = e.state[key], e.tasks[key]
        stream = task.stream
        period = e.builder.tiles[tile].compute_period_ps
        if (e.compute_contexts != 1 or e.event_observer is not None or e.weight_cache is not None
                or e.operand_readiness != 'contiguous_prefix' or stream is None
                or not state.get('stream_scale_consumed') or state['finish_ps'] is not None
                or period != e.spec.noc_period_ps or e.now % period):
            return None
        reuse = stream.macs//stream.weight_data_bytes
        rate = min(stream.weight_read_bytes_per_cycle, stream.macs_per_cycle//reuse)
        before = state.get('stream_consumed', 0)
        ready = e.operand_frontiers[key].ready_bytes
        # Do not depend on any future operand. Leave the task tail to the exact
        # transition, where completion and downstream work become observable.
        n = min((ready-before)//rate, (stream.weight_data_bytes-before-1)//rate)
        if n < 2:
            return None
        # These observations describe demand, not a hardware budget or guard.
        return ServiceInterval(key, tile, e.now, period, n, rate, reuse, before, ready,
            bool(e.packet_info or e.active_edges or not e.network.drained()),
            bool(e.requests or e.reading), bool(e.native.record()['pending']))

    def service(self, e):
        """True means this compute boundary was handled without ordinary update."""
        live = [(tile, key) for tile, keys in e.engine.items() for key in keys]
        run = self.live
        if run is not None and (live != [(run.tile, run.task)]
                or e.now > run.start+(run.count-1)*run.period):
            self.materialize(e)
            run = None
        if len(live) != 1:
            return False
        tile, key = live[0]
        period = e.builder.tiles[tile].compute_period_ps
        if e.now % period:
            return run is not None
        if run is not None and run.last_seen == e.now:
            return True
        if e.compute_service_tick.get(tile) == e.now:
            return False
        if run is None:
            run = self._recognize(e, tile, key)
            if run is None:
                return False
            self.live = run
        if self.evidence == 'full':
            e.log('stream_compute', task=key, tile=tile, weight_bytes=run.rate,
                  scale_bytes=0, macs=run.rate*run.reuse)
        else:
            ordinal = (e.now-run.start)//period
            before = e.events.at_time.get(e.now, 0)
            if not run.tie_runs or run.tie_runs[-1][1] != before:
                run.tie_runs.append([ordinal, before])
        run.last_seen = e.now
        self.service_visits += 1
        return True

    def record(self):
        record=dict(schema=2 if self.bulk_services else 1, evidence=self.evidence, intervals=self.intervals,
            ordinary_weight_updates=self.ordinary_updates, batch_updates=self.batch_updates,
            batched_compute_cycles=sum(r['cycles'] for r in self.intervals),
            compute_service_visits=self.service_visits,
            contract='one streaming context; committed contiguous prefix funds service; '
                'deferred progress materialized before fallback; host/native time does not jump; '
                'task tail ordinary; all native feedback remains active')
        if self.bulk_services:
            record['bulk_services']=self.bulk_services
            record['contract']='committed-prefix one-context service; certified native callback horizons; ordinary native clocks and feedback; task tail exact'
        return record
