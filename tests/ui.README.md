# UI verification

Runtime: plain HTML/CSS/JavaScript; **no npm, Node, bundler, CDN or external font is required in production**. The Go server embeds `web/*` and serves assets from `/app.css`, `/app.js`, etc.

## Unit and DOM tests

Use Node 22. The only dev dependency is **jsdom 26.1.0**; install outside the application tree:

```sh
UI_TEST_DEPS="$HOME/.cache/mihon-ui-test"
npm install --prefix "$UI_TEST_DEPS" --no-save --ignore-scripts --no-audit --no-fund jsdom@26.1.0
NODE_PATH="$UI_TEST_DEPS/node_modules" node --test tests/ui.test.cjs tests/ui.dom.cjs
```

Pure view/helper tests can run without dependencies:

```sh
node --test tests/ui.test.cjs
```

On the current machine (no host Node), the executed equivalent uses the existing image:

```sh
docker run --rm \
  -e NODE_PATH=/scratch/mihon-ui-test/node_modules \
  -v /home/mazaya/.hermes/cache/scratch:/scratch \
  -v /home/mazaya/mihon-web:/app -w /app \
  nikolaik/python-nodejs:python3.14-nodejs22 \
  node --test tests/ui.test.cjs tests/ui.dom.cjs
```

Tests were written and observed RED before the corresponding helper, route, DOM, bridge, root-asset-path, loaded-image-progress, and login-validation implementations. DOM tests use clearly scoped HTTP fixtures; they do not install repositories/extensions or seed the engine.

Coverage: all five routes; honest empty state; category merge including explicit category 0; text/attribute escaping; long source IDs; exact REST methods/forms and chapter-index/page paths; all-fetch CSRF; HTTP/GraphQL errors; history bridge; queue bridge; preference writes/readback; bookmark writes/readback; repository trust acknowledgement; login visibility/validation; progress only after successful image loading.

## Mobile webtoon scroll regressions

```sh
python3 -m venv "$HOME/.cache/mihon-browser-test"
"$HOME/.cache/mihon-browser-test/bin/pip" install playwright==1.64.0
"$HOME/.cache/mihon-browser-test/bin/python" -m playwright install --with-deps chromium
"$HOME/.cache/mihon-browser-test/bin/python" tests/test_reader_scroll.py
```

Fourteen Chromium tests use generated technical PNGs and delayed/out-of-order HTTP fixtures. They cover independent reveal while earlier pages are pending; prioritised resume without preceding-image waits; native touch/wheel visual-anchor preservation; natural ratios/no permanent gaps; stable failure slots; retry-only-on-click, repeated-click deduplication, repeat failure, bounded concurrency and handler cleanup; LTR/RTL retry and navigation; and visible-only progress. These tests never contact production. GitHub Actions runs the same pinned Playwright suite and includes its output in `ci-status`.

The reader fetches at most three page images concurrently and displays each successful image immediately in its own slot. Width-based estimates reserve unknown sizes; replacing an earlier estimate compensates scroll to preserve the visible reading anchor. A negative scrollY correction can therefore be correct: visual content displacement is the regression criterion, except unavoidable document-end scroll-range clamping. Resume is prioritised, not held behind earlier images. Failures are terminal until their own **Coba lagi** button is clicked; scrolling, resizing, revisiting a failed paged image and other image completions do not requeue it. Retry buttons stay disabled while queued/in-flight. Loaded images keep natural ratios without permanent spacer gaps.

`ops/reader-scroll-qa.py` separately exercises the **actual** engine images for `/reader/143/10` through the candidate or public website. It creates a temporary real login, aborts browser API mutations, checks chapter progress against a captured snapshot, and logs out with readback. It uses mobile native touch input and browser-level network throttling, not response fixtures. Credentials stay in the existing private server file. Supported targets are explicitly restricted to the public origin and local candidate ports; screenshots/traces are written outside Git. This is Chromium mobile emulation, not certification on a physical iPhone/Safari.

## Read-only stable-engine smoke

Opt-in, no seeding or mutations. It uses actual HTTP responses from the engine and the exact curated query strings in `bridge.go` to render all primary routes and every More section. `ENGINE_URL` must point to the private **v2.4.2366** engine. The test skips when it is unset.

```sh
ENGINE_URL=http://127.0.0.1:4567 node --test tests/ui.engine.cjs
```

Executed against the running local container without publishing its API:

```sh
docker run --rm --network container:mihon-engine \
  -e ENGINE_URL=http://127.0.0.1:4567 \
  -v /home/mazaya/mihon-web:/app:ro -w /app \
  nikolaik/python-nodejs:python3.14-nodejs22 \
  node --test tests/ui.engine.cjs
```

The real library/history/extensions/repositories were empty; no manga or third-party repository was added to make the test pass. Desktop login and empty-library layout were also inspected in Chromium using a temporary local static preview; the library visual test used an explicitly empty fixture, not invented engine content.

## Exact integration choices / limitations

- Stable REST remains authoritative for library/chapter/category/source/extension/backup actions. All fetch requests send CSRF, including legacy mutating GETs. Images never use `updateProgress=true`.
- All library = explicit category 0 plus every named category, merged by manga ID. Category 0 is uncategorized, not all library.
- `/api/bridge` is used for history, repositories, and polling download status; HTTP 200 GraphQL errors are checked. Bridge history/downloads omit source-order indices, so actual REST chapter lists resolve chapter IDs into chapter indices before reader/dequeue links are generated.
- Download queue control paths are plural `/api/v1/downloads/{start,stop,clear}`; individual enqueue/dequeue paths use singular `/api/v1/download/{mangaId}/chapter/{chapterIndex}`.
- Repositories are never preseeded. Repository addition requires a checked trust acknowledgement; APK install/update and upload require confirmation about executable third-party code.
- Backup import validates raw gzipped protobuf first and shows the engine report. Stable REST can conceal internal restore failures, so the UI does not claim an HTTP 200 proves full restoration; users must inspect restored content.
- Not implemented: tracker login/binding, source-specific filter/preferences editors, source migration, global source search, history deletion, Android offline/storage/hardware features, statistics/incognito, advanced reader image manipulation, or full pixel/feature parity with Android. These are disclosed in More.
- Real nonempty manga/reader/download/extension-install/backup-import end-to-end flows were not exercised against the private engine, because it has no seeded content and no user-approved third-party repository. Unit/DOM coverage uses explicit fixtures instead.
