"""A later committed chunk cannot fill a prefix hole, even with the same byte count."""
import heapq,os,tempfile,unittest
from copy import deepcopy
from pathlib import Path
from w2w.architecture.presets import vertical_memory
from w2w.architecture.compiler import compile_machine
from w2w.domain.execution import ResidentObject,ReadAccess,StreamGemm,ComputeTask,ExecutionGraph
from w2w.system.kernel import execute_system
from w2w.backends.booksim.adapter import factory
from w2w.validation.system_execution import audit_system_result


class DelayedDescriptorFixture:
    # A controlled availability fixture, NOT a performance DRAM model.
    boundary='controller_payload_ready_after_native_bus';streaming=True;stream_origin='home_controller';atomic_bytes=32
    def __init__(self):self.future=[];self.ready=[];self.serial=0
    def submit(self,req,now):
        self.serial+=1
        delay=300000 if req.object_offset==0 else 80000 if req.object_offset==4096 else 10000
        heapq.heappush(self.future,(now+delay,self.serial,req));return True
    def advance(self,now):
        done=[]
        while self.future and self.future[0][0]<=now:
            _,_,req=heapq.heappop(self.future)
            self.ready.extend((req.id,i,32) for i in range(0,req.size_bytes,32));done.append(req.id)
        return done
    def take_ready(self):r,self.ready=self.ready,[];return r
    def record(self):return dict(kind='delayed_descriptor_causal_fixture',pending=len(self.future))
    def close(self):pass


@unittest.skipUnless(os.getenv('W2W_BOOKSIM_BINARY'),'Native BookSim required')
class OperandReadiness(unittest.TestCase):
    def test_later_chunk_waits_for_earlier_hole(self):
        machine=compile_machine(vertical_memory('distributed'))
        obj=ResidentObject('W','m0_0',0,8224)
        task=ComputeTask('gemm','c0',3,(ReadAccess('W',8192,32),ReadAccess('W',0,8192)),
            stream=StreamGemm('W',8192,32,8192,4096,4096))
        graph=ExecutionGraph((task,),(obj,));rows={}
        for policy in ('byte_count','contiguous_prefix'):
            with tempfile.TemporaryDirectory() as directory:
                r=execute_system(machine,graph,native=DelayedDescriptorFixture(),operand_readiness=policy,
                    time_advance='boundaries',max_ps=1000000,
                    network_factory=factory(binary=Path(os.environ['W2W_BOOKSIM_BINARY']),directory=Path(directory)/'network'))
                self.assertTrue(audit_system_result(r)['passed']);rows[policy]=r
        byte=rows['byte_count'];prefix=rows['contiguous_prefix']
        missing=next(e['time_ps'] for e in byte['events'] if e['kind']=='stream_operand_ready' and e['object_offset']==0)
        self.assertTrue(any(e['kind']=='stream_compute' and e['weight_bytes'] and e['time_ps']<missing for e in byte['events']))
        missing=next(e['time_ps'] for e in prefix['events'] if e['kind']=='stream_operand_ready' and e['object_offset']==0)
        self.assertFalse(any(e['kind']=='stream_compute' and e['weight_bytes'] and e['time_ps']<missing for e in prefix['events']))
        self.assertEqual(byte['compute_busy_ps'],prefix['compute_busy_ps'])
        self.assertGreater(prefix['makespan_ps'],byte['makespan_ps'])
        self.assertGreater(prefix['operand_readiness']['peak_metadata_bytes']['c0'],0)
        bad=deepcopy(byte);bad['operand_readiness']['policy']='contiguous_prefix'
        with self.assertRaisesRegex(ValueError,'contiguous committed'):audit_system_result(bad)
