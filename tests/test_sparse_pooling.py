import itertools
import unittest
import numpy as np
from w2w.service.matching_placement import contoured,ReticleService,mixture
from w2w.synthesis.sparse_pooling import factor_certificate,complete_blocks,pool_expectation,block_physical,matching_candidates,FixedLayoutService


class SparsePoolingTests(unittest.TestCase):
    def test_factor_certificates_and_decomposition(self):
        p=contoured();edges={(e['c'],e['m']) for e in p.edges}
        for d,flow in [(2,72),(3,106),(4,126)]:
            cert=factor_certificate(36,edges,d)
            self.assertEqual(cert['flow'],flow)
            self.assertEqual(sum(e[2] for e in cert['cut_edges']),flow)
            self.assertEqual(cert['feasible'],d==2)
        full={(c,m) for c in range(4) for m in range(4)}
        cert=factor_certificate(4,full,4)
        self.assertEqual(len({(c,m) for match in cert['matchings'] for c,m in enumerate(match)}),16)
        self.assertEqual(complete_blocks(36,edges,3),0)
        self.assertEqual(complete_blocks(36,edges,4),0)

    def test_block_expectation_and_all_local_states(self):
        for d,expected in [(2,1.462857142857143),(3,2.0073949579831933),(4,2.4507257448433917)]:
            self.assertAlmostEqual(pool_expectation(d)['expectation'],expected)
            p=block_physical(d);a=np.full((d,d),1/d)
            service=ReticleService(p);reduced=FixedLayoutService(p,a)
            for bits in itertools.product((False,True),repeat=d):
                if not any(bits):continue
                active=np.flatnonzero(bits).tolist();rate=min(d/len(active),.8*d,4.)
                for objective in ('throughput','common'):
                    result=service.solve(a,active,objective,floor=1)
                    self.assertTrue(result['feasible']);self.assertAlmostEqual(result['mean'],rate)
                self.assertAlmostEqual(reduced.solve(bits)['mean'],rate)

    def test_repeated_matchings_are_not_regular_factors(self):
        p=contoured();candidates=matching_candidates(p,range(2))
        explicit=ReticleService(p);rng=np.random.default_rng(12345)
        for candidate in candidates:
            a=candidate['layout'];reduced=FixedLayoutService(p,a)
            np.testing.assert_allclose(mixture(candidate['matchings'],[1/candidate['terms']]*candidate['terms']),a)
            self.assertFalse(a.flags.writeable)
            self.assertEqual(np.count_nonzero(a[0]),2)
            for count in (1,9,18,36):
                for _ in range(3):
                    active=np.zeros(36,bool);active[rng.choice(36,count,replace=False)]=True
                    result=reduced.solve(active)
                    for objective,key in [('throughput','mean'),('common','common')]:
                        reference=explicit.solve(a,np.flatnonzero(active),objective,floor=1)
                        self.assertTrue(reference['feasible'])
                        self.assertAlmostEqual(result[key],reference['mean'])

    def test_shared_port_is_not_free_bandwidth(self):
        p=block_physical(2);a=np.full((2,2),.5)
        for e in p.edges:e['cp']=0
        with self.assertRaises(ValueError):FixedLayoutService(p,a)
        # A legal shared memory port still constrains the combined flow.
        p=block_physical(3);a=np.full((3,3),1/3)
        for e in p.edges:
            if e['c']<2:e['mp']=0
        result=FixedLayoutService(p,a).solve([True,True,False])
        reference=ReticleService(p).solve(a,[0,1],floor=1)
        self.assertAlmostEqual(result['mean'],1.2)
        self.assertAlmostEqual(result['common'],1.2)
        self.assertAlmostEqual(reference['mean'],result['mean'])


if __name__=='__main__':unittest.main()
