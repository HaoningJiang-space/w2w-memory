"""Causal regressions: missing paths, real transfer, contention, feedback and native boundaries."""
from dataclasses import replace
from copy import deepcopy
import os
import unittest

from w2w.domain.execution import ComputeTask, ControlEdge, DataEdge, ExecutionGraph, ReadAccess, ResidentObject
from w2w.domain.protocol import Packet
from w2w.domain.system import mesh_system
from w2w.experiments.run_system_microbench import closed_loop_fixture
from w2w.memory.backend import RamulatorAbsolute
from w2w.network.router import CreditNetwork
from w2w.system.builder import SystemBuilder
from w2w.system.kernel import execute_system
from w2w.validation.system_execution import audit_system_result


def data_graph(size=64):
    return ExecutionGraph((ComputeTask('a', 'c0', 5), ComputeTask('b', 'c1', 1)),
                          data=(DataEdge('tensor', 'a', 'b', size),))


class SystemStructureTests(unittest.TestCase):
    def test_no_path_cannot_complete_data_task(self):
        spec = mesh_system(1, 2)
        disconnected = replace(spec, links=tuple(l for l in spec.links if l.kind == 'HB'))
        with self.assertRaisesRegex(ValueError, 'No executable route'):
            execute_system(disconnected, data_graph())
        result = execute_system(spec, data_graph())
        self.assertGreater(result['makespan_ps'], 6000)
        self.assertEqual(audit_system_result(result)['data_bytes'], 64)

    def test_no_stitch_profile_rejects_same_layer_edges(self):
        with self.assertRaisesRegex(ValueError, 'cross-reticle'):
            SystemBuilder(replace(mesh_system(), allow_stitching=False))

    def test_memory_never_used_as_compute_router(self):
        spec = mesh_system(1, 2)
        builder = SystemBuilder(spec)
        self.assertEqual(builder.route('c0', 'c1'), ('c0>c1',))
        illegal = replace(spec.links[-1], src='m0', dst='c1', id='fake', resource_id='fake')
        with self.assertRaisesRegex(ValueError, 'home HB'):
            SystemBuilder(replace(spec, links=spec.links+(illegal,)))

    def test_no_duplicate_capacity(self):
        spec = mesh_system()
        links = (replace(spec.links[0], resource_id=spec.links[1].resource_id), *spec.links[1:])
        with self.assertRaisesRegex(ValueError, 'duplicated'):
            SystemBuilder(replace(spec, links=links))

    def test_no_implicit_clock_or_width_conversion(self):
        spec = mesh_system()
        with self.assertRaisesRegex(ValueError, 'CDC'):
            SystemBuilder(replace(spec, links=(replace(spec.links[0], period_ps=777), *spec.links[1:])))

    def test_cyclic_task_graph_rejected(self):
        with self.assertRaisesRegex(ValueError, 'cycle'):
            ExecutionGraph((ComputeTask('a', 'c0', 1), ComputeTask('b', 'c1', 1)),
                           control=(ControlEdge('a', 'b'), ControlEdge('b', 'a')))

    def test_B0_has_communication_but_no_remote_reads(self):
        spec, graph = closed_loop_fixture()
        with self.assertRaisesRegex(ValueError, 'B0 forbids'):
            execute_system(replace(spec, baseline='B0'), graph)
        self.assertTrue(audit_system_result(execute_system(replace(spec, baseline='B0'), data_graph()))['passed'])

    def test_residency_without_direct_HB_is_legal_in_B1(self):
        spec, graph = closed_loop_fixture()
        self.assertNotIn(('c1', 'm0'), SystemBuilder(spec).edges)
        result = execute_system(spec, graph)
        self.assertEqual(audit_system_result(result)['read_words'], 8)

    def test_object_capacity_overlap_and_read_bounds(self):
        spec, graph = closed_loop_fixture()
        variants = [replace(graph, objects=graph.objects+(ResidentObject('duplicate', 'm0', 32, 64),)),
                    replace(graph, objects=(ResidentObject('weight', 'm0', 512*1024**2, 256),)),
                    replace(graph, objects=(ResidentObject('weight', 'm0', 0, 32),))]
        for bad in variants:
            with self.subTest(graph=bad), self.assertRaises(ValueError):
                SystemBuilder(spec).validate_graph(bad)


