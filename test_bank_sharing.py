import unittest
import numpy as np
from bank_sharing import *

class BankSharingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.aligned=geometry('aligned');cls.xy=geometry('half_shifted')

    def test_masks_cost_and_fixed_budgets(self):
        for k in (1,2,4):
            for name,mask in templates(k):
                self.assertTrue(all(len(s)==k for s in mask))
                self.assertTrue(all(private_owner(b) in mask[b] for b in range(BANKS)))
                self.assertEqual(circuit_cost(mask)['bank_port_connections'],BANKS*k)
        for p in (self.aligned,self.xy):
            self.assertEqual((len(p.compute),len(p.memory)),(36,36))
            self.assertLessEqual(max(p.summary()['compute_hb_tb_s']),4.)

    def test_boundary_private_exact_and_periodic_reference(self):
        mask=templates(1)[0][1]
        demand=np.full(36,4.)
        f=BankFabric(self.xy,mask)
        self.assertAlmostEqual(PoolingNetwork(f).evaluate(demand)['oracle_tb_s'],30.25)
        torus=periodic_reference(self.xy)
        self.assertEqual(len(torus.edges),36*PORTS)
        self.assertAlmostEqual(PoolingNetwork(BankFabric(torus,mask)).evaluate(demand)['oracle_tb_s'],36.)
        interior=np.zeros(36);interior[interior_compute_ids()]=4
        self.assertEqual(np.count_nonzero(interior),25)
        self.assertAlmostEqual(PoolingNetwork(f).evaluate(interior)['oracle_tb_s'],25.)

    def test_static_home_cannot_pool_remote_memory(self):
        f=BankFabric(self.xy,templates(4)[0][1]);layout=f.plan_layout('home_striped')
        d=np.zeros(36);d[14]=4
        self.assertAlmostEqual(f.compile(layout,np.full(PAGES,1/PAGES)).solve(d)['total_tb_s'],1.)
        self.assertAlmostEqual(f.compile().solve(d)['total_tb_s'],4.)

    def test_inaccessible_pages_block_stream_not_drop_requests(self):
        f=BankFabric(self.xy,templates(1)[0][1]);layout=f.plan_layout('home_striped')
        d=np.full(36,4.)
        r=f.compile(layout,np.full(PAGES,1/PAGES)).solve(d)
        self.assertEqual(r['total_tb_s'],0.)
        self.assertEqual(r['blocked_active_clients'],36)
        self.assertAlmostEqual(r['unreachable_demand_fraction'],.75)

    def test_bank_hotspot_and_common_rate(self):
        f=BankFabric(self.aligned,templates(4)[0][1]);layout=f.plan_layout('home_striped')
        weights=np.zeros(PAGES);weights[0]=1
        d=np.zeros(36);d[0]=4
        r=f.compile(layout,weights).solve(d,'common')
        self.assertAlmostEqual(r['total_tb_s'],BANK_BW)
        self.assertAlmostEqual(r['common_completion'],BANK_BW/4)

    def test_static_layout_capacity_hash_and_no_mutation(self):
        f=BankFabric(self.xy,templates(2)[0][1])
        training=scenarios(self.xy,[0],fractions=(.25,),patterns=('uniform',))
        layout=f.plan_layout('static_train_greedy',training)
        self.assertLessEqual(max(f.validate_layout(layout)),BANK_GIB)
        before=f.layout_hash(layout)
        f.compile(layout,np.full(PAGES,1/PAGES)).solve(training[0].demand)
        self.assertEqual(before,f.layout_hash(layout))
        bad=np.zeros_like(layout)
        with self.assertRaises(ValueError):f.validate_layout(bad)

    def test_maxflow_lp_duality_and_monotonic_private_to_full(self):
        d=scenarios(self.xy,[100],fractions=(.25,),patterns=('uniform',))[0].demand
        values=[]
        for k in (1,2,4):
            f=BankFabric(self.xy,templates(k)[0][1]);cut=PoolingNetwork(f).evaluate(d)
            self.assertAlmostEqual(cut['oracle_tb_s'],f.compile().solve(d)['total_tb_s'])
            self.assertAlmostEqual(sum(cut['cut_components'].values()),cut['min_cut_tb_s'])
            values.append(cut['oracle_tb_s'])
        self.assertLessEqual(values[0],values[1]);self.assertLessEqual(values[1],values[2])

if __name__=='__main__':unittest.main()
