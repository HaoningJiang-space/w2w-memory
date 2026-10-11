"""Full-shape GQA, capacity, actual positions and no free SRAM cache shrink."""
import copy,unittest
from dataclasses import asdict
from w2w.architecture.llm_deployment import LLMProfile,context_catalog
from w2w.architecture.presets.recipes import from_recipe
from w2w.architecture.compiler import compile_machine
from w2w.architecture.npu_profile import reference_profile
from w2w.workloads.patterns_adapter import RoutingObservation
from w2w.serving.batcher import group
from w2w.mapping.llm_context import lower_context
from w2w.system.npu_kernel import NPUKernelModel
from w2w.system.builder import SystemBuilder


class LLMContext(unittest.TestCase):
    def test_output_shards_keep_full_reductions_and_pay_bounded_input_trees(self):
        from w2w.validation.context_projections import audit_projection_call
        machine=compile_machine(from_recipe('configs/machine/v3-small.json','distributed'));p=LLMProfile();profile=reference_profile()
        shape=dict(hidden=p.hidden,intermediate=p.intermediate,experts=p.experts,topk=p.topk)
        catalog=context_catalog(machine,shape,('0','1'),'up_local',p,context_projection_policy='output_sharded')
        original=context_catalog(machine,shape,('0','1'),'up_local',p)
        self.assertEqual(sum(o.size_bytes for o in catalog['objects']),sum(o.size_bytes for o in original['objects']))
        rows=tuple(RoutingObservation('fixture/request','prefill',t,None,'0',tuple(range(8)),'fixture') for t in range(32))
        b=group('batch',rows);g,k,meta=lower_context(b,machine,catalog,profile,{},prefix='W0/L0/')
        builder=SystemBuilder(machine).validate_graph(g);model=NPUKernelModel(profile,k,auxiliary=meta['auxiliary']);model.validate(machine,g)
        result=dict(graph=asdict(g),npu_execution=model.record(),runtime_metadata=meta)
        self.assertEqual(audit_projection_call(result,b,catalog,'W0/L0/')['projection_macs'],32*71303168)
        self.assertEqual({a['kind']:len(a['shards']) for a in meta['projection_assemblies']},{'q':16,'k':4,'v':4,'o':16})
        for assembly in meta['projection_assemblies']:
            for node in assembly['input_copies']:
                self.assertLess(builder.footprint[node['task']],8*1024**2-16*1024)
        bad=copy.deepcopy(result);bad['runtime_metadata']['projection_assemblies'][0]['shards'][0]['scale_row_begin']=1
        with self.assertRaises(ValueError):audit_projection_call(bad,b,catalog,'W0/L0/')
        bad=copy.deepcopy(result);node=bad['runtime_metadata']['projection_assemblies'][3]['input_copies'][0]['task']
        bad['npu_execution']['auxiliary'][node]['output_sram_bytes']=0
        with self.assertRaises(ValueError):audit_projection_call(bad,b,catalog,'W0/L0/')

    def test_full_gqa_shapes_legal_layout_and_kv_positions(self):
        machine=compile_machine(from_recipe('configs/machine/v3-small.json','distributed'));p=LLMProfile()
        shape=dict(hidden=p.hidden,intermediate=p.intermediate,experts=p.experts,topk=p.topk)
        catalog=context_catalog(machine,shape,('0','1'),'up_local',p);profile=reference_profile()
        rows=tuple(RoutingObservation('captured/request','prefill',t,None,'0',tuple(range(8)),'fixture') for t in range(2))
        b=group('batch',rows);g,k,meta=lower_context(b,machine,catalog,profile,{},prefix='W0/L0/')
        SystemBuilder(machine).validate_graph(g);NPUKernelModel(profile,k,auxiliary=meta['auxiliary']).validate(machine,g)
        self.assertEqual(len(meta['kv_appends']),4);self.assertEqual(len(meta['kv_reads']),8)
        self.assertEqual(sum(x.M*x.N*x.K for key,x in k.items() if key.endswith('/qk')),64*2*2*128)
        self.assertEqual(sum(x.M*x.N*x.K for key,x in k.items() if key.endswith('/pv')),64*2*128*2)
        self.assertEqual(k['W0/L0/context/q'].N,8192)
        self.assertTrue(any('V_transpose' in key for key in meta['auxiliary']))
        with self.assertRaises(ValueError):lower_context(b,machine,catalog,profile,{('0','captured/request'):1},prefix='bad/')

    def test_embedding_head_are_distinct_full_bf16_residency(self):
        machine=compile_machine(from_recipe('configs/machine/v3-small.json','distributed'));p=LLMProfile()
        catalog=context_catalog(machine,dict(hidden=4096,intermediate=1536,experts=128,topk=8),('0','1'),'up_local',p,embedding=True,head=True)
        e=sum(o.size_bytes for o in catalog['objects'] if o.id.startswith('embedding/'))
        h=sum(o.size_bytes for o in catalog['objects'] if o.id.startswith('lm_head/'))
        self.assertEqual(e,2*151936*4096);self.assertEqual(h,e)
        self.assertFalse({o.storage_id for o in catalog['objects'] if o.id.startswith('embedding/')} &
            {o.storage_id for o in catalog['objects'] if o.id.startswith('lm_head/')})
