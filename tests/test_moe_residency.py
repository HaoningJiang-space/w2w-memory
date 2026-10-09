"""Residency changes physical sources, while preserving logical layer work."""
from dataclasses import asdict
import gzip
import json
from pathlib import Path
import unittest

from w2w.experiments.run_residency_study import logical_work
from w2w.system.builder import SystemBuilder
from w2w.workloads.moe_task_graph import LAYER_COHORTS, compile_layer, machine


class MoEResidencyTest(unittest.TestCase):
    def test_pair_preserves_published_graph_and_machine(self):
        root = Path('artifacts/results/system/moe_layer/hbm2')
        with gzip.open(root/'input.json.gz', 'rt') as handle:
            previous = json.load(handle)
        with gzip.open(root/'registration.json.gz', 'rt') as handle:
            registration = json.load(handle)
        graph, _ = compile_layer()
        self.assertEqual(asdict(graph), previous['graph'])
        self.assertEqual(asdict(machine()), registration['cases'][0]['spec'])

    def test_frozen_all_expert_layout_and_equal_work(self):
        layouts = {}
        for cohort in LAYER_COHORTS:
            pair, pm = compile_layer(cohort=cohort)
            four, fm = compile_layer(cohort=cohort, residency='four_way')
            self.assertEqual(logical_work(pair), logical_work(four))
            self.assertEqual(pm['tokens'], fm['tokens'])
            for policy, graph in (('pair', pair), ('four_way', four)):
                if policy in layouts:
                    self.assertEqual(layouts[policy], graph.objects)
                layouts[policy] = graph.objects
                SystemBuilder(machine()).validate_graph(graph)
            for expert in range(128):
                shards = [o for o in four.objects if o.id.startswith(f'expert{expert}/')]
                memories = {int(o.memory[1:]) for o in shards}
                self.assertEqual(len(memories), 4)
                self.assertIn(fm['owners'][expert], memories)
                self.assertEqual(sum(o.size_bytes for o in shards), 18_878_976)
                self.assertEqual(max(m%6 for m in memories)-min(m%6 for m in memories), 1)
                self.assertEqual(max(m//6 for m in memories)-min(m//6 for m in memories), 1)

    def test_validation_requests_are_disjoint(self):
        seen = set()
        for cohort in LAYER_COHORTS:
            _, metadata = compile_layer(cohort=cohort)
            ids = {t['id'] for t in metadata['tokens']}
            self.assertFalse(seen & ids)
            self.assertEqual(len(ids), 4 if cohort == 'c2_b4' else 1)
            seen |= ids


if __name__ == '__main__':
    unittest.main()
