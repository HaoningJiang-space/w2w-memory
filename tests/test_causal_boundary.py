"""Reservation visibility, first callback, conservative barriers and native clocks."""
import os,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from test_interactive_compute import ready
from test_compute_epoch import semantic_tasks
from w2w.backends.ramulator.rwdl import RamulatorRWDL
from w2w.system.causal_boundary import CausalBoundary


class FirstEvent:
    def __init__(self,at=3):self.at=at;self.cycle=0
    def advance_until_event(self,target):
        self.cycle=min(target,self.at)
        return self.cycle,[(0,self.at)] if target>=self.at else []
    def advance(self,target):self.cycle=target;return []
    def send(self,*_):return True


def backend():
    b=RamulatorRWDL.__new__(RamulatorRWDL)
    b.impl=FirstEvent();b.last_ps=2000;b.native_cycle=0;b.prefetched=[];b.reserved_until=None
    b.pending={0};b.accepted=1;b.completed=0;b.domain_count=1;b.atom_limit=1<<20
    return b


def eligible():
    e=ready();e.now=2000;e._stream_compute_progress()
    b=backend()
    e.native=SimpleNamespace(queues={},aggregate={},ready=[],native_events=[],future=[],backend=b,
        first_callback_boundary=lambda now,limit:b.advance_until_event(limit))
    e.network.native_idle=True;e.network.future=[];e.network.ready_packets=set();e.network.receiver_waiters={}
    return e


class CausalBoundaryTests(unittest.TestCase):
    def test_callback_is_not_visible_until_reserved_boundary(self):
        b=backend();stop=b.advance_until_event(100000)
        self.assertEqual(stop,11280);self.assertEqual(b.pending,{0});self.assertEqual(b.completed,0)
        with self.assertRaises(ValueError):b.submit(0,1)
        with self.assertRaises(ValueError):b.advance(10000)
        with self.assertRaises(ValueError):b.advance(12000)
        self.assertEqual(b.advance(stop),[(0,3)])
        self.assertEqual(b.completed,1);self.assertFalse(b.pending)

    def test_no_callback_cap_still_locks_new_input(self):
        b=backend();self.assertEqual(b.advance_until_event(5520),5520)
        with self.assertRaises(ValueError):b.submit(0,1)
        self.assertEqual(b.advance(5520),[])
        self.assertTrue(b.pending)

    def test_compute_bulk_matches_exact_services_before_callback(self):
        e=eligible();exact=ready();exact.interactive_compute=None
        exact.now=2000;exact._stream_compute_progress()
        c=CausalBoundary();stop=c.plan(e,100000)
        self.assertEqual(stop,11280);self.assertEqual(c.intervals[0]['bulk_services'],9)
        for at in range(3000,stop,1000):exact.now=at;exact._stream_compute_progress()
        e.now=stop;e.native.backend.advance(stop);e.interactive_compute.materialize(e)
        self.assertEqual(semantic_tasks(e),semantic_tasks(exact))
        self.assertEqual(e.events,exact.events);self.assertEqual(e.busy_ps,exact.busy_ps)
        self.assertEqual(e.interactive_compute.record()['schema'],2)

    def test_transport_frontend_queues_and_unknown_callback_disable(self):
        for change in (lambda e:setattr(e.network,'native_idle',False),
                       lambda e:e.network.future.append((5000,)),
                       lambda e:e.native.queues.update(domain=['request']),
                       lambda e:e.native.aggregate.update(gateway=['atom']),
                       lambda e:e.reading.add('gemm'),
                       lambda e:e.native.backend.pending.clear(),
                       lambda e:setattr(e.native,'first_callback_boundary',None)):
            e=eligible();change(e)
            self.assertIsNone(CausalBoundary().plan(e,100000))
            self.assertIsNone(e.native.backend.reserved_until)

    def test_known_frontend_event_and_deadline_cap_the_interval(self):
        e=eligible();e.native.future=[(5000,)]
        # The fake native also obeys the caller's capped known-event horizon.
        self.assertEqual(CausalBoundary().plan(e,100000),5000)
        self.assertEqual(e.interactive_compute.bulk_services,2)
        e=eligible();self.assertEqual(CausalBoundary().plan(e,5511),5480)
        self.assertEqual(e.interactive_compute.bulk_services,3)

    def test_forged_skipped_clock_and_service_accounting_rejected(self):
        from dataclasses import asdict
        from copy import deepcopy
        from w2w.validation.causal_boundary import audit_causal_boundary
        e=eligible();c=CausalBoundary();stop=c.plan(e,100000)
        e.now=stop;e.native.backend.advance(stop);e.interactive_compute.materialize(e)
        raw=dict(spec=asdict(e.spec),graph=asdict(e.graph),events=e.events,quantum_ps=40,
            drained_ps=130000,causal_boundary=c.record(),interactive_compute=e.interactive_compute.record())
        proof=audit_causal_boundary(raw)
        self.assertEqual(proof['omitted_boundaries'],11)
        for change in (lambda r:r['causal_boundary'].update(bulk_services=1),
                       lambda r:r['causal_boundary']['intervals'][0].update(resume_ps=12000),
                       lambda r:r['events'].pop()):
            bad=deepcopy(raw);change(bad)
            with self.assertRaises(ValueError):audit_causal_boundary(bad)


@unittest.skipUnless(os.getenv('W2W_RAMULATOR_BRIDGE'),'Native bridge required')
class NativeFirstCallback(unittest.TestCase):
    def test_matches_tick_reference_and_preserves_refresh(self):
        with tempfile.TemporaryDirectory() as directory:
            paths=[Path(directory)/name for name in ('normal','first')]
            normal=RamulatorRWDL(1,domain_count=1,refresh=True,command_trace=paths[0])
            fast=RamulatorRWDL(1,domain_count=1,refresh=True,command_trace=paths[1])
            limit=20_000_000
            try:
                self.assertEqual(normal.submit(0,0),fast.submit(0,0))
                stop=fast.advance_until_event(limit)
                candidate=fast.advance(stop);candidate+=fast.advance(limit)
                reference=[]
                for now in range(3760,limit+1,3760):reference+=normal.advance(now)
                self.assertEqual(candidate,reference);self.assertEqual(stop,reference[0][1]*3760)
                self.assertEqual(normal.native_cycle,fast.native_cycle)
                self.assertEqual(normal.record()['stats'],fast.record()['stats'])
            finally:normal.close();fast.close()
            traces=[Path(str(p)+'.ch0').read_bytes() for p in paths]
            self.assertEqual(*traces);self.assertIn(b'REFab',traces[0])
