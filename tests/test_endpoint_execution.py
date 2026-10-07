import unittest
import numpy as np
from w2w.endpoints.endpoint_execution import execute,EndpointFixedService
from w2w.service.guaranteed_service_exchange import contoured_geometry,ExposureFabric,Channels,FixedService
from w2w.synthesis.service_driven_fabric import paired_layout


class ExecutionTests(unittest.TestCase):
    def test_blocking_word_serialization(self):
        for bits in (64,128,192,256):
            r=execute(bits,0,slots=4096,warmup=256)
            expected=1/np.ceil(256/bits)
            self.assertAlmostEqual(r['total_per_native'],expected,delta=1/4096)
            self.assertLessEqual(max(r['peak_words']),1)

    def test_parallel_drain_and_depth(self):
        direct=execute(128,0)
        buffered=execute(128,1)
        self.assertAlmostEqual(direct['total_per_native'],.5)
        self.assertAlmostEqual(buffered['total_per_native'],1.)
        # One 256-bit holding slot cannot pack a 192-bit lane fully across words.
        self.assertAlmostEqual(execute(192,1,active=(0,))['total_per_native'],.5)
        self.assertAlmostEqual(execute(192,2,active=(0,))['total_per_native'],.75)

    def test_ordered_bursts_and_backpressure(self):
        shallow=execute(128,1,policy='ordered')
        deep=execute(128,8,policy='ordered')
        self.assertGreater(shallow['backpressure_slots'],0)
        self.assertGreater(deep['total_per_native'],shallow['total_per_native'])
        self.assertLessEqual(deep['total_per_native'],1)
        self.assertLessEqual(max(deep['peak_words']),8)

    def test_stalls_conserve_words(self):
        stalled=execute(128,2,stall_period=16,stall_length=8)
        self.assertLessEqual(stalled['total_per_native'],.5+2/8192)
        self.assertEqual(stalled['issued_words'],stalled['completed_words']+stalled['outstanding_words'])
        self.assertGreater(stalled['backpressure_slots'],0)


class BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fabric=ExposureFabric(contoured_geometry(),tuple((0,2,3) for _ in range(32)),
                                  Channels((8000,0,8000,8000,0)))
        cls.layout,cls.matching=paired_layout(cls.fabric)

    def test_original_unchanged_and_wide_equivalence(self):
        f=self.fabric;before=f.limits.copy();d=np.ones(36)*4
        old=FixedService(f,self.layout).solve(d)
        for contract in ('direct','buffered_envelope','elastic'):
            new=EndpointFixedService(f,self.layout,contract).solve(d)
            self.assertAlmostEqual(old['total_tb_s'],new['total_tb_s'])
        np.testing.assert_array_equal(before,f.limits)

    def test_serial_time_not_renamed_elastic(self):
        d=np.ones(36)*4
        direct=EndpointFixedService(self.fabric,self.layout,'direct',.5)
        buf=EndpointFixedService(self.fabric,self.layout,'buffered_envelope',.5)
        self.assertAlmostEqual(direct.solve(d,0)['tb_s_per_active'],.5)
        self.assertFalse(direct.solve(d,1)['feasible'])
        self.assertAlmostEqual(buf.solve(d,1)['tb_s_per_active'],1.)

    def test_unreachable_fixed_bytes_not_replaced(self):
        model=EndpointFixedService(self.fabric,self.layout,'elastic')
        d=np.zeros(36);c=self.matching['pairs'][0][0];d[c]=4
        caps={(c,int(b)):1/32 for b in np.flatnonzero(self.layout.shares[c])}
        del caps[c,next(iter(b for cc,b in caps))]
        limited=model.with_delivered_caps(caps).solve(d,0)
        self.assertEqual(limited['served_tb_s'][c],0)


if __name__=='__main__':unittest.main()
