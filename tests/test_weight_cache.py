"""Native causal cache lifetime: a warm hit, eviction and a paid reload."""
import os,tempfile,unittest
from pathlib import Path
from w2w.architecture.presets import vertical_memory
from w2w.architecture.compiler import compile_machine
from w2w.domain.execution import ResidentObject,ReadAccess,StreamGemm,ComputeTask,ControlEdge,ExecutionGraph
from w2w.backends.ramulator import VerticalRWDL
from w2w.backends.booksim.adapter import factory
from w2w.system.kernel import execute_system
from w2w.system.weight_cache import WeightCacheConfig
from w2w.validation.vertical_access import audit_vertical_result


@unittest.skipUnless(os.getenv('W2W_BOOKSIM_BINARY') and os.getenv('W2W_RAMULATOR_BRIDGE'),'Native tools required')
class CacheLifetime(unittest.TestCase):
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
