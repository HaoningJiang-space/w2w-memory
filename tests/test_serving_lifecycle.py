import copy
import unittest
from w2w.serving.requests import ServingRequest,RequestLifecycle
from w2w.serving.pipeline import PipelineLinks
from w2w.architecture.llm_deployment import LLMProfile
from w2w.system.npu_auxiliary import phase,work,auxiliary_program
from w2w.architecture.npu_profile import reference_profile


class ServingLifecycle(unittest.TestCase):
    def test_unknown_phase_negative_step_and_extra_emission_are_rejected(self):
        r=RequestLifecycle(iter((ServingRequest('real/request',46,128,'sha'),)))
        for phase,step,time in (('decode',-1,0),('unknown',-1,0),('prefill',0,0),('prefill',None,0.5)):
            with self.assertRaises(ValueError):r.emit('real/request',phase,step,time)
        r.emit('real/request','prefill',None,100)
        with self.assertRaises(ValueError):r.emit('real/request','decode',128,200)

    def test_serving_notice_must_bind_physical_window_and_buffer_fences(self):
        from w2w.validation.llm_context import audit_stage_notice
        row=dict(index=1,makespan_ps=300,drained_ps=320,sha256='window',decoded_sha256='decoded',
            metadata=dict(input_ticket_sha256='ticket',release_ps=200,heads=[],
                calls=[dict(phase='decode',decode_step=0,token_ids=['fixture-token'])]))
        ticket=dict(committed_ps=150);prior=dict(source_release_ps=200)
        ack=dict(source_release_ps=330,producer_notice_sha256='notice')
        notice=dict(stage=0,index=1,makespan_ps=300,drained_ps=320,window_sha256='window',decoded_sha256='decoded',
            input_ticket_sha256='ticket',release_ps=200,heads=[],phase='decode',decode_step=0,tokens=1)
        audit_stage_notice(notice,row,0,ticket,'ticket',ack,'notice',prior)
        for field,value in (('drained_ps',250),('window_sha256','another-window'),('heads',[{'task':'invented'}]),('release_ps',150)):
            changed=copy.deepcopy(notice);changed[field]=value
            with self.assertRaises(ValueError):audit_stage_notice(changed,row,0,ticket,'ticket',ack,'notice',prior)
        with self.assertRaises(ValueError):audit_stage_notice(notice,row,0,ticket,'ticket',ack,'notice')
        with self.assertRaises(ValueError):audit_stage_notice(notice,row,0,ticket,'ticket',dict(ack,source_release_ps=319),'notice',prior)

    def test_idle_frontier_does_not_expose_a_blocked_future_task(self):
        from types import SimpleNamespace
        from w2w.system.idle_boundary import next_idle_boundary
        e=SimpleNamespace(requests={},packet_info={},reading=set(),active_edges=set(),cache_waiting={},
            memory_candidates=set(),ready_tasks=set(),engine={},outstanding={},mc_pool_slots={},mc_slots={},
            native=SimpleNamespace(compute_epoch_quiescent=lambda:True),network=SimpleNamespace(drained=lambda:True),
            unallocated={'root','dependent'},state={'root':{},'dependent':{}},predecessors={'root':set(),'dependent':{'root'}},
            tasks={'root':SimpleNamespace(release_ps=500000000),'dependent':SimpleNamespace(release_ps=0)},
            now=0,window_final_ps=None,spec=SimpleNamespace(noc_period_ps=1000,dram_period_ps=3760))
        self.assertEqual(next_idle_boundary(e,40,1000000000),500000000)
        e.requests={'pending':{}};self.assertIsNone(next_idle_boundary(e,40,1000000000));e.requests={}
        e.state['root']['done']=True;self.assertIsNone(next_idle_boundary(e,40,1000000000))
    def test_no_metrics_from_partial_or_reordered_token_sequence(self):
        r=RequestLifecycle((ServingRequest('real/request',46,128,'sha'),))
        with self.assertRaises(ValueError):r.metrics()
        with self.assertRaises(ValueError):r.emit('real/request','decode',0,10)
        r.emit('real/request','prefill',None,100)
        for n in range(128):r.emit('real/request','decode',n,200+n*100)
        self.assertEqual(r.metrics()['real/request']['ttft_ps'],100)
        self.assertEqual(r.metrics()['real/request']['tpot_ps'],100)
        with self.assertRaises(ValueError):r.emit('real/request','decode',127,14000)

    def test_shared_finite_link_ports_and_ordered_vector_phases(self):
        links=PipelineLinks(LLMProfile());a=links.transfer(0,1,8192,0,window=0,kind='activation')
        b=links.transfer(2,1,8192,0,window=0,kind='activation')
        self.assertGreater(b,a);self.assertGreaterEqual(links.events[1]['start_ps'],a)
        with self.assertRaises(ValueError):links.transfer(0,1,32*8192+1,0,window=1,kind='activation')
        p=reference_profile();code=auxiliary_program(work((phase('reduce',read=4096,ops=1024,floor=13),
            phase('normalize',read=4096,write=4096,ops=1024))),p)
        self.assertEqual(len(code),14)
        self.assertTrue(all(row['output_sram_bytes']==0 for row in code[:13]))
