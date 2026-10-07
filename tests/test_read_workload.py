"""Independent tiny-system oracles and evidence boundaries for read replay."""
from dataclasses import replace
from fractions import Fraction
import json
from pathlib import Path
import tempfile
import unittest

from tests.fixtures.tiny_fabric import two_compute_two_memory
from w2w.domain import EndpointSpec, StaticLayout
from w2w.domain.endpoint import NativeProfile
from w2w.experiments.run_read_workload import hardware_evidence
from w2w.service.read_replay import ReadReplayConfig, replay_reads
from w2w.synthesis.role_interfaces import static_shared_fifo
from w2w.workloads.moe_reads import compile_moe_reads, synthetic_moe_captures
from w2w.workloads.read_residency import ReadResidency
from w2w.workloads.read_trace import ReadObject, ReadSpan, ReadTask, ReadTrace
from w2w.workloads.read_trace import synthetic_read_suite
from w2w.analysis.read_completion import completion_metrics, projected_frontier


def home_design():
    base = two_compute_two_memory()
    return replace(base, structure='home', home_fraction=Fraction(1),
                   exposure=replace(base.exposure, mask=((0,),), port_bits=(8000, 0, 0)),
                   endpoint=EndpointSpec((256, 0, 0), (0, 0, 0), mode='direct'),
                   layout=StaticLayout(((1., 0.), (0., 1.))))


def read_trace(words=6, both=False):
    objects = (ReadObject('a', words * 32, 0), ReadObject('b', words * 32, 1))
    tasks = (ReadTask('a', 0, (ReadSpan('a', 0, words * 32),)),)
    if both:
        tasks += (ReadTask('b', 1, (ReadSpan('b', 0, words * 32),)),)
    return ReadTrace(objects, tasks, 'synthetic', 'unit analytical fixture')


FAST = ReadReplayConfig(request_latency_slots=0, native_latency_slots=0, link_latency_slots=0)


class ReadTraceTests(unittest.TestCase):
    def test_roundtrip_and_invalid_dag(self):
        trace = read_trace()
        self.assertEqual(ReadTrace.from_record(json.loads(json.dumps(trace.record()))), trace)
        with self.assertRaisesRegex(ValueError, 'cycle'):
            replace(trace, tasks=(replace(trace.tasks[0], dependencies=('a',)),))
        with self.assertRaisesRegex(ValueError, 'dependency'):
            replace(trace, tasks=(replace(trace.tasks[0], dependencies=('missing',)),))

    def test_invalid_address_owner_and_alignment(self):
        trace = read_trace()
        for span in (ReadSpan('a', 1, 32), ReadSpan('a', 192, 32), ReadSpan('b', 0, 32)):
            with self.subTest(span=span), self.assertRaises(ValueError):
                replace(trace, tasks=(replace(trace.tasks[0], reads=(span,)),))
        with self.assertRaises(ValueError):
            ReadReplayConfig(outstanding_words_per_compute=True)

    def test_exact_residence_and_unique_local_addresses(self):
        trace = read_trace(words=13, both=True)
        design = two_compute_two_memory(home_fraction=Fraction(8, 13), widths=(256, 160, 160), depths=(1, 2, 2))
        layout = ReadResidency(design, trace)
        addresses = [layout.locate(o.id, i)[:2] for o in trace.objects for i in range(13)]
        self.assertEqual(len(set(addresses)), 26)
        self.assertEqual(layout.count('a', 0, 13), {0: 8, 1: 5})
        for first in range(13):
            for count in range(14 - first):
                from collections import Counter
                self.assertEqual(layout.count('a', first, count),
                                 dict(Counter(layout.locate('a', i)[0] for i in range(first, first + count))))

    def test_fixed_addresses_allow_different_phase_fractions(self):
        design = two_compute_two_memory()
        trace = read_trace()
        layout = ReadResidency(design, trace)
        words = [ReadTask(str(i), 0, (ReadSpan('a', i * 32, 32),)) for i in range(3)]
        self.assertEqual({next(iter(layout.task_bytes(t))) for t in words}, {0, 1})
        original = layout.sha256
        for t in words:
            layout.task_bytes(t)
        self.assertEqual(layout.sha256, original)

    def test_actual_capacity_counts_all_resident_objects(self):
        design = home_design()
        # Existing fractional contract fits, but imported objects do not.
        huge = ReadTrace((ReadObject('large', 3 * 2**30, 0),),
                         (ReadTask('small_read', 0, (ReadSpan('large', 0, 32),)),),
                         'synthetic', 'capacity adversary')
        with self.assertRaisesRegex(ValueError, 'capacity'):
            ReadResidency(design, huge)

    def test_unreachable_layout_rejected(self):
        design = two_compute_two_memory()
        broken = replace(design, geometry=replace(design.geometry, routes=design.geometry.routes[:2]))
        with self.assertRaises((ValueError, KeyError)):
            ReadResidency(broken, read_trace())


