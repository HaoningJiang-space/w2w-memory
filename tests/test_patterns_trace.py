"""Input correctness; synthetic format fixtures never substitute for real data."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from tests.test_read_workload import home_design, FAST
from w2w.workloads.patterns_trace import compile_patterns, load_requests, project_demand, batches
from w2w.workloads.read_trace import ReadTrace
from w2w.service.read_replay import replay_reads
from w2w.experiments.fetch_patterns_sample import fetch, OriginBoundAuthorization
from urllib.request import Request

FIXTURE=Path(__file__).parent/'fixtures/patterns_input'


class PatternsInputTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'input';shutil.copytree(FIXTURE,self.root)
        self.spec=json.loads((self.root/'execution.json').read_text())
        self.manifest=self.root/'manifest.json'

    def update_request(self, index, change):
        path=self.root/f'request{index}.json';value=json.loads(path.read_text());change(value)
        data=json.dumps(value).encode();path.write_bytes(data)
        manifest=json.loads(self.manifest.read_text());manifest['requests'][index]['sha256']=sha256(data).hexdigest()
        self.manifest.write_text(json.dumps(manifest))

    def test_union_not_token_multiplication_and_layer_barriers(self):
        trace,summary=compile_patterns(self.manifest,self.spec)
        first=summary['windows'][0]
        self.assertEqual(first['activated_experts'],[0,1])
        self.assertEqual(first['logical_read_bytes'],2*3328)
        self.assertEqual(first['no_reuse_reference_bytes'],4*3328)
        self.assertEqual(len(trace.objects),8)  # all experts, including inactive ones
        self.assertFalse(summary['captured_routing'])
        self.assertEqual(ReadTrace.from_record(trace.record()),trace)
        by_id={t.id:t for t in trace.tasks}
        for previous,current in zip(summary['windows'],summary['windows'][1:]):
            self.assertTrue(all(by_id[k].dependencies==(previous['join_task'],) for k in current['task_ids']))
        self.assertEqual(summary['total_logical_read_bytes'],sum(r.size_bytes for t in trace.tasks for r in t.reads))

    def test_refill_has_mixed_decode_positions_and_no_padding(self):
        requests,_=load_requests(self.manifest,self.spec)
        windows=list(batches(requests,'iteration_refill',2))
        self.assertEqual([(r.id,s) for r,s in windows[1][1]],
                         [('synthetic_request0',1),('synthetic_request2',0)])
        observed=[(r.id,s) for _,active in windows for r,s in active]
        self.assertEqual(len(observed),6);self.assertEqual(len(set(observed)),6)
        cohort=list(batches(requests,'fixed_cohort',2))
        self.assertEqual(cohort[1][1][0][0].id,'synthetic_request0')
        self.assertEqual(len(cohort[1][1]),1)
        self.assertEqual(cohort[3][1][0][0].id,'synthetic_request2')

    def test_flat_decode_and_explicit_truncation(self):
        self.update_request(0,lambda value:value[1].update({'1':value[1]['1'][0]}))
        self.spec['batching']['max_decode_steps']=1
        _,summary=compile_patterns(self.manifest,self.spec)
        self.assertEqual([r['omitted_decode_steps'] for r in summary['requests']],[2,0,1])
        self.assertEqual(sum(w['token_count'] for w in summary['windows']),6)  # 3 requests x 2 layers

    def test_reject_hash_change(self):
        (self.root/'request0.json').write_text('[]')
        with self.assertRaisesRegex(ValueError,'SHA256'):compile_patterns(self.manifest,self.spec)

    def test_reject_prefill_as_decode_and_unknown_layer(self):
        self.update_request(0,lambda value:value[1].update({'1':[[0,1],[2,3]]}))
        with self.assertRaisesRegex(ValueError,'exactly one token'):compile_patterns(self.manifest,self.spec)
        self.spec['layers'][0]['key']='missing'
        with self.assertRaisesRegex(ValueError,'Missing selected layer'):compile_patterns(self.manifest,self.spec)

    def test_unknown_experts_and_incomplete_static_placement(self):
        self.update_request(0,lambda value:value[1].update({'1':[[0,4]]}))
        with self.assertRaisesRegex(ValueError,'expert IDs'):compile_patterns(self.manifest,self.spec)
        self.spec['layers'][0]['compute_by_expert'].pop()
        with self.assertRaisesRegex(ValueError,'unobserved'):compile_patterns(self.manifest,self.spec)

    def test_demand_and_residence_connect_to_existing_replay(self):
        for layer in self.spec['layers']:layer['compute_by_expert']=[0,1,0,1];layer['weight_bytes']=64
        self.spec['compute_count']=2
        trace,summary=compile_patterns(self.manifest,self.spec)
        projection=project_demand(home_design(),trace,summary['windows'])
        self.assertEqual(sum(projection['resident_bytes_per_bank']),8*64)
        for window,projected in zip(summary['windows'],projection['windows']):
            self.assertEqual(projected['memory_bytes'],window['read_bytes_per_compute'])
            self.assertEqual(sum(projected['bank_bytes'].values()),window['logical_read_bytes'])
        result=replay_reads(home_design(),trace,FAST)
        self.assertEqual(result['logical_bytes'],summary['total_logical_read_bytes'])
        self.assertEqual(result['audit']['delivered_words']*32,summary['total_logical_read_bytes'])

    def test_whole_object_residency_exceeds_capacity_without_rescaling(self):
        for layer in self.spec['layers']:
            layer['compute_by_expert']=[0,1,0,1];layer['weight_bytes']=2**40
        self.spec['compute_count']=2
        trace,summary=compile_patterns(self.manifest,self.spec)
        with self.assertRaisesRegex(ValueError,'capacity'):project_demand(home_design(),trace,summary['windows'])


class BoundedDownloadTests(unittest.TestCase):
    def test_token_never_sent_to_mirror(self):
        with tempfile.TemporaryDirectory() as folder,patch('w2w.experiments.fetch_patterns_sample.get_bytes') as mock:
            with self.assertRaisesRegex(ValueError,'official|huggingface.co'):
                fetch('https://hf-mirror.com','subject',Path(folder)/'out',token_file='not-read.txt')
            mock.assert_not_called()

    def test_cross_host_redirect_strips_authorization(self):
        original=Request('https://huggingface.co/datasets/example',headers={'Authorization':'Bearer placeholder'})
        redirected=OriginBoundAuthorization().redirect_request(original,None,302,'Found',{},'https://cdn.example.test/file')
        self.assertFalse(redirected.has_header('Authorization'))

    def test_gated_metadata_does_not_replace_file_authorization(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);secret=root/'credential';secret.write_text('hf_testplaceholder')
            def response(url,limit,token=None):
                self.assertEqual(token,'hf_testplaceholder')
                if '/tree/' in url:return json.dumps([dict(type='file',path='subject/request.json',size=20)]).encode()
                if '/resolve/' in url:raise RuntimeError('HTTP 403: GatedRepo')
                self.assertIn('expand=sha',url)
                return json.dumps(dict(sha='a'*40,gated='auto')).encode()
            with patch('w2w.experiments.fetch_patterns_sample.get_bytes',side_effect=response):
                with self.assertRaisesRegex(RuntimeError,'GatedRepo'):
                    fetch('https://huggingface.co','subject',root/'out',token_file=secret)
            receipt=(root/'out/download_receipt.json').read_text()
            self.assertNotIn('hf_testplaceholder',receipt)
            self.assertFalse((root/'out/manifest.json').exists())

    def test_only_smallest_file_and_pinned_revision(self):
        revision='a'*40;payload=b'[{"0": [[0]]}, {"0": [[0]]}]'
        listing=[dict(type='file',path='subject/large.json',size=999999),
                 dict(type='file',path='subject/small.json',size=len(payload)),
                 dict(type='directory',path='subject/nested',size=0)]
        def response(url,limit):
            if '/tree/' in url:return json.dumps(listing).encode()
            if '/resolve/' in url:
                self.assertIn(revision,url);self.assertTrue(url.endswith('small.json'));return payload
            return json.dumps(dict(sha=revision,gated=False)).encode()
        with tempfile.TemporaryDirectory() as folder,patch('w2w.experiments.fetch_patterns_sample.get_bytes',side_effect=response) as mock:
            out=Path(folder)/'output';record=fetch('https://example.test','subject',out,1,100,100)
            self.assertEqual(len(record['downloaded']),1);self.assertEqual(mock.call_count,3)
            self.assertEqual(json.loads((out/'manifest.json').read_text())['requests'][0]['sha256'],sha256(payload).hexdigest())

    def test_access_denial_has_no_alternate_host_or_raw_download(self):
        with tempfile.TemporaryDirectory() as folder,patch('w2w.experiments.fetch_patterns_sample.get_bytes',side_effect=RuntimeError('HTTP 403')) as mock:
            out=Path(folder)/'output'
            with self.assertRaisesRegex(RuntimeError,'403'):fetch('https://example.test','subject',out)
            self.assertEqual(mock.call_count,1)
            self.assertEqual(json.loads((out/'download_receipt.json').read_text())['downloaded'],[])
            self.assertFalse((out/'manifest.json').exists())


if __name__=='__main__':unittest.main()
