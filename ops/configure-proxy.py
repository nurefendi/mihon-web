#!/usr/bin/env python3
"""Pin the actual NPM peer for the app's trusted forwarding boundary.
Preserves all private credentials and an existing explicit repository allowlist.
Does not deploy automatically; run compose after reviewing proxy config.
"""
import ipaddress
import json
import os
from pathlib import Path
import subprocess

root = Path('/home/mazaya/mihon-web-deploy')
p = root / 'runtime.env'
raw = p.read_text()
info = json.loads(subprocess.check_output(['docker', 'inspect', 'nginx-proxy-manager-app-1']))[0]
peer = ipaddress.ip_address(info['NetworkSettings']['Networks']['npm-net']['IPAddress'])
value = str(peer) + ('/32' if peer.version == 4 else '/128')
lines = [line for line in raw.splitlines() if not line.startswith('TRUSTED_PROXY_CIDRS=')]
lines.append('TRUSTED_PROXY_CIDRS=' + value)
if not any(line.startswith('TRUSTED_REPOSITORY_URLS=') for line in lines):
    lines.append('TRUSTED_REPOSITORY_URLS=')
tmp = root / 'runtime.env.new'
fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, 'w') as f:
    f.write('\n'.join(lines) + '\n')
os.chmod(tmp, 0o600)
os.replace(tmp, p)
print('Trusted proxy peer configured:', value, '; credentials and repository choices not displayed.')
