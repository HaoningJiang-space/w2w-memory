"""Analysis contracts: capacity, units, missing evidence and EDP inequalities."""
import unittest
from w2w.analysis.compute_memory_competition import Occupancy, clocks
from w2w.analysis.energy_edp import evaluate, threshold, command_energy, edp_range


class CompetitionEnergy(unittest.TestCase):
    def test_ownership_half_open_global_clocks(self):
        x=Occupancy([(0,'a',True),(500,'b',True),(2500,'a',False),(3000,'b',False)],2)
        self.assertEqual(x.area,5000)
        self.assertEqual(x.blocked_clocks(501,2500,1000),2)
        self.assertEqual(x.blocked_clocks(2500,3000,1000),0)
        self.assertEqual(x.blocked_time(750,1250),500)
        self.assertEqual(clocks(501,3000,1000),2)
        with self.assertRaises(ValueError):Occupancy([(0,'a',True),(0,'b',True)],1)
        with self.assertRaises(ValueError):Occupancy([(0,'a',True)],1)

    def test_units_residual_and_edp_threshold(self):
        a=dict(makespan_ps=10**12,counts={'macs':10**12,'noc_data_bit_mm':0},native_read_atoms=1)
        b=dict(a,makespan_ps=5*10**11,counts={'macs':2*10**12,'noc_data_bit_mm':0})
        c={'macs':1,'noc_data_bit_mm':0}
        self.assertEqual(evaluate(a,c,common_power_w=1,residual_j=1)['energy_j'],3)
        self.assertEqual(threshold(a,b)['candidate_energy_ratio_limit'],2)
        self.assertEqual(threshold(a,b)['edp_difference_coefficient']['macs'],0)
        self.assertTrue(threshold(a,b)['modeled_nonnegative_coefficient_dominance'])
        box=edp_range(a,b,{'macs':[1,3],'noc_data_bit_mm':[0,0]},power_range=[0,0],
            residual_reference_range=[0,0],residual_candidate_range=[0,2])
        self.assertEqual(box['edp_difference_max_j_s'],1)
        self.assertFalse(box['candidate_better_for_entire_declared_box'])
        with self.assertRaises(ValueError):evaluate(a,{'macs':1},common_power_w=0,residual_j=0)
        with self.assertRaises(ValueError):evaluate(a,dict(c,noc_data_bit_mm=1),common_power_w=0,residual_j=0)
        with self.assertRaises(ValueError):evaluate(a,c,common_power_w=float('nan'),residual_j=0)
        with self.assertRaises(ValueError):command_energy(a,{'passed':True,'read_atoms':1},{})


if __name__=='__main__':unittest.main()
