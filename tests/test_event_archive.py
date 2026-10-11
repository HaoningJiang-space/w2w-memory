import unittest
import json
from copy import deepcopy
from w2w.common.event_archive import encode,decode,canonical_sha


class EventArchive(unittest.TestCase):
    def test_all_types_missing_fields_large_negative_deltas_and_order(self):
        r=dict(schema='physical',a=[1,{'x':False}],events=[
            dict(kind='a',time_ps=10**15,task='expert/62',bytes=32,flag=True),
            dict(kind='b',time_ps=10**15,task='expert/9',latency=1.25,metrics={'none':None}),
            dict(kind='a',time_ps=10**15+1,task='expert/62',bytes=-32),
            dict(kind='b',time_ps=10**15+17,task='expert/62',latency=2.5,metrics=[1,None])])
        self.assertEqual(decode(encode(r)),r)
        self.assertEqual(canonical_sha(decode(encode(r))),canonical_sha(r))
        numeric=dict(events=r['events'],counter={0:3,2:4,10:5})
        transmitted=json.loads(json.dumps(encode(numeric)))
        self.assertEqual(decode(transmitted),json.loads(json.dumps(numeric)))
        for mutate in (lambda a:a['events_codec']['strings'].__setitem__(0,'forged'),
            lambda a:a['events_codec'].update(order='AA=='),
            lambda a:a['events_codec']['columns'][0].update(count=1),
            lambda a:a.update(a=[2])):
            bad=deepcopy(encode(r));mutate(bad)
            with self.assertRaises((ValueError,IndexError)):decode(bad)
