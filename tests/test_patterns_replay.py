from copy import deepcopy
import unittest

from tests.test_read_workload import FAST, home_design, read_trace
from w2w.analysis.patterns_replay import check_coverage, check_delivery
from w2w.service.read_replay import replay_reads


class ReplayArchiveTests(unittest.TestCase):
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
