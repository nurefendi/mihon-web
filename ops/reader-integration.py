#!/usr/bin/env python3
"""Real-engine integration using an explicitly labelled CBZ in ISOLATED containers.
Requires pre-provisioned mihon-engine-test / mihon-db-test / mihon-web-integration.
Never point this at production. No mock API/seed content is added to production.
"""
from pathlib import Path
import json
import subprocess
import requests
from playwright.sync_api import sync_playwright

base = 'http://127.0.0.1:18085'
env_path = Path('/home/mazaya/.hermes/cache/scratch/mihon-fixture/runtime-test.env')
env = dict(line.split('=', 1) for line in env_path.read_text().splitlines() if '=' in line)
assert env['PUBLIC_ORIGIN'] == base and '@tcp(mihon-db-test:' in env['MYSQL_DSN']
# Integration DB was previously used by unit integration tests; reset only its
# bootstrap password to this test's independently generated hash.
hash_value = env['BOOTSTRAP_PASSWORD_HASH']
assert "'" not in hash_value
subprocess.run(['docker', 'exec', '-i', 'mihon-db-test', 'sh', '-c', 'MYSQL_PWD="$MARIADB_PASSWORD" mariadb -u "$MARIADB_USER" -D mihon_test'], input="UPDATE app_users SET password_hash='" + hash_value + "' WHERE id=1;", text=True, check=True, capture_output=True)
s = requests.Session()
s.trust_env = False
r = s.post(base + '/login', headers={'Origin': base}, data={'username': 'admin', 'password': 'isolated-browser-integration-only'}, allow_redirects=False)
assert r.status_code == 303, r.status_code
csrf = s.get(base + '/app-session').json()['csrfToken']
s.headers['X-CSRF-Token'] = csrf

def get(path):
    r = s.get(base + path, timeout=60)
    assert r.status_code == 200, (path, r.status_code, r.text[:100])
    return r

def bridge(op):
    r = s.post(base + '/api/bridge', json={'operation': op, 'variables': {}}, timeout=60)
    assert r.status_code == 200 and not r.json().get('errors'), (op, r.text[:100])
    return r.json()['data']

m = next(m for m in get('/api/v1/source/0/popular/1').json()['mangaList'] if m['title'] == '__Integration_fixture_NOT_CONTENT')
mid = m['id']
get(f'/api/v1/manga/{mid}?onlineFetch=true')
get(f'/api/v1/manga/{mid}/library')
assert get(f'/api/v1/manga/{mid}').json()['inLibrary'] is True
chapters = get(f'/api/v1/manga/{mid}/chapters?onlineFetch=true').json()
assert len(chapters) == 1, chapters
idx = chapters[0]['index']
chapter = get(f'/api/v1/manga/{mid}/chapter/{idx}').json()
assert chapter['pageCount'] == 2, chapter
for n in range(2):
    image = get(f'/api/v1/manga/{mid}/chapter/{idx}/page/{n}')
    assert image.content[:8] == b'\x89PNG\r\n\x1a\n' and image.headers['Content-Type'].startswith('image/')
r = s.patch(base + f'/api/v1/manga/{mid}/chapter/{idx}', data={'bookmarked': 'true', 'read': 'true', 'lastPageRead': '1'})
assert r.status_code == 200
chapter = get(f'/api/v1/manga/{mid}/chapter/{idx}').json()
assert chapter['bookmarked'] and chapter['read'] and chapter['lastPageRead'] == 1 and chapter['lastReadAt'] > 0
assert any(c['id'] == chapter['id'] for c in bridge('history')['chapters']['nodes'])
export = get('/api/v1/backup/export')
assert export.content[:2] == b'\x1f\x8b'
validation = s.post(base + '/api/v1/backup/validate', data=export.content, headers={'Content-Type': 'application/octet-stream'})
assert validation.status_code == 200
print('PASS real local-source CBZ → details → library → chapter images → bookmark/read/progress → global history → backup validation')

errors = []
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
    ctx = browser.new_context(viewport={'width': 390, 'height': 844})
    ctx.add_cookies([{'name': c.name, 'value': c.value, 'url': base, 'httpOnly': True, 'sameSite': 'Lax'} for c in s.cookies])
    page = ctx.new_page()
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto(base + f'/reader/{mid}/{idx}?mode=webtoon&at=0', wait_until='networkidle')
    page.evaluate('window.MihonReady')
    images = page.locator('.reader-pages img')
    assert images.count() == 2, page.locator('main').inner_text()
    page.wait_for_function("Array.from(document.querySelectorAll('.reader-pages img')).every(i=>i.complete&&i.naturalWidth>0)")
    out = Path('/home/mazaya/.hermes/cache/scratch/mihon-visual')
    out.mkdir(exist_ok=True)
    page.screenshot(path=str(out / 'reader-isolated-fixture.png'), full_page=True)
    assert not errors, errors
    ctx.close()
    browser.close()
print(json.dumps({'real_engine_reader': True, 'images_loaded': 2, 'browser_errors': errors, 'production_seeded': False}))
