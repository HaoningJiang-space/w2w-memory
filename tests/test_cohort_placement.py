from fractions import Fraction
import unittest
import numpy as np

from tests.fixtures.tiny_fabric import two_compute_two_memory
from w2w.synthesis.cohort_placement import (pair_score, independent_object_floor_possible,
    assignment_loads, score, swap_search, resource_matrix)
from w2w.theory.cohort_service import native_full_load_limits


class CohortPlacementTests(unittest.TestCase):
    def test_same_marginals_different_completion(self):
        x = np.array([[1,1,0,0], [0,0,1,1]])
        self.assertEqual(score(x, np.ones(2), [0,0,1,1], np.eye(2)), 2)
        self.assertEqual(score(x, np.ones(2), [0,1,0,1], np.eye(2)), 1)
        np.testing.assert_array_equal(assignment_loads(x, [0,0,1,1], 2).sum(axis=0), [2,2])

    def test_best_swap_preserves_capacity_and_reaches_tiny_optimum(self):
        x = np.array([[1,1,0,0], [0,0,1,1]])
        r = swap_search(x, np.ones(2), [0,0,1,1], np.eye(2), rounds=2, candidates=6)
        self.assertEqual(r['score'], 1)
        self.assertEqual(sorted(r['owners']), [0,0,1,1])
        for item in r['history']:
            self.assertLessEqual(item['after'], item['before'])

    def test_pair_work_sum_and_imbalance_equal_native_resources(self):
        for f in (Fraction(1,2), Fraction(4,7), Fraction(4,5), Fraction(1)):
            for a in range(5):
                for b in range(5):
                    self.assertEqual(pair_score(a,b,f), max(f*a+(1-f)*b, f*b+(1-f)*a))

    def test_object_specific_split_conflicts_with_universal_floor(self):
        self.assertTrue(independent_object_floor_possible([Fraction(4,7)]*2, [Fraction(4,7)]*3))
        self.assertFalse(independent_object_floor_possible([1, Fraction(4,7)], [1, Fraction(4,7)]))

    def test_private_and_striped_object_mix_consumes_native_slack(self):
        f = Fraction(4,7)
        result = native_full_load_limits([[(1,0),(f,1-f)],[(0,1),(1-f,f)]])
        self.assertEqual(result['worst_native_loads'], ['10/7','10/7'])
        self.assertEqual(result['uniform_service_scale'], '7/10')
        self.assertFalse(result['native_floor_feasible'])

    def test_all_two_compute_object_choices_match_direct_enumeration(self):
        from itertools import product
        for a,b,c,d in product((Fraction(0),Fraction(1,2),Fraction(1)), repeat=4):
            result = native_full_load_limits([[(a,1-a),(b,1-b)],[(c,1-c),(d,1-d)]])
            expected = all(x+y<=1 and 2-x-y<=1 for x in (a,b) for y in (c,d))
            self.assertEqual(result['native_floor_feasible'], expected)

    def test_resource_matrix_captures_pair_and_request_window(self):
        design = two_compute_two_memory(widths=(256,192,192), depths=(1,2,2), home_fraction=Fraction(4,7))
        a = resource_matrix(design, window=6, rx_depth=3)
        for left in range(4):
            for right in range(4):
                self.assertAlmostEqual(float((np.array([left,right])@a).max()), float(pair_score(left,right,Fraction(4,7))))
        limited = resource_matrix(design, window=3, rx_depth=3)
        self.assertGreater(float((np.array([2,0])@limited).max()), float(pair_score(2,0,Fraction(4,7))))


if __name__ == '__main__':
    unittest.main()
