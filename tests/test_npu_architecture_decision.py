"""Reader-contract fixtures are not captured application performance evidence."""
import copy
import unittest
from w2w.analysis.architecture_decision import baseline_screen


def reader_cases():
    cases=[]
    # These deliberately fictitious receipts exercise ranking and rejection.
    for B in (1,4,16,32):
        for policy,time,traffic in (('reference',100,10),('phase_split',80,20),('up_local',90,5)):
            cases.append(dict(B=B,baseline=policy,passed=True,full_captured_lifecycle=True,
                registration_sha256='reader-fixture-only',cohort_sha256=f'fixture-{B}',
                original_request_hashes=[f'fixture-request-{B}'],executed_layers=['0','1'],
                token_expert_assignments=B*8,npu_macs=B*1000,npu_service_cycles=B*10,
                npu_service={'macs':B*1000},late_window_time_ps=time//2,
                proof=dict(makespan_ps=time,drained_ps=time+1,native_bytes=100),
                activity_counts=dict(noc_cell_bit_mm=traffic,macs=B*1000)))
    return cases


class ArchitectureDecisionReader(unittest.TestCase):
    def test_mapping_ranking_is_not_architecture_acceptance(self):
        result=baseline_screen(reader_cases())
        self.assertTrue(result['complete_mapping_screen'])
        self.assertFalse(result['architecture_gate_passed'])
        self.assertFalse(result['new_hardware_justified'])
        row=result['batches']['32']
        self.assertEqual(row['fastest_observed_mapping'],'phase_split')
        self.assertEqual(set(row['non_dominated_mappings']),{'phase_split','up_local'})

    def test_missing_duplicate_incomplete_or_changed_work_is_rejected(self):
        original=reader_cases()
        bad=[original[:-1],original+[original[0]]]
        for field,value in (('passed',False),('full_captured_lifecycle',False),
                            ('cohort_sha256','another-cohort'),('npu_service_cycles',999),
                            ('original_request_hashes',['another-source']),('executed_layers',['0','0'])):
            changed=copy.deepcopy(original);changed[1][field]=value;bad.append(changed)
        for cases in bad:
            with self.subTest(cases=cases[-1]['baseline']):
                with self.assertRaises(ValueError):baseline_screen(cases)

    def test_invalid_late_window_or_activity_cannot_create_a_pareto_winner(self):
        for field,value in (('late_window_time_ps',0),('late_window_time_ps',101),('late_window_time_ps',float('nan'))):
            cases=reader_cases();cases[0][field]=value
            with self.assertRaises(ValueError):baseline_screen(cases)
        cases=reader_cases();cases[0]['activity_counts']['noc_cell_bit_mm']=-1
        with self.assertRaises(ValueError):baseline_screen(cases)


if __name__=='__main__':unittest.main()
