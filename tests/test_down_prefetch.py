"""Native counterexample gate retains math, SRAM and finite shared ports."""
import unittest,os,tempfile,copy
from pathlib import Path
from dataclasses import replace
from w2w.mapping.down_prefetch import whole_matrix_down_prefetch


def fixture():
    from w2w.architecture.compiler import compile_machine
    from w2w.architecture.presets import vertical_memory
    from w2w.workloads.moe import build_moe
    from w2w.mapping.static_weights import static_weights
    from w2w.mapping.compute_placement import place_projection_compute
    from w2w.mapping.lowering import lower
    m=compile_machine(vertical_memory());l=build_moe(((0,1),),hidden=1024,intermediate=512,experts=4,topk=2)
    a=static_weights(l,m.stack,'reference');w=static_weights(l,m.stack,'phase-split')
    g,meta=lower(l,m,w,place_projection_compute(l,m.stack,a,w,'up_local_compute'),execution_policy='s1')
    return m,g,meta


class DownPlan(unittest.TestCase):
    def test_fetch_plan_preserves_math_and_previous_block_release(self):
        m,g,meta=fixture();p=whole_matrix_down_prefetch(g)
        self.assertEqual(len(p.releases),8)
        tasks={t.id:t for t in g.tasks}
        for row in p.releases:
            self.assertNotIn(row.task[:-4]+'activation',row.fetch_predecessors)
            self.assertEqual(row.demand_tasks,(row.task[:-4]+'gate',row.task[:-4]+'up'))
            self.assertTrue(all(key in tasks for key in row.fetch_predecessors))
        from w2w.domain.execution import ControlEdge
        with self.assertRaises(ValueError):whole_matrix_down_prefetch(replace(g,control=(*g.control,ControlEdge('e0/b0/gate','e0/b0/up'))))


@unittest.skipUnless(os.getenv('W2W_BOOKSIM_BINARY') and os.getenv('W2W_RAMULATOR_BRIDGE'),'Native tools required')
class DownNative(unittest.TestCase):
    def test_prefetch_real_returns_before_H_without_early_math_or_extra_slots(self):
        from w2w.backends.ramulator import VerticalRWDL
        from w2w.backends.booksim.adapter import factory
        from w2w.system.kernel import execute_system
        from w2w.validation.vertical_access import audit_vertical_result
        from w2w.validation.request_control import audit_request_control
        from w2w.validation.down_prefetch import audit_down_prefetch
        m,g,meta=fixture();records=[]
        for enabled in (False,True):
            native=VerticalRWDL(m,refresh=True,request_control=True)
            try:
                with tempfile.TemporaryDirectory() as directory:
                    r=execute_system(m,g,native=native,network_factory=factory(binary=Path(os.environ['W2W_BOOKSIM_BINARY']),
                        directory=Path(directory)/'network',ready_router_ids=tuple(x.id for x in m.routers),ready_slots=16),
                        compute_contexts=2,fetch_contexts=2,read_issue_policy='round_robin',operand_readiness='contiguous_prefix',
                        activation_sram_read_bytes_per_cycle=128,time_advance='boundaries',max_ps=10**9,
                        down_prefetch_plan=whole_matrix_down_prefetch(g) if enabled else None)
                    self.assertTrue(audit_vertical_result(r)['passed']);self.assertTrue(audit_request_control(r)['passed'])
                    self.assertEqual(sum(e['macs'] for e in r['events'] if e['kind']=='stream_compute'),meta['macs'])
                    self.assertLessEqual(max(r['fetch_execution']['peak_contexts'].values()),2)
                    self.assertLessEqual(max(r['outstanding_peak'].values()),32)
                    if enabled:
                        proof=audit_down_prefetch(r);self.assertGreater(proof['early_allocations'],0)
                        bad=copy.deepcopy(r);bad['down_prefetch']['plan']['releases'][0]['fetch_predecessors']=[]
                        with self.assertRaises(ValueError):audit_down_prefetch(bad)
                        owner=proof['early_tasks'][0]
                        bad=dict(r,events=[e for e in r['events'] if not (e.get('task')==owner and
                            e['kind'] in ('down_prefetch_acquire','down_prefetch_release'))])
                        with self.assertRaises(ValueError):audit_down_prefetch(bad)
                    records.append((r['graph'],r['native']['completed_atoms']))
            finally:native.close()
        self.assertEqual(records[0],records[1])


if __name__=='__main__':unittest.main()
