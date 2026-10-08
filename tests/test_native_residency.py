"""Native completion audit rejects lost returns and altered bank ownership."""
from copy import deepcopy
import gzip
import json
from pathlib import Path
import unittest

from w2w.validation.native_residency import check_native_counts


class NativeResidencyAuditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path('artifacts/results/dram/command_bridge/b_cfg_hbm2_reference.json.gz')
        cls.row = json.loads(gzip.decompress(path.read_bytes()))

    def test_archive_and_pending_return(self):
        self.assertEqual(sum(r['words'] for r in check_native_counts(self.row, 589968)), 589968)
        row = deepcopy(self.row)
        row['native_backend']['pending_words'] = 1
        with self.assertRaisesRegex(ValueError, 'pending'):
            check_native_counts(row, 589968)

    def test_bank_controller_disagreement(self):
        row = deepcopy(self.row)
        active = next(c for c in row['native_backend']['stats']['controller'] if c['num_read_reqs'])
        active['num_read_reqs_served'] -= 1
        with self.assertRaisesRegex(ValueError, 'bank/controller'):
            check_native_counts(row, 589968)


if __name__ == '__main__':
    unittest.main()
