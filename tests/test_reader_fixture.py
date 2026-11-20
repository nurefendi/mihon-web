"""Offline fixture regressions; executed only in GitHub Actions."""
import importlib.util
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile
import zlib

SCRIPT = Path(__file__).with_name('setup-reader-fixture.py')
CONSUMER = SCRIPT.parent.parent / 'ops' / 'reader-integration.py'


def load_fixture():
    spec = importlib.util.spec_from_file_location('reader_fixture', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReaderFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith('MIHON_FIXTURE_')}

    def run_cli(self, *args, extra_env=None, no_site=False):
        return subprocess.run(
            [sys.executable, *(['-S'] if no_site else []), str(SCRIPT), *map(str, args)],
            env={**self.env, **(extra_env or {})}, cwd=self.root,
            text=True, capture_output=True, timeout=30,
        )

    def generate(self, root=None, *args, extra_env=None):
        root = root or self.root / 'arbitrary parent' / 'nested' / 'fixture'
        result = self.run_cli('--output-dir', root, *args, extra_env=extra_env)
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = root if root.is_absolute() else self.root / root
        self.assertEqual(result.stdout.strip(), str(expected.resolve()))
        self.assertIn('never production', result.stderr.lower())
        return root

    def read_env(self, root):
        return dict(line.split('=', 1) for line in (root / 'runtime-test.env').read_text().splitlines())

    def test_import_has_no_io_or_bcrypt_dependency(self):
        with mock.patch.dict(sys.modules, {'bcrypt': None}), \
                mock.patch.object(Path, 'mkdir', side_effect=AssertionError('import mkdir')), \
                mock.patch.object(Path, 'open', side_effect=AssertionError('import open')), \
                mock.patch('tempfile.mkdtemp', side_effect=AssertionError('import tempfile')):
            module = load_fixture()
        self.assertTrue(callable(module.main))

    def test_cli_uses_nested_output_directory(self):
        root = self.generate()
        self.assertEqual(sorted(p.name for p in root.iterdir()), ['001.cbz', 'runtime-test.env'])

    def test_relative_output_directory(self):
        self.generate(Path('relative') / 'nested')
        self.assertTrue((self.root / 'relative/nested/001.cbz').is_file())

    def test_output_env_and_cli_precedence(self):
        configured = self.root / 'env directory'
        result = self.run_cli(extra_env={'MIHON_FIXTURE_DIR': str(configured)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(configured))
        self.generate(self.root / 'cli', extra_env={'MIHON_FIXTURE_DIR': str(configured)})

    def test_default_is_unique_private_temp_directory(self):
        paths = []
        for _ in range(2):
            result = self.run_cli(extra_env={'TMPDIR': str(self.root)})
            self.assertEqual(result.returncode, 0, result.stderr)
            path = Path(result.stdout.strip())
            self.assertEqual(path.parent, self.root)
            self.assertTrue(path.name.startswith('mihon-reader-fixture-'))
            self.assertEqual(path.stat().st_mode & 0o777, 0o700)
            paths.append(path)
        self.assertNotEqual(*paths)

    def test_archive_is_repeatable_with_original_pixels(self):
        root = self.generate()
        first = (root / '001.cbz').read_bytes()
        self.generate(root)
        self.assertEqual(first, (root / '001.cbz').read_bytes())
        with zipfile.ZipFile(root / '001.cbz') as archive:
            self.assertEqual(archive.namelist(), ['001.png', '002.png'])
            for name, color in [('001.png', (40, 70, 120)), ('002.png', (80, 130, 90))]:
                data = archive.read(name)
                self.assertEqual(data[:8], b'\x89PNG\r\n\x1a\n')
                self.assertEqual(struct.unpack('!2I', data[16:24]), (64, 96))
                offset, pixels = 8, b''
                while offset < len(data):
                    size = struct.unpack('!I', data[offset:offset + 4])[0]
                    if data[offset + 4:offset + 8] == b'IDAT':
                        pixels += data[offset + 8:offset + 8 + size]
                    offset += size + 12
                self.assertEqual(zlib.decompress(pixels), (b'\x00' + bytes(color) * 64) * 96)

    def test_private_modes_even_when_reusing_public_outputs(self):
        root = self.generate()
        keep = root / 'unrelated.txt'
        keep.write_text('do not delete')
        root.chmod(0o755)
        for name in ['001.cbz', 'runtime-test.env']:
            (root / name).chmod(0o644)
        self.generate(root)
        self.assertEqual(root.stat().st_mode & 0o777, 0o700)
        for name in ['001.cbz', 'runtime-test.env']:
            self.assertEqual((root / name).stat().st_mode & 0o777, 0o600)
        self.assertEqual(keep.read_text(), 'do not delete')

    def test_defaults_remain_isolated_and_password_is_bcrypt(self):
        import bcrypt
        env = self.read_env(self.generate(extra_env={
            'MYSQL_DSN': 'must-not-inherit', 'PUBLIC_ORIGIN': 'https://production.invalid',
            'ENGINE_URL': 'https://production.invalid',
        }))
        self.assertEqual(env['MYSQL_DSN'], 'mihon_test:isolated-test-only@tcp(mihon-db-test:3306)/mihon_test?parseTime=true')
        self.assertEqual(env['PUBLIC_ORIGIN'], 'http://127.0.0.1:18085')
        self.assertEqual(env['ENGINE_URL'], 'http://mihon-engine-test:4567')
        self.assertEqual(env['LISTEN_ADDR'], ':8080')
        self.assertEqual(env['BOOTSTRAP_USERNAME'], 'admin')
        self.assertTrue(bcrypt.checkpw(b'isolated-browser-integration-only', env['BOOTSTRAP_PASSWORD_HASH'].encode()))

    def test_explicit_runtime_overrides_and_cli_precedence(self):
        root = self.generate(None, '--public-origin', 'http://127.0.0.1:19085',
                             '--engine-url', 'http://engine-test:4568',
                             '--mysql-dsn', 'test:only@tcp(db-test:3307)/test',
                             '--listen-addr', ':8090', extra_env={
                                 'MIHON_FIXTURE_PUBLIC_ORIGIN': 'http://127.0.0.1:20085',
                             })
        env = self.read_env(root)
        self.assertEqual(env['PUBLIC_ORIGIN'], 'http://127.0.0.1:19085')
        self.assertEqual(env['ENGINE_URL'], 'http://engine-test:4568')
        self.assertEqual(env['MYSQL_DSN'], 'test:only@tcp(db-test:3307)/test')
        self.assertEqual(env['LISTEN_ADDR'], ':8090')

    def test_prefixed_runtime_environment_overrides(self):
        overrides = {'MYSQL_DSN': 'test:only@tcp(db-test:3307)/test',
                     'PUBLIC_ORIGIN': 'http://127.0.0.1:19085',
                     'ENGINE_URL': 'http://engine-test:4568', 'LISTEN_ADDR': ':8090'}
        root = self.generate(extra_env={'MIHON_FIXTURE_' + key: value for key, value in overrides.items()})
        env = self.read_env(root)
        for key, value in overrides.items():
            self.assertEqual(env[key], value)

    def test_rejects_env_line_injection_before_creating_output(self):
        root = self.root / 'rejected'
        result = self.run_cli('--output-dir', root, '--engine-url', 'http://engine-test\nMYSQL_DSN=bad')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(root.exists())

    def test_rejects_symlinked_outputs_without_touching_target(self):
        target = self.root / 'outside'
        target.write_text('untouched')
        root = self.root / 'fixture'
        root.mkdir()
        (root / 'runtime-test.env').symlink_to(target)
        result = self.run_cli('--output-dir', root)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(target.read_text(), 'untouched')
        link = self.root / 'linked-root'
        link.symlink_to(root, target_is_directory=True)
        result = self.run_cli('--output-dir', link)
        self.assertNotEqual(result.returncode, 0)

    def test_help_and_missing_bcrypt_do_not_create_output(self):
        result = self.run_cli('--help', no_site=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--output-dir', result.stdout)
        result = self.run_cli('--output-dir', self.root / 'not-created', no_site=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('bcrypt', result.stderr)
        self.assertFalse((self.root / 'not-created').exists())

    def test_consumer_help_needs_no_optional_dependencies(self):
        result = subprocess.run([sys.executable, '-S', str(CONSUMER), '--help'],
                                env=self.env, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--fixture-dir', result.stdout)

    def test_consumer_refuses_missing_fixture_before_network_or_db(self):
        result = subprocess.run([sys.executable, '-S', str(CONSUMER)], env=self.env,
                                text=True, capture_output=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('--fixture-dir', result.stderr)


if __name__ == '__main__':
    unittest.main()
