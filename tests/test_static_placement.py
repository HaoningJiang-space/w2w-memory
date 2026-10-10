"""Memory-only changes cannot remap tasks, tensors or the warm SRAM preload."""
import unittest
from w2w.architecture.presets import vertical_memory
from w2w.architecture.compiler import compile_machine
from w2w.workloads.moe import build_moe
from w2w.mapping.static_weights import static_weights,POLICIES
from w2w.mapping.sequence import lower_sequence


class StaticPlacement(unittest.TestCase):
    def test_catalog_is_independent_of_eval_routing(self):
        stack=vertical_memory();a=build_moe(((0,),),experts=4,topk=1,intermediate=512)
        b=build_moe(((3,),),experts=4,topk=1,intermediate=512)
        for policy in POLICIES:self.assertEqual(static_weights(a,stack,policy),static_weights(b,stack,policy))

    def test_compute_and_preload_are_frozen_across_memory_layouts(self):
        spec=compile_machine(vertical_memory());shape=dict(experts=4,topk=1,intermediate=512)
        logical=build_moe(((0,),),**shape);reference=static_weights(logical,spec.stack,'reference')
        graphs=[];preloads=[]
        for policy in POLICIES:
            graph,meta,preload=lower_sequence(((0,),(3,)),spec,layers=2,shape=shape,
                weight_layout=static_weights(logical,spec.stack,policy),compute_reference=reference)
            graphs.append(graph);preloads.append(preload)
        for graph,preload in zip(graphs[1:],preloads[1:]):
            self.assertEqual(graph.tasks,graphs[0].tasks);self.assertEqual(graph.data,graphs[0].data)
            self.assertEqual(graph.control,graphs[0].control);self.assertEqual(preload,preloads[0])
            self.assertEqual([(o.id,o.size_bytes,o.storage_id) for o in graph.objects],
                             [(o.id,o.size_bytes,o.storage_id) for o in graphs[0].objects])
        self.assertNotEqual(graphs[2].objects,graphs[0].objects)

    def test_gate_up_intervention_preserves_down_addresses_and_locked_objects(self):
        stack=vertical_memory();logical=build_moe(((0,),),experts=4,topk=1,intermediate=512)
        hybrid=static_weights(logical,stack,'hybrid')
        changed=static_weights(logical,stack,'hybrid-gate-up-striped')
        self.assertEqual([w for w in hybrid if w.tensor.endswith('/down')],
                         [w for w in changed if w.tensor.endswith('/down')])
        self.assertTrue(any(a.memory!=b.memory for a,b in zip(hybrid,changed)))
        for a,b in zip(hybrid,changed):
            if a.memory==b.memory:self.assertEqual(a,b)
        for memory in {w.memory for w in changed}:
            intervals=sorted((w.offset_bytes,w.offset_bytes+w.size_bytes) for w in changed if w.memory==memory)
            self.assertTrue(all(a[1]<=b[0] for a,b in zip(intervals,intervals[1:])))


if __name__=='__main__':unittest.main()
