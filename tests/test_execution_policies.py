"""Distinguish queued compute contexts from actual nonpreemptive array owners."""
import copy,unittest
from dataclasses import asdict,replace

from tools.validate_npu_physical import graph
from w2w.architecture.compiler import compile_machine
from w2w.architecture.npu_profile import reference_profile
from w2w.architecture.presets.recipes import from_recipe
from w2w.domain.execution import ExecutionGraph
from w2w.system.operand_streaming import StreamingKernelModel,reprogram_streaming_graph,streaming_program
from w2w.system.row_mapping import RowMappingKernelModel,reprogram_graph
from w2w.validation.npu_resources import audit_npu_result


def queued_fixture(streaming):
    p=reference_profile();machine=compile_machine(from_recipe('configs/machine/v3-small.json','distributed'))
    tasks=[];objects=[];edges=[];kernels={}
    for index in range(2):
        g,ks=graph(machine,1,128,4096,p,f'k{index}');name=f'W{index}'
        objects.append(replace(g.objects[0],id=name,offset_bytes=index*1048576));edges.extend(g.data)
        tasks.extend(replace(t,reads=tuple(replace(r,object_id=name) for r in t.reads),
            stream=replace(t.stream,weight_object=name) if t.stream else None) for t in g.tasks)
        kernels.update({k:replace(v,weight_object=name) for k,v in ks.items()})
    g=ExecutionGraph(tasks,objects,edges)
    if streaming:g=reprogram_streaming_graph(g,kernels,p);model=StreamingKernelModel(p,kernels)
    else:g=reprogram_graph(g,kernels,p,'row_auto');model=RowMappingKernelModel(p,kernels,policy='row_auto')
    events=[dict(kind='data_deliver',time_ps=0,edge=e.id) for e in edges];cursor=0
    for key in kernels:
        plan=model.plans[key];tile=next(t.tile for t in tasks if t.id==key)
        events.extend((dict(kind='task_start',time_ps=0,task=key,tile=tile),
            dict(kind='cache_operands_ready',time_ps=0,task=key,tile=tile)))
        if streaming:
            code=streaming_program(1,128,4096,'FP8_E4M3FN',p)[0]
            events.extend(dict(kind='npu_cycle',time_ps=(cursor+i)*1000,task=key,tile=tile,program_cycle=i,**asdict(row)) for i,row in enumerate(code))
        else:
            events.append(dict(kind='npu_epoch',time_ps=cursor*1000,task=key,tile=tile,end_ps=(cursor+plan['cycles'])*1000,
                cycles=plan['cycles'],program_sha256=plan['program_sha256'],macs=plan['macs'],service=plan['service'],peak_service=plan['peak_service']))
        cursor+=plan['cycles'];events.append(dict(kind='task_finish',time_ps=cursor*1000,task=key,tile=tile))
    return dict(spec=asdict(machine),graph=asdict(g),events=sorted(events,key=lambda e:e['time_ps']),
        operand_readiness=dict(policy='contiguous_prefix'),npu_execution=model.record())


class ExecutionPolicies(unittest.TestCase):
    def test_two_queued_contexts_have_serial_physical_array_owners(self):
        for streaming in (False,True):
            result=queued_fixture(streaming)
            self.assertEqual(audit_npu_result(result)['macs'],2*128*4096)
            bad=copy.deepcopy(result);tile=result['graph']['tasks'][0]['tile']
            bad['events'].append(dict(kind='compute_service',time_ps=0,task='k0/input',tile=tile,cycles=1))
            bad['events'].sort(key=lambda e:e['time_ps'])
            with self.assertRaises(ValueError):audit_npu_result(bad)


if __name__=='__main__':unittest.main()
