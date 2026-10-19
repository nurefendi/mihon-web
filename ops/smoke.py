#!/usr/bin/env python3
"""Bounded authenticated smoke; private generated credentials never printed.
Creates then removes one explicitly labelled empty category; restores preferences.
Requires requests. --resolve bypasses only DNS, not TLS verification.
"""
import argparse
import json
from pathlib import Path
import secrets
import socket
from urllib.parse import urlparse
import requests

p = argparse.ArgumentParser()
p.add_argument('--base', default='https://mg.namiza.id')
p.add_argument('--origin', default='https://mg.namiza.id')
p.add_argument('--password-file', default='/home/mazaya/mihon-web-deploy/admin-password')
p.add_argument('--resolve')
a = p.parse_args()
base = a.base.rstrip('/')
host = urlparse(base).hostname
if a.resolve:
    original = socket.getaddrinfo
    socket.getaddrinfo = lambda h, port, *args, **kw: original(a.resolve if h == host else h, port, *args, **kw)
s = requests.Session()
s.trust_env = False
results = []

def check(label, condition):
    if not condition:
        raise AssertionError(label)
    results.append(label)
    print('PASS', label)

def req(method, path, **kw):
    return s.request(method, base + path, timeout=60, allow_redirects=False, **kw)

check('health database and engine', req('GET', '/healthz').json() == {'database': True, 'engine': True, 'ok': True})
check('anonymous API denied', req('GET', '/api/v1/source/list').status_code == 401)
check('login available', req('GET', '/login').status_code == 200)
check('foreign login Origin denied', req('POST', '/login', headers={'Origin': 'https://attacker.invalid'}, data={'username': 'admin', 'password': 'not-a-secret-test'}).status_code == 403)
r = req('POST', '/login', headers={'Origin': a.origin}, data={'username': 'admin', 'password': Path(a.password_file).read_text().strip()})
check('administrator login', r.status_code == 303 and r.headers.get('Location') == '/library')
cookie = r.cookies.get('mihon_session')
check('secure session cookie attributes', cookie is not None and all(x in r.headers.get('Set-Cookie', '') for x in ['HttpOnly', 'SameSite=Lax', 'Secure']))
# Local loopback candidate tests must explicitly replay this Secure cookie;
# production browsers only receive it over verified HTTPS.
if base.startswith('http://'):
    s.headers['Cookie'] = 'mihon_session=' + cookie
session = req('GET', '/app-session').json()
check('authenticated session identity', session.get('username') == 'admin' and len(session.get('csrfToken', '')) == 64)
csrf = {'X-CSRF-Token': session['csrfToken']}
check('missing CSRF denies preferences mutation', req('PUT', '/api/preferences', json={'theme': 'dark', 'readerMode': 'webtoon', 'gridColumns': 3}).status_code == 403)
check('legacy mutating GET requires CSRF', req('GET', '/api/v1/downloads/clear').status_code == 403)
check('engine configuration inaccessible', req('GET', '/api/v1/settings/about').status_code == 403)
check('arbitrary GraphQL inaccessible', req('POST', '/api/bridge', headers=csrf, json={'query': '{settings{authPassword}}'}).status_code == 400)
prefs = req('GET', '/api/preferences').json()
category_id = None
try:
    changed = {'theme': 'dark' if prefs['theme'] != 'dark' else 'light', 'readerMode': 'rtl', 'gridColumns': 3}
    check('preferences write', req('PUT', '/api/preferences', headers=csrf, json=changed).status_code == 200)
    check('preferences readback', req('GET', '/api/preferences').json() == changed)
    for op, key in [('library', 'mangas'), ('history', 'chapters'), ('downloads', 'downloadStatus'), ('repositories', 'extensionStores')]:
        r = req('POST', '/api/bridge', headers=csrf, json={'operation': op, 'variables': {}})
        data = r.json()
        check('engine bridge ' + op, r.status_code == 200 and not data.get('errors') and key in data.get('data', {}))
    sources = req('GET', '/api/v1/source/list').json()
    check('real source response', isinstance(sources, list) and any(x['id'] == '0' for x in sources))
    check('local popular response', req('GET', '/api/v1/source/0/popular/1').status_code == 200)
    label = '__smoke_no_manga_' + secrets.token_hex(5)
    check('category create', req('POST', '/api/v1/category', headers=csrf, data={'name': label}).status_code == 200)
    rows = req('GET', '/api/v1/category').json()
    found = [row for row in rows if row['name'] == label]
    check('category create readback', len(found) == 1)
    category_id = found[0]['id']
    check('category rename', req('PATCH', '/api/v1/category/' + str(category_id), headers=csrf, data={'name': label + '_renamed'}).status_code == 200)
    rows = req('GET', '/api/v1/category').json()
    check('category rename readback', any(row['id'] == category_id and row['name'] == label + '_renamed' for row in rows))
    exported = req('GET', '/api/v1/backup/export')
    check('backup export real gzip', exported.status_code == 200 and exported.content[:2] == b'\x1f\x8b')
    validated = req('POST', '/api/v1/backup/validate', headers={**csrf, 'Content-Type': 'application/octet-stream'}, data=exported.content)
    check('backup validation', validated.status_code == 200 and isinstance(validated.json().get('missingSources'), list))
finally:
    r = req('PUT', '/api/preferences', headers=csrf, json=prefs)
    check('preferences restored and verified', r.status_code == 200 and req('GET', '/api/preferences').json() == prefs)
    if category_id is not None:
        r = req('DELETE', '/api/v1/category/' + str(category_id), headers=csrf)
        check('temporary category removed and verified', r.status_code == 200 and not any(row['id'] == category_id for row in req('GET', '/api/v1/category').json()))
check('logout', req('POST', '/logout', headers=csrf).status_code == 303)
check('session revoked', req('GET', '/app-session').status_code == 401)
print(json.dumps({'passed': len(results), 'base': base, 'fixtures_left': False}))
