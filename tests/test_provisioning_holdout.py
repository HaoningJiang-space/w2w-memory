from copy import deepcopy
import unittest

from w2w.experiments.run_provisioning_holdout import jobs
from w2w.workloads.patterns_trace import RequestRoutes
from w2w.workloads.provisioning_holdout import assign_owners, fit_owners, split_requests


class HoldoutTests(unittest.TestCase):
    def test_request_split_is_disjoint_and_ignores_routing(self):
        manifest = dict(requests=[dict(id=f'model/{s}/{i}.json', sha256='irrelevant')
                                  for s in ('a', 'b') for i in range(14)])
        previous = dict(groups=[dict(requests=['model/a/0.json', 'model/b/0.json'])])
        result = split_requests(manifest, previous, train_per_subject=2, groups=2)
        ids = result['training'] + sum(result['tests'], [])
        self.assertEqual(len(set(ids)), 12)
        self.assertFalse(set(ids) & set(result['excluded_previous']))
        altered = deepcopy(manifest)
        altered['requests'].reverse()
        for r in altered['requests']:
            r['sha256'] = 'different'
        self.assertEqual(result, split_requests(altered, previous, train_per_subject=2, groups=2))

    def test_duplicate_or_short_corpus_is_rejected(self):
        previous = dict(groups=[])
        with self.assertRaises(ValueError):
            split_requests(dict(requests=[dict(id='m/a/1'), dict(id='m/a/1')]), previous)
        with self.assertRaises(ValueError):
            split_requests(dict(requests=[dict(id='m/a/1')]), previous)

    def test_batch_union_and_equal_batch_weight(self):
        requests = tuple(RequestRoutes(str(i), 0, (((e,),),), {}) for i, e in enumerate((0, 0, 1, 2)))
        spec = dict(compute_count=2, layers=[dict(key='0', expert_count=4)])
        result = fit_owners(requests, spec, (1, 2))['0']
        self.assertEqual(result['training_scores'], [4, 3, 3, 0])
        self.assertEqual(result['score_denominator'], 8)
        self.assertEqual(result['compute_by_expert'], [0, 1, 1, 0])
        self.assertEqual(result['selected_loads'], [4, 6])
        self.assertEqual(result['modulo_loads'], [7, 3])
        self.assertEqual(result['resident_experts'], [2, 2])

    def test_owner_capacity_includes_unobserved_experts(self):
        owners = assign_owners([100, 0, 0, 0, 0, 0, 0], 3, 3)
        self.assertEqual(len(owners), 7)
        self.assertLessEqual(max(owners.count(c) for c in range(3)), 3)
        with self.assertRaises(ValueError):
            assign_owners([1]*7, 2, 3)

    def test_incomplete_training_cohorts_are_rejected(self):
        requests = (RequestRoutes('a', 0, (((0,),),), {}),)
        with self.assertRaises(ValueError):
            fit_owners(requests, dict(compute_count=1, layers=[dict(key='0', expert_count=1)]), (2,))

    def test_registered_job_coverage(self):
        cases = [dict(id=f'h{g}_b{b}', batch_size=b) for g in range(3) for b in (1, 4, 16)]
        selected = jobs(cases)
        self.assertEqual(len(selected), 87)
        self.assertEqual(len(set(selected)), 87)
        self.assertEqual(sum(label == 'home_mod' for _, label, _ in selected), 9)
        self.assertEqual(sum(n == 192 for _, _, n in selected), 15)


if __name__ == '__main__':
    unittest.main()
