import unittest
import numpy as np
from types import SimpleNamespace
from w2w.service.matching_placement import audit,mixture,ReticleService


class MatchingTests(unittest.TestCase):
    def test_unique_chain_vs_cycle(self):
        chain={(0,0),(1,0),(1,1),(2,1),(2,2)}
        a=audit(3,chain,True)
        self.assertTrue(a['unique']);self.assertEqual(a['allowed_edges'],3)
        self.assertEqual(a['balanced_layout_dimension'],0)
        cycle=chain|{(0,2)};a=audit(3,cycle,True)
        self.assertEqual(a['allowed_edges'],6);self.assertEqual(a['max_disjoint'],2)
        self.assertEqual(a['balanced_layout_dimension'],1)
        layout=mixture(a['pack'],[.5,.5])
        np.testing.assert_allclose(layout.sum(axis=0),1)
        np.testing.assert_allclose(layout.sum(axis=1),1)

    def test_matching_does_not_remove_capacity_constraint(self):
        # Two compute/two memory, separate ports per edge, fixed 50/50 layout.
        for capacity,expected in [(.8,1.6),(.4,.8)]:
            p=SimpleNamespace(compute=[SimpleNamespace(vertical_connectors=[0,1])]*2,
                memory=[SimpleNamespace(vertical_connectors=[0,1])]*2,
                edges=[dict(c=c,m=m,cp=m,mp=c) for c in range(2) for m in range(2)],
                edge_bandwidth=lambda e:capacity)
            service=ReticleService(p);a=np.full((2,2),.5)
            self.assertAlmostEqual(service.solve(a,[0])['mean'],expected)
            full=service.solve(a,[0,1],'common')
            self.assertAlmostEqual(full['mean'],min(1,expected))
            self.assertLess(full['residual'],1e-8)

    def test_disjoint_packing_upper_bound(self):
        a=audit(4,{(c,m) for c in range(4) for m in range(4)},True)
        self.assertEqual(a['max_disjoint'],4)
        self.assertEqual(len({(c,m) for p in a['pack'] for c,m in enumerate(p)}),16)


if __name__=='__main__':unittest.main()
