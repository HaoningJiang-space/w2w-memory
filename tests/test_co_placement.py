"""Real Up/X/U routing, finite cache placement and matched-work intervention."""
import os,tempfile,unittest,copy
from pathlib import Path
from dataclasses import asdict
from w2w.architecture.compiler import compile_machine
from w2w.architecture.presets import vertical_memory
from w2w.workloads.moe import build_moe
from w2w.mapping.static_weights import static_weights
from w2w.mapping.compute_placement import place_projection_compute,PROJECTION_POLICIES
from w2w.mapping.lowering import lower
from w2w.mapping.sequence import lower_sequence
from w2w.validation.co_placement import audit_co_placement_inputs


class ProjectionMapping(unittest.TestCase):
    def test_only_up_moves_and_nonlocal_work_is_matched(self):
        from w2w.experiments.run_co_placement import inputs
        cases={p:inputs(p,'cold')[3] for p in PROJECTION_POLICIES}
        self.assertTrue(audit_co_placement_inputs(cases)['passed'])
        with self.assertRaises(ValueError):audit_co_placement_inputs(dict(cases,unsupported_control=cases['up_local_compute']))
        tasks={p:{t['id']:t for t in d['graph']['tasks']} for p,d in cases.items()}
        up='e62/b8/up';old=tasks['reference_compute'][up]['tile']
        self.assertNotEqual(tasks['up_local_compute'][up]['tile'],old)
        self.assertNotEqual(tasks['up_matched_nonlocal'][up]['tile'],old)
        bad=copy.deepcopy(cases)
        t=next(t for t in bad['up_local_compute']['graph']['tasks'] if t['id']==up)
        t['tile']=old
        with self.assertRaises(ValueError):audit_co_placement_inputs(bad)

    def test_single_expert_cannot_claim_matched_nonlocal_control(self):
        spec=compile_machine(vertical_memory());logical=build_moe(((0,),),hidden=1024,intermediate=512,experts=4,topk=1)
        ref=static_weights(logical,spec.stack,'reference');weights=static_weights(logical,spec.stack,'phase-split')
        with self.assertRaises(ValueError):place_projection_compute(logical,spec.stack,ref,weights,'up_matched_nonlocal')

    def test_warm_catalog_is_moved_to_actual_consumer_and_not_duplicated(self):
        from w2w.experiments.run_co_placement import inputs
        cases={p:inputs(p,'multilayer')[3] for p in PROJECTION_POLICIES[:2]}
        self.assertTrue(audit_co_placement_inputs(cases)['passed'])
        a,b=(cases[p]['cache']['initial_resident'] for p in PROJECTION_POLICIES[:2])
        self.assertEqual([name for _,name in a],[name for _,name in b])
        self.assertTrue(any(x[0]!=y[0] for x,y in zip(a,b) if x[1].endswith('/up')))
        bad=copy.deepcopy(cases);bad['up_local_compute']['cache']['initial_resident']=a
        with self.assertRaises(ValueError):audit_co_placement_inputs(bad)


@unittest.skipUnless(os.getenv('W2W_BOOKSIM_BINARY') and os.getenv('W2W_RAMULATOR_BRIDGE'),'Native tools required')
class LocalProjectionNative(unittest.TestCase):
    def test_input_and_up_results_use_real_dataedges_with_shared_services(self):
        from w2w.backends.ramulator import VerticalRWDL
        from w2w.backends.booksim.adapter import factory
        from w2w.system.kernel import execute_system
        from w2w.system.weight_cache import WeightCacheConfig
        from w2w.validation.vertical_access import audit_vertical_result
        from w2w.validation.request_control import audit_request_control
        from w2w.analysis.co_placement import traffic_by_operand
        spec=compile_machine(vertical_memory());shape=dict(hidden=1024,intermediate=512,experts=4,topk=1)
        logical=build_moe(((0,),),**shape);anchor=static_weights(logical,spec.stack,'reference');weights=static_weights(logical,spec.stack,'phase-split')
        for cached in (False,True):
            if cached:
                graph,meta,preload=lower_sequence(((0,),(1,),(0,)),spec,layers=2,shape=shape,weight_layout=weights,
                    compute_reference=anchor,execution_policy='s1',projection_policy='up_local_compute')
                preload=tuple((tile,name) for tile,name in preload if '/e0/' in name)
                cache=WeightCacheConfig(data_bytes_per_cluster=512*1024,initial_resident=preload)
            else:
                graph,meta=lower(logical,spec,weights,place_projection_compute(logical,spec.stack,anchor,weights,'up_local_compute'),execution_policy='s1');cache=None
            native=VerticalRWDL(spec,refresh=True,request_control=True)
            try:
                with tempfile.TemporaryDirectory() as d:
                    r=execute_system(spec,graph,native=native,compute_contexts=2,fetch_contexts=2,read_issue_policy='round_robin',
                        operand_readiness='contiguous_prefix',weight_cache=cache,time_advance='boundaries',max_ps=1000000000,
                        activation_sram_read_bytes_per_cycle=128,network_factory=factory(binary=Path(os.environ['W2W_BOOKSIM_BINARY']),
                            directory=Path(d)/'network',ready_router_ids=tuple(x.id for x in spec.routers),ready_slots=16))
                    self.assertTrue(audit_vertical_result(r)['passed']);self.assertTrue(audit_request_control(r)['passed'])
                    traffic=traffic_by_operand(r)
                    self.assertEqual(traffic['operands']['weight/up']['remote_endpoint_payload_bytes'],0)
                    self.assertGreater(traffic['operands']['U/to_activation']['remote_endpoint_payload_bytes'],0)
                    self.assertEqual(sum(traffic['actual_macs_by_cluster'].values()),meta['macs'])
                    self.assertLessEqual(max(r['outstanding_peak'].values()),32)
                    self.assertLessEqual(max(r['fetch_execution']['peak_contexts'].values()),2)
                    if cached:
                        self.assertGreater(r['weight_cache']['stats'].get('hits',0),0)
                        self.assertGreater(r['weight_cache']['stats'].get('reload_bytes',0),0)
                        self.assertGreater(r['weight_cache']['stats'].get('evictions',0),0)
            finally:native.close()


if __name__=='__main__':unittest.main()
