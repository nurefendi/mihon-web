#!/usr/bin/env python3
"""Operator-only approval of exact repository URLs (no automatic installation).
The publisher and recursive metadata/APK code become trusted engine authority.
Usage: python3 ops/approve-repository.py --trust-publisher HTTPS_INDEX_URL [...]
"""
import argparse
import os
from pathlib import Path
from urllib.parse import urlsplit
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--trust-publisher', action='store_true', required=True)
p.add_argument('urls', nargs='+')
a = p.parse_args()
path = Path('/home/mazaya/mihon-web-deploy/runtime.env')
lines = path.read_text().splitlines()
existing = []
for line in lines:
    if line.startswith('TRUSTED_REPOSITORY_URLS='):
        existing.extend(filter(None, line.split('=', 1)[1].split(',')))
for raw in a.urls:
    u = urlsplit(raw)
    if u.scheme != 'https' or not u.hostname or u.username or u.password or u.query or u.fragment or not u.path or ',' in raw or '\n' in raw or len(raw) > 2048:
        p.error('Expected an exact HTTPS index URL without credentials/query/fragment')
    if raw not in existing:
        existing.append(raw)
lines = [line for line in lines if not line.startswith('TRUSTED_REPOSITORY_URLS=')]
lines.append('TRUSTED_REPOSITORY_URLS=' + ','.join(existing))
tmp = path.with_suffix('.new')
fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, 'w') as f:
    f.write('\n'.join(lines) + '\n')
os.chmod(tmp, 0o600)
os.replace(tmp, path)
print('Exact repository approvals saved. No repository or extension was installed. Recreate only the web service to load them.')
