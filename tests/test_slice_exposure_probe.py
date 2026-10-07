import unittest
import numpy as np
from w2w.service.bank_sharing import geometry
from w2w.endpoints.slice_exposure_probe import graph,solve

class EndpointTests(unittest.TestCase):
    def test_single_client_and_full_load_preserve_parent_caps(self):
        p=geometry('half_shifted')
        c=next(c for c in range(36) if len({e['m'] for e in p.edges if e['c']==c})==4)
        single=np.zeros(36);single[c]=4
        for mode,architecture,expected in [('fixed_share','partitioned',1),('fixed_share','striped',1),
                ('fixed_share','pooled',4),('elastic_bank','partitioned',1),('elastic_bank','striped',4)]:
            g=graph(p,architecture,mode)
            self.assertAlmostEqual(solve(g,single)['total_tb_s'],expected)
            self.assertLessEqual(solve(g,np.full(36,4))['total_tb_s'],36)
    def test_aligned_has_no_extra_service_from_more_endpoints(self):
        p=geometry('aligned');d=np.zeros(36);d[10]=4
        for mode in ('fixed_share','elastic_bank'):
            self.assertAlmostEqual(solve(graph(p,'striped',mode),d)['total_tb_s'],1)

if __name__=='__main__':unittest.main()
