"""Adversarial coverage/state checks for opt-in intra-array dimension mapping."""
import copy,unittest
from dataclasses import asdict,replace

from w2w.architecture.npu_profile import reference_profile
from w2w.system.npu_kernel import program
from w2w.system.row_mapping import best_os,folded_program,select_program
from w2w.validation.row_mapping import row_work


class RowMapping(unittest.TestCase):
    def test_all_supported_m_shapes_preserve_work_and_physical_ports(self):
        p=reference_profile()
        for M in (1,2,4,8,16,32):
            for N,K in ((128,4096),(4096,128)):
                code,plan=select_program(M,N,K,'FP8_E4M3FN',p,'row_auto')
                self.assertEqual(sum(i.macs for i in code),M*N*K)
                self.assertTrue(all(i.macs<=16384 and i.vector_ops<=4096 for i in code))
                self.assertTrue(all(max(i.bank_peak_weight_bytes,i.bank_peak_activation_bytes)<=256 for i in code))
                if 'row_mapping' in plan:row_work(dict(M=M,N=N,K=K,weight_dtype='FP8_E4M3FN'),plan,asdict(p))
                else:self.assertEqual(plan,best_os(M,N,K,'FP8_E4M3FN',p)[1])

    def test_duplicate_row_owner_missing_k_and_unpaid_state_rejected(self):
        p=reference_profile();_,plan=folded_program(1,128,4096,'FP8_E4M3FN',p,4)
        kernel=dict(M=1,N=128,K=4096,weight_dtype='FP8_E4M3FN')
        bad=copy.deepcopy(plan);bad['waves'][0][1]['row_group']=bad['waves'][0][0]['row_group']
        with self.assertRaises(ValueError):row_work(kernel,bad,asdict(p))
        bad=copy.deepcopy(plan);bad['waves'][0][0]['k']=128
        with self.assertRaises(ValueError):row_work(kernel,bad,asdict(p))
        bad=copy.deepcopy(plan);bad['scratch_bytes']-=plan['row_mapping']['configuration_bytes']
        with self.assertRaises(ValueError):row_work(kernel,bad,asdict(p))
        with self.assertRaises(ValueError):folded_program(1,128,4096,'FP8_E4M3FN',replace(p,vector_ops_per_cycle=4095),4)

    def test_spare_row_mapping_does_not_change_default_or_bf16_program(self):
        p=reference_profile()
        baseline=program(1,128,4096,'FP8_E4M3FN',p)[1]
        self.assertEqual(select_program(1,128,4096,'FP8_E4M3FN',p,'reference_os')[1],baseline)
        self.assertEqual(select_program(1,128,4096,'BF16',p,'row_auto'),program(1,128,4096,'BF16',p))
        self.assertGreater(baseline['cycles'],0)
        with self.assertRaises(ValueError):folded_program(8,128,4096,'FP8_E4M3FN',p,4)


if __name__=='__main__':unittest.main()
