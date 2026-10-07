import unittest
import numpy as np
from w2w.geometry.memory_model import Budgets,MemoryFabric,construct_memory_system
from run_experiment import construct_system_for_single_design, compute_results_for_single_system

class MemoryTests(unittest.TestCase):
    def make(self,method='aligned',mode='partitioned',budgets=None):
        s=construct_memory_system(dict(wafer_diameter=200,method=method),dict(reticle_size=(26.,33.)))
        return MemoryFabric(s,budgets,mode)

    def test_aligned_independent_memories(self):
        f=self.make();s=f.summary();n=len(f.compute)
        self.assertEqual(s['compute_degree'],[1]*n)
        self.assertEqual(s['component_count'],n)
        self.assertIsNone(s['structural_diameter'])
        self.assertEqual(s['reachable_capacity_gib'],[16]*n)
        self.assertAlmostEqual(f.solve([4]*n)['total_tb_s'],n)

    def test_shared_bank_no_double_count(self):
        f=self.make('half_shifted','pooled');n=len(f.compute)
        m=max(range(len(f.memory)),key=lambda m:sum(e['m']==m for e in f.edges))
        out=f.solve([4]*n,allowed_memories=[{m}]*n)
        self.assertAlmostEqual(out['total_tb_s'],1)

    def test_partitioned_vs_pooled_single_interior(self):
        a=self.make('half_shifted');n=len(a.compute)
        c=next(i for i,d in enumerate(a.summary()['compute_degree']) if d==4)
        demand=np.zeros(n);demand[c]=4
        self.assertAlmostEqual(a.solve(demand)['total_tb_s'],1)
        self.assertAlmostEqual(a.summary()['reachable_capacity_gib'][c],16)
        b=self.make('half_shifted','pooled')
        self.assertAlmostEqual(b.solve(demand)['total_tb_s'],4)
        self.assertAlmostEqual(b.summary()['reachable_capacity_gib'][c],64)
        b.budgets=Budgets(controller_tb_s=1)
        self.assertAlmostEqual(b.solve(demand)['total_tb_s'],1)

    def test_budget_conservation_and_matched_resources(self):
        for method in ('aligned','half_shifted_x','half_shifted'):
            f=self.make(method);s=f.summary()
            self.assertEqual((s['n_compute'],s['n_memory']),(12,12))
            self.assertLessEqual(max(s['compute_hb_tb_s']),4+1e-8)
            self.assertLessEqual(max(s['memory_hb_tb_s']),4+1e-8)
            self.assertLessEqual(f.solve([4]*12)['total_tb_s'],12)

    def test_fairness_and_inaccessible_memory(self):
        f=self.make();n=len(f.compute)
        self.assertAlmostEqual(f.solve([4]*n,'fair')['common_fraction'],.25)
        self.assertEqual(f.solve([4]*n,allowed_memories=[set()]*n)['total_tb_s'],0)
        self.assertEqual(f.solve([0]*n)['total_tb_s'],0)
        with self.assertRaises(ValueError): f.solve([-1]*n)

    def test_hb_sweep_recomputes_edge_limits(self):
        f=self.make('half_shifted','pooled');n=len(f.compute)
        c=next(i for i,d in enumerate(f.summary()['compute_degree']) if d==4)
        demand=np.zeros(n);demand[c]=4
        for hb in (1.,2.,4.):
            f.budgets=Budgets(compute_hb_tb_s=hb,memory_hb_tb_s=hb)
            self.assertAlmostEqual(f.solve(demand)['total_tb_s'],hb)

    def test_partial_overlap_does_not_create_bandwidth(self):
        f=self.make('half_shifted_x','pooled')
        # Move all memory reticles by another quarter-reticle: interfaces split.
        for r in f.memory:
            r.x -= 6.5
            r.shape_points=[(x-6.5,y) for x,y in r.shape_points]
            for v in r.vertical_connectors:v.x-=6.5
        f=MemoryFabric(f.system,bank_mode='pooled')
        self.assertLessEqual(max(f.summary()['compute_hb_tb_s']),4+1e-8)
        self.assertTrue(any(e['compute_port_fraction']<1 for e in f.edges))

    def test_entrypoint_and_simulator_guard(self):
        d=dict(integration_level='memory_and_logic',wafer_diameter=200,method='aligned')
        s=construct_system_for_single_design(d,dict(reticle_size=(26.,33.)))
        self.assertIn('memory_analysis',compute_results_for_single_system(s,'test',False,False))
        with self.assertRaises(ValueError): compute_results_for_single_system(s,'test',True,False)

if __name__=='__main__': unittest.main()
