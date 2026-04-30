# Wave 122 — Frontend tech-debt close + bundle/image bandwidth reduction (April 2026)

**Branch**: `egorribun`
**Scope**: Option C (L) — 6 SWs over 6 commits.
**Bundle**: PROD main chunk **179,867 bytes** (W121 polish: 175,744 → +4,123 bytes from guu_logo base64-inlining; well under 200 KB raw budget). VITE_LHCI build **178,892 bytes** (+4,123 same delta). Build × 3 reproducible (identical hash `B6SYYOCh`).

## Executive summary

Wave 122 closes 4 of 6 W121-inherited backlog items + 1 partial close + 1 unblocking documentation:

| # | Item | Status | SW |
|---|------|--------|-----|
| #5b | Image asset replacement (~875 KB savings) | ✅ closed | SW1 |
| #5a | Unused-JS reduction (vendor-pdf, ~166 KB/page across 7 routes) | ✅ closed (vendor-pdf portion) | SW2 |
| #2 | CI integration for cross-env URL_STATE_E2E | ⚠ partial close (step in workflow file, ci.yml wire-up deferred) | SW3 |
| #7 | Lighthouse 13 LHR JSON format compatibility | ✅ closed (audit revealed forward-compatible) | SW4 |
| #1 | Chromatic baseline (Storybook+Vite8 upstream) | ✅ resolved as "monitor + document" (4 active upstream issues) | SW5 |
| #6 | Mobile perf round 2 (XL own-wave) | ⏳ deferred per W121 user decision | — |
| — | Audit + docs | ✅ closed | SW6 |

**Headline wins**:
- **~875 KB image bandwidth saved** across 5 pages (guu_logo single fix benefits all): 249.6 KB → 3.6 KB (-98.6%), background.png 774 KB → background.jpg 145 KB (-81.3%), default_avatar 11 KB → 2.6 KB (-76.4%) plus picsum URL pattern fix on Dashboard story rail.
- **vendor-pdf chunk now truly lazy**: pdf-libs (jspdf + html2canvas + dompurify, ~622 KB raw) excluded from BOTH HTML modulepreload AND PWA service worker precache. LHCI `unused-javascript` on /news 211→45 KB (-166 KB), /events 190→23 KB (-167 KB).
- **/dashboard Perf 0.43 → 0.47** (3-run median, +0.04) — narrowest gate margin URL improved.
- **Chromatic upstream confirmed** — 4 active issues at storybookjs/storybook + vitejs/rolldown-vite + rolldown/rolldown match our exact failure modes; no new issues filed (would have been duplicates).

## Commits on origin

| # | SHA | Title | Files | +/− |
|---|---|---|---|---|
| 1 | `69b56413a` | `fix(wave122-sw1-image-assets)` — resize 3 + delete dead asset | 9 | +3 / −4 |
| 2 | `067b209f0` | `perf(wave122-sw2-vendor-pdf-lazy)` — drop pdf-lib from preload + SW precache | 1 | +49 / −8 |
| 3 | `b7949965b` | `ci(wave122-sw3-url-state-e2e-step)` — add cross-env URL_STATE_E2E step | 1 | +18 / 0 |
| 4 | `f15316e13` | `docs(wave122-sw4-lhr-format)` — Lighthouse 13.1.0 LHR property paths | 2 | +26 / 0 |
| 5 | `ddfef1c75` | `docs(wave122-sw5-chromatic-upstream)` — upstream Storybook+Vite8 trackers | 1 | +23 / 0 |
| 6 | `f128489aa` | `docs(wave122-sw6-audit)` — AUDIT + CLAUDE trail + W123 prep | 2 | +362 / 0 |

---

## SW1 — `fix(wave122-sw1-image-assets)`: ~875 KB savings

**Files**: `frontend/src/assets/{guu_logo.png,background.png→background.jpg,spotify_icon.png}`, `frontend/public/fallbacks/default_avatar.png`, `frontend/src/pages/{Profile.tsx,Dashboard.tsx}`, `frontend/src/components/profile/ProfileHeader.tsx`, `frontend/src/tests/pageTranslations.test.tsx`.

### Approach

