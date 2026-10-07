from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest

from tests.test_read_workload import FAST, home_design, read_trace
from w2w.analysis.patterns_replay import check_coverage, check_delivery, check_routing_union
from w2w.service.read_replay import replay_reads
from w2w.analysis.request_window import window_certificate
from w2w.validation.patterns_replay import check_frozen_accounting


class ReplayArchiveTests(unittest.TestCase):
    def test_unchanged_global_totals_cannot_hide_wrong_bank_or_route(self):
        trace, design = read_trace(19, both=True), home_design()
        row = replay_reads(design, trace, FAST)
        certificate = window_certificate(design, trace, FAST)
        check_frozen_accounting(certificate, row, trace.word_bytes)
        for target in ('native', 'route', 'task', 'embedded'):
            bad = deepcopy(row)
            if target == 'native':
                keys = list(bad['native_words_by_bank'])
                bad['native_words_by_bank'][keys[0]] -= 1
                bad['native_words_by_bank'][keys[1]] += 1
            elif target == 'route':
                bad['routes'][0]['received_words'] -= 1
                bad['routes'][1]['received_words'] += 1
            elif target == 'task':
                key = next(iter(bad['tasks'][0]['bank_bytes']))
                bad['tasks'][0]['bank_bytes'][key] -= 32
            else:
                bad['design']['name'] = 'unrelated design'
            # Previously the global conservation check alone accepted these.
            check_delivery(trace, bad)
            with self.subTest(target=target), self.assertRaises(ValueError):
                check_frozen_accounting(certificate, bad, trace.word_bytes)

    def test_shifted_child_before_parent_is_rejected_even_with_valid_duration(self):
        trace, design = read_trace(19, both=True), home_design()
        trace = replace(trace, tasks=(trace.tasks[0], replace(trace.tasks[1], dependencies=('a',))))
        row = replay_reads(design, trace, FAST)
        certificate = window_certificate(design, trace, FAST)
        check_frozen_accounting(certificate, row, trace.word_bytes)
        child = next(t for t in row['tasks'] if t['id'] == 'b')
        for field in ('start_slot', 'reads_done_slot', 'finish_slot'):
            child[field] -= 1
        with self.assertRaisesRegex(ValueError, 'dependency'):
            check_frozen_accounting(certificate, row, trace.word_bytes)

    def test_independent_union_rejects_per_token_weight_reads_and_missing_residency(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            entries = []
            for index, selected in enumerate(([0, 1], [1, 2])):
                raw = json.dumps([{'0': [[3, 0]]}, {'0': [selected]}]).encode()
                path = f'{index}.json'
                (root / path).write_bytes(raw)
                entries.append(dict(path=path, sha256=sha256(raw).hexdigest()))
            manifest = root / 'manifest.json'
            manifest.write_text(json.dumps(dict(requests=entries)))
            spec = dict(layers=[dict(key='0', top_k=2, weight_bytes=64,
                                     compute_by_expert=[0, 1, 2, 3])])
            demand = dict(total_resident_weight_bytes=256, windows=[dict(
                expert_token_counts={'0': 1, '1': 2, '2': 1},
                activated_experts=[0, 1, 2], logical_read_bytes=192)])
            check_routing_union(manifest, spec, 1, demand)
            bad = deepcopy(demand)
            bad['windows'][0]['logical_read_bytes'] = 256
            with self.assertRaisesRegex(ValueError, 'full weight bytes'):
                check_routing_union(manifest, spec, 1, bad)
            bad = deepcopy(demand)
            bad['total_resident_weight_bytes'] = 192
            with self.assertRaisesRegex(ValueError, 'Inactive experts'):
                check_routing_union(manifest, spec, 1, bad)

    def test_duplicate_cannot_hide_missing_design(self):
        plan = dict(groups=[dict(id='g0')], batch_sizes=[1], design_indices=[0, 1],
                    primary_outstanding=192, control_outstanding=128, control_groups=[])
        rows = [dict(case='g0_b1', design_index=i, window=192) for i in (0, 1)]
        check_coverage(plan, rows)
        for invalid in (rows[:1], [rows[0], rows[0]], rows + [rows[0]]):
            with self.assertRaises(ValueError):
                check_coverage(plan, invalid)

    def test_control_window_must_not_replace_primary(self):
        plan = dict(groups=[dict(id='g0')], batch_sizes=[1], design_indices=[0],
                    primary_outstanding=192, control_outstanding=128, control_groups=['g0'])
        rows = [dict(case='g0_b1', design_index=0, window=n) for n in (128, 192)]
        check_coverage(plan, rows)
        rows[1]['window'] = 256
        with self.assertRaises(ValueError):
            check_coverage(plan, rows)

    def test_unscaled_delivery_and_route_tampering(self):
        trace = read_trace(19)
        row = replay_reads(home_design(), trace, FAST)
        check_delivery(trace, row)
        bad = deepcopy(row)
        bad['audit']['delivered_words'] -= 1
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            check_delivery(trace, bad)
        bad = deepcopy(row)
        bad['routes'][0]['sent_bits'] -= 1
        with self.assertRaisesRegex(ValueError, 'conservation'):
            check_delivery(trace, bad)
        bad = deepcopy(row)
        bad['tasks'][0]['logical_bytes'] -= 32
        with self.assertRaisesRegex(ValueError, 'Task bytes'):
            check_delivery(trace, bad)


if __name__ == '__main__':
    unittest.main()
