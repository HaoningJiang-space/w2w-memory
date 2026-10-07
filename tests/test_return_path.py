import unittest
from fractions import Fraction
from dataclasses import replace

from w2w.theory.return_path import packed_rx_requirement, return_path_period
from tests.fixtures.tiny_fabric import two_compute_two_memory
from tests.test_read_workload import read_trace
from w2w.workloads.read_trace import ReadSpan
from w2w.service.read_replay import ReadReplayConfig, replay_reads


class ReturnPathTests(unittest.TestCase):
    def test_isolated_prediction_matches_long_word_replay(self):
        for width, rx in ((160, 2), (160, 3), (192, 2), (192, 3)):
            design = two_compute_two_memory(widths=(256, width, width), depths=(1, 2, 2),
                                            home_fraction=Fraction(1, 2))
            # Preserve legal reciprocal residency; this phase reads only the
            # odd-address words, which all reside at the peer in this fixture.
            trace = read_trace(4800)
            trace = replace(trace, tasks=(replace(trace.tasks[0], reads=tuple(
                ReadSpan('a', i * 32, 32) for i in range(1, 4800, 2))),))
            rate = Fraction(return_path_period(width, 2, rx)['words_per_slot'])
            row = replay_reads(design, trace, ReadReplayConfig(
                outstanding_words_per_compute=4096, rx_depth_words=rx))
            self.assertLessEqual(abs(row['makespan_slots'] - 2400 / rate), 5)

    def test_packing_phase_requires_more_than_ceil_word_beats(self):
        result = packed_rx_requirement(256, 160, 1)
        self.assertEqual(result['beat_spans'], [2, 3, 2, 3, 2])
        self.assertEqual(result['necessary_mean_rx_occupancy'], '17/8')
        self.assertEqual(result['minimum_integer_rx'], 3)
        self.assertEqual(packed_rx_requirement(256, 192, 1)['necessary_mean_rx_occupancy'], '9/4')

    def test_receiver_requirement_is_not_monotone_in_width(self):
        self.assertEqual([packed_rx_requirement(256, w, 1)['minimum_integer_rx'] for w in (128, 160, 192, 224, 256)],
                         [2, 3, 3, 3, 2])

    def test_periodic_word_witnesses_at_two_and_three_rx_entries(self):
        for width, depth, rx, rate in ((128, 1, 2, '1/2'), (160, 2, 2, '3/5'), (192, 2, 2, '2/3'),
                                      (160, 2, 3, '5/8'), (192, 2, 3, '3/4'), (256, 1, 2, '1')):
            row = return_path_period(width, depth, rx)
            self.assertEqual(row['words_per_slot'], rate)
            self.assertEqual(len(row['periodic_states']), row['period_slots'])

    def test_link_latency_and_receiver_capacity_limit_service(self):
        self.assertEqual(return_path_period(256, 1, 1)['words_per_slot'], '1/2')
        self.assertEqual(return_path_period(256, 1, 2, link_latency=2)['words_per_slot'], '2/3')
        for width in (64, 96, 128, 160, 192, 224, 256):
            low = Fraction(return_path_period(width, 2, 2)['words_per_slot'])
            high = Fraction(return_path_period(width, 2, 3)['words_per_slot'])
            self.assertLessEqual(low, high)
            self.assertLessEqual(high, Fraction(width, 256))


if __name__ == '__main__':
    unittest.main()
