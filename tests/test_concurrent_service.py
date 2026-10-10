"""S1 removes artificial projection order without adding native/arithmetic service."""
import os,tempfile,unittest
from pathlib import Path
from w2w.architecture.presets import vertical_memory
from w2w.architecture.compiler import compile_machine
from w2w.workloads.moe import build_moe
from w2w.mapping.static_weights import static_weights
from w2w.mapping.compute_placement import place_compute
from w2w.mapping.lowering import lower


class DependencyPolicy(unittest.TestCase):
    def test_sequence_keeps_layer_storage_preload_and_sequence_barriers(self):
        from w2w.mapping.sequence import lower_sequence
        spec=compile_machine(vertical_memory());shape=dict(experts=4,topk=1,hidden=1024,intermediate=1536)
        tokens=((0,),(1,))
        a,ma,pa=lower_sequence(tokens,spec,shape=shape)
        b,mb,pb=lower_sequence(tokens,spec,shape=shape,execution_policy='s1')
        self.assertEqual(a.tasks,b.tasks);self.assertEqual(a.objects,b.objects);self.assertEqual(a.data,b.data)
        self.assertEqual(pa,pb)
        for key in ma:self.assertEqual(ma[key],mb[key])
        controls={(e.producer,e.consumer) for e in b.control}
        self.assertIn(('I0001/t0/combine','I0002/t0/input'),controls)
        self.assertIn(('I0000/e0/b0/accumulate','I0000/e0/b1/up'),controls)
        self.assertNotIn(('I0000/e0/b0/gate','I0000/e0/b0/up'),controls)
        for key in ('macs','vector_ops','catalog_weight_bytes','active_unique_weight_bytes'):
            self.assertEqual(ma[key],mb[key])

    def test_independent_projections_keep_block_and_mathematical_dependencies(self):
        spec=compile_machine(vertical_memory());logical=build_moe(((0,),),experts=4,topk=1)
        weights=static_weights(logical,spec.stack,'reference');placement=place_compute(logical,spec.stack,weights)
        a,_=lower(logical,spec,weights,placement);b,_=lower(logical,spec,weights,placement,execution_policy='s1')
        self.assertEqual(a.tasks,b.tasks);self.assertEqual(a.objects,b.objects);self.assertEqual(a.data,b.data)
        controls={(e.producer,e.consumer) for e in b.control}
        self.assertNotIn(('e0/b0/gate','e0/b0/up'),controls)
        self.assertIn(('e0/b0/accumulate','e0/b1/gate'),controls)
        self.assertIn(('e0/b0/accumulate','e0/b1/up'),controls)

    def test_phase_split_moves_only_up_to_same_row_peer(self):
        stack=vertical_memory();a=build_moe(((0,),),experts=4,topk=1)
        reference=static_weights(a,stack,'reference');split=static_weights(a,stack,'phase-split')
        self.assertEqual([(w.tensor,w.size_bytes) for w in reference],[(w.tensor,w.size_bytes) for w in split])
        for old,new in zip(reference,split):
            if old.tensor.endswith('/up'):self.assertNotEqual(old.memory,new.memory)
            else:self.assertEqual(old,new)
        b=build_moe(((3,),),experts=4,topk=1)
        self.assertEqual(split,static_weights(b,stack,'phase-split'))


