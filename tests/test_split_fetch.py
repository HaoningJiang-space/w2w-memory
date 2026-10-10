import os,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from w2w.system.return_tracker import ReturnTracker


class FiniteReturnState(unittest.TestCase):
    def test_tags_remain_finite_after_issue_context_retires(self):
        h=SimpleNamespace(builder=SimpleNamespace(tiles={'c0':object()}),
            spec=SimpleNamespace(outstanding_per_tile=1,memory_request_bytes=4096),
            tasks={'matrix':SimpleNamespace(tile='c0',reads=[SimpleNamespace(size_bytes=8192)])},
            log=lambda *a,**k:None)
        r=ReturnTracker(h,1);r.acquire('matrix')
        a=SimpleNamespace(id='a',task='matrix');b=SimpleNamespace(id='b',task='matrix')
        r.bind(a)
        with self.assertRaises(RuntimeError):r.bind(b)
        with self.assertRaises(RuntimeError):r.issue_done('matrix')
        r.commit('a');r.bind(b);r.issue_done('matrix')
        self.assertFalse(r.can_allocate('c0'))
        with self.assertRaises(RuntimeError):r.complete('matrix')
        r.commit('b');r.complete('matrix')
        self.assertTrue(r.can_allocate('c0'))
        with self.assertRaises(RuntimeError):r.commit('b')
        self.assertEqual(r.metadata_bytes,24)


@unittest.skipUnless(os.getenv('W2W_BOOKSIM_BINARY') and os.getenv('W2W_RAMULATOR_BRIDGE'),'Native tools required')
class SplitNative(unittest.TestCase):
    def test_shared_ports_and_independent_return_audit(self):
        from w2w.architecture.compiler import compile_machine
        from w2w.architecture.presets import vertical_memory
        from w2w.workloads.moe import build_moe
        from w2w.mapping.static_weights import static_weights
        from w2w.mapping.compute_placement import place_compute
        from w2w.mapping.lowering import lower
        from w2w.backends.ramulator import VerticalRWDL
        from w2w.backends.booksim.adapter import factory
        from w2w.system.kernel import execute_system
        from w2w.validation.vertical_access import audit_vertical_result
        from w2w.validation.return_tracking import audit_return_tracking
        spec=compile_machine(vertical_memory())
        logical=build_moe(((0,),),hidden=1024,intermediate=512,experts=4,topk=1)
        anchor=static_weights(logical,spec.stack,'reference');weights=static_weights(logical,spec.stack,'phase-split')
        graph,meta=lower(logical,spec,weights,place_compute(logical,spec.stack,anchor),execution_policy='s1')
        native=VerticalRWDL(spec,refresh=True,request_control=True)
        try:
            with tempfile.TemporaryDirectory() as d:
                result=execute_system(spec,graph,native=native,compute_contexts=2,fetch_contexts=2,return_contexts=3,
                    read_issue_policy='round_robin',operand_readiness='contiguous_prefix',
                    activation_sram_read_bytes_per_cycle=128,time_advance='boundaries',max_ps=1000000000,
                    network_factory=factory(binary=Path(os.environ['W2W_BOOKSIM_BINARY']),directory=Path(d)/'network',
                        ready_router_ids=tuple(r.id for r in spec.routers),ready_slots=16))
                self.assertTrue(audit_vertical_result(result)['passed'])
                proof=audit_return_tracking(result);self.assertEqual(proof['metadata_bytes_per_cluster'],304)
                self.assertEqual(sum(e.get('macs',0) for e in result['events'] if e['kind']=='stream_compute'),meta['macs'])
                self.assertLessEqual(max(result['outstanding_peak'].values()),32)
                self.assertEqual(result['fetch_execution']['return_tracking']['live_bindings'],0)
                e=next(e for e in result['events'] if e['kind']=='return_context_release')
                previous=e['association'];e['association']=9
                with self.assertRaises(ValueError):audit_return_tracking(result)
                e['association']=previous
        finally:native.close()


if __name__=='__main__':unittest.main()
