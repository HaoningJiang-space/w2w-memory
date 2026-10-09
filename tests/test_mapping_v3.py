import unittest
from dataclasses import asdict
from w2w.workloads.moe import build_moe
from w2w.architecture.presets import vertical_memory
from w2w.architecture.compiler import compile_machine
from w2w.mapping.data_placement import place_weights
from w2w.mapping.compute_placement import place_compute
from w2w.mapping.lowering import lower
from w2w.system.builder import SystemBuilder


class MappingV3(unittest.TestCase):
    def test_same_workload_different_fabric_and_gateway(self):
        logical=build_moe(((0,1,2,3,4,5,6,7),))
        plans=[]
        for organization,columns in (('central',2),('distributed',2),('distributed',1)):
            s=vertical_memory(organization,columns=columns)
            spec=compile_machine(s);w=place_weights(logical,s);p=place_compute(logical,s,w)
            graph,meta=lower(logical,spec,w,p)
            SystemBuilder(spec).validate_graph(graph)
            plans.append(meta)
        self.assertEqual(plans[0]['weight_layout_sha256'],plans[1]['weight_layout_sha256'])
        self.assertEqual(plans[0]['compute_placement_sha256'],plans[1]['compute_placement_sha256'])
        self.assertEqual(len({p['logical_sha256'] for p in plans}),1)
        self.assertEqual(len({p['macs'] for p in plans}),1)
        self.assertEqual(plans[0]['weight_read_bytes'],8*18878976)

    def test_tensor_identity_is_not_a_copy(self):
        logical=build_moe(((0,1,2,3,4,5,6,7),))
        x=next(t for t in logical.tensors if t.id.startswith('X/'))
        self.assertEqual(len(x.consumers),2*8*12)
        self.assertEqual(sum(t.id.startswith('X/') for t in logical.tensors),1)
        self.assertEqual(x.storage_id,x.id)
        self.assertFalse(any(word in repr(asdict(logical)) for word in ('router_id','gateway_id','home_tile')))


if __name__=='__main__':unittest.main()
