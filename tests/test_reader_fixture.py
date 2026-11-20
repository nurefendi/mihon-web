"""Offline fixture regressions; executed only in GitHub Actions."""
import importlib.util
from pathlib import Path
import sys
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


if __name__ == '__main__':
    unittest.main()
