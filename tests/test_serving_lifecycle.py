import unittest
from w2w.serving.requests import ServingRequest,RequestLifecycle
from w2w.serving.pipeline import PipelineLinks
from w2w.architecture.llm_deployment import LLMProfile
from w2w.system.npu_auxiliary import phase,work,auxiliary_program
from w2w.architecture.npu_profile import reference_profile


class ServingLifecycle(unittest.TestCase):
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
