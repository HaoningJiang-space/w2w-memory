"""Coverage, independent layer routing and explicit post-router MoE semantics."""
import copy,unittest
from w2w.workloads.moe_trace import normalize
from w2w.workloads.captured_moe import build_captured_moe


class CapturedMoETrace(unittest.TestCase):
    def capture(self):
        shape=dict(hidden=4096,intermediate=1536,experts=128,topk=8,layers=2)
        raw=[{'0':[list(range(8)),list(range(8,16))],
              '1':[list(range(16,24)),list(range(24,32))]},
             {'0':[list(range(8))],'1':[list(range(32,40))]},
             {'0':[list(range(8,16))],'1':[list(range(40,48))]}]
        return raw,shape

    def test_no_prefill_decode_or_layer_substitution(self):
        raw,shape=self.capture();r=normalize(raw,dict(id='fixture',sha256='synthetic'),shape)
        self.assertEqual(r['prefill'],raw[0]);self.assertEqual(r['decode']['1'][1],raw[2]['1'][0])
        self.assertEqual(r['coverage']['expert_assignments'],64)
        self.assertEqual(r['coverage']['decode_tokens'],2)
        for field in ('omitted_layers','omitted_prefill_tokens','omitted_decode_tokens'):
            self.assertEqual(r['coverage'][field],0)
        self.assertFalse(r['availability']['router_probabilities'])
        for mutate in ('missing','duplicate','null','bool'):
            bad=copy.deepcopy(raw)
            if mutate=='missing':bad[1].pop('1')
            elif mutate=='duplicate':bad[1]['1'][0][1]=bad[1]['1'][0][0]
            elif mutate=='null':bad[1]['1']=None
            else:bad[1]['1'][0][0]=True
            with self.assertRaises(ValueError):normalize(bad,dict(id='fixture',sha256='synthetic'),shape)

    def test_dispatch_and_combine_preserve_real_expert_membership(self):
        selections=(tuple(range(8)),tuple(range(4,12)))
        r=build_captured_moe(selections)
        dispatch=[o for o in r.operations if o.kind=='moe_dispatch']
        self.assertEqual(len(dispatch),16)
        for token,selected in enumerate(selections):
            self.assertEqual({o.expert for o in dispatch if o.token_ids==(token,)},set(selected))
        gate=next(o for o in r.operations if o.id=='e4/b0/gate')
        self.assertEqual(gate.token_ids,(0,1));self.assertEqual(gate.macs,2*4096*128)
        combine=[o for o in r.operations if o.kind=='moe_combine']
        self.assertEqual(len(combine),2)
        for o in combine:
            output_inputs=[t for t in r.tensors if o.id in t.consumers and '/output' in t.id]
            self.assertEqual(len(output_inputs),8)
        self.assertEqual(len(r.weight_sizes),128*12*3)

    def test_real_layer_namespaces_and_complete_request_phases(self):
        from w2w.architecture.presets.recipes import from_recipe
        from w2w.architecture.compiler import compile_machine
        from w2w.mapping.captured_sequence import lower_captured_request
        raw,shape=self.capture();r=normalize(raw,dict(id='fixture',sha256='synthetic'),shape)
        m=compile_machine(from_recipe('configs/machine/v3-small.json','distributed'))
        g,meta=lower_captured_request(r,m,('0','1'))
        self.assertEqual(len(meta['invocations']),6)
        self.assertEqual([i['token_count'] for i in meta['invocations']],[2,2,1,1,1,1])
        self.assertEqual(meta['invocations'][1]['token_experts'],raw[0]['1'])
        self.assertEqual(meta['invocations'][3]['token_experts'],raw[1]['1'])
        self.assertEqual({o.id.split('/')[0] for o in g.objects},{'L0','L1'})
        self.assertEqual(meta['omitted_execution_tokens'],0)
        self.assertTrue(any('/dispatch/' in t.id for t in g.tasks))
        with self.assertRaises(ValueError):lower_captured_request(r,m,('0','0'))

    def test_direct_raw_audit_detects_layer_reuse(self):
        import json,gzip,tempfile
        from pathlib import Path
        from w2w.workloads.moe_trace import import_corpus,verify_corpus,file_sha
        from w2w.common.fingerprints import digest_read_v1 as digest
        raw,shape=self.capture()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'raw.json';path.write_text(json.dumps(raw))
            manifest=dict(schema='w2w.pbc-files.v1',evidence='captured',source='fixture',revision='fixture',
                requests=[dict(id='fixture/model/request',path='raw.json',sha256=file_sha(path))])
            (root/'manifest.json').write_text(json.dumps(manifest))
            config=dict(model_type='qwen3_moe',mlp_only_layers=[],decoder_sparse_step=1,hidden_size=4096,
                moe_intermediate_size=1536,num_experts=128,num_experts_per_tok=8,num_hidden_layers=2,
                quantization_config=dict(weight_block_size=[128,128]))
            (root/'config.json').write_text(json.dumps(config))
            (root/'source.json').write_text(json.dumps(dict(model='fixture/model',revision='fixture',sha256=file_sha(root/'config.json'))))
            out=root/'out';receipt=import_corpus(root/'manifest.json',root/'config.json',root/'source.json',out)
            audit=verify_corpus(root/'manifest.json',out)
            self.assertTrue(audit['compared_every_raw_selection'])
            (out/'coverage-audit.json').write_text(json.dumps(audit))
            from w2w.experiments.run_captured_moe import prepare
            prepare(root/'study',out,0,('0','1'))
            reg=json.loads((root/'study/registration.json').read_text())
            self.assertEqual((reg['prefill_tokens'],reg['decode_tokens'],reg['execution_omitted_tokens']),(2,2,0))
            self.assertEqual(reg['selected_expert_catalog_bytes'],2*2416508928)
            self.assertEqual(len(reg['cases']),2)
            target=out/receipt['requests'][0]['path'];r=json.load(gzip.open(target,'rt'))
            r['decode']['1']=r['decode']['0']
            with gzip.open(target,'wt') as f:json.dump(r,f)
            receipt['requests'][0]['file_sha256']=file_sha(target)
            receipt['requests'][0]['normalized_sha256']=digest(r)
            (out/'manifest.json').write_text(json.dumps(receipt))
            with self.assertRaises(ValueError):verify_corpus(root/'manifest.json',out)


if __name__=='__main__':unittest.main()
