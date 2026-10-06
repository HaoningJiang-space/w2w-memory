import unittest
import numpy as np
from bank_sharing import geometry,templates,scenarios
from guaranteed_service_exchange import (contoured_geometry,balanced_assignment,Channels,
    ExposureFabric,StripedLayout,FixedService,FreePlacementService)
from service_driven_fabric import (evaluate_layout,optimize_layout,structural_width_cap,
    paired_layout,exact_pair_expectation,exposure_proposals)

class ServiceDrivenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.physical=contoured_geometry()
        cls.training=scenarios(cls.physical,[500],fractions=(.25,),patterns=('uniform','clustered','correlated'))

    def test_exact_acceptance_improves_pilot_and_preserves_floor(self):
        p=self.physical;f=ExposureFabric(p,balanced_assignment(p,(1,4)),Channels((8000,6000,6000,6000,6000)))
        original=StripedLayout.reciprocal(f)
        layout,trace=optimize_layout(f,original,self.training,iterations=2)
        self.assertGreater(trace['final_score'],trace['initial_score']+.01)
        self.assertTrue(FixedService(f,layout).full_load_certificate(.9)['feasible'])
        self.assertLessEqual(max(layout.bank_storage_gib),.5+1e-8)
        accepted=[t for t in trace['trace'] if t['accepted']]
        self.assertTrue(accepted)
        for t in accepted:self.assertGreater(max(x['score'] for x in t['trials'] if x['feasible']),t['before'])

    def test_no_false_gain_on_aligned(self):
        f=ExposureFabric(geometry('aligned'),templates(4)[0][1],Channels((8000,)*4))
        layout,trace=optimize_layout(f,StripedLayout.home(f),self.training,iterations=1)
        self.assertAlmostEqual(trace['initial_score'],1.)
        self.assertAlmostEqual(trace['final_score'],1.)

    def test_structural_width_trim_preserves_routes_and_service(self):
        p=self.physical;f=ExposureFabric(p,balanced_assignment(p,(1,4)),Channels((8000,6000,6000,6000,6000)))
        trimmed=structural_width_cap(f)
        self.assertEqual(trimmed.channels.port_bits,(8000,4000,0,0,4000))
        layout=StripedLayout.reciprocal(f)
        for phase in self.training:
            for model in (FixedService,FreePlacementService):
                a=model(f,layout) if model is FixedService else model(f)
                b=model(trimmed,layout) if model is FixedService else model(trimmed)
                self.assertAlmostEqual(a.solve(phase.demand,.9)['total_tb_s'],b.solve(phase.demand,.9)['total_tb_s'])

    def test_k3_matching_and_exact_population(self):
        for ports,matched in [((2,3),36),((1,4),30)]:
            mask=tuple((0,)+ports for _ in range(32))
            f=ExposureFabric(self.physical,mask,Channels((8000,6000,6000,6000,6000)))
            # Full pair bandwidth needs >=1 TB/s at selected ports, not .75.
            widths=tuple(8000 if p==0 or p in ports else 0 for p in range(5))
            f=ExposureFabric(self.physical,mask,Channels(widths))
            layout,matching=paired_layout(f)
            self.assertEqual(matching['matched_clients'],matched)
            model=FixedService(f,layout)
            for c,peer in matching['pairs'][:2]:
                d=np.zeros(36);d[c]=4
                self.assertAlmostEqual(model.solve(d)['total_tb_s'],2.)
                d[peer]=4
                self.assertAlmostEqual(model.solve(d)['total_tb_s'],2.)
        self.assertAlmostEqual(exact_pair_expectation(36,36,9),1.7714285714285714)

    def test_activity_matching_and_repeated_proposals(self):
        mask=tuple((0,2,3) for _ in range(32))
        f=ExposureFabric(self.physical,mask,Channels((8000,0,8000,8000,0)))
        layout,matching=paired_layout(f,self.training,True)
        exact=evaluate_layout(f,layout,self.training,1.)['score']
        self.assertAlmostEqual(exact,1+matching['matching_weight'])
        base=ExposureFabric(self.physical,balanced_assignment(self.physical,(1,4)),Channels((8000,6000,6000,6000,6000)))
        options=exposure_proposals(base,StripedLayout.reciprocal(base),self.training)
        self.assertTrue(options)
        for option in options:
            self.assertLessEqual(sum(map(len,option['mask'])),68)
            self.assertTrue(all(set(old)<=set(new) for old,new in zip(base.mask,option['mask'])))

if __name__=='__main__':unittest.main()
