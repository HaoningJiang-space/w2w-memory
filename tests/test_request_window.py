"""Independent small-system checks for necessary bounds and exhaustive sizing."""
from copy import deepcopy
from dataclasses import replace
from fractions import Fraction
import unittest

from tests.fixtures.tiny_fabric import two_compute_two_memory
from tests.test_read_workload import FAST, home_design, read_trace
from w2w.analysis.request_window import (check_bound, completion_lower_bound,
    rate_window_lower_bound, request_cost_frontier, scan_minimum_window, window_certificate)
from w2w.service.read_replay import ReadReplayConfig, replay_reads
from w2w.workloads.read_trace import ReadSpan, ReadTask


class RequestBoundTests(unittest.TestCase):
    def test_exact_b_byte_mix_and_lifetime(self):
        design = two_compute_two_memory(widths=(256, 160, 160), depths=(1, 2, 2),
                                        home_fraction=Fraction(8, 13))
        trace = read_trace(13)
        cert = window_certificate(design, trace, ReadReplayConfig())
        task = cert['tasks'][0]
        self.assertEqual([(r['words'], r['minimum_word_lifetime_slots']) for r in task['routes']],
                         [(8, 3), (5, 4)])
        self.assertEqual(task['required_credit_word_slots'], 44)
        self.assertEqual(rate_window_lower_bound(task, 52), 176)
        # Same fixed mix at the registered finite length: 8448 / 128 = 66.
        task = window_certificate(design, read_trace(2496), ReadReplayConfig())['tasks'][0]
        self.assertEqual(task['required_credit_word_slots'], 8448)

    def test_single_credit_exact_delayed_home_oracle(self):
        config = ReadReplayConfig(outstanding_words_per_compute=1)
        design, trace = home_design(), read_trace(4)
        cert = window_certificate(design, trace, config)
        row = replay_reads(design, trace, config)
        self.assertEqual(completion_lower_bound(cert, 1), 12)
        self.assertEqual(row['makespan_slots'], 12)
        self.assertTrue(check_bound(cert, row))

    def test_zero_latency_still_occupies_one_slot(self):
        cert = window_certificate(home_design(), read_trace(4), FAST)
        self.assertEqual(cert['tasks'][0]['required_credit_word_slots'], 4)
        self.assertEqual(completion_lower_bound(cert, 128), 4)

    def test_partial_stripe_uses_actual_address_counts(self):
        design, trace = two_compute_two_memory(), read_trace(6)
        # Locate a shared word without assuming that a one-word span has mix 2:1.
        from w2w.workloads.read_residency import ReadResidency
        residence = ReadResidency(design, trace)
        word = next(i for i in range(6) if residence.locate('a', i)[2] != 0)
        trace = replace(trace, tasks=(replace(trace.tasks[0], reads=(ReadSpan('a', word * 32, 32),)),))
        cert = window_certificate(design, trace, ReadReplayConfig())
        self.assertEqual(cert['tasks'][0]['required_credit_word_slots'], 4)
        self.assertEqual(completion_lower_bound(cert, 128), 4)

    def test_dependency_compute_and_release_bound(self):
        trace = read_trace(4)
        trace = replace(trace, tasks=(replace(trace.tasks[0], compute_slots=3),
                                     ReadTask('join', None, dependencies=('a',)),
                                     ReadTask('next', 0, trace.tasks[0].reads, ('join',), release_slot=10)))
        cert = window_certificate(home_design(), trace, FAST)
        row = replay_reads(home_design(), trace, FAST)
        self.assertEqual(completion_lower_bound(cert, 128), 14)
        self.assertEqual(row['makespan_slots'], 14)
        self.assertTrue(check_bound(cert, row))

    def test_bound_survives_competition_backpressure_and_native_delay(self):
        design, trace = two_compute_two_memory(), read_trace(17, both=True)
        for window in (1, 3, 8):
            for delays in ((0, 0, 0), (2, 1, 3)):
                with self.subTest(window=window, delays=delays):
                    config = ReadReplayConfig(request_latency_slots=delays[0],
                        native_latency_slots=delays[1], link_latency_slots=delays[2],
                        outstanding_words_per_compute=window, rx_depth_words=1, rx_ready=(0, 1, 1))
                    cert = window_certificate(design, trace, config)
                    self.assertTrue(check_bound(cert, replay_reads(design, trace, config)))

    def test_request_issue_limit_is_included(self):
        design, trace = two_compute_two_memory(), read_trace(12)
        config = replace(FAST, request_words_per_compute_slot=1)
        cert = window_certificate(design, trace, config)
        self.assertGreaterEqual(completion_lower_bound(cert, 128), 12)
        self.assertTrue(check_bound(cert, replay_reads(design, trace, config)))

    def test_identity_and_timing_mismatch_rejected(self):
        design, trace = home_design(), read_trace(4)
        cert = window_certificate(design, trace, ReadReplayConfig())
        with self.assertRaisesRegex(ValueError, 'configuration'):
            check_bound(cert, replay_reads(design, trace, FAST))
        row = replay_reads(design, trace, ReadReplayConfig())
        row['residence_sha256'] = 'incorrect'
        with self.assertRaisesRegex(ValueError, 'identity'):
            check_bound(cert, row)

    def test_optimistic_observation_rejected(self):
        design, trace = home_design(), read_trace(4)
        config = ReadReplayConfig(outstanding_words_per_compute=1)
        cert = window_certificate(design, trace, config)
        row = replay_reads(design, trace, config)
        row['tasks'][0]['read_wait_slots'] = 11
        with self.assertRaisesRegex(ValueError, 'necessary bound'):
            check_bound(cert, row)


