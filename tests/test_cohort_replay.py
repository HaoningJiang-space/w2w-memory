from copy import deepcopy
from dataclasses import replace
import unittest

from w2w.workloads.cohort_replay import select_requests, jobs, logical_signature, frozen_owners
from w2w.workloads.read_trace import ReadTrace, ReadObject, ReadTask, ReadSpan
from w2w.validation.cohort_replay import check_trace


class CohortReplayTests(unittest.TestCase):
    def test_selection_is_disjoint_and_ignores_input_order(self):
        ids=[f'model/{s}/{i}' for s in ('a','b') for i in range(14)]
        previous={'split':{'training':[ids[0]],'excluded_previous':[ids[1]],'tests':[[ids[2]],[ids[3]]]}}
        corpus={'requests':[{'id':k} for k in ids]}
        result=select_requests(corpus,previous)
        chosen=sum(result['groups'],[])
        self.assertEqual(len(chosen),len(set(chosen)))
        self.assertFalse(set(chosen)&set(ids[:4]))
        corpus['requests'].reverse()
        self.assertEqual(result,select_requests(corpus,previous))

    def test_short_corpus_is_rejected_instead_of_reusing_requests(self):
        corpus={'requests':[{'id':f'model/a/{i}'} for i in range(5)]}
        old={'split':{'training':[],'excluded_previous':[],'tests':[]}}
        with self.assertRaisesRegex(ValueError,'Insufficient'):
            select_requests(corpus,old)

    def test_frozen_maps_preserve_resident_counts(self):
        maps=frozen_owners()
        self.assertEqual(set(maps),{'marginal','home','k2','wide','c'})
        for owners in maps.values():
            self.assertEqual([owners.count(c) for c in range(36)],
                             [maps['marginal'].count(c) for c in range(36)])
        self.assertEqual(len(jobs()),81)
        self.assertEqual(len(set(jobs())),81)

    def test_reconstruction_rejects_changed_owner_bytes_and_dependency(self):
        owners=[0,1]
        objects=(ReadObject('layer:0/expert:0',64,0),ReadObject('layer:0/expert:1',64,1))
        task=ReadTask('batch0/layer0/expert0',0,(ReadSpan(objects[0].id,0,64),))
        join=ReadTask('batch0/layer0/join',None,dependencies=(task.id,))
        trace=ReadTrace(objects,(task,join),'captured','fixture')
        case={'requests':['r'],'decode_step':1}
        routes={'r':{'decode':[[[0]]]}}
        check_trace(trace,case,routes,owners,64)
        for changed in (replace(trace,tasks=(replace(task,reads=(ReadSpan(objects[0].id,0,32),)),join)),
                        replace(trace,tasks=(task,replace(join,dependencies=()))),
                        replace(trace,objects=(replace(objects[0],compute=1),objects[1]),tasks=(replace(task,compute=1),join))):
            with self.assertRaisesRegex(ValueError,'Objects, owners'):
                check_trace(changed,case,routes,owners,64)
        renamed=replace(trace,source='different provenance')
        self.assertEqual(logical_signature(trace),logical_signature(renamed))


if __name__=='__main__': unittest.main()
