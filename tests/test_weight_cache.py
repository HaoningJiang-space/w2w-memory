"""Native causal cache lifetime: a warm hit, eviction and a paid reload."""
import os,tempfile,unittest
from dataclasses import asdict
from pathlib import Path
from w2w.architecture.presets import vertical_memory
from w2w.architecture.compiler import compile_machine
from w2w.domain.execution import ResidentObject,ReadAccess,StreamGemm,ComputeTask,ControlEdge,ExecutionGraph
from w2w.backends.ramulator import VerticalRWDL
from w2w.backends.booksim.adapter import factory
from w2w.system.kernel import execute_system
from w2w.system.weight_cache import WeightCacheConfig
from w2w.validation.vertical_access import audit_vertical_result
from w2w.validation.request_control import audit_request_control
from w2w.analysis.gateway_hierarchy import completion_record


@unittest.skipUnless(os.getenv('W2W_BOOKSIM_BINARY') and os.getenv('W2W_RAMULATOR_BRIDGE'),'Native tools required')
class CacheLifetime(unittest.TestCase):
    def test_eviction_without_revisit_is_valid(self):
        # A deliberately small causal cache, not an application-sized study.
        stack=vertical_memory('distributed');spec=compile_machine(stack)
        size=524416;data=524288;scale=128;profile=stack.compute_clusters[0].profile
        objects=tuple(ResidentObject(name,'m0_0',i*size,size) for i,name in enumerate(('A','B','C')))
        tasks=tuple(ComputeTask(key,'c0',33,(ReadAccess(obj,data,scale),ReadAccess(obj,0,data)),
            stream=StreamGemm(obj,data,scale,data,profile.macs_per_cycle,profile.weight_read_bytes_per_cycle))
            for key,obj in (('a','A'),('b','B'),('c','C')))
        graph=ExecutionGraph(tasks,objects,control=(ControlEdge('a','b'),ControlEdge('b','c')))
        config=WeightCacheConfig(data_bytes_per_cluster=size,initial_resident=(('c0','A'),))
        native=VerticalRWDL(spec,refresh=False)
        try:
            with tempfile.TemporaryDirectory() as directory:
                result=execute_system(spec,graph,native=native,time_advance='boundaries',compute_contexts=2,
                    weight_cache=config,max_ps=100000000,
                    network_factory=factory(binary=Path(os.environ['W2W_BOOKSIM_BINARY']),directory=Path(directory)/'network'))
                result.update(audit=audit_vertical_result(result),control_audit=audit_request_control(result),source_commit='causal-no-revisit-fixture')
                stats=result['weight_cache']['stats']
                self.assertEqual(stats.get('reload_bytes',0),0)
                self.assertEqual(stats['compulsory_bytes'],2*size);self.assertEqual(stats['evictions'],2)
                self.assertEqual(result['native']['array_capacity_bytes'],64*1024**2)
                self.assertEqual(result['native']['domain_count'],128)
                self.assertEqual(result['native']['total_array_capacity_bytes'],8*1024**3)
                self.assertIn('512-Mbit',result['native']['scope'])
                inputs=dict(graph=asdict(graph),metadata=dict(invocations=[dict(input_task='a',finish_task='c')],
                    logical_weight_read_bytes=3*size,active_unique_weight_bytes=3*size),
                    resources=dict(compute=dict(sram_bytes=sum(c.profile.sram_bytes for c in stack.compute_clusters))))
                summary=completion_record(result,inputs,'causal-no-revisit-fixture',None)
                self.assertTrue(summary['complete']);self.assertTrue(summary['capacity_eviction_observed'])
                self.assertFalse(summary['capacity_reload_observed'])
        finally:native.close()

    def test_warm_hit_then_eviction_and_reload(self):
        stack=vertical_memory('distributed');spec=compile_machine(stack)
        size=524416;data=524288;scale=128
        profile=stack.compute_clusters[0].profile
        objects=tuple(ResidentObject(name,'m0_0',i*size,size) for i,name in enumerate(('A','B')))
        tasks=[]
        for key,obj in (('a','A'),('b','B'),('c','A')):
            stream=StreamGemm(obj,data,scale,data,profile.macs_per_cycle,profile.weight_read_bytes_per_cycle)
            tasks.append(ComputeTask(key,'c0',33,(ReadAccess(obj,data,scale),ReadAccess(obj,0,data)),stream=stream))
        graph=ExecutionGraph(tuple(tasks),objects,control=(ControlEdge('a','b'),ControlEdge('b','c')))
        config=WeightCacheConfig(data_bytes_per_cluster=size,initial_resident=(('c0','A'),))
        native=VerticalRWDL(spec,refresh=False)
        try:
            with tempfile.TemporaryDirectory() as d:
                r=execute_system(spec,graph,native=native,time_advance='boundaries',compute_contexts=2,weight_cache=config,max_ps=100000000,
                    network_factory=factory(binary=Path(os.environ['W2W_BOOKSIM_BINARY']),directory=Path(d)/'network'))
                audit=audit_vertical_result(r);stats=r['weight_cache']['stats']
                self.assertEqual(audit['native_bytes'],2*size)
                self.assertEqual(stats['hit_bytes'],size)
                self.assertEqual(stats['reload_bytes'],size)
                self.assertEqual(stats['compulsory_bytes'],size)
                self.assertEqual(stats['evictions'],2)
                self.assertEqual(r['weight_cache']['initial_resident_bytes'],size)
        finally:native.close()