class ReadReplayTests(unittest.TestCase):
    def test_home_direct_analytic_completion(self):
        result = replay_reads(home_design(), read_trace(4), FAST)
        self.assertEqual(result['makespan_slots'], 4)
        self.assertEqual(result['audit']['delivered_words'], 4)
        self.assertEqual(result['slot_ns'], .032)
        self.assertEqual(result['effective_tb_s'], 1.)

    def test_dependency_and_compute_delay_are_closed_loop(self):
        trace = read_trace(4)
        trace = replace(trace, tasks=(replace(trace.tasks[0], compute_slots=3),
                                      ReadTask('next', 0, trace.tasks[0].reads, ('a',))))
        result = replay_reads(home_design(), trace, FAST)
        self.assertEqual(result['tasks'][0]['reads_done_slot'], 4)
        self.assertEqual(result['tasks'][1]['start_slot'], 7)
        self.assertEqual(result['makespan_slots'], 11)

    def test_shared_required_bytes_and_analytic_single_speed(self):
        result = replay_reads(two_compute_two_memory(), read_trace(6), FAST)
        self.assertEqual(result['makespan_slots'], 4)
        self.assertEqual(result['tasks'][0]['bank_bytes'], {0: 128, 1: 64})
        self.assertEqual(result['audit']['sent_bits'], 6 * 256)

    def test_partial_words_cross_beats_and_drain_finite_tail(self):
        design = two_compute_two_memory(widths=(256, 160, 160), depths=(1, 2, 2),
                                        home_fraction=Fraction(8, 13))
        result = replay_reads(design, read_trace(13), FAST)
        self.assertEqual(result['makespan_slots'], 8)
        self.assertEqual(result['audit']['delivered_words'], 13)

    def test_credit_and_receiver_backpressure_preserve_bytes(self):
        design, trace = two_compute_two_memory(), read_trace(30, both=True)
        base = replay_reads(design, trace, FAST)
        constrained = replay_reads(design, trace, replace(FAST, outstanding_words_per_compute=1,
                                   rx_depth_words=1, rx_ready=(0, 0, 1), request_latency_slots=2,
                                   native_latency_slots=1, link_latency_slots=2))
        self.assertGreater(constrained['makespan_slots'], base['makespan_slots'])
        self.assertEqual(constrained['audit']['delivered_words'], 60)
        self.assertLessEqual(max(constrained['peak_outstanding_words']), 1)
        self.assertTrue(all(r['peak_rx_words'] <= 1 for r in constrained['routes']))

    def test_native_readiness_is_not_unlimited_supply(self):
        design, trace = home_design(), read_trace(4)
        stopped = replace(design, endpoint=replace(design.endpoint, native=NativeProfile('half', (0, 1))))
        self.assertEqual(replay_reads(stopped, trace, FAST)['makespan_slots'], 8)

    def test_timeout_and_word_limit_fail_without_partial_success(self):
        for config in (replace(FAST, rx_ready=(0,), max_slots=10), replace(FAST, max_trace_words=1)):
            with self.assertRaises((RuntimeError, ValueError)):
                replay_reads(home_design(), read_trace(), config)

    def test_configurable_ablation_and_late_successor(self):
        design = two_compute_two_memory()
        trace = read_trace(12, both=True)
        trace = replace(trace, tasks=trace.tasks + (ReadTask('again', 0, trace.tasks[0].reads, ('a', 'b')),
                                                    ReadTask('join', None, dependencies=('again',))))
        configured = static_shared_fifo(design, share_serializer=True)
        a = replay_reads(design, trace, FAST)
        b = replay_reads(configured, trace, FAST)
        for key in ('residence_sha256', 'tasks', 'routes', 'delivery_sha256', 'audit', 'makespan_slots'):
            self.assertEqual(a[key], b[key], key)
        self.assertNotEqual(a['design_sha256'], b['design_sha256'])

    def test_zero_byte_barriers_and_compute_serialization(self):
        trace = read_trace(2)
        trace = replace(trace, tasks=(ReadTask('barrier', None),
                                      replace(trace.tasks[0], dependencies=('barrier',)),
                                      ReadTask('b', 0, trace.tasks[0].reads)))
        result = replay_reads(home_design(), trace, FAST)
        self.assertEqual(result['makespan_slots'], 4)
        self.assertEqual(result['tasks'][2]['compute_queue_slots'], 2)


