from pathlib import Path
import struct, zlib, zipfile, os, bcrypt
root = Path('/home/mazaya/.hermes/cache/scratch/mihon-fixture')
root.mkdir(exist_ok=True)
def png(r, g, b):
    def chunk(t, data):
        return struct.pack('!I', len(data)) + t + data + struct.pack('!I', zlib.crc32(t + data) & 0xffffffff)
    raw = b''.join(b'\x00' + bytes([r, g, b]) * 64 for _ in range(96))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', 64, 96, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')
with zipfile.ZipFile(root / '001.cbz', 'w') as z:
    z.writestr('001.png', png(40, 70, 120))
    z.writestr('002.png', png(80, 130, 90))
env = '\n'.join([
    'MYSQL_DSN=mihon_test:isolated-test-only@tcp(mihon-db-test:3306)/mihon_test?parseTime=true',
    'PUBLIC_ORIGIN=http://127.0.0.1:18085',
    'ENGINE_URL=http://mihon-engine-test:4567',
    'BOOTSTRAP_USERNAME=admin',
    'BOOTSTRAP_PASSWORD_HASH=' + bcrypt.hashpw(b'isolated-browser-integration-only', bcrypt.gensalt()).decode(),
    'LISTEN_ADDR=:8080', '',
])
(root / 'runtime-test.env').write_text(env)
os.chmod(root / 'runtime-test.env', 0o600)
print('Created labelled two-page test CBZ and isolated runtime config; never production data.')
