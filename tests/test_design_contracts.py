"""Unit/contract/integration gates. All service systems here have only 2C+2M."""
import ast
from dataclasses import FrozenInstanceError, replace
from fractions import Fraction
from pathlib import Path
import unittest
from tests.fixtures.tiny_fabric import two_compute_two_memory
from w2w.domain import EndpointEnvelope, EndpointSpec, NativeProfile, StaticLayout
from w2w.endpoints.role_execution import execute_periodic, ratio_sequence
from w2w.endpoints.contracts import role_envelope
from w2w.service.adapters import service_problem, solve_service
from w2w.service.evaluator import CandidateEvaluator
from w2w.service.cost import CostModel


class EndpointUnitTests(unittest.TestCase):
    def test_complete_word_tail_and_readiness(self):
        for depth, expected in ((1, .5), (2, .75)):
            spec = EndpointSpec((192,), (depth,))
            saturated = execute_periodic(spec, (0,))
            sparse = execute_periodic(spec, (0,), NativeProfile('alternate', (1, 0)))
            self.assertEqual(saturated['total_per_native'], expected)
            self.assertEqual(sparse['total_per_native'], .5)
            self.assertTrue(saturated['state_repeated'])

    def test_fixed_order_and_credit_state_are_in_witness(self):
        spec = EndpointSpec((256, 160), (1, 2))
        seq = ratio_sequence(0, 1, 8, 13)
        trace = execute_periodic(spec, seq)
        self.assertEqual(trace['rate_per_native'], [8/13, 5/13])
        stalled = execute_periodic(spec, seq, credits=((0, 0), (256, 160)))
        self.assertLess(stalled['total_per_native'], trace['total_per_native'])
        self.assertEqual(stalled['period_slots'] % 2, 0)

    def test_never_ready_and_invalid_credits(self):
        spec = EndpointSpec((256,), (1,))
        self.assertEqual(execute_periodic(spec, (0,), NativeProfile('off', (0,)))['total_per_native'], 0)
        with self.assertRaises(ValueError):
            execute_periodic(spec, (0,), credits=((257,),))
        with self.assertRaises(ValueError):
            EndpointSpec((128,), (0,))


class DesignContractTests(unittest.TestCase):
    def test_design_is_deeply_frozen(self):
        design = two_compute_two_memory()
        with self.assertRaises(FrozenInstanceError):
            design.endpoint.widths = (128, 128, 128)
        with self.assertRaises(TypeError):
            design.layout.shares[0][0] = 1.
        with self.assertRaises(ValueError):
            replace(design, endpoint=EndpointSpec((256, 0, 128), (1, 0, 1)))
        with self.assertRaises(ValueError):
            StaticLayout(((.2, .2),))
        # Polygon intersection arithmetic can put a full overlap a few ulps over 1.
        routes = list(design.geometry.routes)
        routes[0] = (*routes[0][:4], 1 + 1e-14, 1.)
        replace(design.geometry, routes=routes)
        routes[0] = (*routes[0][:4], 1.01, 1.)
        with self.assertRaises(ValueError):
            replace(design.geometry, routes=routes)

    def test_endpoint_caps_are_consumed_without_mutating_design(self):
        design = two_compute_two_memory()
        before = design.layout.sha256
        model = service_problem(design)
        self.assertAlmostEqual(solve_service(design, [4, 0])['total_tb_s'], 1.5)
        caps = {(0, 0): 1., (0, 1): .25}
        limited = model.with_delivered_caps(caps)
        self.assertAlmostEqual(limited.solve([4, 0], 0)['total_tb_s'], .75)
        self.assertAlmostEqual(model.solve([4, 0], 0)['total_tb_s'], 1.5)
        self.assertEqual(before, design.layout.sha256)

    def test_missing_bytes_cannot_be_replaced(self):
        design = two_compute_two_memory()
        model = service_problem(design).with_delivered_caps({(0, 0): 1.})
        self.assertEqual(model.solve([4, 0], 0)['total_tb_s'], 0.)
        with self.assertRaises(ValueError):
            service_problem(design, EndpointEnvelope(resource_caps=((('absent',), 1.),)))

    def test_shared_ledger_checks_bank_and_port_resources(self):
        design = two_compute_two_memory()
        model = service_problem(design)
        self.assertLess(model.audit_rates([1, 1]), 1e-12)
        self.assertGreater(model.audit_rates([2, 2]), 0.)
        # Constrain an actual shared resource via its stable label.
        envelope = role_envelope(design)
        envelope = replace(envelope, resource_caps=envelope.resource_caps + ((('memory_group_arb', 0, 0), .2),))
        result = solve_service(design, [4, 0], envelope)
        self.assertAlmostEqual(result['total_tb_s'], .3)

    def test_domain_imports_have_no_numerical_or_io_dependencies(self):
        for path in Path('w2w/domain').glob('*.py'):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or '']
                    self.assertFalse(any(v.split('.')[0] in ('numpy', 'scipy', 'networkx', 'shapely', 'pathlib', 'subprocess') for v in names))


class TinyIntegrationTests(unittest.TestCase):
    def test_serial_vs_buffered_half_width(self):
        for mode, depth, full in (('direct', 0, .5), ('buffered', 1, 1.)):
            design = two_compute_two_memory((128, 128, 128), (depth, depth, depth), Fraction(1, 2), mode)
            evaluator = CandidateEvaluator(design)
            self.assertAlmostEqual(evaluator.replay([0, 1])['executed_tb_s'], full)
            self.assertAlmostEqual(evaluator.replay([0])['executed_tb_s'], 1.)

    def test_role_candidates_and_pair_activity_oracle(self):
        for widths, depths, fraction, single in (
                ((192, 192, 192), (2, 2, 2), Fraction(1, 2), 1.5),
                ((256, 128, 128), (1, 1, 1), Fraction(2, 3), 1.5),
                ((256, 160, 160), (1, 2, 2), Fraction(8, 13), 1.625)):
            evaluator = CandidateEvaluator(two_compute_two_memory(widths, depths, fraction))
            self.assertAlmostEqual(evaluator.replay([0])['executed_tb_s'], single)
            self.assertAlmostEqual(evaluator.replay([0, 1])['executed_tb_s'], 1.)
            self.assertAlmostEqual(evaluator.population(1)['exact_mean_tb_s'], single)

    def test_aggregate_overload_is_rejected(self):
        design = two_compute_two_memory()
        narrow = replace(design, exposure=replace(design.exposure, port_bits=(4000, 8000, 8000)))
        with self.assertRaisesRegex(ValueError, 'joint credits'):
            CandidateEvaluator(narrow)

    def test_cost_uses_same_endpoint_and_counts_unused_direction(self):
        design = two_compute_two_memory()
        cost = CostModel.evaluate(design)
        self.assertEqual(cost['export_lane_bits'], 512)
        self.assertEqual(cost['endpoint_storage_bits'], 768)
        self.assertEqual(cost['bank_port_connections'], 3)
        late = CostModel.evaluate(design, 'port')
        self.assertGreater(late['access_wire_bit_mm'], cost['access_wire_bit_mm'])
        self.assertEqual(late['endpoint_storage_bits'], cost['endpoint_storage_bits'])


if __name__ == '__main__':
    unittest.main()
