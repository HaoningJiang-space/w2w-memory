"""Ownership conservation, raw callback units and missing evidence fail closed."""
import unittest
from w2w.analysis.memory_service_causality import PHASES, explain_pool_window


def fixture():
    events=[]
    for n, offset in enumerate((0,40,90)):
        key=f'gate/read{n}'
        times=dict(read_issue=0,mc_accept=10,native_accept=20,array_first_ready=40,
            array_last_ready=60,native_first_ready=65,native_ready=80,mc_release=90,read_deliver=100)
        for kind,at in times.items():
            e=dict(kind=kind,time_ps=at+offset,request=key)
            if kind=='read_issue':e.update(task='gate',bytes=32,bank=0,word_address=n)
            if kind in ('mc_accept','mc_release'):e['memory']='m0'
            if kind.startswith('array_'):e.update(domain='d0',gateway='g0',hb_tail_ps=at+offset+30)
            events.append(e)
        for kind,at in [('request_control_send',22),('request_control_arrive',26),
                        ('domain_descriptor_begin',30),('domain_range_issued',50),('request_ack_arrive',60)]:
            e=dict(kind=kind,time_ps=at+offset,request=key,domain='d0',gateway='g0')
            if kind=='request_control_send':e.update(end_ps=24+offset,arrival_ps=26+offset)
            events.append(e)
    return dict(events=sorted(events,key=lambda e:e['time_ps']),
        native=dict(request_control=dict(enabled=True),accepted_atoms=6),
        spec=dict(memories=[dict(id='m0',mc_pool_id='p0',gateway_id='g0',domain_ids=['d0'],banks=1,transaction_slots=2)],
            stack=dict(dram_domains=[dict(id='d0',period_ps=10)],
                collection_paths=[dict(domain_id='d0',gateway_id='g0',pipeline_cycles=2,period_ps=10)],native_policy={})))


class MemoryCausality(unittest.TestCase):
    def test_disjoint_capacity_time_and_bus_tail_convention(self):
        r=fixture()
        x=explain_pool_window(r,'gate')
        self.assertEqual(x['target_descriptors'][0]['last_array_callback_ps'],70)
        self.assertEqual(sum(x['target_descriptors'][0]['phase_ps'].values()),80)

    def test_full_pool_has_no_unattributed_slot_time(self):
        r=fixture()
        # Full occupancy is [50,90), exactly ending at target's final issue.
        x=explain_pool_window(r,'gate')
        self.assertEqual(x['mc_full_wall_ps'],40)
        self.assertEqual(sum(x['full_window_phase_slot_ps'].values()),80)
        self.assertEqual(set(x['full_window_phase_slot_ps']),set(PHASES))
        self.assertAlmostEqual(sum(x['full_window_phase_fraction'].values()),1)

    def test_missing_or_impossible_physical_evidence_is_rejected(self):
        r=fixture();r['events']=[e for e in r['events'] if not (e['request']=='gate/read0' and e['kind']=='domain_range_issued')]
        with self.assertRaises(ValueError):explain_pool_window(r,'gate')
        r=fixture();next(e for e in r['events'] if e['kind']=='array_last_ready')['hb_tail_ps']+=10
        with self.assertRaises(ValueError):explain_pool_window(r,'gate')
        r=fixture();r['native']['accepted_atoms']+=1
        with self.assertRaises(ValueError):explain_pool_window(r,'gate')


if __name__=='__main__':unittest.main()
