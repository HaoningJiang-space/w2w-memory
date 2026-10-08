"""Admission/completion/credit contract, plus optional pinned native integration."""
from dataclasses import replace
import os
import tempfile
import unittest
from pathlib import Path

from tests.fixtures.tiny_fabric import two_compute_two_memory
from tests.test_read_workload import read_trace, FAST
from w2w.service.read_replay import replay_reads


class DelayedBackend:
    def __init__(self, latency=9, capacity=2):
        self.tick = self.accepted = self.completed = self.peak = 0
        self.pending = {}
        self.latency, self.capacity = latency, capacity

    def validate(self, *args): pass

    def advance(self, tick):
        self.tick = tick
        done = [key for key, ready in self.pending.items() if ready <= tick]
        for key in done: del self.pending[key]
        self.completed += len(done)
        return done

    def submit(self, request):
        if len(self.pending) == self.capacity: return None
        ticket = self.accepted
        self.accepted += 1
        self.pending[ticket] = self.tick + self.latency
        self.peak = max(self.peak, len(self.pending))
        return ticket

    def record(self):
        return dict(accepted_words=self.accepted, completed_words=self.completed,
                    pending_words=len(self.pending), upstream_pending=len(self.pending))


class CompletionContractTests(unittest.TestCase):
    def test_delayed_completion_and_bounded_return_reservation(self):
        design, trace = two_compute_two_memory(), read_trace()
        reference = replay_reads(design, trace, FAST)
        backend = DelayedBackend()
        row = replay_reads(design, trace, FAST, native_backend=backend)
        self.assertEqual(row['audit']['delivered_words'], reference['audit']['delivered_words'])
        self.assertEqual(row['residence_sha256'], reference['residence_sha256'])
        self.assertGreater(row['makespan_slots'], reference['makespan_slots'])
        self.assertLessEqual(backend.peak, 2)
        self.assertTrue(row['audit']['every_slot_conserved'])
        self.assertEqual(row['schema'], 'w2w.read-replay.dram.v1')
        self.assertNotIn('native_backend', reference)

    def test_duplicate_completion_is_rejected(self):
        class Broken(DelayedBackend):
            def advance(self, tick):
                done = super().advance(tick)
                return done + done
        with self.assertRaisesRegex(RuntimeError, 'repeated native completion'):
            replay_reads(two_compute_two_memory(), read_trace(), FAST, native_backend=Broken())

    def test_stalled_receiver_keeps_requests_live(self):
        row = replay_reads(two_compute_two_memory(), read_trace(),
                           replace(FAST, rx_ready=(1, 0, 0, 0), rx_depth_words=1),
                           native_backend=DelayedBackend())
        self.assertEqual(row['audit']['issued_words'], row['audit']['delivered_words'])
        self.assertTrue(all(r['peak_rx_words'] <= 1 for r in row['routes']))


@unittest.skipUnless(os.environ.get('W2W_RAMULATOR_BRIDGE'), 'optional native bridge not configured')
class NativeHBM2Tests(unittest.TestCase):
    def make(self, **kwargs):
        from w2w.service.dram.ramulator import RamulatorHBM2
        value = RamulatorHBM2(1, slot_ps=1000, **kwargs)
        self.addCleanup(value.close)
        return value

    def one(self, backend, bank, address, start):
        backend.advance(start)
        ticket = backend.submit(dict(bank=bank, address=address))
        self.assertIsNotNone(ticket)
        for tick in range(start + 1, start + 1000):
            if ticket in backend.advance(tick): return tick
        self.fail('DRAM request failed to complete')

    def test_row_hit_conflict_and_exact_burst(self):
        b = self.make(refresh=False)
        first = self.one(b, 0, 0, 0)
        hit = self.one(b, 0, 1, first)
        conflict = self.one(b, 0, 32, hit)
        self.assertGreater(first, hit - first)
        self.assertGreater(conflict - hit, hit - first)
        self.assertEqual(b.record()['completed_words'], 3)
        with self.assertRaises(ValueError): b.submit(dict(bank=32, address=0))
        with self.assertRaises(ValueError): b.submit(dict(bank=0, address=1 << 19))

    def test_native_queue_backpressure(self):
        b = self.make(queue_depth=2, refresh=False)
        accepted = [b.submit(dict(bank=0, address=i)) for i in range(12)]
        self.assertTrue(any(t is None for t in accepted))
        count = sum(t is not None for t in accepted)
        done = []
        for tick in range(1, 1000):
            done.extend(b.advance(tick))
            if len(done) == count: break
        self.assertEqual(len(set(done)), count)
        self.assertEqual(b.record()['upstream_pending'], 0)

    def test_refresh_commands_and_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'commands'
            b = self.make(command_trace=path)
            b.advance(4500)
            self.one(b, 0, 0, 4500)
            b.close()
            trace = Path(str(path) + '.ch0').read_text()
            self.assertIn('REFab', trace)
            self.assertIn(',RD,', trace)


if __name__ == '__main__': unittest.main()
