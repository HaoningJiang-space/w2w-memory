from fractions import Fraction
import unittest
from w2w.theory.beat_return import beat_path_period


class BeatReturnTests(unittest.TestCase):
    def test_two_slots_preserve_full_width_with_local_space(self):
        for width,depth in ((128,1),(160,2),(192,2),(256,1)):
            for stages in (0,1,2,4):
                row=beat_path_period(width,depth,stages)
                self.assertEqual(Fraction(row['words_per_slot']),Fraction(width,256))
                self.assertEqual(row['payload_bits']['link'],2*stages*width)

    def test_one_slot_without_ready_lookahead_loses_bandwidth(self):
        for width in (160,192,256):
            row=beat_path_period(width,2,stages=1,stage_slots=1)
            self.assertEqual(Fraction(row['words_per_slot']),Fraction(width,512))

    def test_stalls_conserve_words_and_bound_storage(self):
        for pattern in ((0,), (1,0), (1,1,1,1,0,0,0,0), (0,)*31+(1,)*17):
            for width in (128,160,192,256):
                row=beat_path_period(width,2,stages=4,sink_ready=pattern)
                rate=Fraction(row['words_per_slot'])
                self.assertLessEqual(rate,min(Fraction(width,256),Fraction(sum(pattern),len(pattern))))
                self.assertLessEqual(row['peak_occupancy']['rx_units']*32,row['payload_bits']['rx'])
                self.assertLessEqual(row['peak_occupancy']['link_units']*32,row['payload_bits']['link'])
                if sum(pattern):
                    self.assertGreater(rate,0)

    def test_rtl_reservoir_is_separate_from_pipeline_storage(self):
        for width in (160,192):
            row=beat_path_period(width,2,stages=4)
            self.assertEqual(row['payload_bits']['rx'],384)
            self.assertEqual(row['payload_bits']['source'],512)
            self.assertEqual(row['payload_bits']['held_beat'],width)
            self.assertEqual(row['payload_bits']['link'],8*width)


if __name__=='__main__': unittest.main()
