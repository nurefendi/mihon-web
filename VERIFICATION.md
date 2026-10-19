# Verification — first web release

Date: 2026-10-19 (WIB). This documents actual execution, not full Mihon feature parity.

## Exercised

- Docker runtime image built successfully. Docker build ran Go tests, `go vet`, and compiled the executable; final candidate image size reported by Docker was 25.3 MB. UI assets served by that image were hash-compared with every local JS/CSS/SVG file and matched.
- Backend developer exercised `go test -race -count=1 -v ./...`, `go vet ./...`, and a binary build. Real MariaDB integration used disposable `mihon-db-test` / `mihon_test`, never Quiz Web's database. Independent reviewer reran Go unit tests and vet with integration disabled.
- Parent reran the final source with **race detection, real disposable MariaDB integration, and the real isolated engine together**: `go test -p 2 -race -count=1 ./...` passed, followed by `go vet -p 2 ./...`. Test variables targeted only `mihon-db-test` and `mihon-engine-test`.
- Parent reran **24 UI helper/view/DOM tests**, all passed, using Node 22 + dev-only jsdom 26.1.0. This includes the reported title-search regression and repository canonical-URL readback. The production service does not run Node or jsdom.
- **29 bounded HTTP checks passed against the candidate and again against public HTTPS `https://mg.namiza.id`**. Checks include health for DB and engine; anonymous rejection; origin/CSRF restrictions including legacy mutating GETs; login/logout and cookie attributes; curated bridge library/history/download/repository queries; preferences write/readback/restoration; category create/rename/delete with readback; real local-source response; actual gzip backup export and validation. No smoke-test category remains.
- Real Chromium authenticated public-browser navigation exercised Library, Browse, Updates, History, More, and settings/categories/downloads/extensions sections. Desktop 1440×1000 and mobile 390×844 screenshots were captured and visually inspected. No application JS exceptions or horizontal overflow were observed. Screenshots are private QA artifacts outside this repository.
- Cloudflare injects its analytics beacon into public HTML; the app's strict self-only CSP blocks it. Browser QA records this separately (12 expected blocked-beacon messages), **does not loosen CSP**, and still fails on every other console/page error. This is an external analytics compatibility notice, not a claim of a perfectly empty console.
- **Nonempty real-engine reader integration passed** in separate containers, using an explicitly labelled, two-page technical CBZ fixture under the built-in local source. Actual Suwayomi responses exercised source browsing → manga details → add to library → chapter/images → read/bookmark/page progress → global history → backup validation. Chromium rendered both real image responses successfully with no page errors. No fake API response or manga collection was inserted into production.
- Production web and engine are Compose-owned (`mihon-web/web`, `mihon-web/engine`). Web is loopback-only on 8084 and attached to `npm-net`, `quiz-net`, `mihon-net`; engine has **no host-published API port**. New `mihon_web` schema contains only the three app tables with its dedicated scoped user. Quiz Web still returned HTTP 200 after proxy deployment.
- Origin TLS and Cloudflare public TLS both returned login HTTP 200. Certificate SAN covers only the intended new domain. `certbot renew --cert-name mihon-web --dry-run --no-random-sleep-on-renew` succeeded. A persistent user-systemd timer checks this certificate daily.

## Security review / release gate

Independent review identified repository-fetch trust, reverse-proxy-wide login throttling, and DNS-dependent repository removal as blockers. All were fixed with observed RED→GREEN regression tests: exact operator-configured repository allowlist (empty is denied before DNS); DNS-independent repository removal; explicit trusted-proxy CIDRs plus one overwritten client-IP header; and single-slot upload admission. Unit tests, `go vet`, and the final fixer's race run passed. A focused independent re-review returned `passed: true` with no remaining security concerns or logic errors. Intentionally trusted repository metadata/APK publishers remain executable authorities, not sandboxed untrusted input.

The Nginx config trusts Cloudflare client identity only for the official edge ranges, overwrites the app's dedicated client-IP header, and Go accepts it only from the pinned actual NPM peer. Private runtime configuration includes the user's explicitly selected Keiyoushi URL and its observed canonical engine URL; no other repository was automatically approved or installed.

