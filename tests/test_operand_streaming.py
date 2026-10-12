"""Coordinate readiness and policy persistence; no byte-prefix/oracle shortcut."""
import unittest
from dataclasses import replace
from types import SimpleNamespace

from w2w.architecture.npu_profile import reference_profile
from w2w.domain.execution import ComputeTask,StreamGemm
from w2w.domain.npu import GemmKernel
from w2w.system.operand_streaming import StreamingKernelModel,streaming_program
from w2w.system.row_mapping import RowMappingKernelModel


class OperandStreaming(unittest.TestCase):
    def test_gate_first_tick_needs_distinct_output_rows_not_a_byte_prefix(self):
        p=reference_profile();k=GemmKernel('g',1,128,4096,'W');model=StreamingKernelModel(p,{'g':k})
        frontier=SimpleNamespace(mask=(1<<16)-1)
        model.bind_execution(SimpleNamespace(operand_readiness='contiguous_prefix',spec=SimpleNamespace(memory_request_bytes=4096),operand_frontiers={'g':frontier}))
        task=ComputeTask('g','c0',model.plans['g']['cycles'],stream=StreamGemm('W',524288,128,k.macs,16384,32768))
        state=dict(read_bytes=65536,stream_scale_delivered=128)
        self.assertFalse(model.ready('g',state,task))
        # Out-of-order complete descriptors at each original N tile are legal;
        # this is an explicitly funded coordinate policy, not prefix counting.
        frontier.mask=sum(1<<i for i in range(0,128,16))
        self.assertTrue(model.ready('g',state,task))
        state['stream_scale_delivered']=0
        self.assertFalse(model.ready('g',state,task))

    def test_probe_rom_work_is_paid_and_all_weights_covered(self):
        p=reference_profile()
        for N,K in ((128,4096),(4096,128)):
            code,plan,masks=streaming_program(1,N,K,'FP8_E4M3FN',p)
            self.assertEqual(sum(i.macs for i in code),N*K)
            self.assertEqual(len(code),len(masks))
            self.assertGreater(plan['scratch_bytes'],plan['streaming']['base_plan']['scratch_bytes'])
            self.assertGreater(plan['service']['activation_sram_bytes'],plan['streaming']['base_plan']['service']['activation_sram_bytes'])
            covered=0
            for mask in masks:covered|=mask
            self.assertEqual(covered,(1<<128)-1)

    def test_policy_survives_window_replacement_and_wrong_interface_rejected(self):
        p=reference_profile();k=GemmKernel('g',1,128,4096,'W')
        stream=StreamingKernelModel(p,{'g':k});next_k=replace(k,operation_id='next')
        self.assertIsInstance(stream.for_window({'next':next_k},{}),StreamingKernelModel)
        row=RowMappingKernelModel(p,{'g':k},policy='row_auto')
        self.assertEqual(row.for_window({'next':next_k},{}).policy,'row_auto')
        with self.assertRaises(ValueError):stream.bind_execution(SimpleNamespace(operand_readiness='byte_count',spec=SimpleNamespace(memory_request_bytes=4096)))


if __name__=='__main__':unittest.main()