class NetworkTests(unittest.TestCase):
    def run_network(self, spec, messages, blocked_until=0):
        builder = SystemBuilder(spec)
        network = CreditNetwork(builder)
        waiting = [Packet(key, src, dst, cls, size, builder.route(src, dst))
                   for key, src, dst, cls, size in messages]
        completion = {}
        for now in range(0, 2_000_000, spec.noc_period_ps):
            network.arrive(now)
            def accept(packet):
                if now < blocked_until: return False
                completion[packet.id] = now
                return True
            network.deliver(now, accept)
            waiting = [packet for packet in waiting if not network.try_send(packet, now)]
            network.step(now)
            if not waiting and network.drained():
                return network, completion
        self.fail('Bounded network failed to drain')

    def test_single_flow_serialization_slope(self):
        spec = mesh_system(1, 2, input_buffer_flits=16, injection_flits=32, packet_payload_bytes=128)
        _, short = self.run_network(spec, [('p', 'c0', 'c1', 'activation', 32)])
        _, long = self.run_network(spec, [('p', 'c0', 'c1', 'activation', 128)])
        self.assertEqual(long['p']-short['p'], 6*spec.noc_period_ps)

    def test_two_hops_stream_instead_of_reserializing_packet(self):
        spec = mesh_system(1, 3, input_buffer_flits=16, injection_flits=32, packet_payload_bytes=128)
        _, a = self.run_network(spec, [('p', 'c0', 'c1', 'activation', 128)])
        _, b = self.run_network(spec, [('p', 'c0', 'c2', 'activation', 128)])
        self.assertEqual(b['p']-a['p'], 3000)  # one router + two link pipeline cycles

    def test_shared_classes_never_duplicate_link_capacity(self):
        spec = mesh_system(1, 3)
        network, _ = self.run_network(spec, [('a', 'c0', 'c2', 'activation', 64),
                                             ('r', 'c1', 'c2', 'response', 64)])
        sends = [e for e in network.events if e['kind'] == 'link_send']
        self.assertEqual(len(sends), len({(e['resource'], e['time_ps']) for e in sends}))
        self.assertEqual(network.link_flits['c1>c2'], 10)

    def test_ejection_backpressure_propagates_and_drains(self):
        spec = mesh_system(1, 2, input_buffer_flits=1, injection_flits=5, ejection_packets=1)
        messages = [(f'p{i}', 'c0', 'c1', 'activation', 64) for i in range(8)]
        network, completion = self.run_network(spec, messages, blocked_until=200000)
        self.assertGreater(network.rejections, 0)
        self.assertGreaterEqual(min(completion.values()), 200000)
        self.assertTrue(network.drained())
        self.assertLessEqual(max(v for k, v in network.peak_queue.items() if k[1] != 'NI'), 1)

    def test_credit_RTT_limits_small_window(self):
        spec = mesh_system(1, 2, input_buffer_flits=1)
        long = replace(spec, links=tuple(replace(l, credit_cycles=10) for l in spec.links))
        _, a = self.run_network(spec, [('p', 'c0', 'c1', 'activation', 64)])
        _, b = self.run_network(long, [('p', 'c0', 'c1', 'activation', 64)])
        _, c = self.run_network(replace(long, input_buffer_flits=16), [('p', 'c0', 'c1', 'activation', 64)])
        self.assertGreater(b['p'], a['p'])
        self.assertLess(c['p'], b['p'])

    def test_link_order_does_not_change_time(self):
        spec = mesh_system()
        messages = [('a', 'c0', 'c3', 'activation', 64), ('b', 'c1', 'c3', 'response', 64)]
        _, a = self.run_network(spec, messages)
        _, b = self.run_network(replace(spec, links=tuple(reversed(spec.links))), messages)
        self.assertEqual(a, b)


