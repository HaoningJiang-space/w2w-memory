import unittest
import numpy as np
from bank_sharing import geometry,templates
from guaranteed_service_exchange import (contoured_geometry,balanced_assignment,Channels,
    ExposureFabric,FixedService,FreePlacementService,complementary_phases)
from memory_fabric_dse import project_static_layout,activity_affinity,mutate_mask,bandwidth_moves

class FabricDSETests(unittest.TestCase):
    def test_offline_projection_and_relaxed_oneway_layout(self):
        p=geometry('half_shifted_x');f=ExposureFabric(p,templates(4)[0][1],Channels((8000,)*4))
        training=complementary_phases(contoured_geometry())
        strict=project_static_layout(f,training,1.)
        relaxed=project_static_layout(f,training,.9)
        def remote(layout):return sum(layout.shares[c,:c*32].sum()+layout.shares[c,(c+1)*32:].sum() for c in range(36))/36
        self.assertAlmostEqual(remote(strict),0)
        self.assertGreater(remote(relaxed),0)
        model=FixedService(f,relaxed)
        self.assertTrue(model.full_load_certificate(.9)['feasible'])
        for phase in training:
            result=model.solve(phase.demand,minimum=.9)
            upper=FreePlacementService(f).solve(phase.demand,minimum=.9)
            self.assertLessEqual(result['total_tb_s'],upper['total_tb_s']+1e-8)
        self.assertLessEqual(max(relaxed.bank_storage_gib),.5+1e-8)

    def test_same_marginals_distinct_joint_statistics(self):
        p=contoured_geometry();a=complementary_phases(p,(1,4));b=complementary_phases(p,(2,3))
        np.testing.assert_array_equal(sum(s.demand for s in a),sum(s.demand for s in b))
        self.assertGreater(np.max(abs(activity_affinity(a,36)-activity_affinity(b,36))),.9)

    def test_nonuniform_edges_and_conserved_width(self):
        p=contoured_geometry();mask=balanced_assignment(p,(2,3))
        changed=mutate_mask(mask,p,4)
        self.assertEqual(len(changed),4)
        self.assertTrue(any(len(set(map(len,m)))>1 for m in changed))
        q=(8000,6000,6000,6000,6000)
        for move in bandwidth_moves(q):
            self.assertEqual(sum(move),32000)
            self.assertGreaterEqual(min(move),0)

if __name__=='__main__':unittest.main()

class InheritedLayoutTests(unittest.TestCase):
    def test_added_edge_preserves_parent_service(self):
        from guaranteed_service_exchange import StripedLayout
        p=contoured_geometry();mask=balanced_assignment(p,(2,3));channels=Channels((8000,6000,6000,6000,6000))
        parent=ExposureFabric(p,mask,channels);layout=StripedLayout.reciprocal(parent)
        altered=list(mask);altered[0]=tuple(sorted(set(mask[0])|{1}))
        child=ExposureFabric(p,altered,channels)
        for phase in complementary_phases(p):
            before=FixedService(parent,layout).solve(phase.demand,.9)
            after=FixedService(child,layout).solve(phase.demand,.9)
            self.assertGreaterEqual(after['total_tb_s']+1e-8,before['total_tb_s'])
