# AUDIT — Wave 194 (HARD-tier Storybook story batch + Chromatic verification)

**Date**: 2026-05-28
**Branch**: `egorribun` · **PR**: [#1126](https://github.com/egorribun/university_ecosystem/pull/1126)
**Scope**: User-chosen **B + F combo** (Q0 options 2 + 4) → **B** continue the W193 "D scope" with non-backdrop stories that need data/context mocks; **F** Chromatic visual verification. Q1 answer "давай всё. 1-4" → **all four component groups**. 54th consecutive wave preserving brainstorming + Phase 1 Explore + Phase 3 Review + W141 anti-pattern discipline.

---

## Headline

W193 brought backdrop visual-regression coverage to 11/11. W194 extends Storybook coverage to the **9 highest-complexity non-backdrop components** — the ones the opening prompt flagged "HARD tier" because they need data/context mocks rather than copy-paste from a backdrop factory. Unlike W193's decorator-only stories, each W194 story constructs realistic mock data or a tsc-typed mock object.

Discoverable Storybook story files: **68 → 77** (+9). Total index entries **374** (299 stories + 75 autodocs). The **Map-marker group (group 4) was the genuine risk** — each `<Marker>` requires a live MapLibre GL `<Map>` (WebGL) with no prior art for maplibre-in-Storybook. A **spike-first** discipline (BuildingMarker built + verified before POI/Event) confirmed maplibre inits in the real-Chromium Storybook iframe, so the group shipped fully rather than honest-deferring.

**4 SW story commits + this SW5 audit = 5 commits.** Bundle main JS + server.js **byte-identical (filename + content) to W193** across 3 fresh builds — the 9 unbundled stories leave the PROD bundle completely untouched. vitest **1270p/12s/0f** preserved exactly across all 4 story SWs.

---

## SW breakdown

### SW1 — `0907ab4f6` `feat(wave194-sw1-activity-viz-stories)` (3 files, +328)
- NEW `features/activity/components/{ActivityTrendChart,ActivityBarChart,ActivityHeatmap}.stories.tsx`. 10 story variants + 3 autodocs.
- **Shared `themed(dark)` decorator** wraps `.activity-theme` (for `--activity-*` tokens that `.activity-chart-card` reads) + **`LazyMotion features={domAnimation}`**: TrendChart/BarChart use framer-motion `m.polyline`/`m.rect`, and `preview.tsx` provides NO LazyMotion (verified by Read) — mirror of AppProviders W124 SW1. Heatmap omits LazyMotion (no `m.*`) but keeps `.activity-theme` for the `--activity-heat-*` tokens + `useLanguage()` (satisfied by the global preview LanguageProvider).
- `chromatic: { pauseAnimationAtEnd: true }` settles the m.polyline pathLength draw-in for deterministic snapshots.
- TrendChart: Default (7pts) / TwoPoints (min line) / SinglePoint (<2 → `noChartData` fallback) / DarkMode. BarChart: Default (mixed graded/100 + ungraded) / Empty (fallback) / DarkMode. Heatmap: Default (90d dense) / Sparse (30d) / DarkMode — deterministic counts per relative-day offset (W184 SW2 jitter, no `Math.random`); grid is today-relative by construction (Chromatic collect-only auto-accepts the daily drift).
- **Gates**: tsc 0, lint 0, build-storybook SUCCESS 9.39s (344 entries), vitest 1270p/12s/0f.

### SW2 — `9b4da0971` `feat(wave194-sw2-auth-form-stories)` (2 files, +280)
- NEW `components/auth/{LoginCredentialForm,MfaChallengeView}.stories.tsx`. 9 story variants + 2 autodocs.
- Both components consume their `useLoginForm()` / `useMfaFlow()` return as a single `form` / `mfa` **prop** (LoginCredentialForm.tsx:11-12, MfaChallengeView.tsx:10-16) — they never call the coupled hook, so each story supplies a **tsc-typed mock object** (no real auth coupling beyond the global RouterProvider for the `<Link>`s).
- `LoginHarness` calls a real `useForm<LoginValues>()` + real `useState` for caps/showPassword (the component uses functional updaters), assembles the 19-field `ReturnType<typeof useLoginForm>` mock, spreads scalar overrides. Variants: Default / WithError / WithEmailSuggestion / NoPasskey / DarkMode.
- `buildMfa()` returns a `ReturnType<typeof useMfaFlow>` mock; otp/webauthn challenges are `MfaMethodChallengeOut` objects (method + challenge_token + challenge_expires_at required — confirmed at types.gen.ts:1069). Variants: OtpOnly / WebAuthnAndOtp / GeneralError / DarkMode.
- **§Honesty**: MfaChallengeView renders a live `ParticleAuthBackground` rAF canvas (its VITE_E2E_MODE short-circuit is test-only) → non-deterministic Chromatic orb background; collect-only mode (W112 SW1) auto-accepts; the glass card UI in front is stable.
- **Gates**: tsc 0 (mock shapes tsc-clean, no cast needed), lint 0, build-storybook SUCCESS (355 entries), vitest 1270p/12s/0f.

### SW3 — `f6685fba0` `feat(wave194-sw3-messageinput-story)` (1 file, +77)
- NEW `components/messenger/MessageInput.stories.tsx`. 3 variants (Default / Mobile / DarkMode) + autodocs.
- Single `onSend` prop, zero context. selectedFiles/text/attach-menu are interaction-driven internal state → static stories render the empty composer (attachment previews + active violet send-gradient surface via live canvas interaction). Decorator adds LazyMotion (`m.*` + AnimatePresence) + `.messenger-theme` scope (`--messenger-*` send-button tokens, W181 SW1) over a `bg-msg-chat` backdrop.
- **Gates**: tsc 0, lint 0, build-storybook SUCCESS (`bg-msg-chat` utility valid), vitest 1270p/12s/0f.

### SW4 — `4b6ebcdc5` `feat(wave194-sw4-map-marker-stories)` (3 files, +300) — SPIKE-FIRST
- NEW `components/map/{BuildingMarker,POIMarker,EventMarker}.stories.tsx`. 12 variants + 3 autodocs.
- Each marker is a `react-map-gl/maplibre` `<Marker>` requiring a live MapLibre GL `<Map>` context → a shared minimal `<Map>` decorator wraps each story with an **EMPTY offline mapStyle** `{ version: 8, sources: {}, layers: [] }` (typed `StyleSpecification`) so Storybook needs **NO network tile fetch**; markers are HTML overlays positioned once maplibre inits. Coord gotcha **FIX-100-01** respected (`geoCoords [lat,lng]` → `longitude={[1]} latitude={[0]}`). Real data: `getCampusBuildings("en")[0]` + `CAMPUS_POIS`; hand-crafted `MapEvent` mock.
- **SPIKE (real-Chrome Playwright on served storybook-static, scratch `wave194-spike.mjs` deleted post-verification) PASSED for all 3 marker types**: maplibre `<Map>` inits (`.maplibregl-canvas` present), pins render + visible, **0 console errors**. EventMarker PopupOpen verified the TanStack `<Link to="/events/$id">` renders against the global preview memory-router (`popupCount: 1`, 0 errors) — visually confirmed amber pin + localized popup card. **Wave 147 SW5's HEADLESS canvas-never-visible concern did NOT apply** — the Storybook iframe is real Chromium with WebGL.
- BuildingMarker: Default / Selected / Highlighted / PopupOpen / DarkMode. POIMarker: Default (transport) / Food / PopupOpen / DarkMode. EventMarker: Default / PopupOpen / DarkMode.
- **Gates**: tsc 0 (maplibre `StyleSpecification` + `getCampusBuildings` + `CAMPUS_POIS` + `MapEvent` types resolve), lint 0, build-storybook SUCCESS 10.08s (maplibre-gl in build cleanly — W116 SW-Stretch workbox cap handles it), vitest **1270p/12s/0f** (`@storybook/addon-vitest` does NOT run the map stories in jsdom — the W124 SW3 WebGL-in-jsdom risk did NOT materialize).

### SW5 — (this commit) audit + F verification + housekeeping
- NEW `docs/audits/AUDIT_WAVE194.md` (this file).
- N+3 rotation: `git mv docs/audits/AUDIT_WAVE191.md docs/audits/archive/AUDIT_WAVE191.md` → active waves **W192/W193/W194**.
- CLAUDE.md ## Audit Trail row + 1 NEW Gotcha (maplibre-in-Storybook minimal `<Map>` + empty offline mapStyle decorator pattern).
- `docs/audits/INDEX.md` updates (W194 → active, W191 → archive, rotation-history line).
- MEMORY.md compaction (W191 verbose → one-liner + trimmed over-bloated W193 row) + W194 row (`.claude` profile).
- NEW `memory/wave194_backlog.md` + `memory/wave195_opening_prompt.md` (`.claude` profile).
- **F (Chromatic)** — post-push: the Chromatic CI run on the W194 HEAD captures the 9 new story baselines (collect-only mode auto-accepts new baselines). Build URL + snapshot/story counts handed to the user for the dashboard spot-check (the dashboard review is user-side — collect-only mode does not block CI).

---

## Bundle (empirical, 3 fresh `rm -rf dist && npm run build`)

| Artifact | W194 (× 3 identical) | vs W193 baseline |
|----------|----------------------|------------------|
| main JS | `index-B8BD2TjY.js` 180,273 b sha `1bff1fd7…c97` | **BYTE-IDENTICAL** (filename + content) |
| server.js | 24,024 b sha `fb8a5860…8631` | **BYTE-IDENTICAL** (filename + content) |

The 9 `.stories.tsx` files are picked up only by Storybook's glob (`.storybook/main.ts:15`), NOT by the Vite app entry graph — so the PROD bundle is completely untouched. W193's filename even stayed `B8BD2TjY` (W193's own glob-widen had shifted it `CGBUMlAV → B8BD2TjY`; W194 added no further perturbation). **W134 SW3 → W193 ≥52-wave LOCAL-MACHINE BYTE-IDENTICAL invariant EXTENDS to ≥53-wave.** Tree-shake invariant ✓ (0 `lhci-mock-user` in PROD assets). Map-marker stories pull maplibre-gl into the **Storybook** build only, not the prod app bundle.

---

## Gates (end-of-wave)

- tsc 0 (× 4 SW) · eslint `--max-warnings=0` 0 (× 4 SW)
- vitest **1270 passed / 12 skipped / 0 failed** (W193 baseline preserved EXACTLY — `.stories.tsx` not registered in the default vitest project; map stories not run in jsdom)
- build-storybook SUCCESS — **77 unique story files** (68 + 9), 374 index entries (299 stories + 75 autodocs)
- npm audit **0 production vulnerabilities** (W191 baseline preserved)
- i18n parity **18/18** (no new keys — stories reuse component i18n)
- Cargo.lock **no drift** after Build × 3
- Build × 3 main JS + server.js **BYTE-IDENTICAL** to W193
- Map-marker spike: maplibre `<Map>` WebGL inits + pins visible + 0 console errors (real-Chrome Playwright, all 3 marker types)

---

## §Honesty trajectory: 0-2 → 0-2 OPEN

Only the 2 structural-by-design W134 non-goals carry forward (unchanged): **W134 §H#2** bundle-delta recording-only + **W134 §H#10** /messenger Phase 5 SSR by-design (per W161 SW2). The 9 new stories are net-positive coverage, NOT §Honesty closures.

NEW W194 caveats (characterization-only, not blocking, by-design):
1. **MfaChallengeView particle-canvas Chromatic noise** — the live `ParticleAuthBackground` rAF canvas makes the MFA story's orb background non-deterministic for Chromatic snapshots. Collect-only mode (W112 SW1) auto-accepts; the card UI is stable. By-design (the component hard-renders the canvas; not modified for a story).
2. **ActivityHeatmap today-relative grid** — the component builds its date grid from `new Date()`, so the heatmap grid + month labels drift by calendar day. Counts are deterministic per relative-day offset; collect-only auto-accepts the daily drift.
3. **F is half user-side** — Chromatic build URL + counts gathered post-push; the visual dashboard review needs the user's Chromatic login.

---

## W141 anti-pattern compliance

- **#1 STRICT 1-iter per SW** → **104th-108th vindications** (5 SW each landed in 1 iter; SW4's spike-first honest-defer fallback was UNUSED because the spike passed — discipline held without needing the defer).
- **#3 Phase 3 verify-before-write** → **117th-119th vindications**: Read of `preview.tsx` confirmed it lacks LazyMotion (prevented an `m.*` runtime throw on the activity charts); Read of LoginCredentialForm/MfaChallengeView confirmed they consume the hook-return as a prop (not the coupled hook — collapsed the "auth coupling" difficulty); Read of types.gen.ts:1069 confirmed the exact `MfaMethodChallengeOut` shape before writing the mock.
- **#4 closures after empirical verification** → **48th vindication**: bundle invariant attributed AFTER Build × 3 sha match; Map-marker group shipped AFTER the real-Chrome spike + screenshot visual confirmation (not after compile alone).
- **#15 (ARCHIVED W159 SW4) preserved 89th-93rd consecutive waves** — all 5 W194 commits fired the W156 SW4 husky pre-commit chain cleanly (lint-staged + prettier --write + eslint --fix + detect-secrets + Python-2 except check). NO `--no-verify`.

**0 NEW (z) discoveries** from W194 SW execution proper (spike-first prevented the Map-marker cascade) — extends the low-(z) streak to **29 of last 29 waves (W145-W194)**. **0 NEW anti-patterns** (14-pattern register stable post-W159 #15 archival).

---

## NEW Gotcha (added to CLAUDE.md ## Gotchas)

**MapLibre markers in Storybook need a minimal `<Map>` decorator + empty offline mapStyle** (W194 SW4): `react-map-gl/maplibre` `<Marker>` components throw without a `<Map>` ancestor. Wrap each marker story in `<Map initialViewState={{longitude, latitude, zoom}} mapStyle={{version:8, sources:{}, layers:[]}} attributionControl={false} style={{width:"100%",height:"100%"}}>` inside a fixed-size container; the empty style avoids network tile fetches (markers are HTML overlays positioned once maplibre inits). Import `maplibre-gl/dist/maplibre-gl.css` + type the empty style as `StyleSpecification` from `maplibre-gl`. Verified rendering in the real-Chromium Storybook iframe (Wave 147 SW5's headless canvas-never-visible issue does NOT apply). `@storybook/addon-vitest` does NOT run these stories in jsdom (vitest count unchanged), so no WebGL-in-jsdom failure.

---

## W195+ candidates

- **A) Maintenance mode** (CANONICAL DEFAULT per W171 Lesson #1) — no real production trigger pushing; fires on a real trigger or chosen scope.
- **B) Remaining non-backdrop stories** — Profile Header/Editor, Navbar, MobileBottomNav (HARD-tier, context mocks).
- **C) Path E XL messenger backend wave** (~6-10h) — read_at + Reaction table + voice_message_url migrations + endpoints + ws-hub types per W125 Phase 5; backend EMPIRICALLY NOT READY per W190 pre-flight (`Message.read_status: bool` only). W196 picks up the UI.
- **D) Lighthouse #17021 monitoring tick** — next window W196-W200 per W192 SW1 calibration.
- **F) Chromatic visual verification deep review** — once the W194 baselines land, review the 12 new map/auth/messenger/activity story snapshots on the dashboard.

