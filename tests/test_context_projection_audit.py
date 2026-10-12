"""Reject same-byte wrong tensors and unpaid dependencies in projection evidence."""
import copy
import unittest
from dataclasses import asdict

from w2w.architecture.compiler import compile_machine
from w2w.architecture.llm_deployment import LLMProfile,context_catalog
from w2w.architecture.npu_profile import reference_profile
from w2w.architecture.presets.recipes import from_recipe
from w2w.mapping.llm_context import lower_context
from w2w.serving.batcher import group
from w2w.system.npu_kernel import NPUKernelModel
from w2w.validation.context_projections import audit_projection_call
from w2w.workloads.patterns_adapter import RoutingObservation


class ProjectionAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        machine=compile_machine(from_recipe('configs/machine/v3-small.json','distributed'))
        p=LLMProfile();npu=reference_profile();cls.prefix='W0/L0/'
        shape=dict(hidden=p.hidden,intermediate=p.intermediate,experts=p.experts,topk=p.topk)
        cls.batch=group('fixture',(RoutingObservation('fixture/request','prefill',0,None,'0',tuple(range(8)),'fixture'),))
        cls.cases={}
        for policy in ('whole_matrix_local','output_sharded'):
            catalog=context_catalog(machine,shape,('0','1'),'up_local',p,context_projection_policy=policy)
            graph,kernels,meta=lower_context(cls.batch,machine,catalog,npu,{},prefix=cls.prefix)
            result=dict(graph=asdict(graph),npu_execution=NPUKernelModel(npu,kernels,auxiliary=meta['auxiliary']).record(),runtime_metadata=meta)
            cls.cases[policy]=(catalog,result)

    def check_rejected(self,result,policy='output_sharded'):
        with self.assertRaises(ValueError):
            audit_projection_call(result,self.batch,self.cases[policy][0],self.prefix)

    def test_valid_policy_evidence_survives_json_round_trip(self):
        import json
        for policy,(catalog,result) in self.cases.items():
            with self.subTest(policy=policy):
                proof=audit_projection_call(json.loads(json.dumps(result)),self.batch,catalog,self.prefix)
                self.assertEqual(proof['projection_macs'],71303168)

    def test_same_size_other_tensor_cannot_replace_o_input(self):
        for policy,(_,saved) in self.cases.items():
            with self.subTest(policy=policy):
                bad=copy.deepcopy(saved)
                if policy=='output_sharded':
                    assembly=next(a for a in bad['runtime_metadata']['projection_assemblies'] if a['kind']=='o')
                    root=next(c for c in assembly['input_copies'] if c['source']==self.prefix+'context/head_concat')
                    key=root['task'];root['source']=self.prefix+'context/q_norm/rope'
                else:key=self.prefix+'context/o'
                for edge in bad['graph']['data']:
                    if edge['consumer']==key:edge['producer']=self.prefix+'context/q_norm/rope'
                self.check_rejected(bad,policy)

    def test_duplicate_assembly_cannot_be_hidden_by_dict_conversion(self):
        bad=copy.deepcopy(self.cases['output_sharded'][1])
        bad['runtime_metadata']['projection_assemblies'].append(copy.deepcopy(bad['runtime_metadata']['projection_assemblies'][0]))
        self.check_rejected(bad)

    def test_descriptor_init_must_precede_copy_and_gather(self):
        saved=self.cases['output_sharded'][1];assembly=saved['runtime_metadata']['projection_assemblies'][0]
        for key in (assembly['task'],assembly['input_copies'][0]['task']):
            with self.subTest(task=key):
                bad=copy.deepcopy(saved);work=bad['npu_execution']['auxiliary'][key]
                work['phases']=tuple(reversed(work['phases']))
                self.check_rejected(bad)

    def test_weight_read_must_fetch_the_complete_original_object(self):
        for policy,(_,saved) in self.cases.items():
            with self.subTest(policy=policy):
                bad=copy.deepcopy(saved)
                key=(bad['runtime_metadata']['projection_assemblies'][0]['shards'][0]['task']
                    if policy=='output_sharded' else self.prefix+'context/q')
                task=next(t for t in bad['graph']['tasks'] if t['id']==key)
                task['reads'][0]['size_bytes']-=32
                self.check_rejected(bad,policy)

    def test_gather_cannot_accept_an_extra_payload(self):
        bad=copy.deepcopy(self.cases['output_sharded'][1]);key=bad['runtime_metadata']['projection_assemblies'][0]['task']
        extra=copy.deepcopy(next(e for e in bad['graph']['data'] if e['consumer']==key))
        extra.update(id='fixture/extra-gather-input',producer=self.prefix+'context/head_concat')
        bad['graph']['data']=(*bad['graph']['data'],extra)
        self.check_rejected(bad)

    def test_copy_metadata_cannot_omit_a_tree_node(self):
        bad=copy.deepcopy(self.cases['output_sharded'][1]);assembly=bad['runtime_metadata']['projection_assemblies'][0]
        assembly['input_copies'].pop()
        self.check_rejected(bad)

    def test_precision_contract_cannot_change_behind_shape_counts(self):
        saved=self.cases['output_sharded'][1];key=saved['runtime_metadata']['projection_assemblies'][0]['shards'][0]['task']
        for field,value in (('input_dtype','FP8_E4M3FN'),('accumulator_dtype','BF16'),('scale_group',(64,128)),('cached_weights',False)):
            with self.subTest(field=field):
                bad=copy.deepcopy(saved);bad['npu_execution']['kernels'][key][field]=value
                self.check_rejected(bad)
