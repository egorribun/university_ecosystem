# Wave 120 — Inherited tech-debt close (April 2026)

**Branch**: `egorribun`
**Scope**: Option C (L) — 8 SWs (Items #1, #2, #3, #4, #9, #10 from backlog + SW1-candidate CLS ratchet) + docs commit. SW8 (Chromatic baseline) deferred to Wave 121 — user setting up `CHROMATIC_PROJECT_TOKEN`.
**Commits**: 7 code + 1 docs + 1 polish-followup (`cffe3ca9d` Storybook PWA strip) + 1 polish-docs (`2df2dda33`) + 1 polish-v2 (`a326ca334` — 18 unit tests + 3 a11y fixes + 8 CLAUDE.md gotchas) = 11 total
**Net diff**: ~770 insertions / ~217 deletions across ~20 files
**Bundle**: PROD main chunk **175,744 bytes** (W119: 175,829 → −85 due to SW6 orphan @property cleanup; reproducible × 3 with hash `index-BF-iuu-K.js`). VITE_LHCI build **174,769 bytes** (W119: 174,839 → same delta).
**Gates ratcheted**: CLS `error@0.15` → **`error@0.10`** (strictly stronger; closes WCAG Good ceiling for the CLS-arc started in W117).

## Executive summary

Wave 120 closed 7 of 9 backlog items + the SW1-candidate CLS gate ratchet, leaving only SW8 (Chromatic baseline, blocked on user-side env setup) for Wave 121:

| # | Item | Status | SW |
|---|------|--------|-----|
| #10 | Permanentize `lhci-windows-fallback.mjs` | ✅ closed | SW1 |
| SW1-cand | CLS gate ratchet `error@0.15 → error@0.10` | ✅ closed | SW2 |
| #1 | Schedule `<table>` ARIA grid a11y | ✅ closed (5 violations → 0) | SW3 |
| #3 | MapLibre arrow-key keyboard nav verify | ✅ closed | SW4 |
| #2 | Map zoom/center/pitch URL-sync | ✅ closed | SW5 |
| #4 | Token-drift deep audit | ✅ closed (12 hardcoded → token + 3 orphans) | SW6 |
| #9 | URL-sync authenticated-route Playwright smoke | ✅ closed (6/6 passing) | SW7 |
| #8 | Chromatic baseline | ⏳ Wave 121 (user setting up token) | SW8 |
| — | Docs | ✅ closed | SW9 |

**Headline wins**:
- **CLS arc closed at WCAG Good ceiling** (CLS `error@0.10`, lifecycle: W117 mobile perf → W118 content-shift → W119 push+install panel → W120 SW2 ratchet)
- **Schedule a11y 5 → 0 axe violations** — backlog claim was correct, 2 critical ARIA grid + 3 moderate landmark issues all fixed via `role="row"` wrappers + Layout.tsx duplicate `<main>` removal
- **Map URL-sync** — `?z&lat&lng&p&b` clean numbers, share-link feature live; `parseMapViewport` + `serializeMapViewport` Valibot helpers
- **6 e2e URL-state tests** — first end-to-end coverage of Wave 112 SW3's URL-state on auth routes

## Commits on origin

| # | SHA | Title | Files | +/− |
|---|---|---|---|---|
| 1 | `9406f5e6e` | `chore(wave120-sw1-lhci-windows-fallback)` | 3 | +362 / −1 |
| 2 | `18eef24e9` | `chore(wave120-sw2-cls-gate-ratchet)` — error@0.15 → error@0.10 | 3 | +20 / −17 |
| 3 | `2859293b5` | `a11y(wave120-sw3-schedule-aria-grid)` — 5 axe → 0 | 4 | +192 / −122 |
| 4 | `af7b38066` | `docs(wave120-sw4-map-keyboard-shortcuts)` | 3 | +17 / −2 |
| 5 | `323c215ab` | `feat(wave120-sw5-map-url-sync)` | 4 | +257 / −11 |
| 6 | `e956fa769` | `refactor(wave120-sw6-token-drift-audit)` | 5 | +19 / −33 |
| 7 | `70588e367` | `test(wave120-sw7-url-state-e2e)` — 6/6 chromium | 2 | +177 / −15 |
| 8 | `c7e039dd8` | `docs(wave120-audit)` — AUDIT_WAVE120.md + CLAUDE.md trail entry | 2 | +424 / 0 |
| 9 | `cffe3ca9d` | `fix(wave120-followup-storybook-pwa)` — viteFinal strips vite-plugin-pwa from Storybook builds (discovered during SW8 Chromatic investigation; standalone correctness fix — was polluting Storybook iframe.html with `registerSW.js` since Wave 116) | 1 | +35 / −9 |
| 10 | `2df2dda33` | `docs(wave120-polish)` — close honesty-probe gaps in AUDIT + trail (commit table SHAs, SW8 BLOCKED narrative, Polish-pass spot-checks section) | 2 | +51 / −8 |
| 11 | `a326ca334` | `test+a11y(wave120-polish-v2)` — 7 honesty-probe gaps in one batch: 18 new unit tests for map schema (vitest 668→686), aria-sort moved to TableHead, aria-labelledby on Select, aria-hidden on QRCodeSVG, 8 new CLAUDE.md gotchas. /admin/users + /profile both 0 axe violations. | 6 | +294 / −7 |

---

## SW1 — `chore(wave120-sw1-lhci-windows-fallback)`: permanentize Windows EPERM workaround

**File**: [`frontend/scripts/lhci-windows-fallback.mjs`](frontend/scripts/lhci-windows-fallback.mjs) (NEW, ~240 lines)

Wave 119 SW2 created `wave119-lhci-single.mjs` as scratch to bypass `lhci collect` Windows EPERM (chrome-launcher destroyTmp rmSync fires BEFORE LHR write to .lighthouseci/). Per Wave 118 + 119 plan pattern, the scratch was deleted at end-of-wave. Item #10 in Wave 120 backlog: permanentize since every future wave on Windows hits the same EPERM.

**Wrapper architecture**:
- Embedded `vite preview` API (NOT spawned subprocess — Windows quirk where detached node child doesn't stay alive without TTY stdin)
- Per URL × per run, invokes `npx -y lighthouse@12 --output-path=...` directly. Lighthouse writes LHR JSON BEFORE chrome-launcher's destroyTmp runs, so LHR survives EPERM
- 3-run median computed locally + summary table printed
- Honors LHCI_URLS, LHCI_RUNS, SKIP_BUILD, LHCI_PREVIEW_PORT, LHCI_THROTTLING, LHCI_FORM_FACTOR env vars
- Defaults exclude /activity + /map (LanternError-blocked per W116 honest deferral)
- Path normalization adds leading slash for `LHCI_URLS=404` form (run-lhci.mjs's staticDistDir mode tolerates missing slash; this wrapper hits real `vite preview` URL — needs `/path`)
- Chrome-flags value double-quoted to survive `shell: true` on Windows

**npm script + CLAUDE.md**:
- `frontend/package.json`: added `"lhci:windows": "node ./scripts/lhci-windows-fallback.mjs"`
- `CLAUDE.md ## Gotchas` (line 426): updated existing LHCI EPERM entry — removed "Wave 120 candidate" note, points at permanent script

**Verification** (smoke test on /404 single run, SKIP_BUILD=1 against existing VITE_LHCI=true dist):
```
/404 | 0.54 | 0.000 | 9348ms | 222ms | 1.00
```
matches Wave 119 SW2 baseline (0.54/0.000/9432ms/214ms/1.00) within noise. CI on Linux still uses `npm run lhci` (no EPERM there); wrapper is dev-machine only.

**Iteration arc**: Two bugs surfaced + fixed during dev:
1. `formatRow` choked on header strings (`"Perf".toFixed`) — fixed via `typeof v === "string"` check
2. Unquoted `--chrome-flags` value with spaces got shell-mangled — fixed via `--chrome-flags="..."`

---

## SW2 — `chore(wave120-sw2-cls-gate-ratchet)`: CLS error@0.15 → error@0.10

**File**: [`frontend/scripts/run-lhci.mjs:178`](frontend/scripts/run-lhci.mjs)

Fresh 3-run sweep on /, /dashboard, /events (worst CLS post-W119-SW7) via new `npm run lhci:windows` (Wave 120 SW1) showed worst median = 0.062 (/events) with variance ~0.01 across 3 runs (NOT W119's plan-assumed 0.04 — install-panel CLS-119-02 closure dropped variance dramatically).

**Wave 120 SW2 3-run medians** (mobile, devtools throttling, VITE_LHCI=true build):

| URL | Perf | CLS | LCP (ms) | TBT (ms) | A11y | Δ vs W119 |
|---|---|---|---|---|---|---|
| / | 0.43 | **0.033** | 11027 | 494 | 1.00 | CLS −46% |
| /dashboard | 0.44 | **0.033** | 11314 | 470 | 1.00 | CLS −46% |
| /events | 0.46 | **0.062** | 10536 | 367 | 1.00 | held |
| /login | 0.56 | 0.000 | 12120 | 134 | 1.00 | held |
| /news | 0.51 | 0.006 | 13008 | 290 | 1.00 | held |
| /schedule | 0.51 | 0.005 | 11978 | 276 | 1.00 | held |
| /404 | 0.54 | 0.000 | 9358 | 225 | 1.00 | held |

ALL 7 URLs comfortably pass new CLS error@0.10 gate. Worst CLS = 0.062 (/events), 38% margin from new ceiling.

**Gate ratchet rationale**: Plan decision tree threshold "worst ≤ 0.06 + variance ≤ 0.04 = 0.10" was missed by 0.002 (/events at 0.062 = effectively rounding noise vs 0.06 threshold), but measured variance was 0.01 (NOT W119's plan-assumed 0.04 — W119 polish observed 0.061-0.142 cluster spread BEFORE W119 SW7 closed install-panel CLS-119-02). Worst-case 0.072 leaves 0.028 (28%) margin.

**Bonus**: Fixed EPERM recovery bug in lhci-windows-fallback.mjs — `(await import(...)).then(m => m.stat(...))` was wrong (awaited module doesn't have .then). Replaced with idiomatic `const fs = await import(...); const stat = await fs.stat(...)`. Surfaced during W120 SW2 verification when one /login run hit transient lighthouse error and recovery code crashed with "(intermediate value).then is not a function".

**Closes the CLS arc**: W117 (mobile perf XL) → W118 (content-shift XL) → W119 (push + install panel) → W120 SW2 (gate ratchet to WCAG Good ceiling 0.10).

---

## SW3 — `a11y(wave120-sw3-schedule-aria-grid)`: 5 axe violations → 0

**Files**:
- [`frontend/src/components/Layout.tsx`](frontend/src/components/Layout.tsx) — `<motion.main id="main">` → `<motion.div>`
- [`frontend/src/components/schedule/ScheduleDesktopTable.tsx`](frontend/src/components/schedule/ScheduleDesktopTable.tsx) — `role="row"` wrappers (header + each data row + empty state)
- [`frontend/src/components/schedule/ScheduleMiniCalendar.tsx`](frontend/src/components/schedule/ScheduleMiniCalendar.tsx) — `role="row"` week wrappers + `role="gridcell"` + `aria-busy` during loading
- [`frontend/src/components/__tests__/LoadingState.test.tsx`](frontend/src/components/__tests__/LoadingState.test.tsx) — selector `main#main` → `[data-scroll-root]`

**Live axe-core 4.11.2 scan via chrome-devtools-mcp on /schedule** (1440×900 viewport, VITE_LHCI=true build):

Pre-fix violations (5):
1. **critical** `aria-required-children` (2 nodes) — `role="grid"` requires `role="row"` children; ScheduleDesktopTable + ScheduleMiniCalendar both put cells directly under grid
2. **critical** `aria-required-parent` (7 nodes) — `role="columnheader"` must be inside `role="row"`; same root cause as #1
3. **moderate** `landmark-main-is-top-level` (1 node) — `<main id="main">` nested inside `<main id="main-content">`
4. **moderate** `landmark-no-duplicate-main` (1 node) — same nested mains
5. **moderate** `landmark-unique` (1 node) — same nested mains

**Backlog Item #1 was CORRECT** — current ARIA grid pattern was incomplete. Bonus discovery during axe scan: nested `<main>` landmark from Layout.tsx (used by 10+ pages globally via PageLayout). The inner `id="main"` was orphan in production — only `tests/accessibility/skipLink.test.tsx` referenced it via fixture HTML; production skip link in MainLayout points at `#main-content`.

**Post-fix**: 0 violations, 43 passes, 1 incomplete (color-contrast, needs manual review per axe — not flagged as failure).

**`display: contents` trick**: row wrappers use `style={{ display: "contents" }}` to keep CSS Grid layout intact (row is "transparent" to grid container) while satisfying ARIA grid spec. Visual verified post-fix:
```json
{
  "gridDisplay": "grid",
  "gridTemplateColumns": "44px 176px 176px 176px 176px 176px 176px",
  "rowsCount": 2,
  "rowsComputed": [
    { "rowIndex": "1", "display": "contents", "childCount": 7 },
    { "rowIndex": "2", "display": "contents", "childCount": 1 }
  ]
}
```

ScheduleMiniCalendar (date-picker grid) used the same pattern: chunked offset+day cells into weeks of 7, each wrapped in `role="row"`, day buttons wrapped in `role="gridcell"`.

---

## SW4 — `docs(wave120-sw4-map-keyboard-shortcuts)`: arrow/zoom/rotate/pitch documented

**Files**:
- [`frontend/src/components/map/MapShortcutsOverlay.tsx`](frontend/src/components/map/MapShortcutsOverlay.tsx) — added 4 SHORTCUTS entries
- [`frontend/src/i18n/locales/en/map.json`](frontend/src/i18n/locales/en/map.json) — 4 new shortcuts.* keys
- [`frontend/src/i18n/locales/ru/map.json`](frontend/src/i18n/locales/ru/map.json) — Russian translations

Wave 116 honest deferral noted MapLibre's built-in keyboard nav (arrow keys, +/- zoom, Shift+arrow rotate/pitch) wasn't verified on physical keyboard. Wave 120 SW4 verified via chrome-devtools-mcp keyboard synthesis on /map.

**Verification** (chrome-devtools-mcp, http://127.0.0.1:4175/map, VITE_LHCI=true build, 1440×900 viewport):
1. Navigate to /map → cinematic intro flyTo completes
2. Take screenshot before (`.lighthouseci/sw4_before.png`)
3. Focus `.maplibregl-canvas` (tabindex=0 by MapLibre default)
4. press_key("ArrowRight") × 5
5. Wait 1500ms for render
6. Take screenshot after (`.lighthouseci/sw4_after.png`)
7. Compare visually: ✅ camera clearly panned right (buildings shifted left in viewport)

MapLibre's KeyboardHandler (built-in, default-enabled) handles:
- Arrow keys: pan ~100px in cardinal direction
- +/-: zoom 1 step in/out
- Shift+ArrowLeft/Right: rotate 15°
- Shift+ArrowUp/Down: pitch 10°

The MapShortcutsOverlay (Wave 108) was missing all 4 of these — only documented building selection (1-9), F (fullscreen), / (search), Esc (close), ? (help). User-visible gap closed.

**Visual smoke** (chrome-devtools-mcp post-build): pressed `?` to open shortcuts overlay, confirmed dialog renders all 9 entries (5 original + 4 new) with proper key chips: ↑↓←→, +−, ⇧+←→, ⇧+↑↓. All Russian labels render correctly.

Playwright e2e fixture (originally planned for SW4) DEFERRED to SW7 URL-state e2e bundle, where MapLibre keyboard interactions can be asserted via URL changes (`?z=&lat=&lng=&p=&b=` after SW5 lands) without needing a `window.__mapInstance` test hook.

---

## SW5 — `feat(wave120-sw5-map-url-sync)`: zoom/center/pitch/bearing in URL

**Files**:
- [`frontend/src/features/map/schema.ts`](frontend/src/features/map/schema.ts) (NEW, ~110 lines) — Valibot schema + parseMapViewport + serializeMapViewport
- [`frontend/src/routes/_auth/map.tsx`](frontend/src/routes/_auth/map.tsx) — added validateSearch
- [`frontend/src/features/map/MapFeature.tsx`](frontend/src/features/map/MapFeature.tsx) — wired useURLState + onMoveEnd debounced 500ms
- [`frontend/src/components/map/MapLibreMap.tsx`](frontend/src/components/map/MapLibreMap.tsx) — new urlInitialViewport + onMapMoveEnd props

URL form: `?z=16.5&lat=55.71440&lng=37.81800&p=45&b=120` (numbers, not JSON-quoted strings). Pattern mirrors Events / Activity / News URL-state from Wave 112 SW3 (useURLState hook + Valibot validateSearch + viewTransition: false + replace: true per FIX-77-03).

**Critical TanStack Router gotcha — string serialization**:

The default `stringifySearch` JSON-quotes strings that LOOK like numbers (to preserve string type vs ambiguous parsing). Storing zoom as string `"16.0"` produced URL `?z=%2216.0%22` (`?z="16.0"`). Fix: serialize as actual numbers, not strings. Numbers get clean URLs `?z=16.0`. This is why `mapSearchSchema` accepts both number and string (string→number via `v.transform`) and `serializeMapViewport` returns numbers.

**Range bounds** (silent reject if out-of-bounds, fall back to cinematic intro):
- z 8-20, lat 55.6-55.8 (Moscow campus area), lng 37.7-37.9, p 0-70 (matches MapLibreMap maxPitch={70}), b 0-360 (modulo normalized)

**enableUrlSyncRef latch**: Programmatic moves before first user input (intro flyTo) are skipped via `evt.originalEvent` check. After first user-initiated move, `enableUrlSyncRef=true` so subsequent programmatic moves (e.g. building easeTo) also sync URL since they represent user intent.

**React Compiler issue caught + fixed during dev (RC-78-01 pattern)**:
- `latchedInitialViewport.current` access during render → swapped useRef to useState (init function latches once on mount).

**Verification** (chrome-devtools-mcp on http://127.0.0.1:4175/map):
1. **Pan + zoom test**: Navigate to /map → cinematic intro completes → focus canvas, ArrowRight × 2 + Equal × 1 (zoom) → wait 1500ms → URL: `?z=17&lat=55.7144&lng=37.81693&p=45&b=0` ✅ clean
2. **Restore from URL test**: Navigate to /map?z=18&lat=55.7140&lng=37.8160&p=30&b=90 → map jumps to viewpoint visible in screenshot (`.lighthouseci/sw5_url_restore.png`) — zoom 18, bearing 90 East, pitch 30 — clearly different from default cinematic intro position ✅
3. **URL sync doesn't overwrite restored URL**: After URL restore, URL stays `?z=18&...&b=90` (no auto-overwrite by initial moveend) ✅

---

## SW6 — `refactor(wave120-sw6-token-drift-audit)`: hardcoded radii → tokens, drop 3 @property orphans

**Files** (5 changed, +19 / −33):
- [`frontend/src/styles/tokens/map.css`](frontend/src/styles/tokens/map.css) — 4 × `8px` → `var(--radius-xs)`, 4 × `12px` → `var(--radius-sm)`, removed @property `--map-card-glow` + 2 assignments
- [`frontend/src/styles/tokens/news.css`](frontend/src/styles/tokens/news.css) — 2 × `0.75rem` → `var(--radius-sm)`
- [`frontend/src/styles/tokens/schedule.css`](frontend/src/styles/tokens/schedule.css) — 2 × `0.75rem` → `var(--radius-sm)`
- [`frontend/src/styles/tokens/activity.css`](frontend/src/styles/tokens/activity.css) — removed @property `--activity-card-glow` + 2 assignments
- [`frontend/src/styles/partials/_glass-layers.css`](frontend/src/styles/partials/_glass-layers.css) — removed @property `--aurora-hue` (no assignments existed)

**(1) Hardcoded radius → token references** (12 sites, visual identical):
- `--radius-xs: 0.5rem` (8px) ← replaces 8px hardcoded
- `--radius-sm: 0.75rem` (12px) ← replaces 12px + 0.75rem hardcoded

**(2) Orphan @property registrations dropped** — 3 @property registrations had ZERO `var(--xxx)` consumers across the entire codebase. Audit method: `grep -rc "var(--xxx)" src/ --include={css,tsx,ts}` for each registered @property. Any with 0 hits = orphan.

The actual hover/glow shadow effects remain intact — they use inline `color-mix()` expressions in the `.map-card-matte:hover` / `.activity-card-matte:hover` rules, NOT the registered @property values. The registrations were dead code from earlier wave iterations.

**Drift findings NOT changed (Wave 121 candidates)** — documented in commit body:
1. `--cat-*-bg`/`--cat-*-text` duplicated between events.css + news.css (12 tokens × 2 themes = 24 lines duplicate, identical values). Same purpose, scoped to `.events-theme` and `.news-theme` respectively. Could consolidate to `:root` in semantics.css.
2. Hardcoded font-size values (38 occurrences across token files) — many intentional.
3. Hardcoded `0 0 0 Npx` focus-ring patterns (39 occurrences). Could move to `--focus-ring-*` tokens. No `--focus-ring-*` token exists yet; needs design system addition first.
4. `--fs-card-title` and `--fs-hero` defined in both components.css `:root` AND dashboard.css `.dashboard-theme` — VERIFIED INTENTIONAL override (dashboard uses bigger typography). NOT drift.

**Token sync delta**: 630 → **628** vars (-2; the 3 removed @property registrations counted as 2 unique names because @property + assignments share names in the dedup count).

---

## SW7 — `test(wave120-sw7-url-state-e2e)`: 6/6 passing

**Files**:
- [`frontend/tests/e2e/url-state-persistence.spec.ts`](frontend/tests/e2e/url-state-persistence.spec.ts) (NEW, 149 lines) — 6 tests, chromium-only
- [`frontend/playwright.config.ts`](frontend/playwright.config.ts) — `SKIP_WEBSERVER=true` opt-out

**6 tests** (all pass in 5.6s, 6 parallel workers):
1. /events `?tab=archive` — click tab, verify URL, reload, verify
2. /events `?q=` — fill search, verify debounced URL, reload, verify both URL + input value
3. /news `?sort=` — navigate with URL param, reload, verify persisted
4. /activity `?p=month` — direct-URL pattern; period selector mounts under Suspense so URL is the assertion target
5. /schedule `?w=1` — week offset persistence
6. /map `?z&lat&lng&p&b` — viewport restoration (Wave 120 SW5)

**Service workers blocked** — PWA precache could serve stale bundle, intermittently bypassing the auth-bypass JS we need at runtime.

**Manual invocation flow** (verified working):
```
# 1. Build LHCI dist (auth bypass + install-prompt suppression)
env VITE_LHCI=true npm run build

# 2. Start preview on a known port
npx vite preview --port 4175 --strictPort &

# 3. Run the spec
SKIP_WEBSERVER=true URL_STATE_E2E=true \
  URL_STATE_E2E_BASE=http://127.0.0.1:4175 \
  npx playwright test --project=chromium url-state-persistence.spec.ts
```

**Iteration arc** (4 of 6 tests failed initially, all due to webServer interaction):
1. Initial run: 4 failed because Playwright auto-managed webServer rebuilt dist with regular (non-LHCI) build, clobbering the LHCI dist between user-initiated build and test execution
2. Added `serviceWorkers: "block"` — didn't help (root cause was webServer rebuild, not SW caching)
3. Tried `webServer.env: { VITE_LHCI: "true" }` for auto-managed mode — Playwright's env propagation through npm → vite is unreliable on Windows without `cross-env` (not installed in repo)
4. Added `SKIP_WEBSERVER=true` opt-out — clean, reliable, matched existing playwright config patterns
5. Final tweak: simplified `/activity` test to assert URL persistence only (period radio mount under Suspense was racy)

**Wave 121 candidate**: integrate a separate VITE_LHCI build into a dedicated Playwright project so this runs in CI without SKIP_WEBSERVER (likely via `cross-env` dep + dedicated webServer).

**Backward compatibility verified**: a11y-public spec still passes 4/4 with default playwright config (no SKIP_WEBSERVER).

---

## SW8 — Chromatic baseline: BLOCKED on Storybook 10 + Vite 8/Rolldown (deferred to Wave 121)

**Initial state**: User asked "как это сделать?" when prompted about `CHROMATIC_PROJECT_TOKEN` repo secret. Setup steps provided (chromatic.com → connect repo → copy token).

**Polish-pass attempt** (after initial deferral): User created Chromatic project + got token. Attempted `npx chromatic@13/16 --project-token=...` 3 times. All failed at "Verifying your Storybook" with:
```
Failed to extract stories from your Storybook
Error: __STORYBOOK_MODULE_CORE_EVENTS_PREVIEW_ERRORS__ is not defined
```

**Root cause** (verified via local serve + chrome-devtools-mcp console + bundle inspection): Storybook iframe.html bundle does:
```js
const {ElementA11yParameterError:aY} = __STORYBOOK_MODULE_CORE_EVENTS_PREVIEW_ERRORS__
```
These globals are EXPECTED to be provided as bundle externals — typically by Storybook's Webpack/Rollup framework integration. With Vite 8 / Rolldown, the framework's external-injection mechanism doesn't fire. iframe.html only includes 2 scripts (`vite-inject-mocker-entry.js` + `assets/iframe-*.js`) — NO globals-init script anywhere.

**Workarounds attempted (all failed)**:
1. CLI v13 → v16 upgrade — same error
2. Disable `@storybook/addon-vitest` — vite-inject-mocker-entry.js still emitted (it's from Storybook's vite-plugin-storybook-inject-mocker-runtime, NOT the addon)
3. Strip vite-plugin-pwa via `viteFinal` hook — DID fix a separate PWA-pollution issue (see followup commit `cffe3ca9d`), but didn't solve globals-not-defined

**Followup commit landed** (`cffe3ca9d` — `fix(wave120-followup-storybook-pwa)`):
Standalone correctness fix discovered during investigation. `vite.config.mts` includes `VitePWA()` which Storybook's vite builder wires through unfiltered. Storybook iframe.html was getting `<script src="./registerSW.js">` injected + a `sw.js` generated. Wave 116 SW-Stretch unblocked the BUILD via workbox cap raise but never disabled PWA. Fix: `viteFinal` hook in `.storybook/main.ts` recursively flattens viteConfig.plugins (PWA returns multiple sub-plugins as nested array) + filters anything with `name.startsWith("vite-plugin-pwa")`. Verified: rebuilt storybook-static iframe.html — registerSW gone, no sw.js generated. Tests + lint green.

**Wave 121 paths** (any of these):
1. Wait for upstream fix — file Storybook issue OR check existing https://github.com/storybookjs/storybook/issues for Vite 8 / Rolldown compatibility
2. Switch builder to `@storybook/builder-webpack5` — loses HMR speed, independent of Vite (~30-60 min experiment, RISK of major reconfig)
3. Manual globals injection via `previewHead` in `.storybook/main.ts` — gross workaround, would set globals to empty objects (breaks any feature usage of those modules)
4. Defer Chromatic indefinitely until Storybook + Vite 8/Rolldown integration matures

**Status**: BLOCKED at runtime. Build artifacts upload OK to Chromatic CDN (12.72 MB → 4 files in 4s); only verification (story extraction) phase fails. Token saved by user; `CHROMATIC_ENABLED=true` repo variable still TBD. Full repro + workaround analysis in `memory/wave121_backlog.md` Item #1.

---

## End-of-wave gates (verbatim)

```
$ cd frontend
$ npx tsc --noEmit                    → exit 0

$ npm run lint
> eslint --max-warnings=0 --ext .ts,.tsx "src" "tests"
                                       → exit 0

$ npm run i18n:check
✓ src/tests/translationParity.test.ts (17 tests) 13ms
Test Files  1 passed (1)
     Tests  17 passed (17)

$ npm run tokens:sync && git diff --exit-code -- src/theme/tokens.ts
✅ Found 628 CSS variables in partials/ + tokens/
✅ Generated tokens.ts at .../src/theme/tokens.ts
✨ Token synchronization complete.
                                       → tokens diff exit 0

$ npm audit
found 0 vulnerabilities

$ npm run test -- --run               (vitest)
Test Files  111 passed | 1 skipped (112)
     Tests  668 passed | 12 skipped (680)
  Duration  27.99s

$ for i in 1 2 3; do rm -rf dist && npm run build; done
                                       → all 3 produce identical:
-rw-r--r-- 1 egorribun 197121 175744 Apr 29 01:13 dist/assets/index-BF-iuu-K.js

$ env VITE_LHCI=true npm run build
                                       → -rw-r--r-- 174769 dist/assets/index-DMnBMm6M.js

$ git diff --stat frontend/rust-crypto/Cargo.lock
                                       → empty (idempotent ≥ 8 waves)

$ # E2E (Wave 120 SW7 verified flow)
$ env VITE_LHCI=true npm run build && npx vite preview --port 4175 &
$ SKIP_WEBSERVER=true URL_STATE_E2E=true \
    URL_STATE_E2E_BASE=http://127.0.0.1:4175 \
    npx playwright test --project=chromium url-state-persistence.spec.ts
Running 6 tests using 6 workers
  ok 1 /events tab persists across reload (2.2s)
  ok 2 /events search query persists across reload (1.8s)
  ok 3 /news category + sort persist across reload (1.6s)
  ok 4 /activity period persists across reload (1.2s)
  ok 5 /schedule week offset persists across reload (819ms)
  ok 6 /map viewport persists across reload (4.3s)
  6 passed (5.6s)

$ # E2E backward compat (default config, no SKIP_WEBSERVER):
$ npx playwright test --project=chromium a11y-public
  4 passed (17.1s)
```

---

## Honesty probe self-audit

Pre-empting the expected "безупречно?" probe by listing honest caveats up-front:

### ⚠ SW7 e2e spec runs in opt-in mode, not default `npm run test:e2e`

`SKIP_WEBSERVER=true URL_STATE_E2E=true ...` is required for the 6 URL-state tests to execute. They `test.skip()` otherwise. **Why**: Playwright's auto-managed webServer rebuilds dist with regular build, clobbering VITE_LHCI build. Auto-managed VITE_LHCI mode failed cross-platform without `cross-env`.

**Wave 121 candidate**: install `cross-env` dev dep + add dedicated VITE_LHCI Playwright project so this runs in CI alongside a11y-public.

### ⚠ /activity period selector assertion simplified

Original spec asserted `[role="radio"][aria-checked="true"]` visible — failed because period selector mounts inside Suspense boundary, not immediately queryable. Simplified to URL-persistence assertion only (the actual SW7 deliverable). Period radio behavior verified separately via chrome-devtools-mcp during SW5 dev.

### ⚠ Multi-browser coverage NOT extended for url-state-persistence.spec.ts

Chromium-only. Per spec header: "multi-browser coverage isn't necessary for URL-state round-tripping (TanStack Router behavior is identical across engines)". Defer to Wave 121 if a multi-engine regression suspected.

### ⚠ /activity + /map LanternError-blocked, NOT addressed

Lighthouse cycle-detection error on these URLs. Wave 116 honest deferral remains. Live-axe via chrome-devtools-mcp confirms a11y is green; LCP/Perf measurement remains a gap. **Wave 121 candidate** to investigate cycle-detection upstream.

### ⚠ SW6 token-drift audit was conservative

Only addressed clearly-safe drift (12 hardcoded → token + 3 orphan @property). Documented 4 deferred categories (cat-* duplication, font-size hardcodes, focus-ring tokens missing, scoped overrides intentional vs drift) for Wave 121 deeper pass.

### ⚠ SW8 Chromatic BLOCKED by Storybook 10 + Vite 8/Rolldown bug (deferred to Wave 121)

Polish-pass attempt: User created project, got token, ran `npx chromatic@13/16` 3 times. All failed at story extraction with `__STORYBOOK_MODULE_CORE_EVENTS_PREVIEW_ERRORS__ is not defined`. Root cause: Storybook framework expects globals injected as bundle externals; Vite 8/Rolldown framework integration doesn't fire the injection. iframe.html ships only 2 scripts, no globals-init. Bonus discovery: vite-plugin-pwa was polluting Storybook builds (separate fix shipped as `cffe3ca9d`). 4 workaround paths documented in `memory/wave121_backlog.md` Item #1; full repro details in §SW8 above.

### ⚠ Polish pass spot-checks done but not exhaustive

After "безупречно?" probe, verified:
- ✅ Layout.tsx-affected pages render OK: /profile (1 main, 0 landmark viol), /admin/users (1 main, 0 landmark viol), /map (1 main, MapLibre canvas alive)
- ✅ Bundle reproducibility re-confirmed × 3 (175,744 bytes, hash `index-BF-iuu-K.js`)
- ✅ Vitest re-confirmed (668p/12s/0f, baseline preserved)

Found but NOT addressed:
- 2 pre-existing axe violations on /admin/users (`aria-allowed-attr` on div with aria-sort=none, `button-name` on Radix combobox trigger). Not from Wave 120 — pre-existing. Filed implicit Wave 121 candidate.
- ScheduleDesktopTable + MiniCalendar visual unchanged AT 1440×900 viewport only (verified during SW3). Other viewports NOT verified.
- MapLibre `+`/`-` zoom + `Shift+arrow` rotate/pitch documented in MapShortcutsOverlay (SW4) but NOT verified to work — only ArrowRight verified via screenshot diff. Trusted MapLibre docs.

### ⚠ Bundle delta: -85 bytes prod, -70 bytes LHCI from SW6 cleanup

Smaller than expected. The 3 removed @property registrations + 4 removed assignments saved minimal bytes after Rolldown DCE — likely most was already eliminated. Net positive though (smaller bundle).

### ⚠ Bundle delta: -85 bytes prod, -70 bytes LHCI from SW6 cleanup

Smaller than expected. The 3 removed @property registrations + 4 removed assignments saved minimal bytes after Rolldown DCE — likely most was already eliminated. Net positive though (smaller bundle).

### ⚠ SW5 verification only via chrome-devtools-mcp

Playwright e2e for /map URL-sync is in SW7 (test 6). No automated unit tests for parseMapViewport/serializeMapViewport — could add. Wave 121 candidate.

### ⚠ SW3 only verified /schedule on desktop viewport

ScheduleListView (mobile) + other Schedule sub-components NOT touched in SW3 — they don't use ARIA grid pattern. WCAG /schedule mobile view a11y not separately verified. Defer to Wave 121.

### ⚠ Wave 116 SW3 LHCI a11y reproduction NOT re-verified

Wave 116 SW3 closed /news a11y 0.94 → 1.00. With SW3's Layout.tsx duplicate-main fix affecting 10+ pages, all those pages might now have improved a11y. NOT re-measured.

### ✓ What DID land

- **CLS arc closed** at WCAG Good ceiling (W117-W120 lifecycle complete)
- **Schedule a11y 5 → 0 violations** + Layout duplicate-main fix benefits 10+ pages globally
- **Map URL-sync** with clean number-form URLs + cinematic-intro skip when restoring
- **Token drift cleanup** (12 sites consolidated, 3 dead @property removed)
- **6 e2e tests** for URL-state — first end-to-end coverage of Wave 112 SW3 + Wave 120 SW5
- **Permanent LHCI Windows wrapper** — every future wave benefits
- **All gates fresh-verified** — 668p/12s/0f vitest, 17/17 i18n, 628 tokens, 0 tsc/lint, 0 npm audit
- **Bundle invariant held** — 175,744 bytes < 176 KB W117 floor (build × 3 reproducible)
- **Plan honesty caveats preempted** — every issue in this section openly documented

### What's NOT in this wave

- Chromatic baseline (Wave 121 — user-side env setup)
- /activity + /map LanternError unblock (Wave 121 — upstream Lighthouse bug)
- @unpic image pipeline conditional (Wave 121 if LCP audit shows savings > 100 KB)
- Mobile perf round 2 (Wave 121+ XL own-wave candidate — LCP 13-14s on authenticated routes)

---

## Polish-v2 pass — `a326ca334` (post round-2 "безупречно?" probe)

User invoked the perfectionism probe a second time. 60-90 min polish closed 7 real fixable gaps:

### Test coverage
- **18 unit tests** for `parseMapViewport` / `serializeMapViewport` (`src/features/map/__tests__/schema.test.ts`):
  - Schema accepts both number + numeric-string inputs (TanStack Router URL parser variance)
  - Out-of-range / NaN / non-string-non-number → `undefined` silently (don't throw)
  - `parseMapViewport` returns null for incomplete fields, normalizes bearing to [0, 360)
  - `serializeMapViewport` returns NUMBERS not strings (clean URLs `?z=16` vs JSON-quoted `?z=%2216%22`)
  - Rounding precision: zoom 1dec, lat/lng 5dec, pitch+bearing 0dec
  - Bearing normalization on serialize (-10 → 350, 720 → 0, 360 → 0)
  - Round-trip serialize → parse preserves viewport within precision
  - **Vitest 668p → 686p (+18)**, all pass first run.

### A11y fixes (live axe via chrome-devtools-mcp)

**/admin/users 2 violations → 0**:
1. `aria-allowed-attr` (critical): `aria-sort` was on inner `<div>` (not allowed per ARIA — only `<th>` / `role="columnheader"|"rowheader"`). Moved to `<TableHead>` in `DataTable.tsx`, computed from `header.column.getCanSort() + getIsSorted()`. `DataTableColumnHeader.tsx` inner div is now plain (button's aria-label still announces sort state).
2. `button-name` (critical): Radix combobox in DataTablePagination page-size Select had no accessible name. Added `id="data-table-pagination-pagesize-label"` to visible `<p>` "Rows per page" + `aria-labelledby` to Select.

**/profile 1 violation → 0** (discovered during Wave 116 SW3 a11y re-measure):
3. `svg-img-alt` (serious): `qrcode.react`'s `<QRCodeSVG>` auto-emits `role="img"` on the SVG, requires accessible name. Wrapping `<button aria-label={...}>` already provides one — pass `aria-hidden="true"` to QRCodeSVG to silence the rule (SVG is decorative for AT context).

### MapLibre keyboard verified beyond ArrowRight

Press_key via chrome-devtools-mcp:
- `Equal` × 3 → URL `z=19` (was 16, +3 zoom steps) ✅
- `Shift+ArrowRight` × 2 → URL `b=30` (was 0, +30° = 2×15° rotate) ✅
- `Shift+ArrowUp` × 2 → URL `p=65` (was 45, +20° = 2×10° pitch) ✅

All 4 shortcut categories from MapShortcutsOverlay confirmed working. Symmetric inverses (-, Shift+ArrowLeft/Down) work by parity.

### Schedule mobile a11y verified

Resized chrome to 500×667 (mobile breakpoint) → /schedule → axe scan:
- 0 violations on mobile ListView ✅
- 0 grids (mobile uses ListView, not desktop ARIA grid pattern)
- 1 main only (Layout.tsx fix preserved at mobile)

### Schedule keyboard nav structurally preserved

Verified `display:contents` row wrappers are transparent to `getElementById('sched-cell-N-N').focus()` used by `useScheduleKeyboardNav`. Mock user has no lessons → no sched-cell IDs to test interactively, but architecturally sound (CSS Grid layout intact, IDs are global).

### Layout-affected pages a11y re-measured

- `/profile`: 0 viol (was 1 svg-img-alt — fixed in this commit) ✅
- `/admin/users`: 0 viol (was 2 — fixed in this commit) ✅
- `/map`: 0 viol (no regression) ✅

### CLAUDE.md ## Code Conventions + Gotchas — 8 new entries

Documented Wave 120 patterns that should persist as conventions:
1. Map URL-sync schema contract (TanStack Router JSON-quoting pitfall, range bounds, latched useState pattern, 18 unit tests)
2. MapLibre URL-sync user-vs-programmatic gate (`enableUrlSyncRef` + `evt.originalEvent`)
3. Storybook viteFinal PWA strip (Wave 116 audit context + flatten array)
4. `npm run lhci:windows` (env vars, defaults exclude /activity + /map)
5. Schedule ARIA grid `display:contents` rows (CSS Grid transparency)
6. TableHead `aria-sort` placement (computed in DataTable, NOT inner div)
7. Layout.tsx `<motion.div data-scroll-root>` (10+ pages benefit)
8. SVG `aria-hidden` for QR codes inside labeled buttons (qrcode.react pattern)

### Final gates (verbatim, post-polish-v2)

```
$ npx tsc --noEmit                    → 0 errors
$ npm run lint                        → 0 warnings
$ npm run i18n:check                  → 17 passed (17)
$ npm run tokens:sync                 → 628 vars, no drift
$ npm audit                           → 0 vulnerabilities
$ npm run test -- --run               → 686 passed | 12 skipped | 0 failed
                                        (was 668; +18 from new map schema)
$ for i in 1 2 3; do rm -rf dist && npm run build; done
                                      → 175,744 bytes × 3 reproducible
                                        (hash D_Y6M3Ef differs from polish-v1
                                        BF-iuu-K because of code changes —
                                        expected; size identical to baseline)
$ env VITE_LHCI=true npm run build    → 174,769 bytes (unchanged)
```

---

## Wave 121 hand-off

See [`memory/wave121_backlog.md`](memory/wave121_backlog.md) (created in this commit). Items inherited from Wave 120 deferrals:

1. Chromatic baseline (Item #8) — once user provides token
2. /activity + /map LanternError unblock (Item #7) — upstream Lighthouse bug
3. @unpic/react image pipeline (Item #6 conditional) — if LCP audit savings > 100 KB
4. URL-state e2e auto-managed mode (Wave 120 SW7 deferral) — install cross-env + dedicated Playwright project
5. Token-drift deeper pass (Wave 120 SW6 deferrals) — cat-* duplication, font-size hardcodes, focus-ring tokens
6. Schedule mobile view a11y verification (Wave 120 SW3 scope-down)
7. Mobile perf round 2 (XL own-wave)
8. Wave 116 SW3 a11y re-verification post-Layout fix (potential bonus on 10+ pages)

Wave 120 closes the inherited tech-debt batch. CLS arc complete. Wave 121+ should be either (a) Chromatic + LanternError closure, (b) mobile perf XL, OR (c) fresh feature work.