---

## Polish-v1 (post «безупречно?» probe)

A self-audit pass surfaced 2 claims made at W194 close that had NOT been empirically verified. Both closed here with **zero code fixes** — the wave was correct as committed:

1. **CI `Matrix Expansion` GREEN — CONFIRMED** (was "expected green / in_progress" at SW5 commit time). All 6 workflows on HEAD `204e1c524` are `success`: Dependency Review + Go Lint & SBOM + **Chromatic** (Build 221: 77 components / 299 stories / 299 snapshots, "Build passed") + Wave189 Unauthed Smoke + **CI - Matrix Expansion**; Auto-merge skipped. Strongest W141 #4 closure (attributed AFTER empirical CI verification, not assumption).
2. **All 9 stories runtime-rendered, not just build-verified** — the 6 non-map stories (Activity viz ×3 + Auth forms ×2 + MessageInput) were `build-storybook`-verified + index-registered at close but never rendered in a browser. Re-served storybook-static + a real-Chrome Playwright pass confirmed all 6 render with **0 console errors** + key selectors present: ActivityHeatmap 95 cells; ActivityTrend/BarChart svg present; LoginCredentialForm `#login-submit` (the mock `form` object drives `register`/`control`/`formState` without throwing); MfaChallengeView `.glass-high-fidelity` card renders off the mock `mfa` object + live particle canvas, no throw; MessageInput `#chat-message-input`. Combined with the SW4 Map-marker spike, **9/9 W194 stories are now empirically runtime-verified**.

Artifact integrity re-checked: working tree clean, AUDIT_WAVE194.md complete (129 lines incl this section, long-line paragraphs), MEMORY.md 24,343 b after this polish-v1 row append (under the 24,400 ceiling; 57 b headroom — W195 SW1 compacts per its opening prompt). **§Honesty 0-2 OPEN unchanged** — both audited gaps were verification-only (confirmed fine; no NEW caveats). W141 #4 → **49th vindication** (the probe drove an empirical self-audit, not reassurance).
