"""Independent layer storage and explicit inter-layer/token order on one fabric."""
import unittest
from w2w.architecture.presets import vertical_memory
from w2w.architecture.compiler import compile_machine
from w2w.mapping.sequence import lower_sequence
from w2w.system.builder import SystemBuilder

class SequenceMapping(unittest.TestCase):
    def test_two_layer_addresses_are_distinct_and_mapping_is_matched(self):
        graphs=[]
        for organization in ('central','distributed'):
            machine=compile_machine(vertical_memory(organization))
            graph,meta,preload=lower_sequence(((0,),(1,)),machine,layers=2,
                shape=dict(experts=4,topk=1,intermediate=512))
            SystemBuilder(machine).validate_graph(graph)
            self.assertEqual(len(meta['invocations']),4)
            self.assertEqual(sum(o.size_bytes for o in graph.objects),2*meta['initial_resident_bytes'])
            self.assertTrue(all(obj.startswith('L0/') for _,obj in preload))
            self.assertTrue(any(e.id=='I0001/layer_input' for e in graph.data))
            self.assertTrue(any(e.producer=='I0001/t0/combine' and e.consumer=='I0002/t0/input' for e in graph.control))
            self.assertNotEqual(graph.objects[0].offset_bytes,graph.objects[len(graph.objects)//2].offset_bytes)
            graphs.append(graph)
        self.assertEqual(graphs[0],graphs[1])
