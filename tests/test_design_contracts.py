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
from w2w.synthesis.role_interfaces import static_shared_fifo


class EndpointUnitTests(unittest.TestCase):
    def test_static_fifo_preserves_period_under_credit_stalls(self):
        for width, depth, fraction in ((128, 1, Fraction(2, 3)), (160, 2, Fraction(8, 13))):
            old = EndpointSpec((256, width, width), (1, depth, depth))
            new = replace(old, shared_fifo_ports=(1, 2))
            for port in (1, 2):
                for sequence in ((0,), (port,), ratio_sequence(0, port, fraction.numerator, fraction.denominator)):
                    for credits in (None, ((0, 0, 0), old.widths)):
                        before = execute_periodic(old, sequence, credits=credits)
                        after = execute_periodic(new, sequence, credits=credits, selected_shared_port=port)
                        for key in ('delivered_words', 'sent_bits', 'period_slots', 'transient_slots',
                                    'backpressure_slots', 'ready_opportunities', 'peak_words'):
                            self.assertEqual(before[key], after[key])
                        self.assertEqual(after['physical_fifo_count'], 2)
                        self.assertTrue(after['state_repeated'])

    def test_static_fifo_rejects_dynamic_directions_and_exposes_false_collapse(self):
        old = EndpointSpec((256, 160, 160), (1, 2, 2))
        new = replace(old, shared_fifo_ports=(1, 2))
        with self.assertRaisesRegex(ValueError, 'frozen shared direction'):
            execute_periodic(new, (1, 2), selected_shared_port=1)
        with self.assertRaisesRegex(ValueError, 'frozen shared direction'):
            execute_periodic(new, (0,))  # Even home-only activity cannot choose configuration.
        self.assertEqual(execute_periodic(old, (1, 2))['total_per_native'], 1.)
        self.assertEqual(execute_periodic(old, (1,))['total_per_native'], .625)
        with self.assertRaises(ValueError):
            replace(new, serializer_location='port')

    def test_capacity_matched_ratios_close_native_service(self):
        options=[]
        for width in range(32,257,32):
            for depth in (1,2):
                trace=execute_periodic(EndpointSpec((width,),(depth,)),(0,))
                options.append((width,depth,Fraction(trace['delivered_words'][0],trace['period_slots'])))
        for wh,dh,qh in options:
            for ws,ds,qs in options:
                if qh+qs<1:
                    continue
                fraction=qh/(qh+qs)
                sequence=ratio_sequence(0,1,fraction.numerator,fraction.denominator)
                trace=execute_periodic(EndpointSpec((wh,ws),(dh,ds)),sequence)
                self.assertEqual(trace['total_per_native'],1.)
                self.assertAlmostEqual(trace['rate_per_native'][0],float(fraction))

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
    def test_shared_sender_moves_selection_after_packetization(self):
        for width, depth, fraction, view in ((128,1,Fraction(2,3),256),(160,2,Fraction(8,13),384)):
            old = two_compute_two_memory((256,width,width),(1,depth,depth),fraction)
            fifo = static_shared_fifo(old)
            sender = static_shared_fifo(old,share_serializer=True)
            a,b = CostModel.evaluate(fifo),CostModel.evaluate(sender)
            self.assertEqual(a['static_direction_selector_input_bits'],view)
            self.assertEqual(b['static_direction_selector_input_bits'],width)
            self.assertEqual((a['serializer_instances'],b['serializer_instances']),(2,1))
            for key in ('endpoint_storage_bits','pipeline_register_bits','access_wire_bit_mm','bank_access_driver_bits'):
                self.assertEqual(a[key],b[key])
            for active in ([0],[0,1]):
                self.assertEqual(CandidateEvaluator(fifo).replay(active)['served_tb_s'],
                                 CandidateEvaluator(sender).replay(active)['served_tb_s'])
        with self.assertRaises(ValueError):
            EndpointSpec((256,160,160),(1,2,2),shared_serializer=True)

    def test_static_fifo_keeps_paths_rates_and_accounts_selector(self):
        old = two_compute_two_memory()
        new = static_shared_fifo(old)
        self.assertEqual(new.shared_directions, (1, 2))
        self.assertEqual(new.layout.sha256, old.layout.sha256)
        self.assertEqual(new.exposure, old.exposure)
        self.assertEqual(new.geometry, old.geometry)
        for active in ([0], [1], [0, 1]):
            before = CandidateEvaluator(old).replay(active)
            after = CandidateEvaluator(new).replay(active)
            self.assertEqual(before['served_tb_s'], after['served_tb_s'])
            self.assertEqual(before['common_tb_s'], after['common_tb_s'])
        before, after = CostModel.evaluate(old), CostModel.evaluate(new)
        self.assertEqual((before['endpoint_storage_bits'], after['endpoint_storage_bits']), (768, 512))
        for key in ('export_lane_bits', 'access_wire_bit_mm', 'pipeline_register_bits',
                    'bank_port_connections', 'configured_hb_signal_bits', 'serializer_instances'):
            self.assertEqual(before[key], after[key])
        self.assertEqual(after['static_direction_selector_count'], 1)
        self.assertEqual(after['static_direction_selector_input_bits'], 256)
        self.assertEqual(after['static_direction_selector_output_bits'], 512)
        self.assertEqual(after['static_direction_config_bits'], 1)
        self.assertIsNone(after['static_direction_selector_wire_bit_mm'])
        with self.assertRaises(ValueError):
            CostModel.evaluate(new, 'port')
        caps = dict(role_envelope(new).resource_caps)
        self.assertEqual(caps[('bank_output', 0, 0, 2)], 0.)
        self.assertEqual(caps[('bank_output', 1, 0, 1)], 0.)
        with self.assertRaisesRegex(ValueError, 'unselected shared direction'):
            replace(new, shared_directions=(2, 1))

    def test_static_fifo_rejects_multiple_partners_before_activity_filtering(self):
        from w2w.domain import Geometry, MemoryFabricDesign
        base = two_compute_two_memory()
        xy = ((0., 0.), (1., 0.), (2., 0.))
        routes = tuple((c, c, 0, 0, 1., 1.) for c in range(3)) + (
            (1, 0, 1, 1, 1., 1.), (2, 0, 2, 2, 1., 1.))
        geometry = Geometry('3C3M', xy, xy, routes, base.geometry.bank_xy, base.geometry.port_xy)
        layout = StaticLayout(((1., 0., 0.), (.5, .5, 0.), (.5, 0., .5)))
        design = MemoryFabricDesign('two_peers', 'pair', geometry, base.exposure,
                                    base.endpoint, layout)
        with self.assertRaisesRegex(ValueError, 'multiple shared directions'):
            static_shared_fifo(design)

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
