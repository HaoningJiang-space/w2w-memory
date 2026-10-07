import unittest
import numpy as np
from matching_placement import contoured,ReticleService,mixture
from sparse_pooling import matching_candidates,block_physical
from cycle_configurations import primal_audit
from nonuniform_pooling import CirculationSearch,Evaluation,units,DENOMINATOR


class NonuniformTests(unittest.TestCase):
    def test_sensitivity_has_correct_sign_and_scale(self):
        p=block_physical(2);p.edge_bandwidth=lambda e:.65 if e['c']==e['m'] else .8
        a=np.full((2,2),.5);activity=np.array([[True,False]])
        result=Evaluation(p,a).batch(activity,sensitivity=True,audit=True)
        direction=np.array([[1.,-1.],[-1.,1.]])
        eps=1e-6
        numerical=(Evaluation(p,a+eps*direction).batch(activity)['mean']-
                   Evaluation(p,a-eps*direction).batch(activity)['mean'])/(2*eps)
        self.assertAlmostEqual(float(np.sum(result['gradient']*direction)),numerical,places=5)
        self.assertAlmostEqual(numerical,-2.6,places=5)

    def test_every_generated_move_conserves_bytes_and_budgets(self):
        p=contoured();a=mixture([list(range(36)),[c^1 for c in range(36)]],[.5,.5])
        s=CirculationSearch(p,np.ones((1,36),bool))
        for initial in (a,matching_candidates(p,range(1))[-1]['layout']):
            q=units(initial)
            for fixed in (False,True):
                proposals=s.proposals(q,np.random.default_rng(12).normal(size=a.shape),fixed)
                self.assertTrue(proposals)
                for v in proposals:
                    candidate=v['q']/DENOMINATOR
                    primal_audit(p,candidate,np.ones(36),range(36))
                    np.testing.assert_array_equal(v['q'].sum(axis=0),60)
                    np.testing.assert_array_equal(v['q'].sum(axis=1),60)
                    if fixed:np.testing.assert_array_equal(candidate>0,initial>0)

    def test_new_ratios_and_paths_match_explicit_flow(self):
        p=contoured();a=matching_candidates(p,range(1))[-1]['layout']
        s=CirculationSearch(p,np.ones((1,36),bool))
        proposals=s.proposals(units(a),np.zeros_like(a))
        rng=np.random.default_rng(500);reference=ReticleService(p)
        for v in proposals[::max(1,len(proposals)//12)]:
            layout=v['q']/60;activity=rng.random((3,36))<.25;activity[:,0]=True
            result=Evaluation(p,layout).batch(activity,audit=True)
            for i,active in enumerate(activity):
                for objective,key in [('throughput','means'),('common','common')]:
                    explicit=reference.solve(layout,np.flatnonzero(active),objective,floor=1)
                    self.assertTrue(explicit['feasible'])
                    self.assertAlmostEqual(explicit['mean'],result[key][i])

    def test_invalid_support_and_fraction_rejected(self):
        p=contoured();a=mixture([list(range(36)),[c^1 for c in range(36)]],[.5,.5])
        s=CirculationSearch(p,np.ones((1,36),bool));q=units(a);q[0,0]+=1
        self.assertFalse(s.valid(q))
        with self.assertRaises(ValueError):s.evaluate(q)
        with self.assertRaises(ValueError):units(a+1e-4)

    def test_search_accepts_only_actual_improvements(self):
        p=block_physical(2);p.edge_bandwidth=lambda e:.65 if e['c']==e['m'] else .8
        a=np.full((2,2),.5);s=CirculationSearch(p,np.array([[True,False]]))
        result=s.run(a,fixed_support=True,rounds=2)
        self.assertGreater(result['final_mean'],result['initial_mean'])
        for step in result['trace']:
            if step['accepted']:self.assertGreater(step['training_mean'],step['starting_mean']+1e-7)
        for layout in result['trajectory']:
            primal_audit(p,layout,np.ones(2),range(2))
            np.testing.assert_array_equal(layout>0,a>0)


if __name__=='__main__':unittest.main()
