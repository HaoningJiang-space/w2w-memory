import unittest
from tools.run_fetch_factor_probe import fetch_admission
from w2w.analysis.service_bounds import matrix_pipeline,fetch_state_minimum_holds


class FetchLifetime(unittest.TestCase):
    def test_wait_interval_distinguishes_issue_from_return_only_ownership(self):
        events=[dict(kind=kind,tile='c0',task=task,time_ps=at) for kind,task,at in (
            ('fetch_context_acquire','a',0),('fetch_context_acquire','b',0),
            ('fetch_context_release','a',10),('fetch_context_acquire','c',10),
            ('fetch_context_release','b',12),('fetch_context_release','c',15))]
        result=dict(events=events,graph=dict(tasks=[dict(id=k,tile='c0',reads=[1]) for k in 'abc']))
        stage=dict(tasks={k:dict(milestones=dict(dependency_ready=ready,allocate=allocated,read_issue_last=issued))
            for k,ready,allocated,issued in (('a',0,0,4),('b',0,0,8),('c',2,10,13))})
        report=fetch_admission(result,stage);delay=report['admission_delays']['c']
        self.assertEqual(delay['elapsed_ps'],8)
        self.assertEqual(delay['return_only_slot_overlap_ps'],8)
        self.assertEqual(delay['any_return_only_full_ps'],6)
        self.assertEqual(delay['all_return_only_full_ps'],2)
        self.assertEqual(report['lifetime_summary']['occupied_ps'],27)
        self.assertEqual(report['lifetime_summary']['return_only_ps'],12)
        stage['tasks']['a']['milestones']['read_issue_last']=11
        with self.assertRaises(ValueError):fetch_admission(result,stage)

    def test_whole_matrix_prefetch_is_a_required_strong_three_service_reference(self):
        self.assertEqual(matrix_pipeline(independent_services=3,slices=8)['ideal_schedule_ps'],18436500)
        self.assertEqual(matrix_pipeline(independent_services=3,down_prefetch=True)['ideal_schedule_ps'],16388000)
        self.assertEqual(matrix_pipeline(independent_services=2,slices=8)['payload_work_bound_ps'],32776000)

    def test_return_latency_does_not_become_issue_only_slot_work(self):
        args=dict(descriptors=128,issue_per_cycle=2,period_ps=1000)
        fast=fetch_state_minimum_holds(operand_service_ps=4000000,split=True,**args)
        slow=fetch_state_minimum_holds(operand_service_ps=8000000,split=True,**args)
        self.assertEqual(fast[0],slow[0])
        self.assertEqual(slow[1],2*fast[1])
        self.assertLess(fast[0],fast[1])
        coupled=fetch_state_minimum_holds(operand_service_ps=8000000,**args)
        self.assertEqual(coupled,(slow[1],0))
        self.assertEqual(fetch_state_minimum_holds(operand_service_ps=0,descriptors=0,
            issue_per_cycle=2,period_ps=1000,split=True),(0,0))


if __name__=='__main__':unittest.main()