class MinimumWindowTests(unittest.TestCase):
    def setUp(self):
        self.cert = window_certificate(home_design(), read_trace(4), FAST)

    def test_impossible_deadline_needs_no_replay(self):
        def forbidden(_):
            self.fail('Resource-infeasible target must not launch replay')
        result = scan_minimum_window(self.cert, 3, 16, forbidden)
        self.assertEqual(result['status'], 'impossible_by_resource_bound')

    def test_scan_does_not_assume_monotonicity(self):
        # More credits can alter arbitration; do not binary search this pattern.
        times = {1: 7, 2: 4, 3: 8, 4: 4}
        result = scan_minimum_window(self.cert, 4, 4, times.__getitem__)
        self.assertEqual(result['minimum_window'], 2)
        self.assertEqual(result['evaluated_windows'], [1, 2])

    def test_necessary_credit_interval_is_excluded(self):
        cert = window_certificate(home_design(), read_trace(4), ReadReplayConfig())
        result = scan_minimum_window(cert, 6, 8, lambda _: 6)
        self.assertEqual(result['first_not_excluded_by_bound'], 2)
        self.assertEqual(result['evaluated_windows'], [2])

    def test_range_failure_is_not_global_impossibility(self):
        result = scan_minimum_window(self.cert, 4, 2, lambda _: 5)
        self.assertEqual(result['status'], 'unattained_within_registered_window_range')
        self.assertIsNone(result['minimum_window'])
        self.assertEqual(result['evaluated_windows'], [1, 2])

    def test_request_entries_remain_a_separate_frontier_axis(self):
        row = dict(id='a', makespan_slots=10,
                   cost=dict(export_lane_bits=10, endpoint_storage_bits=10, access_wire_bit_mm=10),
                   config=dict(outstanding_words_per_compute=4))
        other = deepcopy(row)
        other.update(id='b', makespan_slots=9)
        other['config']['outstanding_words_per_compute'] = 8
        self.assertEqual(request_cost_frontier([row, other]), ['a', 'b'])
        other['config']['outstanding_words_per_compute'] = 4
        self.assertEqual(request_cost_frontier([row, other]), ['b'])


if __name__ == '__main__':
    unittest.main()
