"""Directed math, identity, array and SRAM tests; research uses real full traces."""
import unittest
from dataclasses import replace
from w2w.architecture.npu_profile import reference_profile
from w2w.architecture.presets.recipes import from_recipe
from w2w.architecture.compiler import compile_machine
from w2w.workloads.patterns_adapter import RoutingObservation
from w2w.serving.batcher import group
from w2w.mapping.moe_batch_lowering import full_catalog,lower_batch
from w2w.system.npu_kernel import program,NPUKernelModel


class RealNPU(unittest.TestCase):
    def test_real_token_identity_rank_and_grouped_shapes(self):
        rows=tuple(RoutingObservation(f'request{i}','decode',46,0,'0',tuple(range(i,i+8)),'fixture') for i in range(4))
        batch=group('b0',rows)
        self.assertEqual(sum(len(ts) for _,ts in batch.expert_to_tokens),32)
        self.assertEqual(dict(batch.expert_to_tokens)[3],tuple(r.token_id for r in rows))
        self.assertEqual(batch.token_to_experts[0][1],tuple(range(8)))
        m=compile_machine(from_recipe('configs/machine/v3-small.json','distributed'))
        shape=dict(hidden=4096,intermediate=1536,experts=128,topk=8)
        catalog=full_catalog(m,shape,('0','1'),'up_local')
        graph,kernels,meta=lower_batch(batch,m,catalog,reference_profile(),prefix='W0/')
        self.assertEqual(kernels['W0/e3/b0/gate'].M,4)
        self.assertEqual(kernels['W0/e3/b0/down'].K,128)
        self.assertEqual(len({o.id for o in graph.objects}),128*12*3*2+2)
        self.assertEqual(meta['expert_macs'],3*32*4096*1536)
        self.assertTrue(any(e.producer=='W0/router_done' and '/dispatch/' in e.consumer for e in graph.data))
        self.assertTrue(any('/pack' in t.id for t in graph.tasks))
        self.assertTrue(any('/scatter' in t.id for t in graph.tasks))
        NPUKernelModel(reference_profile(),kernels,auxiliary=meta['auxiliary']).validate(m,graph)
        combine=meta['auxiliary']['W0/t0/combine']
        self.assertEqual([p['name'] for p in combine['phases'][1:-1]],[f'ordered-ranked-expert-{e}' for e in range(8)])
        self.assertGreater(combine['activation_sram_bytes'],16*4096)
        self.assertEqual(meta['auxiliary']['W0/e3/pack']['output_sram_bytes'],4*4096*2*24)
        with self.assertRaises(ValueError):full_catalog(m,shape,tuple(str(i) for i in range(94)),'up_local')

    def test_array_shape_and_partial_work_are_not_peak_division(self):
        for size in (16,32):
            p=reference_profile(size)
            for M in (1,2,4,8,16,32):
                for N,K in ((128,4096),(4096,128)):
                    code,meta=program(M,N,K,'FP8_E4M3FN',p)
                    self.assertEqual(sum(i.macs for i in code),M*N*K)
                    self.assertEqual(meta['array_cycles'],sum(max(t['K'] for t in w)+p.rows+p.columns-2 for w in meta['waves']))
                    self.assertGreaterEqual(meta['cycles'],M*N*K/p.macs_per_cycle)
                    self.assertTrue(all(i.macs<=p.macs_per_cycle for i in code))
                    self.assertTrue(all(i.weight_sram_bytes+i.scale_sram_bytes<=p.weight_read_bytes_per_cycle for i in code))
                    self.assertTrue(all(i.activation_sram_bytes<=p.activation_read_bytes_per_cycle for i in code))
                    self.assertTrue(all(i.output_sram_bytes<=p.output_write_bytes_per_cycle for i in code))
        a=program(1,128,4096,'FP8_E4M3FN',reference_profile())[1]
        b=program(1,128,4096,'FP8_E4M3FN',reference_profile(32))[1]
        self.assertNotEqual(a['cycles'],b['cycles'])
        self.assertGreater(a['k_partitions'],1)
        code=program(1,128,4096,'FP8_E4M3FN',reference_profile())[0]
        reduction=[r for r in code if r.phase.startswith('ordered_k_')]
        self.assertEqual([r.phase for r in reduction],['ordered_k_load']+['ordered_k_add']*7+['ordered_k_final_store'])
        self.assertTrue(all(r.output_sram_bytes==0 for r in reduction[:-1]))

    def test_bad_ports_or_unpaid_buffers_rejected(self):
        m=compile_machine(from_recipe('configs/machine/v3-small.json','distributed'))
        with self.assertRaises(ValueError):replace(reference_profile(),arrays=65).validate_cluster(m.stack.compute_clusters[0])
        with self.assertRaises(ValueError):replace(reference_profile(),weight_read_bytes_per_cycle=32769).validate_cluster(m.stack.compute_clusters[0])
        with self.assertRaises(ValueError):program(1,128,4096,'FP8_E4M3FN',replace(reference_profile(),bank_port_bytes_per_cycle=16))


if __name__=='__main__':unittest.main()
