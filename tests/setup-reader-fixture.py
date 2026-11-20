#!/usr/bin/env python3
"""Generate a private, portable two-page fixture. Never production data/config."""
import argparse
import io
import os
from pathlib import Path
import struct
import sys
import tempfile
import zipfile
import zlib

DEFAULT_RUNTIME = {
    'MYSQL_DSN': 'mihon_test:isolated-test-only@tcp(mihon-db-test:3306)/mihon_test?parseTime=true',
    'PUBLIC_ORIGIN': 'http://127.0.0.1:18085',
    'ENGINE_URL': 'http://mihon-engine-test:4567',
    'LISTEN_ADDR': ':8080',
}


def png(r, g, b):
    def chunk(t, data):
        return struct.pack('!I', len(data)) + t + data + struct.pack('!I', zlib.crc32(t + data) & 0xffffffff)
    raw = b''.join(b'\x00' + bytes([r, g, b]) * 64 for _ in range(96))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', 64, 96, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')


def write_private(path, data):
    """Replace only our named output, private from creation (not chmod later)."""
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(data)
        os.replace(temporary, path)
    finally:
        # Only our own temporary file, never caller directories or other data.
        if os.path.exists(temporary):
            os.unlink(temporary)


def generate_fixture(output_dir, runtime):
    # Import/hash before creating anything; --help and import need only stdlib.
    import bcrypt
    password_hash = bcrypt.hashpw(b'isolated-browser-integration-only', bcrypt.gensalt()).decode()
    root = (Path(output_dir).expanduser().absolute() if output_dir else
            Path(tempfile.mkdtemp(prefix='mihon-reader-fixture-')))
    if root.is_symlink():
        raise ValueError('fixture directory must not be a symlink')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name in ('001.cbz', 'runtime-test.env'):
        if (root / name).is_symlink():
            raise ValueError(f'fixture output must not be a symlink: {name}')
    root.chmod(0o700)

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as cbz:
        for name, color in [('001.png', (40, 70, 120)), ('002.png', (80, 130, 90))]:
            # Fixed ZIP metadata makes the complete archive repeatable.
            cbz.writestr(zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)), png(*color))
    env = dict(runtime, BOOTSTRAP_USERNAME='admin', BOOTSTRAP_PASSWORD_HASH=password_hash)
    write_private(root / '001.cbz', archive.getvalue())
    write_private(root / 'runtime-test.env', ''.join(f'{key}={value}\n' for key, value in env.items()).encode())
    return root


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', default=os.environ.get('MIHON_FIXTURE_DIR'),
                        help='Fixture directory (MIHON_FIXTURE_DIR); default: unique private tempfile directory')
    for key, default in DEFAULT_RUNTIME.items():
        parser.add_argument('--' + key.lower().replace('_', '-'),
                            default=os.environ.get('MIHON_FIXTURE_' + key, default),
                            help=f'Isolated test override (MIHON_FIXTURE_{key}); default: {default}')
    args = parser.parse_args(argv)
    runtime = {key: getattr(args, key.lower()) for key in DEFAULT_RUNTIME}
    for key, value in runtime.items():
        if not value or any(char in value for char in '\r\n\x00'):
            parser.error(f'{key} must be a nonempty single-line value without NUL')
    if args.output_dir is not None and not args.output_dir.strip():
        parser.error('--output-dir / MIHON_FIXTURE_DIR must not be empty')
    try:
        root = generate_fixture(args.output_dir, runtime)
    except ImportError:
        parser.error('bcrypt is required to generate fixtures; install it in your isolated test virtualenv')
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print('Created labelled two-page test CBZ and isolated runtime config; never production data or credentials.',
          file=sys.stderr)
    print(root)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
