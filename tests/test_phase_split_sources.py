"""Signed completion accounting retains regressions and inter-window drains."""
import unittest
from tools.analyze_phase_split_sources import signed_accounting


class PairedSources(unittest.TestCase):
    def test_signed_windows_drain_and_mixed_cache_are_conserved(self):
        rows=[dict(phase='decode',cache_class=kind,delta_ps=delta,
            reference_native_bytes=a,candidate_native_bytes=b) for kind,delta,a,b in
            (('both_zero_native',-3,0,0),('both_with_native',10,100,110),('mixed_native',-2,10,0))]
        value=signed_accounting(dict(makespan_ps=100,inter_window_drain_ps=7),
            dict(makespan_ps=93,inter_window_drain_ps=5),dict(windows=rows))
        self.assertEqual(value['signed_total_ps'],7)
        self.assertEqual(value['signed_window_sum_ps'],5)
        self.assertEqual(value['observed_native_classes']['both_zero_native']['slower'],1)
        self.assertEqual(value['observed_native_classes']['both_with_native']['candidate_native_bytes'],110)
        self.assertEqual(value['observed_native_classes']['mixed_native']['benefit_ps'],-2)
        with self.assertRaises(ValueError):signed_accounting(dict(makespan_ps=101,inter_window_drain_ps=7),
            dict(makespan_ps=93,inter_window_drain_ps=5),dict(windows=rows))


if __name__=='__main__':unittest.main()