class CompletionStudyTests(unittest.TestCase):
    def test_join_critical_path_excludes_parallel_work_and_counts_release_gap(self):
        trace = read_trace(6, both=True)
        trace = replace(trace, tasks=(
            ReadTask('a', 0, (ReadSpan('a', 0, 64),), compute_slots=3),
            trace.tasks[1], ReadTask('join', None, dependencies=('a', 'b')),
            ReadTask('after', 0, (ReadSpan('a', 0, 64),), ('join',), release_slot=10)))
        result = replay_reads(home_design(), trace, FAST)
        metrics = completion_metrics(trace, result)
        self.assertEqual(result['makespan_slots'], 12)
        self.assertEqual(metrics['critical_path'], ['b', 'join', 'after'])
        self.assertEqual(metrics['critical_read_wait_slots'], 8)
        self.assertEqual(metrics['critical_release_wait_slots'], 4)
        self.assertEqual(metrics['joins'][0]['arrival_span_slots'], 1)
        self.assertEqual(result['summed_task_read_wait_slots'], 10)

    def test_actual_compute_serialization_is_a_critical_dependency(self):
        trace = read_trace(2)
        trace = replace(trace, tasks=(trace.tasks[0], ReadTask('b', 0, trace.tasks[0].reads)))
        result = replay_reads(home_design(), trace, FAST)
        self.assertEqual(completion_metrics(trace, result)['critical_path'], ['a', 'b'])
        self.assertEqual(result['tasks'][1]['compute_predecessor'], 'a')

    def test_instant_join_precedes_ready_task_arbitration(self):
        trace = read_trace(2)
        trace = replace(trace, tasks=(ReadTask('z_join', None),
                                      replace(trace.tasks[0], dependencies=('z_join',)),
                                      ReadTask('b', 0, trace.tasks[0].reads)))
        result = replay_reads(home_design(), trace, FAST)
        self.assertEqual(result['tasks'][1]['start_slot'], 0)
        self.assertEqual(completion_metrics(trace, result)['critical_path'], ['z_join', 'a', 'b'])

    def test_coordinate_suite_has_constant_resident_objects_and_stage_coverage(self):
        coordinates = tuple((x, y) for y in range(6) for x in range(6))
        suite = synthetic_read_suite(coordinates)
        self.assertEqual(len(suite), 7)
        self.assertTrue(all(t.objects == suite['single'].objects for t in suite.values()))
        moving = suite['moving9']
        self.assertEqual(sorted(t.compute for t in moving.tasks if t.reads), list(range(36)))
        self.assertEqual([t.compute for t in suite['dispersed9'].tasks if t.reads],
                         [0, 2, 4, 12, 14, 16, 24, 26, 28])
        self.assertEqual(sum(r.size_bytes for t in moving.tasks for r in t.reads), 36 * 2496 * 32)
        with self.assertRaises(ValueError):
            synthetic_read_suite(coordinates[:-1])

    def test_projection_retains_cost_tradeoffs_and_removes_dominated_point(self):
        def row(name, time, lane, storage, wire):
            return dict(id=name, makespan_slots=time, cost=dict(export_lane_bits=lane,
                        endpoint_storage_bits=storage, access_wire_bit_mm=wire))
        self.assertEqual(projected_frontier([row('home', 10, 1, 1, 1), row('fast', 5, 2, 1, 2),
                                            row('duplicated', 5, 2, 2, 2)]), ['fast', 'home'])


class MoeImportTests(unittest.TestCase):
    def test_training_only_balance_and_batch_weight_reuse(self):
        train, test = synthetic_moe_captures()
        trace, info = compile_moe_reads(train, test)
        self.assertEqual(len(set(info['assignment'].values())), 36)
        self.assertFalse(info['captured_routing'])
        single = [t for t in trace.tasks if t.id.startswith('batch2/expert')]
        self.assertEqual(len(single), 1)  # two routed tokens share one weight read
        changed = json.loads(json.dumps(test))
        changed['batches'] = [changed['batches'][-1]]
        _, changed_info = compile_moe_reads(train, changed)
        self.assertEqual(info['assignment'], changed_info['assignment'])

    def test_train_test_leakage_and_mismatched_experts_rejected(self):
        train, test = synthetic_moe_captures()
        test['batches'][0]['id'] = train['batches'][0]['id']
        with self.assertRaisesRegex(ValueError, 'overlap'):
            compile_moe_reads(train, test)
        train, test = synthetic_moe_captures()
        test['experts'] = [dict(e, size_bytes=e['size_bytes'] + 32) for e in test['experts']]
        with self.assertRaisesRegex(ValueError, 'identical'):
            compile_moe_reads(train, test)

    def test_hardware_hash_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'evidence.txt').write_text('area report')
            record = dict(design_sha256='design', artifact='evidence.txt', artifact_sha256='bad',
                          source_commit='source', scope='source only', timing_closed=False, measurements={})
            (root / 'links.json').write_text(json.dumps([record]))
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                hardware_evidence(root / 'links.json', [{'design_sha256': 'design'}])


if __name__ == '__main__':
    unittest.main()
