#!/usr/bin/env python3
"""Live public search regression; no fixture/response interception."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright
password = Path('/home/mazaya/mihon-web-deploy/admin-password').read_text().strip()
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage', '--host-resolver-rules=MAP mg.namiza.id 104.21.48.204'])
    context = browser.new_context(viewport={'width': 390, 'height': 844})
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto('https://mg.namiza.id/login', wait_until='networkidle')
    page.locator('[name=username]').fill('admin')
    page.locator('[name=password]').fill(password)
    page.locator('button[type=submit]').click()
    page.wait_for_url('**/library')
    page.goto('https://mg.namiza.id/browse?source=4838485846640015979', wait_until='networkidle')
    page.evaluate('window.MihonReady')
    assert page.locator('[name=mode]').input_value() == 'popular'
    page.locator('[name=q]').fill('one piece')
    with page.expect_response(lambda r: '/api/v1/source/4838485846640015979/search?' in r.url) as found:
        page.get_by_role('button', name='Tampilkan', exact=True).click()
    response = found.value
    page.wait_for_load_state('networkidle')
    page.evaluate('window.MihonReady')
    data = response.json()
    assert response.status == 200 and len(data.get('mangaList', [])) > 0
    assert 'One Piece' in page.locator('main').inner_text()
    assert page.locator('[name=mode]').input_value() == 'search'
    assert not errors, errors
    print(json.dumps({'public_ui_search': 'passed', 'source': 'Komiku', 'query': 'one piece', 'mode_before': 'popular', 'mode_after': 'search', 'results': len(data['mangaList']), 'page_errors': errors}))
    context.close()
    browser.close()