W121 polish A4 caught 417 KB image-delivery waste via Lighthouse 13's `image-delivery-insight` audit. Investigation expanded scope:
- **`background.png`** was a hidden bonus target the W121 audit missed (Profile page wasn't in the LHCI URL set). Source PNG was 740×740 / 774 KB with NO alpha channel — perfect JPEG candidate.
- **`spotify_icon.png`** (108.6 KB) was DEAD CODE — only referenced by a stale `vi.mock()` in `pageTranslations.test.tsx:414`, no production import. Safe to delete.
- **`default_placeholder.png`** (75 KB in `public/fallbacks/`) ALSO appears unused, but the related `IMAGE_PLACEHOLDER_URL` constant points to wrong path (`/fallbacks/placeholder.png` 404s). This is a pre-existing CORRECTNESS bug (not perf), filed for W123.

### Resize execution (via local `sharp@0.34.5`)

| Asset | Before | After | Savings |
|-------|--------|-------|---------|
| `src/assets/guu_logo.png` | 5556×5556 / 255,576 B | 128×128 / **3,613 B** | **-98.6%** (252 KB) |
| `src/assets/background.png` → `background.jpg` (q=85 mozjpeg) | 740×740 / 774,114 B | 740×740 / **144,904 B** | **-81.3%** (615 KB) |
| `public/fallbacks/default_avatar.png` | 450×400 / 11,002 B | 96×96 / **2,595 B** | **-76.4%** (8 KB) |

Picsum URL constructor: `Dashboard.tsx:69` — `/400/700` → `/183/183` (matches StoryList circle display 91.2 px @ 2x retina).

Background filename: `.png` → `.jpg` rename. Coincidentally matches the stale test mock at line 412 (`@/assets/background.jpg`) from a prior wave that referenced .jpg — that mock now correctly intercepts the import.

### Trade-offs

- Main JS chunk +4,813 bytes: guu_logo at 3,613 B is under Vite's default 4 KB inline threshold, so it became base64-inlined. Net win: saves an HTTP round-trip + the asset file entirely. Still well under 200 KB raw budget.
- StoryList CIRCLES use square aspect (CSS clip via border-radius) — 183×183 is correct for circle display. StoryViewer modal opened from a mock story would show pixelated background — acceptable for mock data fallback.

### Visual verification (Claude_Preview)

- guu_logo at 128×128 PNG: renders crisp (Russian Eagle / open book design, navy + red on white)
- background.jpg at 740×740 q=85: blue tile pattern with white school-themed line icons (laptop, book, scissors, etc.) — no visible JPEG artifacts
- default_avatar at 96×96 PNG with alpha: silhouette intact

### LHCI verification (1-run smoke)

- /login `image-delivery-insight`: score 1.00 (was <1 in W121 polish A4)
- / `image-delivery-insight`: score 0.5 (story picsum 183×183 still has minor flag — Lighthouse heuristic stricter than display-size×dpr math; real story covers controlled by backend)

---

## SW2 — `perf(wave122-sw2-vendor-pdf-lazy)`: vendor-pdf truly lazy

**Files**: `frontend/vite.config.mts`.

### Diagnosis

W121 SW9 audit caught `vendor-pdf-*.js` (jspdf + html2canvas + dompurify, ~180 KB transferred) flagged as **162 KB / 91% wasted** on /news + /events + 5+ other routes. Source code (`scheduleExport.ts` + `activityExport.ts`) correctly used dynamic `await import()` — the chunk was loading eagerly via TWO mechanisms:

1. **HTML modulepreload**: Vite/Rolldown auto-injected `<link rel="modulepreload" href=".../vendor-pdf-*.js">` because the manualChunks rule made the chunk reachable from the entry import graph.
2. **PWA service worker precache**: `precacheAndRoute(self.__WB_MANIFEST)` precached EVERY chunk in the manifest — 622 KB raw fetched on SW install, which Lighthouse counts as page load.

### Approach (3-pronged defense-in-depth)

1. **Dropped vendor-pdf manualChunks rule**. Rolldown auto-splits into 4 chunks:
   - `jspdf.es.min-*.js` (399 KB raw / dynamic-only)
   - `html2canvas-*.js` (199 KB raw / dynamic-only — pulled by jspdf)
   - `purify.es-*.js` (21 KB raw / dynamic-only — dompurify, transitive)
   - `es-*.js` (html-to-image, separate chunk via scheduleExport's `import()`)
   
2. **PWA `injectManifest.globIgnores` extended**:
   ```
   globIgnores: [
     "**/bundle-stats.*", "**/offline.html",
     "**/jspdf*.js", "**/html2canvas*.js", "**/purify*.js"
   ]
   ```
   
3. **`build.modulePreload.resolveDependencies`** filter excludes any chunk matching jspdf/html2canvas/purify from HTML preload list. Defense-in-depth — Vite shouldn't preload these now that they're dynamic-only, but the filter survives any future manualChunks regression.

Bonus: moved orphan `modulepreload: { polyfill: false }` from config root (silently ignored by Vite — wrong location) into proper `build.modulePreload`.

### Verification

| Metric | Before SW2 | After SW2 | Δ |
|---|---|---|---|
| precache entries | 181 | 178 | -3 |
| precache size | 5454 KiB | 4848 KiB | **-606 KiB** |
| /news `unused-javascript` | 211 KB | 45 KB | **-166 KB** |
| /events `unused-javascript` | 190 KB | 23 KB | **-167 KB** |
| /news Perf (1-run) | 0.51 | 0.58 | +0.07 |
| /events Perf (1-run) | 0.46 | 0.54 | +0.08 |
| /news LCP (1-run) | 13124 ms | 9078 ms | **-31%** |
| /events LCP (1-run) | 10962 ms | 9690 ms | -12% |

Functional smoke (static analysis): Activity-*.js dynamic-imports `./jspdf.es.min-DBfT9EB6.js`, scheduleExport-*.js dynamic-imports `./jspdf.es.min-*.js` + `./es-*.js`. All chunks exist in `dist/assets/`. Runtime fetch path intact.

### Trade-offs

- 4 chunks vs 1 (negligible — total bytes same; HTTP/2 multiplexing makes parallel-fetch overhead minimal)
- Activity + Schedule each may duplicate jspdf if rolldown decides to inline (current layout shows shared chunk file — dedup works)
- First-export-attempt-while-offline now requires network for jspdf chunk (acceptable; users rarely export PDF offline + online round-trip restores capability after first cache)

---

## SW3 — `ci(wave122-sw3-url-state-e2e-step)`: cross-env step in workflow

**Files**: `.github/workflows/reusable-e2e-tests.yml`.

### Approach

Added new step after the existing default `Run E2E tests` step in `reusable-e2e-tests.yml`:

```yaml
- name: Run URL-state e2e (cross-env auto-managed)
  if: inputs.browser == 'chromium'
  working-directory: frontend
  env:
    URL_STATE_E2E: "true"
    VITE_BACKEND_ORIGIN: http://127.0.0.1:8000
  run: |
    npx playwright test url-state-persistence.spec.ts \
      --project=chromium \
      --reporter=html
```

Inherits Node.js + Playwright browser cache from earlier setup steps. Conditional on `inputs.browser == 'chromium'` (matches W120 SW7 + W121 SW3 chromium-only design). Independent of the default step — Playwright's `webServer.command` (per `playwright.config.ts:73-110`) spins up a SEPARATE VITE_LHCI=true preview on port 4175 via cross-env.

Local re-verification: `URL_STATE_E2E=true npx playwright test --project=chromium url-state-persistence.spec.ts` → **6 passed (18.8s)**.

### ⚠ Honest scope caveat

**`reusable-e2e-tests.yml` is NOT INVOKED from `.github/workflows/ci.yml` today** (discovered during SW3 grep — no caller exists). None of its e2e tests (a11y-public, accessibility, app, mfa, news-share, etc. — 16+ spec files, ~47 test cases) are running in CI right now. The same applies to the new URL_STATE_E2E step.

Wiring up `reusable-e2e-tests.yml` from `ci.yml` would:
- Add backend setup (uvicorn + Redis service) to every CI run (~3-5 min)
- Run the full e2e suite (~5-10 min on 47 tests)
- Substantially increase CI minutes consumed per push/PR

That scope decision is bigger than SW3 (~30 min plan estimate) and warrants its own discussion + measurement of CI cost. **Filed for W123 backlog as a follow-up Item.**

---

## SW4 — `docs(wave122-sw4-lhr-format)`: Lighthouse 13.1.0 LHR docs

**Files**: `frontend/scripts/lhci-windows-fallback.mjs`, `frontend/scripts/run-lhci.mjs`.

### Audit findings

`lhci-windows-fallback.mjs` reads 7 LHR JSON paths in `parseLhr()`:
- `lhr.categories.{performance,accessibility,best-practices,seo}.score`
- `lhr.audits.{cumulative-layout-shift,largest-contentful-paint,total-blocking-time}.numericValue`

W122 SW4 verified all 7 against real Lighthouse 13.1.0 output (`.lighthouseci/lhr_news_run1.json` from a SW2 verification run). All paths present, no schema breaking changes vs the 12.x baseline these fields were originally written against.

`run-lhci.mjs` does NOT read LHR fields directly — delegates entirely to `@lhci/cli` (which now uses lighthouse 13.1.0 transitively via the W121 polish A1 `package.json` overrides).

### Changes

- JSDoc block on `parseLhr()` listing the 7 verified paths + maintenance note (re-verify if bumping to a future Lighthouse major).
- Header comment in `run-lhci.mjs` noting the indirection to `@lhci/cli`.

No functional changes. Item #7 closed via audit-only verification.

---

## SW5 — `docs(wave122-sw5-chromatic-upstream)`: track upstream issues

**Files**: `.github/workflows/chromatic.yml`.

### Web search findings (2026-04-30)

Multiple active upstream issues match our exact problem (W120 SW8 `__STORYBOOK_MODULE_*` + W121 SW7 `import.meta.glob`):

- **[storybookjs/storybook#33789](https://github.com/storybookjs/storybook/issues/33789)** — Vite 8 umbrella tracker
- **[vitejs/rolldown-vite#562](https://github.com/vitejs/rolldown-vite/issues/562)** — primary `__STORYBOOK_MODULE_*` failure
- **[storybookjs/storybook#31711](https://github.com/storybookjs/storybook/issues/31711)** — exact match: SB+Rolldown `__STORYBOOK_MODULE_PREVIEW_API__` undefined
- **[rolldown/rolldown#3982](https://github.com/rolldown/rolldown/issues/3982)** — `import.meta.glob` Rolldown bug (blocks W121 SW7 Webpack-swap fallback)

**No new issues filed** (would have been duplicates).

### Deliverables

- Annotated `.github/workflows/chromatic.yml` header with the 4 upstream URLs + clear "STILL BLOCKED" status + criteria for re-enabling (upstream fix lands → flip `vars.CHROMATIC_ENABLED=true`).
- New `memory/wave122_chromatic_upstream.md` (cross-session reference) captures full diagnosis history, monitoring action (quarterly check via `gh issue view`), and ordered fallback paths.

### Why no source refactor in W122

The `import.meta.glob` callers are foundational paths (i18n loader runs on every page; campus data loads on /map). Source refactor is invasive (~2-4h estimated) AND doesn't unblock the primary `__STORYBOOK_MODULE_*` issue — would only unblock the Webpack fallback. Better signal-to-noise ratio is to wait for upstream Storybook fix (which addresses both).

---

## SW6 — `docs(wave122-sw6-audit)`: this commit

**Files**: `AUDIT_WAVE122.md` (NEW), `CLAUDE.md` (Audit Trail row + selected gotchas), `memory/MEMORY.md` (W122 row), `memory/wave123_backlog.md` (NEW), `memory/wave123_opening_prompt.md` (NEW).

---

## End-of-wave gates (verbatim)

```
$ npx tsc --noEmit                    → exit 0

$ npm run lint                        → exit 0

$ npm run i18n:check                  → 17 passed (17)

$ npm run tokens:sync && git diff --exit-code -- src/theme/tokens.ts
✅ Found 631 CSS variables in partials/ + tokens/
                                       → tokens diff exit 0 (no drift)

$ npm audit                           → 0 vulnerabilities

$ npm run test -- --run               → 686 passed | 12 skipped | 0 failed
                                        Duration  23.43s
                                        (W121 polish baseline preserved)

$ for i in 1 2 3; do rm -rf dist && npm run build; done
                                       → all 3 produce identical:
-rw-r--r-- 1 egorribun 197121 179867 Apr 30 02:48 dist/assets/index-B6SYYOCh.js

$ env VITE_LHCI=true npm run build    → 178,892 bytes dist/assets/index-31ZuyYVm.js

$ git diff --stat -- frontend/rust-crypto/Cargo.lock
                                       → empty (idempotent ≥ 10 waves)

$ npx playwright test --project=chromium tests/e2e/a11y-public.spec.ts
  4 passed (15.9s)

$ URL_STATE_E2E=true npx playwright test --project=chromium tests/e2e/url-state-persistence.spec.ts
  6 passed (18.6s)
```

### LHCI 9-URL × 3-run sweep (mobile, devtools throttling, VITE_LHCI=true, Lighthouse 13.1.0)

Sub-batched per W120 SW1 EPERM mitigation (3 sub-batches × 3 URLs × 3 runs):

| URL | Perf | CLS | LCP (ms) | TBT (ms) | A11y | Δ vs W121 polish |
|-----|------|------|---------|---------|------|------|
| / | 0.46 | 0.061 | 12244 | 385 | 1.00 | Perf +0.02, CLS +0.028 |
| /login | 0.57 | 0.000 | 11338 | 100 | 1.00 | Perf +0.01 |
| /dashboard | **0.47** | 0.061 | 10520 | 365 | 1.00 | **Perf +0.04** ✅ (largest gain), CLS +0.028 |
| /news | 0.53 | 0.006 | 9080 | 241 | 1.00 | Perf +0.01, LCP -12% |
| /schedule | 0.52 | 0.003 | 11998 | 246 | 1.00 | held |
| /events | 0.48 | 0.062 | 11967 | 329 | 1.00 | Perf +0.01 |
| /activity | 0.46 | 0.003 | 11494 | 430 | 1.00 | Perf +0.01 |
| /map | 0.48 | 0.075 | 12159 | 301 | 1.00 | Perf +0.01 |
| /404 | 0.56 | 0.000 | 10697 | 184 | 1.00 | Perf +0.02 |

**ALL 9 URLs pass W120 SW2 ratchet** with margin:
- Perf ≥ 0.40 (worst /, /events, /activity = 0.46 — 15% margin)
- CLS ≤ 0.10 (worst /map = 0.075 — 25% margin; / + /dashboard at 0.061 — 39% margin)
- A11y ≥ 0.95 (all 1.00 ✅ — W121 polish A2 baseline preserved)

---

## Honesty probe self-audit

Pre-empting the expected "безупречно?" probe by listing honest caveats up-front:

### ⚠ SW3 partial close — `reusable-e2e-tests.yml` not invoked from `ci.yml`

Discovered during SW3 grep that the workflow file exists but no caller exists. The new URL_STATE_E2E step is structurally in the right place but won't actually run in CI until someone wires up `reusable-e2e-tests.yml` from `ci.yml`. That decision adds 47 e2e tests + backend setup to every CI run (~5-10 min) — a separate scope decision warranting its own discussion. Filed for W123 as a "wire-up + cost measurement" Item.

### ⚠ SW6 LHCI sweep had to be sub-batched (not single full sweep)

The initial background full-9-URL sweep stopped after 2 LHR runs (Windows EPERM Chrome cleanup bug, W120 SW1 caveat). Re-ran in 3 sub-batches of 3 URLs × 3 runs each (5.4-6.0 min per sub-batch). Results valid + complete, but the wall-clock cost was ~17 min instead of the planned ~25-30 min. Process artifact (port 4174 hung) required manual `taskkill` between attempts.

### ⚠ CLS regression on / + /dashboard (+0.028 each)

Both URLs went from CLS 0.033 → 0.061 between W121 polish A3 and W122 SW6 measurements. Still WELL UNDER the 0.10 gate (39% margin), but a measurable shift. Possible causes:
- Bundle hash changes from SW1 (image inlining) + SW2 (chunk graph) altering load ordering
- Statistical variance — 3-run sometimes shows 0.02-0.04 swings
- Layout-shift attribution: faster paint from smaller bundle means later overlays (NotificationsPermissionPrompt etc) get measured against an earlier baseline

NOT investigated further (gate margin comfortable, A11y unaffected). Could be a W123 mobile-perf-XL investigation target if it persists.

### ⚠ SW1 didn't fix the IMAGE_PLACEHOLDER_URL 404 bug

Discovered during SW1 grep that `IMAGE_PLACEHOLDER_URL = "/fallbacks/placeholder.png"` in `src/constants/placeholders.ts` is a broken path (actual file is `default_placeholder.png`). SmartImage falls through to this URL when the primary src fails — currently 404s. Pre-existing bug (not W122-introduced) but kept OUT of SW1 scope (correctness fix, not perf). Filed for W123.

### ⚠ Picsum URL change might affect StoryViewer modal experience

`Dashboard.tsx:69` mock-stories `cover_url` went from `/400/700` (portrait) → `/183/183` (square). StoryList circles render correctly (square aspect via border-radius). But if a user opens StoryViewer (full-screen modal) on a mock story, the background would be 183×183 pixelated. Acceptable: mock stories are a fallback when API returns empty. Real story covers from backend control their own dimensions.

### ⚠ SW2 jspdf chunk duplication NOT investigated thoroughly

When manualChunks for vendor-pdf was dropped, Rolldown could have created duplicate jspdf bundles for Activity vs Schedule. Spot check shows both reference the SAME `jspdf.es.min-*.js` file, suggesting dedup works. Not exhaustively verified — if a future audit shows duplicates, the fix is to add a fresh manualChunks rule that tags pdf-libs as a dynamic-only chunk (not the original which was preload-eligible).

### ⚠ ci.yml LHCI baselines unchanged in SW6

Per W120 SW2 ratchet (CLS error@0.10, Perf error@0.40): all 9 URLs continue to pass. No gate change in W122. Future ratchet (e.g., Perf error@0.45) could be considered after mobile-perf-XL (W123+) lands more substantial improvements.

### ✓ What DID land

- **~875 KB image bandwidth saved** across 5 pages
- **vendor-pdf truly lazy** — 166-167 KB unused-JS removed from /news + /events
- **/dashboard Perf +0.04** (3-run median) — narrowest gate margin URL improved
- **All 9 URLs A11y = 1.00 ✅** preserved
- **All 9 URLs CLS ≤ 0.10 ✅** preserved
- **Build × 3 reproducible** (179,867 bytes identical hash)
- **Cargo.lock idempotent ≥ 10 waves**
- **vitest 686p/12s/0f** (W121 polish baseline preserved)
- **e2e a11y-public 4/4 + url-state-persistence 6/6** chromium passing
- **LHR format documented** (Lighthouse 13.1.0 forward-compatible verified)
- **Chromatic upstream confirmed** — 4 active issues, monitoring infra in place
- **Bonus dead-code deletion**: spotify_icon.png + stale test mock removed

---

## Wave 123 hand-off

See `memory/wave123_backlog.md`. Items inherited from W122 (post-polish, see §Polish pass below for closures):

1. ~~**Wire up `reusable-e2e-tests.yml` from `ci.yml`**~~ ✅ **CLOSED in W122 polish A1** (`a40b485bd` — `e2e-tests` job + ci-success aggregation update; ~5-10 min/run CI cost).
2. **Mobile perf round 2** (XL own-wave, deferred from W121 + W122) — LCP < 2.5s on authenticated routes.
3. **Chromatic resumption monitoring** (quarterly check on 4 upstream issues per `memory/wave122_chromatic_upstream.md`).
4. ~~**`IMAGE_PLACEHOLDER_URL` 404 bug fix**~~ ✅ **CLOSED in W122 polish A4** (`a40b485bd` — `mv default_placeholder.png placeholder.png` + 4 mockApi refs synced).
5. ~~**`mockApi.ts` `news_placeholder.png` 404**~~ ✅ **CLOSED in W122 polish A4** (same commit, same family).
6. ~~**`default_placeholder.png` (75 KB) orphan**~~ ✅ **CLOSED in W122 polish A4** (renamed to placeholder.png, no longer orphan).
7. **vendor-sentry / vendor-ui unused-JS reduction** (Item #5a partial — SW2 closed only the vendor-pdf portion). Sentry is unavoidable infra; vendor-ui is Framer Motion partial usage. Lower ROI than vendor-pdf was.
8. ~~**CLS variance investigation**~~ ✅ **CLOSED in W122 polish A2** (`a40b485bd` — root-caused to DashboardHero h1 + status-bar; min-h reservation closed 0.061 → 0.040, -34%, with bonus Perf +0.07-0.08).
9. ~~**Investigate jspdf chunk dedup**~~ ✅ **CLOSED in W122 polish A3** (`a40b485bd` — exhaustive grep: 1 distinct chunk per pdf-lib).

**NEW W123 items surfaced during polish**:

10. **ScheduleCard sub-element CLS shift (~0.040 pre-existing)** — surfaced during polish A2 as the residual after h1+status-bar fix. Smaller scope, well under 0.10 gate (60% margin). Monitor in W123; investigate via `layout-shift-elements` if regresses above 0.06.

W122 + polish closes 5 of 6 W121-inherited active items + 1 unblocking documentation + 6 of 9 hand-off items above. The CLS arc + a11y arcs + image-bandwidth arcs are all closed. Remaining work: mobile perf round 2 (XL own-wave) + 3 small W123 items (#3 Chromatic monitoring, #7 vendor-sentry/ui, #10 ScheduleCard CLS monitor).

---

## Polish pass (post round-1 "безупречно?" probe)

User invoked the perfectionism probe after the SW6 docs commit. ~100 min polish closed 5 honesty caveats:

### A1 — `e2e-tests` job wired up in `ci.yml` (closes SW3 caveat)

W122 SW3 modified `reusable-e2e-tests.yml` but left it never invoked from `ci.yml`. A1 adds an `e2e-tests` job (lines 386-401) calling `reusable-e2e-tests.yml` with chromium browser + python-version 3.13. Includes the W122 SW3 URL_STATE_E2E step automatically (gated `if: inputs.browser == 'chromium'`). Added to `ci-success` aggregation `needs` list + results check (now 18 deps, was 17). Cost: ~5-10 min wall-clock per CI run (backend + browser install + ~47 spec cases). YAML validated via PyYAML; local re-verification: 6/6 url-state passing.

### A2 — DashboardHero CLS root-cause fix (closes "natural variance" caveat)

LHR `layout-shifts` audit on / + /dashboard revealed the SAME shifting element (score 0.062, only item): `<div role="status" aria-live="polite">` — DashboardHero status bar containing time/week/parity/weather/date.

**Two fixes** in `src/components/dashboard/DashboardHero.tsx`:
- Status bar div (line 128): added `min-h-[40px]` to reserve flex container height regardless of WeatherWidget loading state
- `<h1>` greeting (line 100): added `min-h-[2lh]` (CSS lh unit = 2 line-heights of current font-size, dynamic) to reserve space for async i18n greeting that initially renders empty/short

**3-run median LHCI on / + /dashboard**:
| Metric | Before A2 | After A2 | Δ |
|---|---|---|---|
| / Perf | 0.46 | 0.54 | **+0.08** |
| / CLS | 0.061 | 0.040 | **−34%** |
| /dashboard Perf | 0.47 | 0.54 | **+0.07** |
| /dashboard CLS | 0.061 | 0.040 | **−34%** |

Remaining 0.040 from ScheduleCard header link (pre-existing, smaller, monitor in W123). Well under 0.10 gate (60% margin).

### A3 — jspdf chunk dedup exhaustively verified (closes spot-check caveat)

Grep across all `dist/assets/*.js` for distinct chunk filenames:

| Library | Distinct chunks |
|---|---|
| jspdf | 1 (`jspdf.es.min-DBfT9EB6.js`) |
| html2canvas | 1 (`html2canvas-Cr_jfP-U.js`) |
| purify (dompurify) | 1 (`purify.es-BuhLKeN0.js`) |
| es (html-to-image) | 1 (`es-CSBSpoQ0.js`) |

Activity-*.js + scheduleExport-*.js BOTH dynamic-import the SAME `jspdf.es.min-DBfT9EB6.js` file. Rolldown auto-dedup confirmed across all 4 lazy-only chunks. **Zero duplication.**

### A4 — `placeholder.png` rename + mockApi sync (closes pre-existing 404 bugs)

Pre-existing bugs surfaced during SW1 grep:
- `IMAGE_PLACEHOLDER_URL = "/fallbacks/placeholder.png"` — file was actually `default_placeholder.png` (mismatch). SmartImage fallback chain silently 404'd.
- `tests/e2e/utils/mockApi.ts` × 4 references to `/fallbacks/news_placeholder.png` (file never existed). E2e fixtures rendered broken images.

**Fix**: `mv default_placeholder.png placeholder.png` (matches the constant which had been pointing here all along) + 4 mockApi.ts refs updated to `/fallbacks/placeholder.png`. SW precache verified (178 entries unchanged, includes `fallbacks/placeholder.png`). No stale grep hits in src + tests + public.

Closes W122 backlog Item #4 + family.

### A5 — Visual verification at REAL display sizes (closes "I didn't verify" caveat)

SW1 only verified PNGs via direct asset URL navigation (browser-default size, not real layout). A5 navigated to `/dashboard` on VITE_LHCI=true `npm run preview` (port 4188, auth bypass active, mock user `LHCI Test User` logged in) via chrome-devtools-mcp browser session.

**Verified at REAL display sizes**:
- guu_logo navbar (32×32 display, top-left): inlined base64 (4842-char src, 3613 bytes PNG decoded), CRISP — Russian Eagle / open-book design with navy + red colors, no pixelation
- guu_logo footer (42×48 display): SAME inline base64 reused (single-source asset shared between both nav + footer sites)
- default_avatar (36×36 display): clean silhouette scaling at 2x retina from 96×96 source
- StoryList circles (~91 px display from /183/183 picsum source): all 6 thumbnails sharp at 2x retina
- DashboardHero status bar (A2 fix preserved): time + week + weather + date populated correctly with NO visible shift

### A6 — Process leak cleanup

A5 spawned `npm run preview --port 4188` in background; killed PID 18172 + verified ports 4174/4175/4188 free post-cleanup. chrome-devtools-mcp page closed.

### Polish-pass commit

| # | SHA | Title | Files | +/− |
|---|---|---|---|---|
| 7 | `a40b485bd` | `fix+ci+docs(wave122-polish)` — close 5 honesty caveats in one batch | 5 | +26 / −9 |

### Final gates (post-polish, verbatim)

```
$ npx tsc --noEmit                    → 0 errors
$ npm run lint                        → 0 warnings
$ npm run i18n:check                  → 17/17
$ npm run tokens:sync && git diff     → no drift (631 vars)
$ npm audit                           → 0 vulnerabilities
$ npm run test -- --run               → 686 passed | 12 skipped | 0 failed
$ for i in 1 2 3; do build; done      → 179,867 bytes / hash DdAbG7rt × 3 reproducible
$ env VITE_LHCI=true npm run build    → 178,892 bytes / hash CiW0SGBC
$ git diff Cargo.lock                 → no drift (idempotent ≥ 11 waves)
$ npx playwright a11y-public          → 4/4 chromium 15.7s
$ URL_STATE_E2E=true npx playwright url-state-persistence.spec.ts → 6/6 chromium 17.5s
```

Bundle SIZE unchanged from W122 SW6 (179,867 prod / 178,892 LHCI) — only hashes differ due to A2 source edits + A4 file rename.

### Honest re-probe (post-polish)

After fixing 5 caveats, only structural deferrals remain:

- ✅ Closed: SW3 partial close (was workflow-only, now fully wired into ci.yml)
- ✅ Closed: / + /dashboard CLS regression (was uninvestigated, root cause fixed via h1+status-bar min-h)
- ✅ Closed: jspdf chunk dedup (was spot-check, now exhaustive grep verification)
- ✅ Closed: IMAGE_PLACEHOLDER_URL 404 + family (was pre-existing correctness, fixed via rename)
- ✅ Closed: visual verification at REAL display sizes (was direct-asset-URL only)

Genuinely structural (Wave 123+):

- Mobile perf round 2 (XL own-wave per user W121 + W122 decisions)
- StoryViewer pixelation on mock stories (acceptable mock-data fallback)
- ScheduleCard header sub-element shift (~0.040 CLS pre-existing, monitor in W123)
- Chromatic upstream issues (#33789, #562, #31711, #3982 — quarterly monitoring)
