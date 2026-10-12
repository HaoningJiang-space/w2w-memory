"""Half-open ownership and bounded-bin observations, not hardware fixtures."""
import unittest
from w2w.common.event_archive import encode
from tools.read_prefill_fetch import pool_ownership,gateway_bounds


class PrefillFetchReadback(unittest.TestCase):
    def test_same_tick_release_and_acquire_preserve_one_slot_area(self):
        raw=encode(dict(spec=dict(memories=[dict(id='m',mc_pool_id='p',transaction_slots=1)]),events=[
            dict(kind='mc_accept',time_ps=1,request='a',memory='m'),
            dict(kind='mc_release',time_ps=2,request='a',memory='m'),
            dict(kind='mc_accept',time_ps=2,request='b',memory='m'),
            dict(kind='mc_release',time_ps=3,request='b',memory='m')]))
        owner=pool_ownership(raw,{'p'})['p']
        self.assertEqual(owner.area,2);self.assertEqual(owner.blocked_time(1,3),2)

    def test_descriptor_released_to_another_interface_is_rejected(self):
        memories=[dict(id=k,mc_pool_id='p',transaction_slots=1) for k in ('m1','m2')]
        raw=encode(dict(spec=dict(memories=memories),events=[dict(kind='mc_accept',time_ps=1,request='a',memory='m1'),
            dict(kind='mc_release',time_ps=2,request='a',memory='m2')]))
        with self.assertRaises(ValueError):pool_ownership(raw,{'p'})

    def test_partial_bins_have_bounds_instead_of_uniform_rate_interpolation(self):
        bins=[dict(start_ps=i*10,end_ps=(i+1)*10,bytes=n,busy_cycles=n//32) for i,n in enumerate((96,64,32))]
        raw=dict(spec=dict(noc_period_ps=1,stack=dict(gateways=[dict(id='g',data_bytes_per_cycle=32)])),
            native=dict(gateway_service_bins=dict(interval_ps=10,gateways={'g':bins})))
        result=gateway_bounds(raw,'g',5,25)
        self.assertEqual(result['payload_bytes_lower'],64);self.assertEqual(result['payload_bytes_upper'],192)
        self.assertEqual(result['busy_fraction_lower'],.1);self.assertEqual(result['busy_fraction_upper'],.3)


if __name__=='__main__':unittest.main()
