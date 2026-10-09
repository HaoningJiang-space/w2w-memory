"""RWDL address/clock conservation, native independence and finite aggregation."""
from dataclasses import replace
import os
from pathlib import Path
import tempfile
import unittest

from w2w.domain.execution import ComputeTask, DataEdge, ExecutionGraph, ReadAccess, ResidentObject
from w2w.domain.protocol import MemoryRequest
from w2w.domain.system import mesh_system
from w2w.memory.rwdl_backend import RWDLAbsolute
from w2w.network.booksim_backend import factory
from w2w.system.kernel import execute_system
from w2w.validation.system_execution import audit_system_result


class ClockTests(unittest.TestCase):
    def test_sparse_clock_preserves_exact_event_ledger(self):
        spec=mesh_system(1,2,noc_period_ps=1000,dram_period_ps=3760)
        spec=replace(spec,tiles=tuple(replace(t,compute_period_ps=700) for t in spec.tiles))
        graph=ExecutionGraph((ComputeTask('a','c0',3,release_ps=91),
                              ComputeTask('b','c1',2,(ReadAccess('w',0,256),))),
                             (ResidentObject('w','m0',0,256),),
                             (DataEdge('activation','a','b',64),))
        a=execute_system(spec,graph,time_advance='gcd',max_ps=2_000_000)
        b=execute_system(spec,graph,time_advance='boundaries',max_ps=2_000_000)
        for field in ('events','tasks','makespan_ps','drained_ps','native','network'):
            self.assertEqual(a[field],b[field],field)
        self.assertLess(b['kernel_iterations'],a['kernel_iterations']/5)
        self.assertTrue(audit_system_result(b)['passed'])


@unittest.skipUnless(os.environ.get('W2W_RAMULATOR_BRIDGE'),'Native RWDL extension required')
class RWDLTests(unittest.TestCase):
    def backend(self, aggregation=256, refresh=True):
        spec=replace(mesh_system(1,2,flit_bytes=256,input_buffer_flits=16,injection_flits=256,
                                packet_payload_bytes=4096,memory_request_bytes=4096),dram_period_ps=3760)
        spec=replace(spec,tiles=tuple(replace(t,sram_bytes=65536) for t in spec.tiles))
        return RWDLAbsolute(spec,aggregation_bytes_per_cycle=aggregation,refresh=refresh)

    def test_two_halves_keep_logical_bank_word_mapping(self):
        backend=self.backend()
        try:
            req=MemoryRequest('r','t','c0','m0',31,17,4096)
            self.assertEqual(backend.address(req,0),(31,34))
            self.assertEqual(backend.address(req,16),(31,35))
            self.assertEqual(backend.address(req,32),(0,36))
            self.assertEqual(backend.address(req,1024),(31,36))
            req=replace(req,word_address=(1 << 19)-1,size_bytes=32)
            self.assertEqual(backend.address(req,16),(31,(1 << 20)-1))
        finally:backend.close()

    def test_native_independent_domains_and_row_conflict(self):
        backend=self.backend(refresh=False)
        try:
            native=backend.backend
            self.assertIsNotNone(native.submit(0,0))
            self.assertIsNotNone(native.submit(1,0))
            completed=native.advance(200_000)
            self.assertEqual(len(completed),2)
            self.assertEqual(completed[0][1],completed[1][1])
            native.submit(0,64)
            native.advance(400_000)
            stats=native.record()['stats']['controller']
            self.assertEqual(sum(c['read_row_conflicts'] for c in stats),1)
        finally:backend.close()

    def test_refresh_is_scheduled_in_native_command_framework(self):
        backend=self.backend()
        try:
            backend.advance(4_200_000)
            stats=backend.record()['stats']['controller']
            self.assertEqual(sum(c['num_maintenance_reqs_served'] for c in stats),64)
        finally:backend.close()

    def drain(self, aggregation):
        backend=self.backend(aggregation)
        try:
            for n in range(4):
                self.assertTrue(backend.submit(MemoryRequest(str(n),'t','c0','m0',0,4*n,4096),0))
            ready,completed=[],[]
            for now in range(0,2_000_000,40):
                done=backend.advance(now)
                ready.extend(backend.take_ready())
                completed.extend(done)
                if len(completed)==4:
                    self.assertEqual(sorted(completed),['0','1','2','3'])
                    break
            else:self.fail('RWDL did not drain')
            for n in range(4):
                self.assertEqual(sorted(offset for key,offset,size in ready if key==str(n)),list(range(0,4096,16)))
            self.assertTrue(all(size==16 for _,_,size in ready))
            record=backend.record()
            self.assertEqual(record['completed_atoms'],1024)
            self.assertEqual(record['pending'],0)
            self.assertEqual(record['reservations_live'],0)
            self.assertLessEqual(max(record['reservation_peak_atoms'].values()),8)
            return now,record
        finally:backend.close()

    def test_aggregation_backpressure_holds_reserved_return_storage(self):
        fast,a=self.drain(256)
        slow,b=self.drain(16)
        self.assertGreater(slow,fast)
        self.assertGreater(b['aggregation_wait_atom_ps'],a['aggregation_wait_atom_ps'])
        self.assertGreater(b['reservation_stall_attempts'],0)
        self.assertLessEqual(max(b['aggregation_peak_bytes'].values()),4096)

    def test_mc_admission_is_shared_across_domains(self):
        backend=self.backend()
        try:
            for n in range(4):
                self.assertTrue(backend.submit(MemoryRequest(str(n),'t','c0','m0',0,n,32),0))
            self.assertFalse(backend.submit(MemoryRequest('full','t','c0','m0',0,4,32),0))
            self.assertFalse(backend.submit(MemoryRequest('phase','t','c0','m1',0,4,32),40))
        finally:backend.close()

    @unittest.skipUnless(os.environ.get('W2W_BOOKSIM_BINARY'),'Existing BookSim required')
    def test_streaming_local_remote_and_sparse_clock_equivalence(self):
        for owner in ('c0','c1'):
            results=[]
            for mode in ('gcd','boundaries'):
                backend=self.backend()
                graph=ExecutionGraph((ComputeTask('a','c0',2),
                    ComputeTask('b',owner,2,(ReadAccess('w',0,8192),))),
                    (ResidentObject('w','m0',0,8192),),(DataEdge('input','a','b',512),))
                with tempfile.TemporaryDirectory() as d:
                    try:
                        r=execute_system(backend.spec,graph,native=backend,time_advance=mode,
                            network_factory=factory(binary=os.environ['W2W_BOOKSIM_BINARY'],
                                                    directory=Path(d)/'network'),max_ps=2_000_000)
                    finally:backend.close()
                self.assertTrue(audit_system_result(r)['passed'])
                self.assertEqual(r['native']['completed_atoms'],512)
                self.assertEqual(r['native']['pending'],0)
                ready={e['request']:e['time_ps'] for e in r['events'] if e['kind']=='native_ready'}
                supply=[e for e in r['events'] if e['kind']=='response_first_supply']
                self.assertTrue(any(e['time_ps']<ready[e['packet'][:-5]] for e in supply))
                results.append(r)
            for field in ('events','tasks','makespan_ps','drained_ps'):
                self.assertEqual(results[0][field],results[1][field],field)


if __name__=='__main__':unittest.main()