## Not yet verified / incomplete

- The user installed Keiyoushi and the Komiku / Komiku.com extensions. Parent read back their actual installed flags and source IDs. Real popular requests returned 10 and 12 titles respectively. Public Chromium title search through Komiku returned two `one piece` matches after the UI regression fix. External chapter reading/download success, other sources, challenge login and tracker OAuth are **not verified**. Sources requiring WebView/Chromium may not work with KCEF disabled.
- Backup **export and validation** are exercised; restoring a nonempty real Mihon backup has not been certified. Stable engine REST may conceal internal restore failure; an HTTP 200 is not sufficient proof of restoration.
- Tracking, source-specific filters/preferences editors, migration, global multi-source search, history deletion, incognito/statistics, full Android viewer controls, browser-offline support and full pixel parity remain roadmap work.
- The app is one administrator / one shared engine library, not secure isolated multi-user hosting.

## Mobile reader scroll fix — 2026-10-20 (WIB)

- The reported backward movement was reproduced with the actual browser rendering code and labelled delayed technical PNG fixtures: downward-only input produced reverse jumps of 180–435 px. A CSS-only probe retaining the old placeholder minimum removed those jumps but would leave gaps; it was not shipped as the workaround.
- Webtoon pages now load in a bounded three-request window and are revealed in order at their natural dimensions, so unknown-size placeholders cannot collapse above the reading position. The fixed-height loading footer does not disappear or shrink. Failed-image slots use a width-based aspect ratio rather than viewport height; a regression first failed by 60 px during a height-only viewport resize, then passed after the fix. Completion explicitly reports failed pages instead of calling them loaded.
- Resume waits for preceding page dimensions, runs once, and is cancelled by a reader gesture. A hidden prefetched page cannot save progress on exit. Loading the saved position can still be delayed when earlier source images are unavailable.
- **Six Chromium scroll regressions passed**, including native CDP touch swipes, all fixture pages revealed, natural image ratios/no gaps, out-of-order loading, resume/cancellation, failed-page continuation/resize, and early-exit progress protection. **24 existing JS helper/view/DOM tests passed**. The rebuilt candidate also ran Go unit tests and vet successfully.
- The real-engine candidate was exercised on `/reader/143/10` at **390×844 and 360×800**, with native touch input and network throttling. Recorded 51 and 49 scroll events respectively, with **no reverse jumps and no horizontal overflow**. The exact no-query route displayed its captured saved page (19) in the viewport. All browser API mutations were aborted; readback confirmed the user's captured chapter progress unchanged and the temporary QA session was logged out.
- **Source-image health did not pass**: during these candidate checks only one image loaded in the initial sections and three failed in each viewport; the saved-position run reported ten failed images. Direct engine probing returned HTTP 500 for page index 1 after 30 seconds, and engine logs recorded `java.io.IOException: Connect timed out`; page index 13 was genuinely served from the engine with HTTP 200. These are real source failures, not invented image responses or evidence of a successful full-chapter read. The scroll fix does not claim to repair the external image host.
- Candidate screenshots show the real broken-image state and its error notice, without horizontal overflow or a full-screen fixed overlay. This verification is Chromium mobile emulation, **not a physical Android/iPhone or Safari certification**. Public deployment and matching CI remain separately verified release gates.

## Reproducible commands

- `go test -race -count=1 ./...` and `go vet ./...`
- See `tests/ui.README.md` for isolated dev-only UI dependencies and real-engine read smoke.
- `ops/smoke.py` performs the bounded HTTP checks using a local private password file. Its temporary category is explicitly labelled and removed; preferences are restored from the captured original values.
- `ops/browser-qa.py` tests the actual public website and screenshots mobile/desktop. Its one-host DNS override preserves TLS verification and was needed because the VPS resolver cached the domain's earlier NXDOMAIN.
- `ops/reader-integration.py` targets **only loopback 18085 and `mihon-db-test`**; it is intentionally guarded against using production. It requires the separately provisioned technical CBZ fixture/engine. It never seeds production content.

GitHub remote commit readback and matching CI status are separate release checks; do not infer them from local tests.
