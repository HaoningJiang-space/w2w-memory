"""Regression checks for the package migration, paths and archived evidence."""
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from w2w.commands import COMMANDS
from w2w.paths import REPO_ROOT


class RepositoryLayoutTests(unittest.TestCase):
    def test_dispatched_process_pool_can_serialize_workers(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, 'pool_probe.py').write_text(
                'from concurrent.futures import ProcessPoolExecutor\n'
                'import multiprocessing\n'
                'def square(value): return value * value\n'
                'if __name__ == "__main__":\n'
                '    for method in ("fork", "spawn"):\n'
                '        with ProcessPoolExecutor(1, mp_context=multiprocessing.get_context(method)) as pool:\n'
                '            print(method, pool.submit(square, 7).result())\n')
            launcher = ('import sys; sys.path.insert(0, sys.argv[1]); '
                        'from w2w.commands import COMMANDS; from w2w.__main__ import main; '
                        'COMMANDS["pool_probe"] = "pool_probe"; main(["pool_probe"])')
            result = subprocess.run([sys.executable, '-c', launcher, folder], cwd=REPO_ROOT,
                                    capture_output=True, text=True, check=True, timeout=30)
            self.assertEqual(result.stdout.splitlines(), ['fork 49', 'spawn 49'])

    def test_moved_result_bytes_are_unchanged(self):
        manifest=json.loads((REPO_ROOT/'artifacts/provenance/layout_migration.json').read_text())
        for path,digest in manifest['result_sha256'].items():
            with self.subTest(path=path):
                self.assertEqual(hashlib.sha256((REPO_ROOT/path).read_bytes()).hexdigest(),digest)

    def test_registered_commands_import_without_running(self):
        # Previously render_endpoint_bridge executed and overwrote figures on import.
        # All public commands must now be import-safe.
        paths=list((REPO_ROOT/'artifacts').rglob('*'))
        before={p:(p.stat().st_size,p.stat().st_mtime_ns) for p in paths if p.is_file()}
        for module in COMMANDS.values():importlib.import_module(module)
        after={p:(p.stat().st_size,p.stat().st_mtime_ns) for p in (REPO_ROOT/'artifacts').rglob('*') if p.is_file()}
        self.assertEqual(before,after)

    def test_dispatch_and_module_entrypoints(self):
        for command in ([sys.executable,'-m','w2w','run_endpoint_bridge','--help'],
                        [sys.executable,'-m','w2w','run_endpoint_bridge.py','--help'],
                        [sys.executable,'-m','w2w.experiments.run_endpoint_bridge','--help']):
            result=subprocess.run(command,cwd=REPO_ROOT,capture_output=True,text=True,check=True)
            self.assertIn('--output',result.stdout)
            self.assertIn('--slots',result.stdout)
        result=subprocess.run([sys.executable,'-m','w2w','unknown'],cwd=REPO_ROOT,capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)


if __name__=='__main__':unittest.main()
