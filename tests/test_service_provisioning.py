"""Analytical counterexamples and independent tiny replay oracles."""
from copy import deepcopy
from dataclasses import replace
from fractions import Fraction
import unittest

from tests.fixtures.tiny_fabric import two_compute_two_memory
from tests.test_read_workload import FAST, home_design, read_trace
from w2w.analysis.service_provisioning import (check_provisioning_bound, credit_matched_split,
    layout_support_certificate, pool_capacity_bound, provisioning_certificate,
    provisioning_lower_bound, steady_rate_bound)
from w2w.domain import Geometry, StaticLayout
from w2w.service.read_replay import ReadReplayConfig, replay_reads
from w2w.synthesis.role_interfaces import static_shared_fifo
from w2w.workloads.read_trace import ReadTask


class ProvisioningTests(unittest.TestCase):
    def test_credit_changes_residency_even_at_same_width(self):
        for q in (Fraction(1, 2), Fraction(5, 8)):
            result = credit_matched_split(32, q, 128)
            self.assertEqual(result['home_fraction'], '4/5')
            self.assertEqual(result['normalized_rate_upper'], '5/4')
        self.assertEqual(steady_rate_bound(32, Fraction(5, 8), Fraction(8, 13), 128), Fraction(13, 11))
        self.assertEqual(credit_matched_split(32, Fraction(5, 8), 160)['home_fraction'], '2/3')
        self.assertEqual(credit_matched_split(32, Fraction(5, 8), 176)['home_fraction'], '8/13')

    def test_closed_form_bounds_all_rational_grid_points(self):
        for q in (Fraction(1, 4), Fraction(1, 2), Fraction(5, 8), Fraction(1)):
            for n in (64, 96, 112, 128, 160, 176, 192, 256):
                result = credit_matched_split(32, q, n)
                optimum = Fraction(result['normalized_rate_upper'])
                for den in range(1, 51):
                    for num in range(1, den + 1):
                        self.assertLessEqual(steady_rate_bound(32, q, Fraction(num, den), n), optimum)

    def test_equal_lifetimes_and_insufficient_native_window(self):
        result = credit_matched_split(32, Fraction(1, 2), 128, 3, 3)
        self.assertEqual(result['normalized_rate_upper'], '4/3')
        result = credit_matched_split(32, Fraction(5, 8), 80)
        self.assertEqual(result['home_fraction'], '1')
        self.assertEqual(result['normalized_rate_upper'], '5/6')
        self.assertFalse(result['baseline_not_excluded'])
        with self.assertRaises(ValueError):
            credit_matched_split(32, Fraction(5, 8), 128, 4, 3)

    def test_pool_preserves_engine_granularity(self):
        baseline = pool_capacity_bound(32, Fraction(5, 8), Fraction(8, 13), 4, 32)
        boost = pool_capacity_bound(32, Fraction(5, 8), Fraction(8, 13), 4, 52)
        self.assertEqual(baseline['minimum_engines_necessary'], 20)
        self.assertEqual(boost['minimum_engines_necessary'], 32)
        self.assertEqual(Fraction(boost['rate_upper_words_per_slot']), Fraction(13, 2))
        self.assertEqual(Fraction(boost['reoptimized_split_normalized_upper']), Fraction(69, 64))
        self.assertEqual(pool_capacity_bound(32, Fraction(5, 8), 1, 0, 32)['minimum_engines_necessary'], 0)

    def test_complete_layout_not_active_subset(self):
        design = two_compute_two_memory()
        cert = layout_support_certificate(design)
        self.assertEqual(cert['dedicated_shared_direction_contexts_per_memory'], 2)
        self.assertEqual(cert['required_shared_direction_contexts_per_memory'], 1)
        self.assertEqual([r['required_shared_directions'] for r in cert['instances']], [[1], [2]])
        cfg = static_shared_fifo(design, share_serializer=True)
        self.assertEqual(layout_support_certificate(cfg)['instances'], cert['instances'])

    def test_two_directions_in_one_deployment_need_two_fixed_bindings(self):
        base = two_compute_two_memory()
        geometry = Geometry('3C3M', ((0, 0), (1, 0), (2, 0)), ((0, 0), (1, 0), (2, 0)),
            ((0, 0, 0, 0, 1., 1.), (1, 1, 0, 0, 1., 1.), (2, 2, 0, 0, 1., 1.),
             (1, 0, 2, 1, 1., 1.), (2, 0, 1, 2, 1., 1.),
             (0, 1, 1, 2, 1., 1.), (0, 2, 2, 1, 1., 1.)),
            base.geometry.bank_xy, base.geometry.port_xy)
        layout = StaticLayout(((1/3, 1/3, 1/3), (1/3, 2/3, 0), (1/3, 0, 2/3)))
        design = replace(base, geometry=geometry, layout=layout)
        # Separate tasks or phases cannot alter this union of resident destinations.
        cert = layout_support_certificate(design)
        self.assertEqual(cert['required_shared_direction_contexts_per_memory'], 2)
        self.assertFalse(cert['memory_wide_single_direction_compatible'])

    def test_missing_route_is_rejected(self):
        design = two_compute_two_memory()
        design = replace(design, geometry=replace(design.geometry, routes=design.geometry.routes[:2]))
        with self.assertRaisesRegex(ValueError, 'physical route'):
            layout_support_certificate(design)

    def test_home_has_no_shared_context(self):
        cert = layout_support_certificate(home_design())
        self.assertEqual(cert['required_shared_direction_contexts_per_memory'], 0)
        self.assertEqual(cert['dedicated_shared_direction_contexts_per_memory'], 0)

    def test_compute_serialization_closes_missing_dag_edges(self):
        trace = read_trace(4)
        trace = replace(trace, tasks=(trace.tasks[0], ReadTask('second', 0, trace.tasks[0].reads)))
        config = ReadReplayConfig(outstanding_words_per_compute=1)
        cert = provisioning_certificate(home_design(), trace, config)
        bound = provisioning_lower_bound(cert, 1)
        self.assertEqual(bound['dag_lower_slots'], 12)
        self.assertEqual(bound['compute_serial_lower_slots'], 24)
        row = replay_reads(home_design(), trace, config)
        self.assertEqual(row['makespan_slots'], 24)
        check_provisioning_bound(cert, row)

    def test_shared_native_cut_counts_all_consumers(self):
        design = two_compute_two_memory(widths=(256, 256, 256), depths=(0, 0, 0),
                                        home_fraction=Fraction(1, 2), mode='direct')
        trace = read_trace(4, both=True)
        cert = provisioning_certificate(design, trace, FAST)
        bound = provisioning_lower_bound(cert, 128)
        self.assertEqual(bound['dag_lower_slots'], 2)
        self.assertEqual(bound['aggregate_cut_lower_slots'], 4)
        check_provisioning_bound(cert, replay_reads(design, trace, FAST))

    def test_bound_with_release_compute_dependencies_and_stalls(self):
        trace = read_trace(11, both=True)
        trace = replace(trace, tasks=(replace(trace.tasks[0], release_slot=3, compute_slots=2),
                                     trace.tasks[1], ReadTask('tail', 0, trace.tasks[0].reads, ('a',))))
        for window in (1, 3, 8):
            config = ReadReplayConfig(outstanding_words_per_compute=window, native_latency_slots=2,
                                      rx_ready=(0, 1, 1), rx_depth_words=1)
            cert = provisioning_certificate(two_compute_two_memory(), trace, config)
            check_provisioning_bound(cert, replay_reads(two_compute_two_memory(), trace, config))

    def test_tampered_completion_rejected(self):
        trace = read_trace(4)
        trace = replace(trace, tasks=(trace.tasks[0], ReadTask('second', 0, trace.tasks[0].reads)))
        config = ReadReplayConfig(outstanding_words_per_compute=1)
        cert = provisioning_certificate(home_design(), trace, config)
        row = deepcopy(replay_reads(home_design(), trace, config))
        row['makespan_slots'] = 12
        with self.assertRaisesRegex(ValueError, 'provisioning'):
            check_provisioning_bound(cert, row)


if __name__ == '__main__':
    unittest.main()
