import unittest
from w2w.analysis.dram_service_limits import required_inflight, analyze


class NativeServiceLimitTests(unittest.TestCase):
    def test_latency_hiding_count_is_not_egress_width(self):
        self.assertEqual(required_inflight(32,16,32),16)
        self.assertEqual(required_inflight(1000,16,32),500)
        self.assertEqual(required_inflight(1000,16.01,32),501)

    def test_native_peak_is_a_shared_channel_constraint(self):
        result=analyze('artifacts/results/dram/command_bridge')
        self.assertEqual(len(result['profiles']),4)
        for row in result['profiles']:
            self.assertEqual(row['native_channel_peak_GB_s'],32)
            self.assertEqual(row['minimum_native_inflight_at_peak'],16)
            self.assertEqual(row['banks_per_memory'],32)
            self.assertEqual(row['independent_pseudochannels'],2)
            self.assertTrue(all(m['fraction_of_channel_peak']<=1 for m in row['active_memories']))


if __name__=='__main__': unittest.main()
