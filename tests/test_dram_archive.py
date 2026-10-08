"""Archived native evidence must agree with independent controller accounting."""
import gzip
from hashlib import sha256
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from w2w.validation.dram_bridge import audit

SOURCE = Path('artifacts/results/dram/command_bridge')
TRACE = Path('artifacts/results/workload/provisioning_holdout/inputs/h0_b1/trace.json')


class DRAMArchiveTests(unittest.TestCase):
    def test_frozen_pilot_readback(self):
        result = audit(SOURCE, TRACE)
        self.assertEqual(result['records'], 8)
        self.assertEqual(result['native_delivered_words'], 4 * 589968)

    def test_native_controller_under_delivery_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'archive'
            shutil.copytree(SOURCE, target)
            manifest = json.loads((target / 'manifest.json').read_text())
            item = next(i for i in manifest['results'] if i['kind'] == 'hbm2_reference')
            path = target / item['path']
            row = json.loads(gzip.decompress(path.read_bytes()))
            controller = next(c for c in row['native_backend']['stats']['controller'] if c['num_read_reqs'])
            controller['num_read_reqs_served'] -= 1
            raw = gzip.compress(json.dumps(row).encode())
            path.write_bytes(raw)
            # Updating the outer hash must not hide a native/frozen-byte mismatch.
            item['sha256'] = sha256(raw).hexdigest()
            (target / 'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'Native controller/clock'):
                audit(target, TRACE)

    def test_missing_design_cannot_claim_a_complete_pilot(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'archive'
            shutil.copytree(SOURCE, target)
            manifest = json.loads((target / 'manifest.json').read_text())
            manifest['results'].pop()
            (target / 'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'Incomplete pilot'):
                audit(target, TRACE)


if __name__ == '__main__': unittest.main()
