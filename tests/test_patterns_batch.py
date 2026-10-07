import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from hashlib import sha1
import numpy as np
from w2w.analysis.patterns_batch import summarize, windows
from w2w.workloads.patterns_download import fetch


class BatchDiagnosticsTests(unittest.TestCase):
    def test_union_reuse_and_complementarity(self):
        a=np.zeros((2,1,1,128),bool);a[:,0,0,[0,2]]=True
        owners=np.arange(128)%36;pairs=[(i,i+1) for i in range(0,36,2)]
        one=summarize(a,[0,1],1,owners,pairs);two=summarize(a,[0,1],2,owners,pairs)
        self.assertEqual(one['weight_read_reuse_saved'],0)
        self.assertEqual(two['weight_read_reuse_saved'],.5)
        self.assertEqual(two['active_client_idle_partner_fraction'],1)
        self.assertEqual(two['bank_only_sequential_bound_ratio'],2)
        self.assertEqual(two['idle_partner_streak_mean_decode_steps'],1)
        self.assertAlmostEqual(two['occupancy_conditioned_idle_partner_null'],34/35)
        a[1]=False;a[1,0,0,[1,3]]=True
        two=summarize(a,[0,1],2,owners,pairs)
        self.assertEqual(two['weight_read_reuse_saved'],0)
        self.assertEqual(two['active_client_idle_partner_fraction'],0)
        self.assertEqual(two['bank_only_sequential_bound_ratio'],1)

    def test_no_padding_or_request_duplication(self):
        a=np.zeros((3,1,1,128),bool);a[:,:,:,0]=True
        self.assertEqual([n for _,_,n in windows(a,[0,1,2],2)],[2,1])
        with self.assertRaises(ValueError):list(windows(a,[0,1,1],2))

    def test_mapping_and_union_conserve_expert_counts(self):
        a=np.zeros((3,2,2,128),bool)
        rng=np.random.default_rng(0)
        for r in range(3):
            for s in range(2):
                for l in range(2):a[r,s,l,rng.choice(128,8,replace=False)]=True
        for union,routed,n in windows(a,[2,0,1],2):
            self.assertTrue(np.all(union.sum(axis=1)<=routed))
            self.assertTrue(np.all(routed==n*8))

    def test_resume_reuses_verified_file_and_rejects_changed_plan(self):
        payload=b'[{"0":[[0]]},{"0":[[0]]}]'
        oid=sha1(b'blob '+str(len(payload)).encode()+b'\0'+payload).hexdigest()
        def response(url,limit):
            if '/tree/' in url:return json.dumps([dict(type='file',path='s/a.json',size=len(payload),oid=oid)]).encode()
            if '/resolve/' in url:return payload
            return json.dumps(dict(sha='a'*40,gated=False)).encode()
        with tempfile.TemporaryDirectory() as d,patch('w2w.workloads.patterns_download.get_bytes',side_effect=response) as mocked:
            fetch('https://example.test','s',d,1,100,100,selection='seeded',seed=17)
            mocked.reset_mock();fetch('https://example.test','s',d,1,100,100,selection='seeded',seed=17,resume=True)
            self.assertEqual(mocked.call_count,2)
            with self.assertRaisesRegex(ValueError,'parameters'):
                fetch('https://example.test','s',d,1,100,100,selection='seeded',seed=18,resume=True)
            Path(d,'request0.json').write_bytes(b'bad')
            with self.assertRaises(ValueError):fetch('https://example.test','s',d,1,100,100,selection='seeded',seed=17,resume=True)

if __name__=='__main__':unittest.main()
