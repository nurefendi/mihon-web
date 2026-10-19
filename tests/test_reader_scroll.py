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

def png(width, height, shade, label):
    def chunk(tag, data):
        return struct.pack('!I', len(data)) + tag + data + struct.pack('!I', zlib.crc32(tag + data) & 0xffffffff)
    # Tiny built-in bitmap lettering keeps these visibly labelled fixtures
    # dependency-free, even in a minimal Playwright-only test environment.
    glyphs = {
        'F': [31, 16, 16, 30, 16, 16, 16], 'I': [31, 4, 4, 4, 4, 4, 31],
        'X': [17, 17, 10, 4, 10, 17, 17], 'T': [31, 4, 4, 4, 4, 4, 4],
        'U': [17, 17, 17, 17, 17, 17, 14], 'R': [30, 17, 17, 30, 20, 18, 17],
        'E': [31, 16, 16, 30, 16, 16, 31], ' ': [0] * 7,
        '1': [4, 12, 4, 4, 4, 4, 14], '2': [14, 17, 1, 2, 4, 8, 31],
        '3': [30, 1, 1, 14, 1, 1, 30], '4': [2, 6, 10, 18, 31, 2, 2],
        '5': [31, 16, 16, 30, 1, 1, 30], '6': [14, 16, 16, 30, 17, 17, 14],
        '7': [31, 1, 2, 4, 8, 8, 8], '8': [14, 17, 17, 14, 17, 17, 14],
    }
    pixels = bytearray(bytes([shade, 90, 130]) * width * height)
    for n, char in enumerate(label):
        for y, bits in enumerate(glyphs[char]):
            for x in range(5):
                if bits & (1 << (4 - x)):
                    for dy in range(3):
                        for dx in range(3):
                            at = ((12 + y * 3 + dy) * width + 12 + n * 18 + x * 3 + dx) * 3
                            pixels[at:at + 3] = bytes([255, 255, 255])
    rows = b''.join(b'\x00' + pixels[y * width * 3:(y + 1) * width * 3] for y in range(height))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', width, height, 8, 2, 0, 0, 0)) + chunk(b'tEXt', b'Description\x00LABELLED TECHNICAL FIXTURE - NOT MANGA') + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b'')

IMAGES = [png(400, h, 50 + i * 10, 'FIXTURE ' + str(i + 1)) for i, h in enumerate([180, 250, 160, 1400, 170, 240, 190, 210])]

