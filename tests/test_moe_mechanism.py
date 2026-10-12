"""Completion-witness and paired-case negatives; no hardware performance fixtures."""
import copy,unittest
from w2w.analysis.moe_mechanism import completion_chain,compare_cases,INTERVALS


def chain_fixture():
    graph=dict(tasks=[dict(id=k,release_ps=r) for k,r in [('early',0),('late',2),('join',0)]],
        control=[dict(producer=k,consumer='join') for k in ('early','late')],data=[])
    def row(k,r,a,o,s,g,c):
        return dict(task=k,dependency_ready_ps=r,completed_ps=c,
            observed_intervals_ps={f:y-x for f,x,y in zip(INTERVALS,[r,a,o,s,g],[a,o,s,g,c])},arithmetic_service_ps=c-g)
    rows=[row('early',0,0,0,0,0,5),row('late',2,2,2,2,2,9),row('join',9,10,14,16,17,20)]
    return graph,dict(tasks={r['task']:r for r in rows})


class MechanismReader(unittest.TestCase):
    def test_latest_dependency_reconstructs_time_without_summing_parallel_tasks(self):
        g,l=chain_fixture();p=completion_chain(g,l,0,20)
        self.assertEqual([r['task'] for r in p['tasks']],['late','join'])
        self.assertEqual(p['initial_release_ps'],2)
        self.assertEqual(p['initial_release_ps']+sum(p['interval_totals_ps'].values()),20)
        self.assertEqual(p['interval_totals_ps']['admit_to_operands_ps'],4)
        self.assertGreater(sum(r['completed_ps']-r['dependency_ready_ps'] for r in l['tasks'].values()),20)

    def test_wrong_release_or_unwitnessed_makespan_is_rejected(self):
        g,l=chain_fixture()
        with self.assertRaises(ValueError):completion_chain(g,l,0,21)
        l['tasks']['join']['dependency_ready_ps']=8
        with self.assertRaises(ValueError):completion_chain(g,l,0,20)

    def test_positive_and_negative_deltas_keep_mixed_cache_cases_separate(self):
        def case(durations,native):
            rows=[]
            for i,(duration,n) in enumerate(zip(durations,native)):
                rows.append(dict(index=i,phase='prefill' if i==0 else 'decode',decode_step=None if i==0 else i-1,
                    groups=[dict(layer='0',expert_token_counts={'7':1})],array_macs=100,array_service_cycles=10,array_service={'read':10},
                    duration_ps=duration,native_bytes=n,gateway_bytes={'g0':n} if n else {},
                    completion_witness=dict(interval_totals_ps={'admit_to_operands_ps':duration-10,'first_grant_to_finish_ps':10})))
            return dict(passed=True,registration_sha256='fixture',cohort_sha256='fixture',machine_sha256='fixture',npu_profile={'peak':16384},cache_budget={'bytes':184},windows=rows)
        a=case([100,50,200,100],[10,0,20,0]);b=case([90,55,150,120],[10,0,10,1])
        p=compare_cases(a,b)
        self.assertEqual(p['phase_and_cache_groups']['prefill']['delta_ps'],10)
        self.assertEqual(p['phase_and_cache_groups']['both_zero_native']['delta_ps'],-5)
        self.assertEqual(p['phase_and_cache_groups']['both_with_native']['delta_ps'],50)
        self.assertEqual(p['phase_and_cache_groups']['mixed_native']['delta_ps'],-20)
        changed=copy.deepcopy(b);changed['windows'][1]['groups'][0]['expert_token_counts']={'8':1}
        with self.assertRaises(ValueError):compare_cases(a,changed)
        changed=copy.deepcopy(b);changed['npu_profile']['peak']=32768
        with self.assertRaises(ValueError):compare_cases(a,changed)


if __name__=='__main__':unittest.main()
