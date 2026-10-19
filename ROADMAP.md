# Mihon Web — feature parity roadmap

This is a **web rewrite in progress**, not an official Mihon release and not a claim of full Android feature parity. The target is to implement the original app's features sequentially. Each feature needs both implementation and an exercised acceptance test before it is marked complete.

Baseline: Mihon source commit `deeb9b2584b6e246135cbd31da49a39e6b6e1e52`; compatibility engine Suwayomi stable `v2.4.2366`, pinned by image digest in `compose.yaml`. Do not update the engine from `stable` blindly: later upstream versions remove some REST operations.

## Stage 1 — usable web core (current implementation)

- [x] Authenticated single shared library; MariaDB-backed sessions, preferences, CSRF protection.
- [x] Mihon DEFAULT light/dark colors, five-tab adaptive navigation, responsive phone/desktop layout.
- [x] Library grid, search, categories, add/remove manga, continue reading.
- [ ] Source list, popular/latest/search, pagination, source configuration.
- [ ] User-managed trusted extension repositories, install/update/uninstall extensions.
- [x] Manga details, chapter listing, chapter read/bookmark status.
- [x] Reader: webtoon, paged LTR/RTL, chapter navigation, saved page progress.
- [ ] Updates, library refresh, reading history.
- [ ] Download queue and chapter download management.
- [x] Category management.
- [x] Client theme, grid, reading-mode preferences saved and consumed at runtime.
- [ ] Compatible backup export/import with validation and restore verification.

## Stage 2 — parity gaps to close individually

- [ ] Full source-specific filters and all Android-compatible source preferences.
- [ ] Global search with bounded per-source concurrency, cancellation, error isolation.
- [ ] Manga source migration including chapter matching and progress/category preservation.
- [ ] Tracking service OAuth/credentials, search/bind/unbind/status/score sync.
- [ ] History removal/clear with correct user-visible semantics.
- [ ] Full library sort/filter/display variants and bulk-selection actions.
- [ ] Full chapter sort/filter/bulk action coverage.
- [ ] Download retry, reorder, cleanup, scheduling, storage policy and auto-download controls.
- [ ] Library update scheduling and exclusions that affect actual engine behavior.
- [ ] Reading statistics, reading-time accounting, per-title statistics.
- [ ] Incognito mode, downloaded-only mode, per-title reading preferences.
- [ ] Full viewer controls: vertical paging, dual page, crop borders, zoom, brightness/color filters, page actions and keyboard/touch behavior.
- [ ] Full theme catalog, AMOLED, font scale/accessibility, locale options.
- [ ] Local comic import workflow and archive/format compatibility.
- [ ] Backup job status, scheduled backups, restore reporting and disaster-recovery rehearsal.
- [ ] Progressive web app/offline browser reading (server downloads alone are not browser offline support).
- [ ] Advanced source WebView/login/challenge compatibility (KCEF currently disabled for VPS memory limits).
- [ ] Secure account/password management and optional multi-user design (current engine library is shared).

## Platform-specific differences

Android intents, OS storage access, orientation locks, hardware volume-key controls, Android notifications/background execution and wallpaper-based Monet colors cannot simply be copied into browser APIs. Record an explicit browser equivalent or a documented incompatibility for each; do not silently call it parity.

## Source repository policy

Mihon and Suwayomi both ship **without a default third-party extension repository**. This deployment intentionally starts with the engine's built-in local source only. Configure the same repository used on your Mihon installation after deciding to trust it. Extensions execute third-party code inside the private engine. Installing an extension does not guarantee every source is reachable or every Android WebView feature works on this server.

## Release gate

Unit/contract tests, isolated MariaDB integration, actual HTTP mutations/readback, a real engine-backed reader flow, phone/desktop visual checks, public HTTPS authentication and GitHub remote SHA readback are separate gates. See `VERIFICATION.md` for what was actually exercised in this release. Empty library/API responses prove wiring only, not successful external-source ingestion.