class Handler(BaseHTTPRequestHandler):
    last_read = 0
    updates = []
    requests = []
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
            Handler.requests.append(i)
            if str(i) in self.headers.get('X-Fixture-Always-Fail-Pages', '').split(','):
                time.sleep(.5)
                return self.send_error(503, 'Explicit persistent technical fixture failure')
            if str(i) in self.headers.get('X-Fixture-Fail-Pages', '').split(','):
                if Handler.requests.count(i) == 1:
                    return self.send_error(503, 'Explicit technical fixture initial failure')
                time.sleep(1.5)
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
        Handler.requests = []
    def tearDown(self):
        for ctx in self.browser.contexts:
            ctx.close()

    def test_failed_manual_retry_requires_another_explicit_click(self):
        ctx = self.browser.new_context(viewport={'width': 390, 'height': 844}, extra_http_headers={'X-Fixture-Always-Fail-Pages': '0'})
        try:
            page = ctx.new_page()
            page.goto(self.base + '/reader/143/10?mode=ltr&at=0', wait_until='domcontentloaded')
            page.evaluate('window.MihonReady')
            retry = page.get_by_role('button', name='Coba lagi', exact=True)
            retry.wait_for()
            for expected in [2, 3]:
                retry.click()
                self.assertTrue(retry.is_disabled())
                page.wait_for_function("() => !document.querySelector('.reader-slot:not([hidden]) .reader-error button').disabled")
                page.wait_for_timeout(2000)
                self.assertEqual(Handler.requests.count(0), expected, 'Even a failed manual retry must not schedule another attempt')
                self.assertEqual(Handler.updates, [])
                self.assertTrue(retry.is_visible())
        finally:
            ctx.close()

    def test_paged_offscreen_completion_does_not_save_progress(self):
        ctx = self.browser.new_context(viewport={'width': 390, 'height': 844}, extra_http_headers={'X-Fixture-Slow-Page': '0', 'X-Fixture-Fail-Pages': '1'})
        try:
            page = ctx.new_page()
            page.goto(self.base + '/reader/143/10?mode=ltr&at=0', wait_until='domcontentloaded')
            page.evaluate('window.MihonReady')
            page.locator('[data-action="page-next"]').click()
            page.wait_for_selector('.reader-page[data-page="1"].image-error')
            page.wait_for_function("() => document.querySelector('.reader-page[data-page=\"0\"]').classList.contains('loaded')", timeout=15000)
            page.evaluate("window.dispatchEvent(new Event('pagehide'))")
            page.wait_for_timeout(700)
            self.assertEqual(Handler.updates, [], 'A successful old page completed offscreen; the displayed page failed, so neither is read')
        finally:
            ctx.close()

    def test_loading_is_bounded_and_retired_retry_handlers_are_inert(self):
        ctx = self.browser.new_context(viewport={'width': 390, 'height': 844}, extra_http_headers={'X-Fixture-Fail-Pages': '0'})
        try:
            page = ctx.new_page()
            in_flight = set()
            peak = [0]
            def started(request):
                if '/chapter/10/page/' in request.url:
                    in_flight.add(request)
                    peak[0] = max(peak[0], len(in_flight))
            page.on('request', started)
            page.on('requestfinished', lambda request: in_flight.discard(request))
            page.on('requestfailed', lambda request: in_flight.discard(request))
            page.goto(self.base + '/reader/143/10?mode=webtoon&at=0', wait_until='domcontentloaded')
            page.evaluate('window.MihonReady')
            page.wait_for_selector('.reader-page[data-page="0"].image-error')
            # Retain the old button, then exercise the app's actual re-render.
            page.evaluate("window.retiredRetry=document.querySelector('.reader-error button');const b=document.createElement('button');b.dataset.action='retry';b.id='fixture-rerender';document.querySelector('main').append(b)")
            page.locator('#fixture-rerender').click()
            page.wait_for_function("() => !document.querySelector('#fixture-rerender')")
            before = Handler.requests.count(0)
            page.evaluate('window.retiredRetry.click()')
            page.wait_for_timeout(2000)
            self.assertEqual(Handler.requests.count(0), before, 'A detached old retry control must not start a request')
            # The first generation may still have network requests finishing;
            # establish a fresh context to measure one active reader's bound.
            ctx.close()
            ctx = self.browser.new_context(viewport={'width': 390, 'height': 844})
            page = ctx.new_page()
            in_flight.clear()
            peak[0] = 0
            page.on('request', started)
            page.on('requestfinished', lambda request: in_flight.discard(request))
            page.on('requestfailed', lambda request: in_flight.discard(request))
            page.goto(self.base + '/reader/143/10?mode=webtoon&at=0', wait_until='domcontentloaded')
            page.evaluate('window.MihonReady')
            for i in range(len(IMAGES)):
                page.locator('.reader-page[data-page="' + str(i) + '"]').locator('..').evaluate('(slot)=>slot.scrollIntoView()')
                page.wait_for_selector('.reader-page[data-page="' + str(i) + '"].loaded')
            self.assertEqual(peak[0], 3, 'Exercise the three-image window without exceeding it')
        finally:
            ctx.close()

    def test_paged_navigation_does_not_implicitly_retry_a_failed_page(self):
        for mode in ['ltr', 'rtl']:
            with self.subTest(mode=mode):
                Handler.requests = []
                ctx = self.browser.new_context(viewport={'width': 390, 'height': 844}, extra_http_headers={'X-Fixture-Fail-Pages': '0,1'})
                try:
                    page = ctx.new_page()
                    page.goto(self.base + '/reader/143/10?mode=' + mode + '&at=0', wait_until='domcontentloaded')
                    page.evaluate('window.MihonReady')
                    page.wait_for_selector('.reader-page[data-page="0"].image-error')
                    page.locator('[data-action="page-next"]').click()
                    page.wait_for_selector('.reader-page[data-page="1"].image-error')
                    page.locator('[data-action="page-prev"]').click()
                    page.wait_for_timeout(2300)
                    self.assertEqual(Handler.requests, [0, 1], 'Returning to a failed page must keep its manual retry, not silently request it again')
                    self.assertTrue(page.get_by_role('button', name='Coba lagi', exact=True).is_visible())
                finally:
                    ctx.close()

    def test_paged_modes_offer_manual_retry_for_each_displayed_failure(self):
        for mode in ['ltr', 'rtl']:
            with self.subTest(mode=mode):
                Handler.requests = []
                Handler.updates = []
                ctx = self.browser.new_context(viewport={'width': 390, 'height': 844}, extra_http_headers={'X-Fixture-Fail-Pages': '0,1'})
                try:
                    page = ctx.new_page()
                    page.goto(self.base + '/reader/143/10?mode=' + mode + '&at=0', wait_until='domcontentloaded')
                    page.evaluate('window.MihonReady')
                    page.wait_for_selector('.reader-page.image-error')
                    retry = page.get_by_role('button', name='Coba lagi', exact=True)
                    self.assertTrue(retry.is_visible())
                    self.assertEqual(Handler.updates, [])
                    page.wait_for_timeout(2200)
                    self.assertEqual(Handler.requests, [0])
                    retry.click()
                    self.assertTrue(retry.is_disabled())
                    retry.evaluate('(b)=>{for(let n=0;n<5;n++)b.dispatchEvent(new MouseEvent("click",{bubbles:true}))}')
                    page.wait_for_selector('.reader-page.loaded')
                    self.assertEqual(page.locator('.reader-slot:not([hidden]) .reader-page').evaluate('(i)=>[i.naturalWidth,i.naturalHeight]'), [400, 180])
                    self.assertEqual(Handler.requests, [0, 0])
                    self.assertTrue(retry.is_hidden())
                    page.locator('[data-action="page-next"]').click()
                    page.wait_for_selector('.reader-page[data-page="1"].image-error')
                    self.assertTrue(page.get_by_role('button', name='Coba lagi', exact=True).is_enabled())
                    page.wait_for_timeout(1200)
                    self.assertEqual(Handler.requests, [0, 0, 1])
                    self.assertNotIn(1, Handler.updates, 'A failed displayed image must not be saved as read')
                    page.get_by_role('button', name='Coba lagi', exact=True).click()
                    page.wait_for_selector('.reader-page[data-page="1"].loaded')
                    self.assertEqual(page.locator('.reader-slot:not([hidden]) .reader-page').evaluate('(i)=>[i.naturalWidth,i.naturalHeight]'), [400, 250])
                    self.assertEqual(Handler.requests, [0, 0, 1, 1])
                finally:
                    ctx.close()

    def test_failed_page_retries_only_on_its_button_and_never_duplicates(self):
        ctx = self.browser.new_context(viewport={'width': 390, 'height': 844}, extra_http_headers={'X-Fixture-Fail-Pages': '0,1'})
        try:
            page = ctx.new_page()
            page.goto(self.base + '/reader/143/10?mode=webtoon&at=0', wait_until='domcontentloaded')
            page.evaluate('window.MihonReady')
            page.wait_for_selector('.reader-page[data-page="1"].image-error')
            slot = page.locator('.reader-slot').filter(has=page.locator('.reader-page[data-page="0"]'))
            retry = slot.get_by_role('button', name='Coba lagi', exact=True)
            self.assertTrue(retry.is_visible(), 'Each failed page needs its own accessible Indonesian retry button')
            self.assertEqual(Handler.updates, [], 'An error or offscreen prefetch cannot save progress')
            page.mouse.wheel(0, 500)
            page.set_viewport_size({'width': 390, 'height': 744})
            page.wait_for_timeout(5500)
            self.assertEqual(Handler.requests.count(0), 1, 'Idle/scroll/resize must never retry a failure')
            self.assertEqual(Handler.requests.count(1), 1)
            # Retry must use the original generated same-origin URL, never a mutable data URL.
            slot.locator('.reader-page').evaluate('(i)=>i.dataset.src="https://invalid.example/not-an-image"')
            retry.click()
            self.assertTrue(retry.is_disabled())
            # Programmatic repeated activation must also be guarded, not just CSS.
            retry.evaluate('(b)=>{for(let n=0;n<8;n++)b.dispatchEvent(new MouseEvent("click",{bubbles:true}))}')
            page.wait_for_selector('.reader-page[data-page="0"].loaded')
            image = page.locator('.reader-page[data-page="0"]')
            self.assertTrue(image.is_visible())
            self.assertEqual(image.evaluate('(i)=>[i.naturalWidth,i.naturalHeight]'), [400, 180])
            self.assertEqual(image.evaluate('(i)=>new URL(i.src).pathname'), '/api/v1/manga/143/chapter/10/page/0')
            self.assertTrue(retry.is_hidden())
            self.assertEqual(image.evaluate('(i)=>{const c=document.createElement("canvas");c.width=i.naturalWidth;c.height=i.naturalHeight;const x=c.getContext("2d");x.drawImage(i,0,0);return [...x.getImageData(0,0,1,1).data]}'), [50, 90, 130, 255], 'Retry must reveal the actual returned fixture pixels')
            page.wait_for_timeout(1800)
            self.assertEqual(Handler.requests.count(0), 2, 'One click must produce exactly one extra HTTP request')
            self.assertEqual(Handler.requests.count(1), 1, 'Retrying page 1 must not retry page 2')
        finally:
            ctx.close()

    def test_ready_page_is_visible_while_first_page_is_delayed(self):
        ctx = self.browser.new_context(viewport={'width': 390, 'height': 844}, extra_http_headers={'X-Fixture-Slow-Page': '0'})
        try:
            page = ctx.new_page()
            page.goto(self.base + '/reader/143/10?mode=webtoon&at=0', wait_until='domcontentloaded')
            page.evaluate('window.MihonReady')
            second = page.locator('.reader-page[data-page="1"]')
            page.wait_for_function("() => document.querySelector('.reader-page[data-page=\"1\"]').naturalWidth > 0", timeout=6000)
            self.assertTrue(second.is_visible(), 'Ready page 2 must not wait behind delayed page 1')
            self.assertEqual(page.locator('.reader-page[data-page="0"]').evaluate('(i)=>i.naturalWidth'), 0)
        finally:
            ctx.close()

    def test_late_size_above_viewport_preserves_visible_image_position(self):
        ctx = self.browser.new_context(viewport={'width': 390, 'height': 844}, extra_http_headers={'X-Fixture-Slow-Page': '0'})
        try:
            page = ctx.new_page()
            page.goto(self.base + '/reader/143/10?mode=webtoon&at=0', wait_until='domcontentloaded')
            page.evaluate('window.MihonReady')
            page.wait_for_selector('.reader-page[data-page="1"].loaded')
            anchor = page.locator('.reader-page[data-page="3"]')
            anchor.locator('..').scroll_into_view_if_needed()
            page.wait_for_selector('.reader-page[data-page="3"].loaded')
            anchor.evaluate('(i)=>{i.scrollIntoView();scrollBy(0,100)}')
            before = anchor.bounding_box()['y']
            self.assertLess(before, 0)
            page.wait_for_selector('.reader-page[data-page="0"].loaded', timeout=15000)
            self.assertAlmostEqual(anchor.bounding_box()['y'], before, delta=1, msg='Keep the same content at the same viewport coordinate when a slot above shrinks')
        finally:
            ctx.close()

    def test_wheel_scrolling_preserves_visual_anchor_when_images_load(self):
        self.check_downward_scroll('wheel')
    def test_native_touch_swipes_preserve_visual_anchor_when_images_load(self):
        self.check_downward_scroll('touch')
    def check_downward_scroll(self, source):
        ctx = self.browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True)
        page = ctx.new_page()
        page.goto(self.base + '/reader/143/10?mode=webtoon&at=0', wait_until='domcontentloaded')
        page.evaluate('window.MihonReady')
        page.wait_for_selector('.reader-page.loaded')
        page.evaluate("""() => {
            window.scrollTrace=[];window.anchorChanges=[];
            addEventListener('scroll',()=>scrollTrace.push({y:scrollY,t:performance.now()}),{passive:true});
            // Observe the actual viewport anchor immediately before/after each
            // image handler, not the sign of compensated scrollY changes.
            const snapshots=new WeakMap();
            document.addEventListener('load',event=>{
                if(!event.target.matches('.reader-page'))return;
                const image=[...document.querySelectorAll('.reader-page.loaded')].find(i=>i!==event.target&&i.getBoundingClientRect().bottom>0&&i.getBoundingClientRect().top<innerHeight);
                if(image)snapshots.set(event.target,{image,top:image.getBoundingClientRect().top,y:scrollY});
            },true);
            document.querySelectorAll('.reader-page').forEach(image=>image.addEventListener('load',()=>{
                const before=snapshots.get(image);
                if(before)anchorChanges.push({page:image.dataset.page,anchor:before.image.dataset.page,before:before.top,after:before.image.getBoundingClientRect().top,y0:before.y,y:scrollY,max:document.documentElement.scrollHeight-innerHeight,delta:before.image.getBoundingClientRect().top-before.top});
            }));
        }""")
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
        sizes = page.evaluate("[...document.querySelectorAll('.reader-page.loaded:not([hidden])')].map(i=>({top:i.getBoundingClientRect().top+scrollY,height:i.getBoundingClientRect().height,width:i.getBoundingClientRect().width,w:i.naturalWidth,h:i.naturalHeight}))")
        for i, size in enumerate(sizes):
            self.assertAlmostEqual(size['height'], size['width'] * size['h'] / size['w'], delta=1)
            if i:
                self.assertAlmostEqual(size['top'], sizes[i - 1]['top'] + sizes[i - 1]['height'], delta=1)
        anchor_changes = page.evaluate('window.anchorChanges')
        ctx.close()
        self.assertGreater(len(trace), 3, 'The test must exercise actual scrolling')
        self.assertGreater(max(x['y'] for x in trace), 100)
        self.assertTrue(anchor_changes, 'Delayed image loads must overlap actual reading')
        for change in anchor_changes:
            # At document ends a short final image can leave too little content
            # to retain the old coordinate. Allow only the unavoidable clamp;
            # never accept displacement while the desired position is scrollable.
            desired = change['y'] + change['delta']
            clamp = desired - min(max(0, desired), max(0, change['max']))
            self.assertAlmostEqual(change['delta'], clamp, delta=1, msg='Loaded image displaced reading content beyond document-end clamping: ' + str(change))
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
    def test_resume_is_prioritized_without_waiting_for_preceding_sizes(self):
        ctx = self.browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, extra_http_headers={'X-Fixture-Slow-Page': '0'})
        try:
            page = ctx.new_page()
            page.add_init_script("window.__resumes=[];const original=Element.prototype.scrollIntoView;Element.prototype.scrollIntoView=function(opts){__resumes.push(this.dataset.page);original.call(this,opts)};")
            page.goto(self.base + '/reader/143/10?mode=webtoon&at=5', wait_until='domcontentloaded')
            page.evaluate('window.MihonReady')
            page.wait_for_function('() => window.__resumes.length > 0', timeout=6500)
            self.assertEqual(Handler.requests[0], 5, 'Saved image must get the first request')
            self.assertEqual(page.evaluate('window.__resumes'), ['5'])
            self.assertEqual(page.locator('.reader-page[data-page="0"]').evaluate('(i)=>i.naturalWidth'), 0)
            rect = page.locator('.reader-page[data-page="5"]').bounding_box()
            self.assertAlmostEqual(rect['y'], 0, delta=1)
            page.wait_for_timeout(1000)
            self.assertEqual(page.evaluate('window.__resumes'), ['5'])
        finally:
            ctx.close()
    def test_exit_before_resume_does_not_save_an_unseen_loaded_page(self):
        ctx = self.browser.new_context(viewport={'width': 390, 'height': 844}, is_mobile=True, has_touch=True, extra_http_headers={'X-Fixture-Slow-Page': '0'})
        page = ctx.new_page()
        page.add_init_script('window.requestAnimationFrame=fn=>setTimeout(()=>fn(performance.now()),10000)')
        page.goto(self.base + '/reader/143/10?mode=webtoon&at=5', wait_until='domcontentloaded')
        page.evaluate('window.MihonReady')
        page.wait_for_function("document.querySelector('.reader-page[data-page=\"5\"]').classList.contains('loaded')", timeout=20000)
        self.assertGreater(page.locator('.reader-page[data-page="5"]').bounding_box()['y'], 844, 'Loaded is not read: saved image is still outside the viewport')
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
        for i in range(4, 8):
            page.locator('.reader-page[data-page="' + str(i) + '"]').locator('..').evaluate('(slot)=>slot.scrollIntoView()')
            page.wait_for_selector('.reader-page[data-page="' + str(i) + '"].loaded', timeout=20000)
        self.assertIn('halaman gagal dimuat', page.locator('.reader-loading').inner_text())
        ctx.close()

if __name__ == '__main__':
    unittest.main(verbosity=2)
