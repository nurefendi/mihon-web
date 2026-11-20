"""Offline fixture regressions; executed only in GitHub Actions."""
import importlib.util
from pathlib import Path
import sys
import os
import subprocess
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).with_name('setup-reader-fixture.py')


class ReaderFixtureTests(unittest.TestCase):
    def test_import_has_no_io_or_bcrypt_dependency(self):
        spec = importlib.util.spec_from_file_location('reader_fixture', SCRIPT)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(sys.modules, {'bcrypt': None}), \
                mock.patch.object(Path, 'mkdir', side_effect=AssertionError('import created a directory')):
            spec.loader.exec_module(module)
        self.assertTrue(callable(module.main))

    def test_cli_uses_nested_output_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'arbitrary parent' / 'nested' / 'fixture'
            env = {k: v for k, v in os.environ.items() if not k.startswith('MIHON_FIXTURE_')}
            result = subprocess.run(
                [sys.executable, str(SCRIPT), '--output-dir', str(root)],
                env=env, text=True, capture_output=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((root / '001.cbz').is_file())
            self.assertTrue((root / 'runtime-test.env').is_file())


if __name__ == '__main__':
    unittest.main()
