"""Check geometric reuse certificates against small exhaustive graph oracles."""
from itertools import permutations
import random
import unittest

from w2w.analysis.template_binding import audit, balanced_support, point_permutation


class TemplateBindingTests(unittest.TestCase):
    def test_point_symmetry_does_not_accept_asymmetric_or_duplicate_points(self):
        points = [(1., 2.), (-1., -2.)]
        self.assertEqual(point_permutation(points, 180), [1, 0])
        self.assertIsNone(point_permutation(points, 90))
        self.assertIsNone(point_permutation([(1., 2.), (-1., -2.01)], 180))
        self.assertIsNone(point_permutation([(0., 0.), (0., 0.)], 0))

    def test_one_way_chain_forces_home_but_cycle_does_not(self):
        home = [(i, i) for i in range(3)]
        one_way = balanced_support(3, home + [(0, 1), (1, 2)])
        self.assertEqual(one_way['matching_usable_edges'], [list(e) for e in home])
        self.assertEqual(one_way['maximum_total_nonhome_fraction'], 0.)
        cycle = balanced_support(3, home + [(0, 1), (1, 2), (2, 0)])
        self.assertEqual(cycle['maximum_total_nonhome_fraction'], 3.)
        self.assertEqual(len(cycle['matching_usable_edges']), 6)

    def test_small_graphs_against_exhaustive_permutations(self):
        rng = random.Random(924)
        for _ in range(12):
            edges = {(i, j) for i in range(4) for j in range(4) if i == j or rng.random() < .4}
            choices = [p for p in permutations(range(4)) if all((c, m) in edges for c, m in enumerate(p))]
            usable = sorted({(c, m) for p in choices for c, m in enumerate(p)})
            maximum = max(sum(c != m for c, m in enumerate(p)) for p in choices)
            cert = balanced_support(4, edges)
            self.assertEqual(cert['matching_usable_edges'], [list(e) for e in usable])
            self.assertAlmostEqual(cert['maximum_total_nonhome_fraction'], maximum)

    def test_frozen_geometry_rotation_is_conditional_not_manufacturing_proof(self):
        result = audit()
        rotation = result['conditional_instance_rotation']
        self.assertEqual(rotation['orientation_counts'], {0: 18, 180: 18})
        self.assertEqual(rotation['rebuilt_overlap_edges'], 146)
        self.assertLess(rotation['maximum_capacity_fraction_error'], 1e-8)
        self.assertEqual(rotation['maximum_static_byte_fraction_error'], 0)
        self.assertIn('unverified', result['manufacturing']['per_instance_rotation'])
        for direction in result['uniform_fixed_direction']:
            self.assertEqual(direction['balanced_layout_relaxation']['maximum_total_nonhome_fraction'], 0.)
        p2 = result['uniform_fixed_direction'][1]
        self.assertEqual(p2['missing_frozen_bank_dependencies'], 576)
        self.assertEqual(len(p2['affected_compute']), 18)


if __name__ == '__main__':
    unittest.main()