@unittest.skipUnless(os.getenv('W2W_BOOKSIM_BINARY') and os.getenv('W2W_RAMULATOR_BRIDGE'),'Native tools required')
class ConcurrentRuntime(unittest.TestCase):
    def test_sequence_hits_and_reloads_release_bounded_fetch_state(self):
        from w2w.mapping.sequence import lower_sequence
        from w2w.backends.ramulator import VerticalRWDL
        from w2w.backends.booksim.adapter import factory
        from w2w.system.kernel import execute_system
        from w2w.system.weight_cache import WeightCacheConfig
        from w2w.validation.vertical_access import audit_vertical_result
        from w2w.validation.request_control import audit_request_control
        spec=compile_machine(vertical_memory());shape=dict(experts=4,topk=1,hidden=1024,intermediate=512)
        catalog=build_moe(((0,),),**shape);anchor=static_weights(catalog,spec.stack,'reference')
        for policy in ('reference','phase-split'):
            weights=static_weights(catalog,spec.stack,policy)
            graph,meta,preload=lower_sequence(((0,),(1,),(0,)),spec,shape=shape,weight_layout=weights,
                compute_reference=anchor,execution_policy='s1')
            preload=tuple((tile,name) for tile,name in preload if '/e0/' in name)
            cache=WeightCacheConfig(data_bytes_per_cluster=512*1024,initial_resident=preload)
            native=VerticalRWDL(spec,refresh=True,request_control=True)
            try:
                with tempfile.TemporaryDirectory() as d:
                    result=execute_system(spec,graph,native=native,compute_contexts=2,fetch_contexts=2,
                        read_issue_policy='round_robin',weight_cache=cache,operand_readiness='contiguous_prefix',
                        activation_sram_read_bytes_per_cycle=128,time_advance='boundaries',max_ps=1000000000,
                        network_factory=factory(binary=Path(os.environ['W2W_BOOKSIM_BINARY']),directory=Path(d)/'network',
                            ready_router_ids=tuple(r.id for r in spec.routers),ready_slots=16))
                    self.assertTrue(audit_vertical_result(result)['passed'])
                    self.assertTrue(audit_request_control(result)['passed'])
                    stats=result['weight_cache']['stats']
                    self.assertGreater(stats.get('hits',0),0);self.assertGreater(stats.get('evictions',0),0)
                    self.assertGreater(stats.get('reload_bytes',0),0)
                    self.assertEqual(result['fetch_execution']['live_contexts'],0)
                    self.assertEqual(sum(e.get('macs',0) for e in result['events'] if e['kind']=='stream_compute'),meta['macs'])
            finally:native.close()

    def test_small_phase_split_has_overlapping_fetch_and_shared_ports(self):
        from w2w.backends.ramulator import VerticalRWDL
        from w2w.backends.booksim.adapter import factory
        from w2w.system.kernel import execute_system
        from w2w.validation.vertical_access import audit_vertical_result
        spec=compile_machine(vertical_memory());logical=build_moe(((0,),),experts=4,topk=1,hidden=1024,intermediate=512)
        reference=static_weights(logical,spec.stack,'reference');weights=static_weights(logical,spec.stack,'phase-split')
        graph,meta=lower(logical,spec,weights,place_compute(logical,spec.stack,reference),execution_policy='s1')
        native=VerticalRWDL(spec,refresh=True,request_control=True,gateway_trace_bin_ps=100000)
        try:
            with tempfile.TemporaryDirectory() as d:
                result=execute_system(spec,graph,native=native,compute_contexts=2,fetch_contexts=2,read_issue_policy='round_robin',
                    operand_readiness='contiguous_prefix',activation_sram_read_bytes_per_cycle=128,time_advance='boundaries',max_ps=1000000000,
                    network_factory=factory(binary=Path(os.environ['W2W_BOOKSIM_BINARY']),directory=Path(d)/'network',
                        ready_router_ids=tuple(r.id for r in spec.routers),ready_slots=16))
                self.assertTrue(audit_vertical_result(result)['passed'])
                first={};last={}
                for e in result['events']:
                    if e['kind']=='read_issue':first.setdefault(e['task'],e['time_ps'])
                    elif e['kind']=='read_deliver':last[e['task']]=e['time_ps']
                self.assertLess(first['e0/b0/up'],last['e0/b0/gate'])
                self.assertLess(first['e0/b0/gate'],last['e0/b0/up'])
                self.assertLessEqual(max(result['outstanding_peak'].values()),32)
                self.assertLessEqual(max(result['fetch_execution']['peak_contexts'].values()),2)
                self.assertEqual(sum(e.get('macs',0) for e in result['events'] if e['kind']=='stream_compute'),meta['macs'])
                bins=result['native']['gateway_service_bins']['gateways']
                both={row['start_ps'] for row in bins['g0_0']}&{row['start_ps'] for row in bins['g0_1']}
                self.assertTrue(both,'Independent local and peer gateways never served in the same observed bin')
        finally:native.close()


if __name__=='__main__':unittest.main()
