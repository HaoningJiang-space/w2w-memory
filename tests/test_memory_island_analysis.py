import json,tempfile,unittest
from pathlib import Path
from tools.run_memory_island_gate import case_paths


class IslandReadbackIdentity(unittest.TestCase):
    def test_same_filename_prefix_does_not_merge_workloads(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for case in ('continuous','continuous-long'):
                path=root/f'run-{case}-0-off';path.mkdir()
                (path/'worker.json').write_text(json.dumps(dict(case=case)))
            for case in ('continuous','continuous-long'):
                self.assertEqual([p.name for p in case_paths(root,case)],[f'run-{case}-0-off'])
