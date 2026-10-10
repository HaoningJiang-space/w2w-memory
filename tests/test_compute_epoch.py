"""Exact local transition, release/tail guards and independent format negatives."""
from copy import deepcopy
from types import SimpleNamespace
import unittest
from w2w.architecture.presets import vertical_memory
from w2w.architecture.compiler import compile_machine
from w2w.domain.execution import ResidentObject, ReadAccess, StreamGemm, ComputeTask, ExecutionGraph
from w2w.system.kernel import SystemExecution
from w2w.system.compute_epoch import advance_compute_epoch
from w2w.validation.compute_epoch import expand_compute_epochs,audit_compute_epoch_intervals


def initialized(release=None):
    spec=compile_machine(vertical_memory('distributed'))
    obj=ResidentObject('W','m0_0',0,8224)
    task=ComputeTask('gemm','c0',1,(ReadAccess('W',0,8224),),
        stream=StreamGemm('W',8192,32,8192,64,64))
    tasks=(task,) if release is None else (task,ComputeTask('later','c1',1,release_ps=release))
    e=SystemExecution(spec,ExecutionGraph(tasks,(obj,)),
        native=SimpleNamespace(boundary='controller_payload_ready_after_native_bus',compute_epoch_quiescent=lambda:True),
        network_factory=lambda *_:SimpleNamespace(drained=lambda:True),compute_epoch=True)
    e.now=1000;e.engine={'c0':['gemm']};e.unallocated.discard('gemm');e.alloc_candidates.discard('gemm')
    e.state['gemm'].update(allocated=True,start_ps=0,issued_all=True,read_bytes=8224,
        stream_scale_consumed=True,stream_weight_delivered=8192,stream_scale_delivered=32,stream_consumed=64,
        stream_tick=1000)
    e.compute_service_tick['c0']=1000;e.busy_ps['c0']=2000
    return e


def semantic_tasks(e):
    return {k:{name:value for name,value in row.items() if name!='iterator'} for k,row in e.state.items()}


class ComputeEpochTests(unittest.TestCase):
    def test_batch_equals_original_compute_updates_and_leaves_tail(self):
        bulk,exact=initialized(),initialized()
        resume=advance_compute_epoch(bulk,1000000)
        self.assertEqual(resume,128000)
        for now in range(2000,resume,1000):
            exact.now=now;exact._stream_compute_progress()
        self.assertEqual(semantic_tasks(bulk),semantic_tasks(exact))
        self.assertEqual(bulk.busy_ps,exact.busy_ps)
        self.assertEqual(bulk.compute_service_tick,exact.compute_service_tick)
        self.assertEqual(bulk.events,exact.events)
        self.assertIsNone(bulk.state['gemm']['finish_ps'])

    def test_release_between_clocks_stops_at_original_integer_grid(self):
        e=initialized(5501)
        self.assertEqual(advance_compute_epoch(e,1000000),5520)
        self.assertEqual(e.compute_epochs[0]['last_service_ps'],5000)

    def test_credit_pending_unavailable_data_observer_and_context_disable(self):
        for alter in (lambda e:setattr(e.network,'drained',lambda:False),
                      lambda e:setattr(e.native,'compute_epoch_quiescent',lambda:False),
                      lambda e:setattr(e,'event_observer',lambda _:None),
                      lambda e:e.engine['c0'].append('gemm'),
                      lambda e:e.state['gemm'].update(stream_weight_delivered=4096),
                      lambda e:e.requests.update(pending={}),
                      lambda e:e.state['gemm'].update(stream_consumed=8191)):
            e=initialized();alter(e);before=deepcopy(semantic_tasks(e))
            self.assertIsNone(advance_compute_epoch(e,1000000))
            self.assertEqual(semantic_tasks(e),before)

    def test_unrecognized_native_backend_has_no_epoch_capability(self):
        e=initialized();del e.native.compute_epoch_quiescent
        self.assertIsNone(advance_compute_epoch(e,1000000))

    def test_compact_independent_expansion_and_bad_service_rejected(self):
        from dataclasses import asdict
        e=initialized();e.compute_epoch_evidence='compact'
        advance_compute_epoch(e,1000000)
        record=dict(graph=asdict(e.graph),spec=asdict(e.spec),events=e.events,drained_ps=129000)
        full=initialized();advance_compute_epoch(full,1000000)
        self.assertEqual(expand_compute_epochs(record)['events'],full.events)
        for field in ('weight_bytes','period_ps','cycles','macs'):
            bad=deepcopy(record);bad['events'][0][field]*=2
            with self.assertRaises(ValueError):expand_compute_epochs(bad)

    def test_deadline_is_not_crossed(self):
        e=initialized()
        self.assertEqual(advance_compute_epoch(e,5511),5480)
        self.assertEqual(e.compute_epochs[0]['last_service_ps'],5000)

    def test_batch_total_cannot_be_forged_with_otherwise_correct_events(self):
        from dataclasses import asdict
        e=initialized();e.compute_epoch_evidence='compact'
        advance_compute_epoch(e,1000000)
        initial=dict(kind='stream_compute',time_ps=1000,task='gemm',tile='c0',weight_bytes=64,scale_bytes=0,macs=64)
        record=dict(graph=asdict(e.graph),spec=asdict(e.spec),events=[initial,*e.events],drained_ps=129000,quantum_ps=40,
            compute_epoch=dict(schema=1,evidence='compact',intervals=e.compute_epochs,batched_compute_cycles=126))
        proof=audit_compute_epoch_intervals(record)
        self.assertEqual(proof['batched_compute_cycles'],126)
        self.assertEqual(proof['omitted_boundaries'],159)
        for mutate in (lambda r:r['compute_epoch'].update(batched_compute_cycles=127),
                       lambda r:r['compute_epoch']['intervals'][0].update(consumed_before=0),
                       lambda r:r['compute_epoch']['intervals'][0].update(last_service_ps=126000)):
            bad=deepcopy(record);mutate(bad)
            with self.assertRaises(ValueError):audit_compute_epoch_intervals(bad)
