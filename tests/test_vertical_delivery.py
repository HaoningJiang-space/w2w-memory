"""Finite readiness cannot become a free bypass or extra residency capacity."""
import unittest
from w2w.architecture.vertical_streaming import CollectiveResidencyDirectory,VerticalStreamContract
from w2w.analysis.vertical_delivery import committed_fifo_bound,local_star


class VerticalDelivery(unittest.TestCase):
    def test_directory_preserves_capacity_and_pays_validity(self):
        r=CollectiveResidencyDirectory().record()
        self.assertEqual((r['slots'],r['original_slots']),(367,367))
        self.assertEqual(r['slot_padding_bytes_per_matrix'],896)
        self.assertEqual((r['original_tag_bytes'],r['tag_bytes'],r['metadata_bytes']),(8192,9216,9616))
        self.assertEqual(r['independent_equal_tag_capacity_bytes'],4*1024**2)
        for kwargs in ({'maximum_owned_scale_bytes':32},{'original_tag_bits':64},{'entries':True}):
            with self.assertRaises(ValueError):CollectiveResidencyDirectory(**kwargs)
        with self.assertRaises(ValueError):CollectiveResidencyDirectory().compile()

    def test_small_fifo_requires_a_different_readiness_contract(self):
        with self.assertRaises(ValueError):VerticalStreamContract(4096)
        r=VerticalStreamContract(4096,additional_staging_bytes=4096).record()
        self.assertTrue(r['requires_staging_read'])
        word=VerticalStreamContract(32).record()
        self.assertEqual(word['prefix_bytes_per_neighborhood'],4224)
        self.assertFalse(word['requires_staging_read'])
        with self.assertRaises(ValueError):VerticalStreamContract(32).compile()

    def test_fifo_replay_charges_committed_bytes_and_rejects_early_compute(self):
        task=dict(id='gemm',tile='c',stream=dict(weight_data_bytes=4096))
        commit=dict(kind='stream_operand_ready',task='gemm',time_ps=1,object_offset=0,bytes=4096)
        use=dict(kind='stream_compute',task='gemm',time_ps=1,weight_bytes=4096)
        r=dict(graph=dict(tasks=[task]),events=[commit,use])
        self.assertEqual(committed_fifo_bound(r)['maximum_bytes'],4096)
        r['events']=[use,commit]
        with self.assertRaises(ValueError):committed_fifo_bound(r)
        r['events']=[commit]
        with self.assertRaises(ValueError):committed_fifo_bound(r)
        r['events']=[dict(kind='cache_lookup',task='gemm',hit=True),use]
        self.assertEqual(committed_fifo_bound(r)['fp8_miss_bytes'],0)

    def test_full_frozen_workload_pays_activation_and_original_scale_transport(self):
        from w2w.experiments.run_co_placement import inputs
        m,g,cache,data=inputs('up_local_compute','cold')
        r=local_star(data['graph'],m.stack)
        self.assertEqual(r['blocks'],96)
        self.assertEqual(r['roles']['X_fanout']['sink_payload_bytes'],96*2*8*8192)
        self.assertEqual(r['roles']['scale_collect']['sink_payload_bytes'],96*2*128)
        self.assertEqual(r['roles']['scale_fanout']['sink_payload_bytes'],96*2*7*128)
        self.assertEqual(r['roles']['H_fanout']['sink_payload_bytes'],96*8*256)
        self.assertGreater(r['totals']['cell_bit_um'],8*r['totals']['payload_byte_um'])


if __name__=='__main__':unittest.main()
