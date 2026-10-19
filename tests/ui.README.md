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
