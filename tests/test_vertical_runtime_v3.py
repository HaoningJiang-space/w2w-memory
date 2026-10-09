"""Small native end-to-end layer and shared-domain access check."""
import os,tempfile,unittest
from dataclasses import replace
from pathlib import Path
from w2w.architecture.presets import vertical_memory
from w2w.architecture.compiler import compile_machine
from w2w.workloads.moe import build_moe
from w2w.mapping.data_placement import place_weights
from w2w.mapping.compute_placement import place_compute
from w2w.mapping.lowering import lower
from w2w.backends.ramulator import VerticalRWDL
from w2w.backends.booksim.adapter import factory
from w2w.system.kernel import execute_system
from w2w.validation.vertical_access import audit_vertical_result
from w2w.domain.protocol import MemoryRequest
from w2w.domain.execution import ComputeTask,ExecutionGraph


@unittest.skipUnless(os.getenv('W2W_BOOKSIM_BINARY') and os.getenv('W2W_RAMULATOR_BRIDGE'),'Native tools required')
class VerticalRuntime(unittest.TestCase):
    def test_finite_contexts_share_one_arithmetic_service(self):
        spec=compile_machine(vertical_memory('central'))
        graph=ExecutionGraph((ComputeTask('a','c0',10),ComputeTask('b','c0',10)))
        native=VerticalRWDL(spec,refresh=False)
        try:
            with tempfile.TemporaryDirectory() as d:
                r=execute_system(spec,graph,native=native,compute_contexts=2,time_advance='boundaries',max_ps=1000000,
                    network_factory=factory(binary=Path(os.environ['W2W_BOOKSIM_BINARY']),directory=Path(d)/'network'))
                self.assertTrue(audit_vertical_result(r)['passed'])
                self.assertEqual(r['compute_execution']['context_peak']['c0'],2)
                self.assertEqual(r['makespan_ps'],20000)
                self.assertEqual(r['compute_busy_ps']['c0'],20000)
                self.assertEqual(r['tasks']['a']['start_ps'],r['tasks']['b']['start_ps'])
        finally:native.close()

    def test_small_complete_ffn(self):
        for organization in ('central','distributed','external'):
            stack=vertical_memory(organization);spec=compile_machine(stack)
            logical=build_moe(((0,),),experts=4,topk=1,intermediate=512)
            weights=place_weights(logical,stack);placement=place_compute(logical,stack,weights)
            graph,meta=lower(logical,spec,weights,placement)
            native=VerticalRWDL(spec,refresh=False)
            try:
                with tempfile.TemporaryDirectory() as directory:
                    r=execute_system(spec,graph,native=native,time_advance='boundaries',max_ps=1000000000,
                        activation_sram_read_bytes_per_cycle=128,
                        network_factory=factory(binary=Path(os.environ['W2W_BOOKSIM_BINARY']),
                            directory=Path(directory)/'network',local_dma='payload_beats',cell_sideband_bits=64))
                    audit=audit_vertical_result(r)
                    self.assertEqual(audit['native_bytes'],4*1573248)
                    starts={e['task']:e['time_ps'] for e in r['events'] if e['kind']=='task_start'}
                    last={e['task']:e['time_ps'] for e in r['events'] if e['kind']=='read_deliver'}
                    self.assertTrue(any(starts[k]<at for k,at in last.items()))
            finally:native.close()

    def test_two_access_views_share_one_native_service(self):
        stack=vertical_memory();original=stack.bank_groups[0]
        alias=replace(original,id='alias')
        stack=replace(stack,bank_groups=(*stack.bank_groups,alias));spec=compile_machine(stack)
        native=VerticalRWDL(spec,refresh=False)
        a=MemoryRequest('a','task','c0',original.id,0,0,32)
        b=replace(a,id='b',memory='alias')
        try:
            self.assertEqual(native.address(a,0),native.address(b,0))
            self.assertEqual(len(native.backend.config['memory_system']['controllers']),128)
            self.assertTrue(native.submit(a,0));self.assertTrue(native.submit(b,0))
            done=set()
            for now in range(0,1000000,40):
                done.update(native.advance(now));native.take_ready()
                if done=={'a','b'}:break
            self.assertEqual(done,{'a','b'})
            self.assertEqual(native.record()['completed_atoms'],4)
            self.assertEqual(native.record()['physical_domain_count'],128)
            self.assertEqual(native.record()['reservations_live'],0)
        finally:native.close()


if __name__=='__main__':unittest.main()
