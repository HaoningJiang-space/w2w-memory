"""Resource conservation and original-scale ownership are design gates."""
import unittest
from dataclasses import replace
from w2w.architecture.domain_compute import domain_compute_specification
from w2w.mapping.domain_weights import domain_weight_catalog
from w2w.analysis.domain_organization import domain_organization_bounds
from w2w.mapping.data_placement import WeightLocation


class DomainOrganization(unittest.TestCase):
    def test_fp8_original_scales_and_bf16_row_math(self):
        from w2w.validation.domain_matrix_math import validate_row_partition,e4m3fn,bf16,row_projection
        def matrix(rows,cols,shift):
            return [[(0x20+((r*3+c+shift)%8))|(128 if (r+c+shift)%3==0 else 0) for c in range(cols)] for r in range(rows)]
        g,u,d=matrix(128,256,0),matrix(128,256,1),matrix(256,128,2)
        proof=validate_row_partition(g,u,d,[0.25,0.5],[0.5,0.25],[0.25,0.5],[(i%3-1)*0.25 for i in range(256)])
        self.assertTrue(proof['passed'])
        self.assertEqual(e4m3fn(0x7e),448);self.assertEqual(bf16(1.0),1.0)
        with self.assertRaises(ValueError):e4m3fn(0x7f)
        with self.assertRaises(ValueError):row_projection(g,[0.25],[0.0]*256,0,16)

    def inputs(self):
        from w2w.experiments.run_co_placement import inputs
        machine,graph,cache,data=inputs('up_local_compute','cold')
        from w2w.workloads.routing_input import load_workload
        logical=load_workload('configs/workloads/c0_b1.json')
        return machine,logical,tuple(WeightLocation(**w) for w in data['weights']),data

    def test_resources_and_control_serialization_are_not_free(self):
        m,l,w,d=self.inputs();p=domain_compute_specification(m.stack);r=p.record()['resources']
        self.assertEqual((len(p.tiles),r['pe_count'],r['macs_per_cycle']),(128,65536,262144))
        self.assertEqual(r['sram_bytes'],3*1024**3);self.assertEqual(r['cache_bytes'],184*1024**2*16)
        self.assertEqual((r['hb_data_bits'],r['hb_control_bits'],p.hb_sites),(16384,1024,17408))
        self.assertEqual((r['staging_bytes'],r['mc_slots'],r['outstanding_descriptors']),(524288,128,512))
        self.assertTrue(all(t.hb_control_bits==8 and t.staging_bytes==4096 for t in p.tiles))
        self.assertEqual(p.local_star_one_way_wire_bit_um,p.removed_collection_wire_bit_um)
        with self.assertRaises(ValueError):p.compile()
        with self.assertRaises(ValueError):domain_compute_specification(m.stack,cache_bytes_per_cluster=184*1024**2+1)
        for invalid in (0,-8,True):
            with self.assertRaises(ValueError):domain_compute_specification(m.stack,cache_bytes_per_cluster=invalid)

    def test_complete_row_reduction_and_shared_scale_identity(self):
        m,l,w,d=self.inputs();p=domain_compute_specification(m.stack);c=domain_weight_catalog(l,m.stack,w,p)
        self.assertEqual(len(c['matrices']),128*12*3)
        self.assertEqual(c['physical_catalog_bytes']-c['logical_catalog_bytes'],128*12*128)
        for phase in ('gate','up','down'):
            a=c['matrices']['weight/e0/b0/'+phase];s=a['slices']
            self.assertEqual(sum(v['data_bytes'] for v in s),4096*128)
            self.assertEqual(sum(v['scale_valid_bytes'] for v in s),128)
            self.assertEqual([v['output_rows'] for v in s],[(i*a['rows']//8,(i+1)*a['rows']//8) for i in range(8)])
            self.assertEqual({v['reduction_columns'] for v in s},{a['columns']})
            if phase!='down':
                self.assertEqual([v['scale_storage_bytes'] for v in s],[128,0,0,0,0,0,0,0])
                self.assertTrue(all(v['original_scale_indices']==tuple(range(32)) for v in s))
            else:self.assertEqual([v['scale_storage_bytes'] for v in s],[32]*8)
        b=domain_organization_bounds(l,p,c)
        self.assertEqual(b['cold_native_bytes'],151031808+96*128)
        self.assertEqual(b['whole_H_down_prefetch_buffer_per_tile'],65536)
        self.assertEqual(b['per_token_state']['down_accumulator_per_tile'],2048)
        with self.assertRaises(ValueError):domain_weight_catalog(l,m.stack,w[:-1],p)
        with self.assertRaises(ValueError):domain_weight_catalog(l,m.stack,(*w,w[0]),p)

    def test_current_up_local_already_has_all_projection_weights_local(self):
        m,l,w,d=self.inputs();objects={o['id']:o for o in d['graph']['objects']}
        memories={g.id:g for g in m.stack.bank_groups};gateways={g.id:g for g in m.stack.gateways};clusters={c.id:c for c in m.stack.compute_clusters}
        for t in d['graph']['tasks']:
            if not t['stream']:continue
            owner=gateways[memories[objects[t['stream']['weight_object']]['memory']].gateway_id]
            self.assertEqual((clusters[t['tile']].position_um,clusters[t['tile']].router_id),(owner.position_um,owner.router_id))


if __name__=='__main__':unittest.main()
