from copy import deepcopy
import unittest

from w2w.validation.cohort_replica import compare_rows


class CohortReplicaTests(unittest.TestCase):
    def setUp(self):
        self.row = dict(makespan_slots=12, delivery_sha256='abc', tasks=[dict(words=5)],
                        wall_seconds=1., cost=dict(wire_mm=1852.2, lane_bits=8192))

    def test_only_runtime_and_tiny_cost_rounding_are_allowed(self):
        other = deepcopy(self.row)
        other['wall_seconds'] = 99.
        other['cost']['wire_mm'] += 1e-12
        self.assertIn('wire_mm', compare_rows(self.row, other))

    def test_rejects_changed_execution_and_missing_fields(self):
        for key, value in [('makespan_slots',13), ('delivery_sha256','bad'), ('tasks',[dict(words=4)])]:
            other = deepcopy(self.row); other[key] = value
            with self.assertRaises(ValueError): compare_rows(self.row, other)
        other = deepcopy(self.row); del other['tasks']
        with self.assertRaises(ValueError): compare_rows(self.row, other)

    def test_rejects_cost_changes_and_nonfinite_values(self):
        for key, value in [('lane_bits',8193), ('wire_mm',1853.), ('wire_mm',float('nan'))]:
            other = deepcopy(self.row); other['cost'][key] = value
            with self.assertRaises(ValueError): compare_rows(self.row, other)


if __name__ == '__main__': unittest.main()
