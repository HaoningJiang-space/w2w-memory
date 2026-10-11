"""Analysis contracts: capacity, units, missing evidence and EDP inequalities."""
import unittest
from w2w.analysis.compute_memory_competition import Occupancy, clocks, competition
from w2w.analysis.energy_edp import evaluate, threshold, command_energy, edp_range


class CompetitionEnergy(unittest.TestCase):
    def test_ready_wait_requires_a_real_competing_grant(self):
        events=[]
        for kind in ['task_allocate','cache_operands_ready','task_start']:
            for key in ['gate','up']:events.append(dict(kind=kind,task=key,time_ps=0))
        for at,key,size in [(0,'gate',0),(1000,'up',0),(2000,'gate',64),(3000,'up',128),(4000,'gate',64)]:
            if at==4000:events.append(dict(kind='task_finish',task='up',time_ps=at))
            events.append(dict(kind='stream_compute',task=key,time_ps=at,weight_bytes=size))
        events.append(dict(kind='task_finish',task='gate',time_ps=5000))
        r=dict(graph=dict(tasks=[dict(id=k,tile='c0',release_ps=0,reads=[],stream=dict(weight_data_bytes=128)) for k in ['gate','up']],objects=[],data=[],control=[]),
            spec=dict(stack=dict(compute_clusters=[dict(id='c0',profile=dict(period_ps=1000))]),memories=[],outstanding_per_tile=32),
            events=events,tasks={'gate':dict(start_ps=0,finish_ps=5000),'up':dict(start_ps=0,finish_ps=4000)},
            compute_busy_ps={'c0':5000},engine_context_ps={'c0':9000},network=dict(event_level='transaction'),
            compute_execution=dict(contexts_per_cluster=2),fetch_execution=dict(contexts_per_cluster=2))
        row=competition(r)['clusters']['c0']
        self.assertEqual(row['shared_grant_wait_ps'],4000)
        self.assertEqual(row['operand_wait_ps'],0)
        r['events'].insert(7,dict(kind='compute_service',task='up',time_ps=0))
        with self.assertRaises(ValueError):competition(r)

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
        self.assertEqual(evaluate(dict(a,drained_ps=2*10**12),c,common_power_w=1,residual_j=1)['energy_j'],4)
        with self.assertRaises(ValueError):evaluate(dict(a,drained_ps=1),c,common_power_w=1,residual_j=1)
        with self.assertRaises(ValueError):threshold(a,dict(b,counts={'macs':-1,'noc_data_bit_mm':0}))
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
