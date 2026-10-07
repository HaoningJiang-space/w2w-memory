import unittest
import numpy as np
from w2w.service.bank_sharing import geometry,templates
from w2w.constants import BANK_BW
from w2w.service.guaranteed_service_exchange import contoured_geometry,balanced_assignment,Channels,ExposureFabric,StripedLayout,FixedService,maximum_nonhome_layout,exact_uniform_pair_mean,complementary_phases


class GuaranteedExchangeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.physical=contoured_geometry()
        cls.mask=balanced_assignment(cls.physical,(2,3))
        cls.fabric=ExposureFabric(cls.physical,cls.mask,Channels((8000,0,4000,4000,0)))
        cls.layout=StripedLayout.reciprocal(cls.fabric)
        cls.problem=FixedService(cls.fabric,cls.layout)

    def test_geometry_and_wire_assignment(self):
        p=self.physical
        self.assertEqual(len(p.compute),36)
        self.assertAlmostEqual(p.memory[0].get_area(),844.8)
        self.assertEqual(sum(e['c']==e['m'] for e in p.edges),36)
        self.assertEqual(len({tuple(sorted((e['c'],e['m']))) for e in p.edges if e['c']!=e['m']}),55)
        cyclic=ExposureFabric(p,balanced_assignment(p,(2,3),'cyclic'),self.fabric.channels)
        self.assertAlmostEqual(cyclic.cost()['wire_mm'],1266.1)
        self.assertAlmostEqual(self.fabric.cost()['wire_mm'],943.6)
        scenario=complementary_phases(p)[0]
        self.assertAlmostEqual(FixedService(cyclic,StripedLayout.reciprocal(cyclic)).solve(scenario.demand)['total_tb_s'],self.problem.solve(scenario.demand)['total_tb_s'])

    def test_static_certificate_and_no_replication(self):
        cert=self.problem.full_load_certificate()
        self.assertTrue(cert['feasible'])
        np.testing.assert_allclose(cert['bank_load_at_floor_tb_s'],BANK_BW)
        np.testing.assert_array_equal(self.layout.counts.sum(axis=1),256)
        np.testing.assert_allclose(self.layout.bank_storage_gib,.125)
        before=self.layout.sha256
        for seed in range(3):
            d=np.zeros(36);d[np.random.default_rng(seed).choice(36,9,replace=False)]=4
            r=self.problem.solve(d)
            self.assertGreaterEqual(r['minimum_tb_s'],1-1e-9)
        self.assertEqual(before,self.layout.sha256)
        with self.assertRaises(ValueError):self.layout.counts[0,0]=5

    def test_width_is_capacity_not_fanin(self):
        self.assertEqual(Channels((8000,)).capacity(8000),1.)
        narrow=ExposureFabric(self.physical,self.mask,Channels((8000,0,256,256,0)))
        self.assertFalse(FixedService(narrow,StripedLayout.reciprocal(narrow)).full_load_certificate()['feasible'])
        with self.assertRaises(ValueError):exact_uniform_pair_mean(narrow,StripedLayout.reciprocal(narrow))
        with self.assertRaises(ValueError):Channels((32001,))
        with self.assertRaises(ValueError):Channels((8000,),bank_link_bits=1.5)

    def test_unidirectional_continuous_limit(self):
        f=ExposureFabric(geometry('half_shifted_x'),dict(templates(2))['xor_1'],Channels((8000,)*4))
        for floor,expected in [(1,0),(.99,.0252525252525),(.95,.131578947368),(.9,.277777777778)]:
            result=maximum_nonhome_layout(f,floor)
            self.assertTrue(result['feasible'])
            self.assertAlmostEqual(result['max_mean_nonhome'],expected,places=8)
        for k,name in [(2,'star_0'),(4,'full')]:
            xy=ExposureFabric(geometry('half_shifted'),dict(templates(k))[name],Channels((8000,)*4))
            self.assertAlmostEqual(maximum_nonhome_layout(xy,1)['max_mean_nonhome'],0)
        xy=ExposureFabric(geometry('half_shifted'),dict(templates(2))['xor_3'],Channels((8000,)*4))
        self.assertFalse(maximum_nonhome_layout(xy,.9)['feasible'])

    def test_exact_expectations_and_marginals(self):
        self.assertAlmostEqual(exact_uniform_pair_mean(self.fabric,self.layout)['mean_tb_s_per_active'],1.3277310924369747)
        f=ExposureFabric(self.physical,balanced_assignment(self.physical,(1,2,3,4)),Channels((8000,2000,2000,2000,2000)))
        self.assertAlmostEqual(exact_uniform_pair_mean(f,StripedLayout.reciprocal(f))['mean_tb_s_per_active'],1.186211,places=6)
        phases=complementary_phases(self.physical,(2,3))
        np.testing.assert_array_equal(sum(s.demand>0 for s in phases),np.ones(36))
        wrong=ExposureFabric(self.physical,balanced_assignment(self.physical,(1,4)),Channels((8000,4000,0,0,4000)))
        problem=FixedService(wrong,StripedLayout.reciprocal(wrong))
        self.assertGreater(self.problem.solve(phases[0].demand)['tb_s_per_active'],problem.solve(phases[0].demand)['tb_s_per_active'])

    def test_strengthened_home_and_original_hotspot_bound(self):
        self.assertAlmostEqual(BANK_BW/.05,.625)
        self.assertAlmostEqual(BANK_BW/(.8/16+3*.2/112),.564516129032258)
        home=ExposureFabric(self.physical,tuple((0,) for _ in range(32)),Channels((8000,0,0,0,0)))
        problem=FixedService(home,StripedLayout.home(home))
        # Every object has the same bank proportions: object weights cancel.
        result=problem.solve(np.full(36,4.))
        self.assertAlmostEqual(result['tb_s_per_active'],1.)
        self.assertEqual(result['missing_byte_fraction'],0)

if __name__=='__main__':unittest.main()
