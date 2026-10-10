"""Same committed frontier, exact service and interruptible deferred state."""
from copy import deepcopy
from dataclasses import asdict
from types import SimpleNamespace
import unittest

from test_compute_epoch import initialized, semantic_tasks
from w2w.system.interactive_compute import InteractiveCompute, OrderedEvidence
from w2w.system.operand_readiness import CommittedWeightPrefix
from w2w.validation.interactive_compute import expand_interactive_compute, audit_interactive_compute


def ready(evidence='full', prefix=4096):
    e = initialized()
    e.compute_epoch = False
    e.operand_readiness = 'contiguous_prefix'
    frontier = CommittedWeightPrefix(8192,4096)
    frontier.receive(0,4096)
    if prefix == 8192:frontier.receive(4096,4096)
    e.operand_frontiers['gemm'] = frontier
    e.state['gemm'].update(stream_weight_delivered=prefix,read_bytes=prefix+32)
    e.interactive_compute = InteractiveCompute(evidence)
    e.network.drained = lambda:False
    e.native.record = lambda:dict(pending=1)
    e.requests['live'] = {}
    if evidence == 'compact':e.events = OrderedEvidence()
    return e


class InteractiveComputeTests(unittest.TestCase):
    def test_active_transport_partial_prefix_equals_exact_state_at_each_boundary(self):
        # Materialization is an explicit read barrier, not a future state update.
        for end in (2000,3000,11000,64000):
            bulk, exact = ready(), ready()
            exact.interactive_compute = None
            for at in range(2000,end+1,1000):
                bulk.now=exact.now=at
                bulk._stream_compute_progress();exact._stream_compute_progress()
                self.assertEqual(bulk._available_weights('gemm'),exact._available_weights('gemm'))
            bulk.interactive_compute.materialize(bulk)
            self.assertEqual(semantic_tasks(bulk),semantic_tasks(exact))
            self.assertEqual(bulk.busy_ps,exact.busy_ps)
            self.assertEqual(bulk.compute_service_tick,exact.compute_service_tick)
            self.assertEqual(bulk.events,exact.events)

    def test_new_prefix_extends_next_interval_without_rewriting_existing_one(self):
        for arrival in (10000,90000):  # Includes depletion, wait, then recovery.
            bulk, exact = ready(), ready()
            exact.interactive_compute = None
            for at in range(2000,154000,1000):
                bulk.now=exact.now=at
                if at == arrival:
                    for e in (bulk,exact):
                        e.operand_frontiers['gemm'].receive(4096,4096)
                        e.state['gemm'].update(stream_weight_delivered=8192,read_bytes=8224)
                bulk._stream_compute_progress();exact._stream_compute_progress()
            bulk.interactive_compute.materialize(bulk)
            self.assertEqual(semantic_tasks(bulk),semantic_tasks(exact))
            self.assertEqual(bulk.events,exact.events)
            self.assertEqual(bulk.interactive_compute.intervals[0]['committed_prefix_bytes'],4096)
            self.assertEqual(bulk.interactive_compute.intervals[1]['committed_prefix_bytes'],8192)

    def test_compact_expansion_preserves_equal_time_insertion(self):
        full, compact = ready(), ready('compact')
        for at in range(2000,8000,1000):
            for e in (full,compact):
                e.now=at
                if at in (2000,5000):e.log('before_service',ordinal=at)
                e._stream_compute_progress()
                e.log('after_service',ordinal=at)
        for e in (full,compact):e.interactive_compute.materialize(e);e.events.sort(key=lambda r:r['time_ps'])
        record=dict(spec=asdict(compact.spec),graph=asdict(compact.graph),events=compact.events,drained_ps=9000)
        self.assertEqual(expand_interactive_compute(record)['events'],full.events)
        for mutation in (lambda row:row.update(cycles=0),lambda row:row.update(weight_bytes=128),
                         lambda row:row.update(tie_runs=[[0,999]]),lambda row:row.update(tie_runs=[[1,0]])):
            bad=deepcopy(record);marker=next(r for r in bad['events'] if r['kind']=='interactive_compute_epoch')
            mutation(marker)
            with self.assertRaises(ValueError):expand_interactive_compute(bad)

    def test_competitor_flushes_only_already_executed_service(self):
        e=ready();e.now=2000;e._stream_compute_progress()
        self.assertEqual(e.state['gemm']['stream_consumed'],64)
        e.engine['c1']=['later']
        e.now=3000
        self.assertFalse(e.interactive_compute.service(e))
        self.assertEqual(e.state['gemm']['stream_consumed'],128)
        self.assertEqual(e.compute_service_tick['c0'],2000)

    def test_byte_count_contexts_cache_observer_and_short_frontier_fall_back(self):
        for change in (lambda e:setattr(e,'operand_readiness','byte_count'),
                       lambda e:setattr(e,'compute_contexts',2),
                       lambda e:setattr(e,'event_observer',lambda _:None),
                       lambda e:setattr(e,'weight_cache',object()),
                       lambda e:e.state['gemm'].update(stream_consumed=4095)):
            e=ready();e.now=2000;change(e)
            before=deepcopy(semantic_tasks(e))
            self.assertFalse(e.interactive_compute.service(e))
            self.assertEqual(semantic_tasks(e),before)

    def test_frontier_holes_are_distinguishable_after_same_future_commit(self):
        # Equal counts AND equal head: holes still determine the next frontier.
        a,b=CommittedWeightPrefix(16384,4096),CommittedWeightPrefix(16384,4096)
        for frontier,later in ((a,8192),(b,12288)):
            frontier.receive(0,4096);frontier.receive(later,4096)
        self.assertEqual(a.head,b.head)
        self.assertEqual(a.mask.bit_count(),b.mask.bit_count())
        a.receive(4096,4096);b.receive(4096,4096)
        self.assertEqual((a.ready_bytes,b.ready_bytes),(12288,8192))

    def test_noncompute_clock_and_duplicate_call_do_not_create_service(self):
        e=ready();e.now=2000;e._stream_compute_progress();e._stream_compute_progress()
        self.assertEqual(e.interactive_compute.service_visits,1)
        e.now=3760;e._stream_compute_progress()
        self.assertEqual(e.interactive_compute.service_visits,1)

    def test_wrong_interval_progress_prefix_count_and_duplicate_marker_rejected(self):
        e=ready('compact')
        e.log('stream_operand_ready',task='gemm',object_offset=0,bytes=4096)
        e.events.append(dict(kind='stream_compute',time_ps=1000,task='gemm',tile='c0',
            weight_bytes=64,scale_bytes=0,macs=64))
        e.interactive_compute.ordinary_updates=1
        for at in range(2000,8000,1000):e.now=at;e._stream_compute_progress()
        e.interactive_compute.materialize(e);e.events.sort(key=lambda r:r['time_ps'])
        raw=dict(spec=asdict(e.spec),graph=asdict(e.graph),events=e.events,drained_ps=9000,
            compute_execution=dict(contexts_per_cluster=1),operand_readiness=dict(policy='contiguous_prefix'),
            interactive_compute=e.interactive_compute.record())
        self.assertEqual(audit_interactive_compute(raw)['arithmetic_updates'],2)
        for mutate in (lambda r:r['interactive_compute'].update(batch_updates=2),
                       lambda r:r['interactive_compute']['intervals'][0].update(consumed_before=0),
                       lambda r:r['interactive_compute']['intervals'][0].update(committed_prefix_bytes=8192),
                       lambda r:r['events'].append(deepcopy(next(x for x in r['events'] if x['kind']=='interactive_compute_epoch')))):
            bad=deepcopy(raw);mutate(bad)
            with self.assertRaises(ValueError):audit_interactive_compute(bad)

