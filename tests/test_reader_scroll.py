"""Mobile webtoon scroll regressions using labelled, deterministic HTTP fixtures.
No real manga, production credentials, or production API responses are used here.
Run with a Python environment containing playwright (Chromium installed).
"""
import json
from pathlib import Path
import re
import struct
import threading
import time
from urllib.parse import parse_qs
import unittest
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from playwright.sync_api import sync_playwright

WEB = Path(__file__).resolve().parents[1] / 'web'

def png(width, height, shade):
    def chunk(tag, data):
        return struct.pack('!I', len(data)) + tag + data + struct.pack('!I', zlib.crc32(tag + data) & 0xffffffff)
    row = b'\x00' + bytes([shade, 90, 130]) * width
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', width, height, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(row * height)) + chunk(b'IEND', b'')

IMAGES = [png(400, h, 50 + i * 10) for i, h in enumerate([180, 250, 160, 1400, 170, 240, 190, 210])]

class Handler(BaseHTTPRequestHandler):
    last_read = 0
    updates = []
    def log_message(self, *args):
        pass
    def send(self, body, kind='application/json'):
        self.send_response(200)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass
    def do_GET(self):
        path = self.path.split('?', 1)[0]
        if path == '/app-session':
            return self.send(json.dumps({'username': 'fixture-user', 'csrfToken': 'fixture-only'}).encode())
        if path == '/api/preferences':
            return self.send(json.dumps({'theme': 'dark', 'readerMode': 'webtoon', 'gridColumns': 3}).encode())
        if path == '/api/v1/manga/143':
            return self.send(json.dumps({'id': 143, 'title': 'SCROLL TEST FIXTURE — NOT MANGA'}).encode())
        chapter = {'id': 1261, 'index': 10, 'name': 'Delayed technical images', 'pageCount': len(IMAGES), 'lastPageRead': Handler.last_read, 'read': False}
        if path == '/api/v1/manga/143/chapters':
            return self.send(json.dumps([chapter]).encode())
        if path == '/api/v1/manga/143/chapter/10':
            return self.send(json.dumps(chapter).encode())
        match = re.fullmatch('/api/v1/manga/143/chapter/10/page/(\\d+)', path)
        if match:
            i = int(match[1])
            if self.headers.get('X-Fixture-Slow-Page') == str(i):
                time.sleep(12)
            elif i > 0:
                time.sleep(2.8 + (i % 3) * .15)
            return self.send(IMAGES[i], 'image/png')
        name = path.lstrip('/')
        if path.startswith('/reader/'):
            name = 'index.html'
        asset = WEB / name
        if name in ['index.html', 'app.css', 'app.js', 'views.js', 'boot.js', 'favicon.svg'] and asset.is_file():
            kind = 'text/css' if name.endswith('.css') else 'application/javascript' if name.endswith('.js') else 'image/svg+xml' if name.endswith('.svg') else 'text/html'
            return self.send(asset.read_bytes(), kind)
        self.send_error(404)
    def do_PATCH(self):
        # Explicit fixture persistence only; the production API is never involved.
        size = int(self.headers.get('Content-Length', 0))
        form = parse_qs(self.rfile.read(size).decode())
        Handler.last_read = int(form['lastPageRead'][0])
        Handler.updates.append(Handler.last_read)
        self.send(b'')

class ReaderScrollTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = 'http://127.0.0.1:' + str(cls.server.server_port)
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.server.shutdown()
        cls.server.server_close()
    def setUp(self):
        Handler.last_read = 0
        Handler.updates = []
    def test_loading_images_does_not_reverse_downward_scroll(self):
        self.check_downward_scroll('wheel')
    def test_native_touch_swipes_do_not_reverse_when_images_load(self):
        self.check_downward_scroll('touch')
    def check_downward_scroll(self, source):
        ctx = self.browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
        page = ctx.new_page()
        page.goto(self.base + '/reader/143/10?mode=webtoon&at=0', wait_until='domcontentloaded')
        page.evaluate('window.MihonReady')
        page.wait_for_selector('.reader-page.loaded')
        page.evaluate("window.scrollTrace=[];addEventListener('scroll',()=>scrollTrace.push({y:scrollY,t:performance.now()}),{passive:true});")
        cdp = ctx.new_cdp_session(page) if source == 'touch' else None
        for _ in range(20):
            if cdp:
                cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': 195, 'y': 650}]})
                for step in range(1, 9):
                    cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': 195, 'y': 650 - step * 45}]})
                    page.wait_for_timeout(20)
                cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})
            else:
                page.mouse.wheel(0, 360)
            page.wait_for_timeout(260)
        page.wait_for_timeout(4000)
        page.wait_for_selector('.reader-page[data-page="7"]:not([hidden]).loaded', timeout=20000)
        self.assertEqual(page.locator('.reader-page:not([hidden])').count(), len(IMAGES))
        trace = page.evaluate('window.scrollTrace')
        # Loaded images retain their natural ratio and touch edge-to-edge: no
        # permanent 70vh gap is allowed as a workaround for the scroll regression.
        sizes = page.evaluate("[...document.querySelectorAll('.reader-page.loaded:not([hidden])')].map(i=>({top:i.offsetTop,height:i.getBoundingClientRect().height,width:i.getBoundingClientRect().width,w:i.naturalWidth,h:i.naturalHeight}))")
        for i, size in enumerate(sizes):
            self.assertAlmostEqual(size['height'], size['width'] * size['h'] / size['w'], delta=1)
            if i:
                self.assertAlmostEqual(size['top'], sizes[i - 1]['top'] + sizes[i - 1]['height'], delta=1)
        backwards = [round(trace[i]['y'] - trace[i - 1]['y'], 2) for i in range(1, len(trace)) if trace[i]['y'] < trace[i - 1]['y'] - 8]
        ctx.close()
        self.assertGreater(len(trace), 3, 'The test must exercise actual scrolling')
        self.assertGreater(max(x['y'] for x in trace), 100)
        self.assertEqual(backwards, [], 'Only downward input was issued, but delayed images moved scroll upward: ' + str(backwards))
    def test_user_gesture_cancels_pending_resume(self):
        ctx = self.browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
        page = ctx.new_page()
        # Delay animation callbacks so a gesture can arrive before auto-resume.
        page.add_init_script("window.__scrollCalls=[];Element.prototype.scrollIntoView=function(){__scrollCalls.push(this.dataset.page)};window.requestAnimationFrame=fn=>setTimeout(()=>fn(performance.now()),500);")
        page.goto(self.base + '/reader/143/10?mode=webtoon&at=5', wait_until='domcontentloaded')
        page.evaluate('window.MihonReady')
        page.evaluate("document.dispatchEvent(new Event('touchstart',{bubbles:true}));")
        page.wait_for_timeout(7000)
        calls = page.evaluate('window.__scrollCalls')
        ctx.close()
        self.assertEqual(calls, [], 'Auto-resume must not override a reader who already started interacting')
    def test_resume_waits_for_preceding_sizes_and_only_runs_once(self):
        ctx = self.browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
        page = ctx.new_page()
        page.add_init_script("window.__resumes=[];const original=Element.prototype.scrollIntoView;Element.prototype.scrollIntoView=function(opts){__resumes.push({page:this.dataset.page,ready:[...document.querySelectorAll('.reader-page')].slice(0,Number(this.dataset.page)+1).every(i=>!i.hidden&&i.naturalWidth>0)});original.call(this,opts)};")
        page.goto(self.base + '/reader/143/10?mode=webtoon&at=5', wait_until='domcontentloaded')
        page.evaluate('window.MihonReady')
        page.wait_for_timeout(1000)
        self.assertEqual(page.evaluate('window.__resumes'), [])
        self.assertEqual(Handler.updates, [], 'Do not overwrite saved progress while restoring the viewport')
        page.wait_for_function('window.__resumes.length > 0', timeout=20000)
        page.wait_for_timeout(1000)
        resumes = page.evaluate('window.__resumes')
        ctx.close()
        self.assertEqual(resumes, [{'page': '5', 'ready': True}])
    def test_exit_before_resume_does_not_save_an_unseen_loaded_page(self):
        ctx = self.browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, extra_http_headers={'X-Fixture-Slow-Page': '0'})
        page = ctx.new_page()
        page.goto(self.base + '/reader/143/10?mode=webtoon&at=5', wait_until='domcontentloaded')
        page.evaluate('window.MihonReady')
        page.wait_for_function("document.querySelector('.reader-page[data-page=\"5\"]').classList.contains('loaded')", timeout=20000)
        self.assertTrue(page.locator('.reader-page[data-page="5"]').is_hidden())
        page.evaluate("window.dispatchEvent(new Event('pagehide'))")
        page.wait_for_timeout(800)
        updates = Handler.updates[:]
        ctx.close()
        self.assertEqual(updates, [], 'A prefetched page is not read until it has actually been shown')
    def test_failed_page_does_not_block_following_pages(self):
        ctx = self.browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
        page = ctx.new_page()
        page.route('**/chapter/10/page/1', lambda route: route.abort())
        page.goto(self.base + '/reader/143/10?mode=webtoon&at=0', wait_until='domcontentloaded')
        page.evaluate('window.MihonReady')
        page.wait_for_selector('.reader-page[data-page="3"]:not([hidden]).loaded')
        failed = page.locator('.reader-page[data-page="1"]')
        self.assertTrue(failed.is_visible())
        self.assertIn('image-error', failed.get_attribute('class'))
        self.assertGreater(failed.bounding_box()['height'], 100)
        height = failed.bounding_box()['height']
        page.set_viewport_size({'width': 390, 'height': 744})
        page.wait_for_timeout(200)
        self.assertAlmostEqual(failed.bounding_box()['height'], height, delta=1, msg='Browser viewport-height changes must not resize an error slot above the reader')
        page.evaluate('scrollTo(0,document.documentElement.scrollHeight)')
        page.wait_for_selector('.reader-page[data-page="7"]:not([hidden]).loaded', timeout=20000)
        self.assertIn('halaman gagal dimuat', page.locator('.reader-loading').inner_text())
        ctx.close()

if __name__ == '__main__':
    unittest.main(verbosity=2)
