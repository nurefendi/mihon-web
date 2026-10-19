#!/usr/bin/env python3
"""Real authenticated browser QA; uses private local generated credential.
No network/response fixtures. Screenshots contain no passwords/cookies/tokens.
"""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright

out = Path('/home/mazaya/.hermes/cache/scratch/mihon-visual')
out.mkdir(exist_ok=True)
password = Path('/home/mazaya/mihon-web-deploy/admin-password').read_text().strip()
errors = []
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage', '--host-resolver-rules=MAP mg.namiza.id 104.21.48.204'])
    context = browser.new_context(viewport={'width': 1440, 'height': 1000})
    page = context.new_page()
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.on('console', lambda msg: errors.append(msg.text) if msg.type == 'error' else None)
    page.goto('https://mg.namiza.id/login', wait_until='networkidle')
    page.screenshot(path=str(out / 'login-desktop.png'), full_page=True)
    page.locator('[name=username]').fill('admin')
    page.locator('[name=password]').fill(password)
    page.locator('button[type=submit]').click()
    page.wait_for_url('**/library')
    page.wait_for_function('window.MihonReady !== undefined')
    page.evaluate('window.MihonReady')
    page.screenshot(path=str(out / 'library-desktop.png'), full_page=True)
    assert 'Perpustakaan masih kosong' in page.locator('main').inner_text()
    assert page.locator('.nav-links a').count() == 5
    paths = ['/browse', '/updates', '/history', '/more', '/more?tab=settings', '/more?tab=categories', '/more?tab=downloads', '/more?tab=extensions']
    for path in paths:
        page.goto('https://mg.namiza.id' + path, wait_until='networkidle')
        page.evaluate('window.MihonReady')
        text = page.locator('main').inner_text()
        assert 'Tidak dapat memuat' not in text and 'jembatan gagal' not in text, path + ': ' + text[:200]
        print('PASS browser', path)
    page.set_viewport_size({'width': 390, 'height': 844})
    page.goto('https://mg.namiza.id/library', wait_until='networkidle')
    page.evaluate('window.MihonReady')
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.screenshot(path=str(out / 'library-mobile.png'), full_page=True)
    page.goto('https://mg.namiza.id/browse', wait_until='networkidle')
    page.evaluate('window.MihonReady')
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.screenshot(path=str(out / 'browse-mobile.png'), full_page=True)
    cloudflare_notices = [e for e in errors if "Loading the script 'https://static.cloudflareinsights.com/beacon.min.js/" in e and 'violates the following Content Security Policy directive' in e]
    app_errors = [e for e in errors if e not in cloudflare_notices]
    print(json.dumps({'application_errors': app_errors, 'blocked_cloudflare_analytics_count': len(cloudflare_notices), 'screenshots': str(out), 'mobile_overflow': False}))
    # Do not weaken app CSP for Cloudflare-injected analytics. This is recorded
    # separately; every other console/page error remains a hard failure.
    assert not app_errors, app_errors
    context.close()
    browser.close()
