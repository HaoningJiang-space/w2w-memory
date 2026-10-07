"""Full-wafer regression only; unit and contract checks use tiny_fabric."""
from dataclasses import replace
import unittest
import numpy as np
from w2w.constants import BANKS
from w2w.service.guaranteed_service_exchange import contoured_geometry, ExposureFabric, Channels
from w2w.service.adapters import service_problem
from w2w.service.evaluator import CandidateEvaluator
from w2w.synthesis.service_driven_fabric import paired_layout
from w2w.synthesis.role_interfaces import catalog


class RoleRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        physical = contoured_geometry()
        fabric = ExposureFabric(physical, tuple((0, 2, 3) for _ in range(BANKS)),
                                Channels((8000, 0, 8000, 8000, 0)))
        _, matching = paired_layout(fabric)
        cls.designs = {d.name: d for d in catalog(physical, matching['pairs'])}

    def test_k2_preserves_private_boundary_and_legal_fixed_bytes(self):
        design = self.designs['k2_s256_matched']
        evaluator = CandidateEvaluator(design)
        self.assertEqual(float(evaluator.model.missing.sum()), 0.)
        single = [evaluator.achieved_rates([c])[0][c] for c in range(36)]
        self.assertIn(1., single)
        self.assertIn(2., single)
        np.testing.assert_allclose(evaluator.achieved_rates(range(36))[0], 1.)
        self.assertTrue(any(len(v['neighbors']) > 1 for v in evaluator.population(9)['clients']))

    def test_k3_layout_cannot_be_silently_reused_on_k2(self):
        k2 = self.designs['k2_s256_matched']
        k3 = self.designs['k3_wide_direct']
        wrong = replace(k2, layout=k3.layout)
        np.testing.assert_allclose(service_problem(wrong).missing, .25)

    def test_registered_pair_means(self):
        for name, expected in (('k3_equal192_d2', 1+(.5)*27/35),
                               ('k3_s128_matched', 1+(.5)*27/35),
                               ('k3_s160_matched', 1+(.625)*27/35),
                               ('k3_wide_direct', 1+27/35)):
            evaluator = CandidateEvaluator(self.designs[name])
            self.assertAlmostEqual(evaluator.population(9)['exact_mean_tb_s'], expected)


if __name__ == '__main__':
    unittest.main()
