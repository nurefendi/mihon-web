#!/usr/bin/env python3
"""Authenticated real-reader mobile QA, without changing the user's progress.
Uses actual HTTP responses; no manga/API fixtures or response substitution.
All browser API mutations are aborted. Only a temporary login/session is created.
Credentials stay in a private local file and are never printed or typed into a page.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urlparse
import requests
from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument('--base', default='https://mg.namiza.id')
parser.add_argument('--out', default='/home/mazaya/.hermes/cache/scratch/mihon-reader-scroll')
a = parser.parse_args()
base = a.base.rstrip('/')
parsed = urlparse(base)
if base not in ['https://mg.namiza.id', 'http://127.0.0.1:18086', 'http://127.0.0.1:8084']:
    raise SystemExit('Refusing to send a private credential outside the explicit app targets')
origin = 'https://mg.namiza.id'
out = Path(a.out)
out.mkdir(parents=True, exist_ok=True)
s = requests.Session()
s.trust_env = False
login = s.post(base + '/login', headers={'Origin': origin}, data={'username': 'admin', 'password': Path('/home/mazaya/mihon-web-deploy/admin-password').read_text().strip()}, timeout=30, allow_redirects=False)
assert login.status_code == 303, 'Real administrator login failed; credential not printed'
cookie = login.cookies.get('mihon_session')
assert cookie
if parsed.scheme == 'http':
    s.headers['Cookie'] = 'mihon_session=' + cookie
session_response = s.get(base + '/app-session', timeout=30)
session_response.raise_for_status()
csrf = session_response.json()['csrfToken']

def snapshot():
    response = s.get(base + '/api/v1/manga/143/chapter/10', timeout=30)
    response.raise_for_status()
    row = response.json()
    return {key: row[key] for key in ['lastPageRead', 'lastReadAt', 'read', 'bookmarked', 'pageCount']}

before = snapshot()
report = {'base': base, 'chapter': '/reader/143/10', 'screens': [], 'blocked_mutations': 0, 'page_errors': []}
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
        for width, height in [(390, 844), (360, 800)]:
            ctx = browser.new_context(viewport={'width': width, 'height': height}, is_mobile=True, has_touch=True)
            ctx.add_cookies([{'name': 'mihon_session', 'value': cookie, 'url': base, 'httpOnly': True, 'secure': parsed.scheme == 'https', 'sameSite': 'Lax'}])
            page = ctx.new_page()
            page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
            def guard(route):
                if route.request.method not in ['GET', 'HEAD']:
                    report['blocked_mutations'] += 1
                    route.abort()
                else:
                    route.continue_()
            page.route('**/api/**', guard)
            cdp = ctx.new_cdp_session(page)
            cdp.send('Network.enable')
            cdp.send('Network.emulateNetworkConditions', {'offline': False, 'latency': 180, 'downloadThroughput': 400000, 'uploadThroughput': 200000, 'connectionType': 'cellular3g'})
            page.goto(base + '/reader/143/10?mode=webtoon&at=0', wait_until='domcontentloaded', timeout=60000)
            page.wait_for_function('() => window.MihonReady !== undefined')
            page.evaluate('window.MihonReady')
            page.wait_for_selector('.reader-page.loaded:not([hidden])', timeout=60000)
            # A real source can begin with a short landscape credit image. Wait
            # for actual scrollable content instead of swiping an empty viewport.
            page.wait_for_function('() => document.documentElement.scrollHeight > innerHeight + 500', timeout=90000)
            page.evaluate("window.scrollTrace=[];addEventListener('scroll',()=>scrollTrace.push({y:scrollY,t:performance.now()}),{passive:true});")
            for _ in range(14):
                cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': width // 2, 'y': height - 160}]})
                for step in range(1, 9):
                    cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': width // 2, 'y': height - 160 - step * 45}]})
                    page.wait_for_timeout(20)
                cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
                page.wait_for_timeout(350)
            page.wait_for_timeout(2500)
            trace = page.evaluate('window.scrollTrace')
            backwards = [round(trace[i]['y'] - trace[i - 1]['y'], 2) for i in range(1, len(trace)) if trace[i]['y'] < trace[i - 1]['y'] - 8]
            metrics = page.evaluate("({loaded:document.querySelectorAll('.reader-page.loaded:not([hidden])').length,failed:document.querySelectorAll('.reader-page.image-error:not([hidden])').length,overflow:document.documentElement.scrollWidth>innerWidth,y:scrollY})")
            if len(trace) <= 3 or max((x['y'] for x in trace), default=0) <= 100:
                page.screenshot(path=str(out / ('failure-' + str(width) + '.png')))
                diagnostic = page.evaluate("({scrollHeight:document.documentElement.scrollHeight,innerHeight,innerWidth,visualScale:visualViewport.scale,images:[...document.querySelectorAll('.reader-page')].map(i=>({page:i.dataset.page,hidden:i.hidden,loaded:i.classList.contains('loaded'),error:i.classList.contains('image-error'),w:i.naturalWidth,h:i.naturalHeight,rect:i.getBoundingClientRect().height})),tail:document.querySelector('.reader-loading')?.textContent})")
                print(json.dumps({'failed_scroll_diagnostic': diagnostic, 'metrics': metrics, 'scroll_events': len(trace)}))
            assert len(trace) > 3 and max(x['y'] for x in trace) > 100, 'No meaningful native touch scrolling occurred'
            assert not backwards, 'Downward-only gestures jumped backward: ' + str(backwards)
            assert not metrics['overflow'], 'Reader overflows horizontally'
            page.screenshot(path=str(out / ('reader-' + str(width) + '.png')))
            (out / ('trace-' + str(width) + '.json')).write_text(json.dumps(trace))
            report['screens'].append({'width': width, 'height': height, 'scroll_events': len(trace), 'backward_jumps': backwards, **metrics})
            # Resize like an expanding/collapsing browser viewport, then continue
            # scrolling; existing images must retain exactly the same dimensions.
            dimensions = page.evaluate("[...document.querySelectorAll('.reader-page.loaded:not([hidden])')].map(i=>i.getBoundingClientRect().height)")
            page.set_viewport_size({'width': width, 'height': height - 100})
            page.wait_for_timeout(250)
            after_resize = page.evaluate("[...document.querySelectorAll('.reader-page.loaded:not([hidden])')].map(i=>i.getBoundingClientRect().height)")
            assert dimensions == after_resize[:len(dimensions)], 'Viewport height changed previously rendered image sizes'
            ctx.close()
        # Exercise the exact URL and its real server-saved resume point too.
        ctx = browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
        ctx.add_cookies([{'name': 'mihon_session', 'value': cookie, 'url': base, 'httpOnly': True, 'secure': parsed.scheme == 'https', 'sameSite': 'Lax'}])
        page = ctx.new_page()
        page.route('**/api/**', guard)
        page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
        page.goto(base + '/reader/143/10', wait_until='domcontentloaded', timeout=60000)
        page.wait_for_function('() => window.MihonReady !== undefined')
        page.evaluate('window.MihonReady')
        mode = page.locator('.reader-shell').get_attribute('data-reader-mode')
        if mode == 'webtoon':
            page.wait_for_selector('.reader-page[data-page="' + str(before['lastPageRead']) + '"].loaded:not([hidden])', timeout=240000)
        else:
            page.wait_for_selector('.reader-page.loaded', timeout=60000)
        page.wait_for_timeout(500)
        target = page.locator('.reader-page[data-page="' + str(before['lastPageRead']) + '"]')
        assert target.is_visible(), 'The saved page was not actually revealed'
        rect = target.bounding_box()
        assert rect['y'] < page.viewport_size['height'] and rect['y'] + rect['height'] > 0, 'The saved page did not intersect the resumed viewport'
        report['exact_route_mode'] = mode
        report['exact_route_resumed_page'] = int(target.get_attribute('data-page')) + 1
        report['exact_route_saved_page_in_viewport'] = True
        report['exact_route_failed_images'] = page.locator('.reader-page.image-error').count()
        ctx.close()
        browser.close()
    report['progress_unchanged'] = snapshot() == before
    assert report['progress_unchanged'], 'Progress changed concurrently; this test never restores or overwrites user data'
    assert not report['page_errors'], report['page_errors']
    (out / 'report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
finally:
    logout = s.post(base + '/logout', headers={'Origin': origin, 'X-CSRF-Token': csrf}, timeout=30, allow_redirects=False)
    assert logout.status_code == 303
    assert s.get(base + '/app-session', timeout=30, allow_redirects=False).status_code in [401, 303]
    s.close()