class CausalExecutionTests(unittest.TestCase):
    def test_control_and_data_have_different_semantics(self):
        spec = mesh_system(1, 2)
        control = ExecutionGraph((ComputeTask('a', 'c0', 5), ComputeTask('b', 'c1', 1)),
                                 control=(ControlEdge('a', 'b'),))
        c = execute_system(spec, control)
        d = execute_system(spec, data_graph())
        self.assertEqual(c['makespan_ps'], 6000)
        self.assertEqual(c['network']['accepted_packets'], 0)
        self.assertGreater(d['makespan_ps'], c['makespan_ps'])
        for row in (c, d): self.assertTrue(audit_system_result(row)['passed'])

    def test_long_wire_changes_time_and_cost(self):
        spec, graph = closed_loop_fixture()
        a = execute_system(spec, graph)
        longer = replace(spec, links=tuple(replace(l, pipeline_cycles=l.pipeline_cycles+4,
                                                 credit_cycles=l.credit_cycles+4) for l in spec.links))
        b = execute_system(longer, graph)
        self.assertGreater(b['makespan_ps'], a['makespan_ps'])
        self.assertGreater(b['physical']['pipeline_bits'], a['physical']['pipeline_bits'])

    def test_native_ready_is_not_consumer_completion(self):
        spec, graph = closed_loop_fixture()
        result = execute_system(spec, graph)
        ready = {e['request']: e['time_ps'] for e in result['events'] if e['kind'] == 'native_ready'}
        delivered = {e['request']: e['time_ps'] for e in result['events'] if e['kind'] == 'read_deliver'}
        self.assertTrue(all(delivered[k] > ready[k] for k in ready))
        self.assertGreater(result['tasks']['expert']['start_ps'], max(ready.values()))

    def test_outstanding_feedback_and_MC_bounds(self):
        spec, graph = closed_loop_fixture()
        a = execute_system(spec, graph)
        b = execute_system(replace(spec, outstanding_per_tile=1,
                                   memories=tuple(replace(m, transaction_slots=1) for m in spec.memories)), graph)
        self.assertGreater(b['makespan_ps'], a['makespan_ps'])
        self.assertLessEqual(max(b['outstanding_peak'].values()), 1)
        self.assertLessEqual(max(b['mc_peak'].values()), 1)
        self.assertTrue(audit_system_result(b)['passed'])

    def test_finite_SRAM_rejects_untiled_working_set(self):
        spec, graph = closed_loop_fixture()
        tiny = replace(spec, tiles=tuple(replace(t, sram_bytes=64) for t in spec.tiles))
        with self.assertRaisesRegex(ValueError, 'working set exceeds'):
            execute_system(tiny, graph)

    def test_finite_SRAM_serializes_preparation(self):
        spec = mesh_system(1, 2)
        graph = ExecutionGraph((ComputeTask('a', 'c0', 4, scratch_bytes=128),
                                ComputeTask('b', 'c0', 4, scratch_bytes=128)))
        result = execute_system(replace(spec, tiles=tuple(replace(t, sram_bytes=128) for t in spec.tiles)), graph)
        self.assertEqual(result['makespan_ps'], 8000)
        self.assertEqual(result['sram_peak_bytes']['c0'], 128)
        self.assertTrue(audit_system_result(result)['passed'])

    def test_clock_boundaries_are_exact(self):
        spec = mesh_system(1, 2, noc_period_ps=1200, dram_period_ps=1000)
        spec = replace(spec, tiles=tuple(replace(t, compute_period_ps=700) for t in spec.tiles))
        result = execute_system(spec, data_graph())
        self.assertEqual(result['quantum_ps'], 100)
        self.assertTrue(all(t['start_ps'] % 700 == 0 for t in result['tasks'].values()))
        self.assertTrue(audit_system_result(result)['passed'])

    def test_data_and_remote_return_share_physical_link(self):
        spec = mesh_system(1, 2)
        graph = ExecutionGraph((ComputeTask('producer', 'c0', 1),
                                ComputeTask('consumer', 'c1', 1, (ReadAccess('w', 0, 256),))),
                               (ResidentObject('w', 'm0', 0, 256),),
                               (DataEdge('dispatch', 'producer', 'consumer', 1024),))
        result = execute_system(spec, graph)
        cls = {e['traffic_class'] for e in result['events'] if e['kind'] == 'link_send' and e['link'] == 'c0>c1'}
        self.assertEqual(cls, {'activation', 'response'})
        self.assertTrue(audit_system_result(result)['passed'])

    def test_auditor_catches_fabricated_early_compute(self):
        spec, graph = closed_loop_fixture()
        result = deepcopy(execute_system(spec, graph))
        event = next(e for e in result['events'] if e['kind'] == 'task_start' and e['task'] == 'expert')
        result['events'].remove(event)
        event['time_ps'] = 0
        result['events'].insert(0, event)
        with self.assertRaisesRegex(ValueError, 'before tensor delivery'):
            audit_system_result(result)

    def test_missing_native_dependency_is_explicit(self):
        spec = replace(mesh_system(), dram_period_ps=1200)
        with self.assertRaisesRegex(ValueError, 'HBM2 reference'):
            RamulatorAbsolute(spec)

    @unittest.skipUnless(os.environ.get('W2W_RAMULATOR_BRIDGE'), 'Optional pinned native bridge not supplied')
    def test_native_absolute_time_adapter(self):
        spec, graph = closed_loop_fixture()
        backend = RamulatorAbsolute(spec)
        try:
            result = execute_system(spec, graph, native=backend)
            self.assertEqual(audit_system_result(result)['read_words'], 8)
            self.assertEqual(result['native']['completed'], 8)
            self.assertEqual(result['native']['pending'], 0)
            # Native callback includes the native bus. Do not duplicate that HB transfer.
            self.assertFalse(any('m' in key for key in result['network']['link_flits']))
        finally:
            backend.close()


if __name__ == '__main__':
    unittest.main()
