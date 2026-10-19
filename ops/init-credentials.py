#!/usr/bin/env python3
"""Generate a one-time private admin credential file; never print secrets."""
import os
from pathlib import Path
import secrets
import bcrypt
root = Path('/home/mazaya/mihon-web-deploy')
root.mkdir(mode=0o700, exist_ok=True)
root.chmod(0o700)
values = dict(line.split('=', 1) for line in (root / 'database.env').read_text().splitlines() if '=' in line)
if (root / 'runtime.env').exists():
    print('Existing runtime credentials preserved; no password rotation.')
else:
    password = secrets.token_urlsafe(24)
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()
    content = '\n'.join([
        f'MYSQL_DSN={values["MYSQL_DSN"]}',
        'PUBLIC_ORIGIN=https://mg.namiza.id',
        'ENGINE_URL=http://mihon-engine:4567',
        'BOOTSTRAP_USERNAME=admin',
        f'BOOTSTRAP_PASSWORD_HASH={hashed}',
        'LISTEN_ADDR=:8080', '',
    ])
    for name, text in [('runtime.env', content), ('admin-password', password + '\n')]:
        fd = os.open(root / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as f:
            f.write(text)
    print('Generated runtime.env and admin-password, mode 0600. Values not displayed.')
