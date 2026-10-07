"""Full-wafer regression only; unit and contract checks use tiny_fabric."""
from dataclasses import replace
import unittest
import numpy as np
from w2w.constants import BANKS
from w2w.service.guaranteed_service_exchange import contoured_geometry, ExposureFabric, Channels
from w2w.service.adapters import service_problem
from w2w.service.evaluator import CandidateEvaluator
from w2w.synthesis.service_driven_fabric import paired_layout
from w2w.synthesis.role_interfaces import catalog, make_candidate, implementation
from w2w.service.cost import CostModel


class RoleRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        physical = contoured_geometry()
        cls.physical = physical
        fabric = ExposureFabric(physical, tuple((0, 2, 3) for _ in range(BANKS)),
                                Channels((8000, 0, 8000, 8000, 0)))
        _, matching = paired_layout(fabric)
        cls.designs = {d.name: d for d in catalog(physical, matching['pairs'])}

    def test_k2_direct_strong_baseline(self):
        design = make_candidate(self.physical, [], 'k2_direct', 'k2',
                                implementation(256,256,mode='direct'), .5)
        evaluator = CandidateEvaluator(design)
        self.assertEqual(CostModel.evaluate(design)['endpoint_storage_bits'],8192)
        self.assertAlmostEqual(evaluator.population(9)['exact_mean_tb_s'],1.3277310924369747)
        self.assertAlmostEqual(evaluator.replay(range(36))['executed_tb_s'],1.)

    def test_alternate_groups_and_partial_pairs_have_legal_own_layouts(self):
        for directions in ((1,4),(1,2,3,4)):
            design = make_candidate(self.physical, [], 'k2_directions', 'k2',
                         implementation(256,256,mode='direct',directions=directions),.5,directions)
            self.assertEqual(float(service_problem(design).missing.sum()),0.)
            self.assertAlmostEqual(CandidateEvaluator(design).replay(range(36))['executed_tb_s'],1.)
        design=make_candidate(self.physical,[(0,1)],'partial','k3',
                              implementation(256,256,mode='direct'),.5,allow_unmatched=True)
        self.assertAlmostEqual(CandidateEvaluator(design).replay(range(36))['executed_tb_s'],1.)

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
