"""Independent ordinary frontend reference, exact command and timing checks."""
import os,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from tools.memory_island_inputs import inputs
from w2w.domain.protocol import MemoryRequest
from w2w.backends.ramulator.rwdl import RamulatorRWDL
from w2w.backends.ramulator.adapter import VerticalRWDL
from w2w.backends.ramulator.island import NativeMemoryIsland


def backend(spec,path):
    p=spec.stack.native_policy
    profile=SimpleNamespace(controller=p,timing=SimpleNamespace(**{k:v for k,v in vars(p).items() if k.startswith('n')}))
    return RamulatorRWDL(1,domain_count=1,array_bytes=spec.stack.dram_domains[0].capacity_bytes,
        profile=profile,refresh=True,command_trace=path)


@unittest.skipUnless(os.getenv('W2W_RAMULATOR_BRIDGE'),'Reviewed native island build required')
class MemoryIslandTests(unittest.TestCase):
    def test_internal_service_and_first_observable_match_ordinary(self):
        for case in ('continuous','pressure','inserted'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as folder:
                spec,_=inputs(case);paths=[Path(folder)/name for name in ('reference','island')]
                normal=VerticalRWDL(spec,backend=backend(spec,paths[0]),request_control=True)
                island=NativeMemoryIsland(spec,backend=backend(spec,paths[1]))
                req=MemoryRequest('r','t','c3','m0_0',0,0,4096)
                requests={0:req}
                if case=='inserted':requests[200*3760]=MemoryRequest('s','t','c3','m0_0',0,256,4096)
                limit=20_000_000
                expected_ready=[];actual_ready=[];expected_events=[];actual_events=[]
                stops=[];completed=[[],[]]
                try:
                    clocks=sorted(set(range(0,limit+1,1000))|set(range(0,limit+1,3760))|{limit})
                    for now in clocks:
                        completed[0].extend((key,now) for key in normal.advance(now))
                        expected_ready.extend((key,offset,now) for key,offset,_ in normal.take_ready())
                        expected_events.extend(normal.take_native_events())
                        if now in requests:self.assertTrue(normal.submit(requests[now],now))
                    now=0;island.advance(0)
                    self.assertTrue(island.submit(requests[0],0))
                    remaining=sorted(at for at in requests if at)
                    while now<limit:
                        cap=remaining[0] if remaining else limit
                        stop,done=island.advance_until(cap)
                        self.assertTrue(now<stop<=cap)
                        completed[1].extend((key,stop) for key in done)
                        actual_ready.extend(island.ready_times);island.take_ready()
                        actual_events.extend(island.take_native_events());stops.append(stop);now=stop
                        if remaining and now==remaining[0]:
                            self.assertTrue(island.submit(requests[now],now));remaining.pop(0)
                    self.assertEqual(expected_ready,actual_ready)
                    self.assertEqual(completed[0],completed[1])
                    self.assertEqual(expected_events,actual_events)
                    self.assertEqual(normal.record(),island.record())
                    self.assertLess(island.host_advances,len(clocks)//3)
                    if case=='pressure':self.assertGreater(island.record()['reservation_stall_attempts'],0)
                    first=expected_ready[0][2];self.assertIn(first,stops)
                finally:normal.close();island.close()
                a,b=[Path(str(p)+'.ch0').read_bytes() for p in paths]
                self.assertEqual(a,b);self.assertIn(b'REFab',a)

    def test_wrong_clock_and_unsupported_machine_rejected(self):
        from w2w.architecture.presets import vertical_memory
        from w2w.architecture.compiler import compile_machine
        spec,_=inputs('continuous')
        with tempfile.TemporaryDirectory() as folder:
            b=backend(spec,Path(folder)/'commands')
            try:
                with self.assertRaises(ValueError):NativeMemoryIsland(compile_machine(vertical_memory('distributed')),backend=b)
                island=NativeMemoryIsland(spec,backend=b);island.advance(0)
                req=MemoryRequest('r','t','c3','m0_0',0,0,32)
                self.assertFalse(island.submit(req,1000))
                with self.assertRaises(ValueError):island.submit(req,3760)
                island.advance(3760);self.assertTrue(island.submit(req,3760))
                with self.assertRaises(ValueError):island.submit(req,3760)
                with self.assertRaises(RuntimeError):island.advance(3000)
            finally:b.close()
