"""Only the new geometry and incremental-return contracts; native backend reused."""
from dataclasses import replace
import os
from pathlib import Path
import tempfile
import unittest

from w2w.domain.execution import ComputeTask, DataEdge, ExecutionGraph, ReadAccess, ResidentObject
from w2w.domain.system import mesh_system
from w2w.memory.backend import RamulatorAbsolute
from w2w.network.booksim_backend import factory
from w2w.system.kernel import execute_system
from w2w.system.wafer_machine import WaferRecipe, from_coordinates
from w2w.validation.system_execution import audit_system_result
from w2w.workloads.moe_task_graph import machine


class GeometryTests(unittest.TestCase):
    def test_coordinates_drive_both_timing_and_cost(self):
        base = machine()
        spec, record = from_coordinates(base)
        links = {l.id:l for l in spec.links}
        self.assertEqual((links['c0>c1'].length_um,links['c0>c1'].pipeline_cycles),(26100,14))
        self.assertEqual((links['c0>c6'].length_um,links['c0>c6'].credit_cycles),(33100,17))
        self.assertEqual(spec.tiles,base.tiles)
        self.assertEqual(spec.memories,base.memories)
        self.assertEqual(spec.input_buffer_flits,16)
        self.assertEqual(len(record['paths']),len(spec.links))
        self.assertGreater(sum(p['data_wire_bit_mm'] for p in record['paths']),
                           sum(l.width_bits*l.length_um/1000 for l in base.links))

    def test_invalid_wafer_or_attachment_rejected(self):
        with self.assertRaisesRegex(ValueError,'outside'):
            from_coordinates(machine(),WaferRecipe(diameter_um=200000))
        spec = machine()
        hb = next(l for l in spec.links if l.id=='m0>c0')
        with self.assertRaisesRegex(ValueError,'overlap'):
            from_coordinates(replace(spec,links=(replace(hb,dst='c1'),)))


@unittest.skipUnless(os.environ.get('W2W_BOOKSIM_SOURCE') and os.environ.get('W2W_BOOKSIM_BINARY')
                     and os.environ.get('W2W_RAMULATOR_BRIDGE'), 'Existing native components required')
class StreamingTests(unittest.TestCase):
    def execute(self, local=False, streaming=True):
        spec=mesh_system(1,2,flit_bytes=32,input_buffer_flits=8,injection_flits=64,
                         packet_payload_bytes=512,memory_request_bytes=512)
        owner='c0' if local else 'c1'
        graph=ExecutionGraph((ComputeTask('producer','c0',2),
                              ComputeTask('consumer',owner,2,(ReadAccess('w',0,1024),))),
                             (ResidentObject('w','m0',0,1024),),
                             (DataEdge('input','producer','consumer',64),))
        native=RamulatorAbsolute(spec,streaming=streaming)
        with tempfile.TemporaryDirectory() as directory:
            try:
                result=execute_system(spec,graph,native=native,network_factory=factory(
                    source=os.environ['W2W_BOOKSIM_SOURCE'],binary=os.environ['W2W_BOOKSIM_BINARY'],
                    directory=Path(directory)/'network'),max_ps=2_000_000)
            finally:
                native.close()
        self.assertTrue(audit_system_result(result)['passed'])
        return result

    def test_partial_supply_precedes_descriptor_completion_local_and_remote(self):
        for local in (False,True):
            with self.subTest(local=local):
                r=self.execute(local)
                ready={e['request']:e['time_ps'] for e in r['events'] if e['kind']=='native_ready'}
                supply=[e for e in r['events'] if e['kind']=='response_first_supply']
                self.assertTrue(any(e['time_ps']<ready[e['packet'][:-5]] for e in supply))
                self.assertEqual(r['native']['completed_words'],32)
                self.assertLessEqual(max(r['mc_peak'].values()),4)

    def test_old_whole_descriptor_mode_still_drains_same_bytes(self):
        a,b=self.execute(streaming=False),self.execute(streaming=True)
        self.assertEqual(a['graph'],b['graph'])
        self.assertEqual(a['audit']['read_words'],b['audit']['read_words'])
        self.assertEqual(a['network']['accepted_packets'],b['network']['accepted_packets'])


if __name__=='__main__':unittest.main()
