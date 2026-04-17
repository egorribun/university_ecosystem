# Wave 112 — Frontend Production Audit (April 2026)

**Branch**: `egorribun`
**Commits**: 6 (`d633ec3ef` → `f57d69420`)
**Files touched**: ~115 (~98 in code commits, +6 in docs)
**Net diff**: +700 / −150 lines (excluding the sync-tokens regeneration of `tokens.ts`)
**Bundle**: main chunk 291 KB / 84 KB gzip (under 500 KB CI gate, no regression)
**Verification**: `tsc --noEmit` 0 · `eslint --max-warnings=0` 0 · `i18n:check` 17/17 · `vite build` 8.3s · all touched tests green

This wave is the first cross-page audit since the project began the polish cycle (Waves 46–111). The previous 65 waves were strictly local — one page, one category, one commit — which was correct for incremental quality but left **architectural drift** between pages invisible. Wave 112 is the first time someone looked at all six target surfaces (dashboard, news, schedule, events, activity, map) at once.

## Sub-wave summary

| # | Commit | Theme | Files |
|---|---|---|---|
| 1 | `d633ec3ef` `feat(wave112-foundation)` | TS strict (`noUncheckedIndexedAccess`), Playwright multi-browser, CI Lighthouse + i18n + Chromatic gates, `useURLState` hook, Map FeatureErrorBoundary, CLDR-aware i18n parity | 62 |
| 2 | `4017e691b` `feat(wave112-activity)` | `src/components/activity/*` → `features/activity/` (17 git mv), `ActivityFeature` orchestrator, TanStack Query v5 `queryOptions()` factory, `sync-tokens.mjs` infra fix, 7 missing motion tokens | 26 |
| 3 | `7ddcc46af` `feat(wave112-url-sync)` | News + Activity URL-state via `useURLState`, Valibot `validateSearch` schemas | 6 |
| 4 | `20f660b56` `feat(wave112-schedule-url)` | Schedule `?w=` URL-state via `useScheduleURLSync` bridge hook (preserves Zustand API + 15 unit tests) | 4 |
| 5 | `be8dc97de` `feat(wave112-a11y)` | Map `aria-roledescription` + sr-only keyboard hint, Activity Trend/Bar charts sr-only data tables, public-route axe-core e2e | 8 |
| 6 | `f57d69420` `perf(wave112-perf)` | SmartImage prop ordering — callers can now override `loading="eager"` + `fetchpriority="high"` for above-the-fold LCP images | 1 |

## What changed by category

### Architecture / cross-page consistency

| Page | Before Wave 112 | After Wave 112 |
|---|---|---|
| Dashboard | custom `useDashboard*` hooks | unchanged (no shared filters to URL-sync) |
| News | TanStack Query + factory keys, **local-state filters** | + URL-sync (`q/cat/sort`) via `useURLState` |
| Schedule | custom `useScheduleData` + Zustand `useScheduleUIStore`, **no URL state** | + URL-sync (`w`) via `useScheduleURLSync` sync-bridge |
| Events | TanStack Query + URL-sync (gold standard since Wave 76) | unchanged |
| Activity | **bare axios + useState/useEffect**, **no `features/` folder**, no ErrorBoundary | TanStack Query v5 + `features/activity/`, `FeatureErrorBoundary`, URL-sync (`p`) |
| Map | `features/map/`, no top-level ErrorBoundary | `FeatureErrorBoundary` wrap, `aria-roledescription`, sr-only keyboard hint |

**Outcome**: 4 of 6 pages now persist filters/period/week through refresh and share-link. Dashboard has no filter state to sync; Map has its own zoom/position model where URL-sync is a separate UX call (out of scope, see "Followups").

### Tooling

| Item | Before | After |
|---|---|---|
| `noUncheckedIndexedAccess` | off | on (142 fallouts fixed) |
| Playwright projects | chromium only | chromium + firefox + webkit + iPhone 15 |
| Lighthouse CI | optional flag-gated, 2 URLs | always on, 8 URLs (home + login + 6 target pages), mobile preset, thresholds 90/95/95/90 (Performance still `warn` until Wave 113 perf pass) |
| i18n parity | manual `npm run i18n:check`, plurals false-positive | blocking CI gate, CLDR-aware (RU `_few/_many/_zero/_two` allowed when EN has `_one/_other`) |
| Visual regression | Storybook only | Chromatic CI workflow added (gated on `CHROMATIC_PROJECT_TOKEN` repo var; collect-only until SW6) |
| Public-route a11y | `accessibility.spec.ts` `describe.skip`'d on broken mock-login | new `a11y-public.spec.ts` runs `axe-core` on `/login` + 404 in light + dark themes (4 cases, all passing critical+serious filter) |

### Pre-existing infrastructure bug fixed (caught en route)

`scripts/sync-tokens.mjs` was reading **only** `src/styles/partials/` (3 files) and ignoring `src/styles/tokens/` (9 files). Each `npm run build` invokes it via `run-build.mjs:52` and silently truncates `src/theme/tokens.ts` from ~193 lines to ~62. The full file persisted in git only because developers happened not to commit the regenerated truncated version. CI's `npm run tokens:sync && git diff --exit-code` gate would have caught it eventually but did not in the recent past — likely because the sync didn't actually re-run on those CI runs.

Fix: extend `extractVariablesFromDir` to scan both directories. Result: 6 → **630 CSS variables** correctly mirrored to TypeScript. Also added 7 motion tokens that consumers (`FadeIn`, `ScaleIn`, `animations.ts`, `motion.ts`, `ChatArea`) were referencing without backing CSS:

  - `--motion-duration-medium: 0.45s`
  - `--motion-duration-typing: 1.4s`
  - `--motion-duration-shimmer: 1.6s`
  - `--motion-duration-pulse: 1.8s`
  - `--motion-duration-pulse-slow: 2s`
  - `--motion-duration-aura: 14s`
  - `--motion-nav-transition: 1.2s`
  - `--motion-stagger-medium: 0.06s`

### Accessibility (WCAG 2.2 AA)

| Surface | Improvement |
|---|---|
| MapLibre container | `aria-roledescription="Campus map"` + sr-only keyboard hint paragraph (WCAG 2.1.1, SC 4.1.2) |
| Activity SVG charts | sr-only `<table>` data mirror with `<caption>` + `scope="col"/"row"` (WCAG 1.1.1, 1.3.1) — Trend chart and Bar chart |
| Activity Heatmap | unchanged — already had per-cell `role="img"` + `aria-label` (WCAG-correct shape for calendar) |
| Public e2e gate | `axe-core` blocks any critical/serious violations on `/login` + 404 in both themes |

Already in place from earlier waves (verified, no work needed):

  - skip-to-main link in `MainLayout` (Wave 35)
  - Map `role="application"` + `aria-label` (Wave 100)
  - ActivityHeatmap per-cell `role="img"` (Wave 86)
  - Activity period selector `role="radiogroup"` (Wave 84)
  - News/Events keyboard navigation (Wave 57/76)
  - ConfirmDialog ARIA, TextField `aria-describedby`, ActionMenu focus rings (Wave 35)

### Performance

  - SmartImage: `loading="lazy"` + `decoding="async"` defaults moved BEFORE `{...rest}` so callers can override for LCP-critical images. Zero behavioural change for current callers.
  - Bundle composition documented (see baseline below) — no new dynamic imports needed in this wave; existing splits (maplibre-gl, jspdf, html2canvas) verified working.

## Bundle baseline (post-Wave 112)

```
maplibre-gl                1025 KB / 272 KB gzip — Map page lazy
index.esm-DlgO4ZKT          465 KB             — keyboard layout DB
                                                 (AZERTY/QWERTY data),
                                                 candidate for Wave 113
                                                 lazy-split investigation
jspdf.es.min                400 KB             — Activity export, lazy
index-*.css                 398 KB /  57 KB gzip — Tailwind + features
index-* main chunk          291 KB /  84 KB gzip — under 500 KB gate
html2canvas                 200 KB             — export, lazy
vendor-react                182 KB             — expected baseline
vendor-ui                   163 KB             — Framer Motion + Lucide
vendor-sentry                75 KB             — isolated chunk
```

## Token-drift audit (no-op finding)

A side-by-side comparison of the six page-scoped token files (`tokens/{dashboard,news,schedule,events,activity,map}.css`) found:

  - **Orb pattern is consistent**: 10/12/8/6% in light, 16/18/14/10% in dark across all five pages that have orbs (Dashboard has its own decorative system). Only the hue varies intentionally — amber for events, sky for news, emerald for activity, teal for map.
  - **Page-scoped shadows are intentional architectural variation**: Activity (Wave 84+) and Map (Wave 88+) introduced their own `--*-card-shadow` tokens; Events / News / Schedule use shared `--shadow-md` / `--shadow-premium-lift` from primitives. Both patterns are valid; no refactor warranted.
  - **Chart inline empty-state ≠ page EmptyState**: `ActivityTrendChart` / `ActivityBarChart` use a 120px inline "no data" message rather than the 28rem-wide `EmptyState` primitive. This is correct per design — `EmptyState` is a page-level primitive, not a chart-card primitive.

## Followups recommended for Wave 113+

1. **`index.esm-DlgO4ZKT.js` (465 KB) lazy-split investigation** — virtual-keyboard layout database is loaded sync. Likely from a TOTP / OTP entry library. Worth mapping to its source and lazy-splitting if not on critical path.
2. **Lighthouse perf pass** — Wave 112's LHCI thresholds keep Performance at `warn` (a11y/bp/seo are gated). A focused Wave 113 should profile each of the six pages, fix the worst offenders, then flip Performance to `error`.
3. **Authenticated 6-page e2e a11y sweep** — `accessibility.spec.ts` is `describe.skip`'d on a mock-login timeout. Either fix the mock or rebuild on top of `useMockApi` so the public-route axe-core gate covers all six target pages.
4. **Image pipeline (`@unpic/react` or similar)** — if Wave 113's LHCI shows "Serve images in next-gen formats" > 100 KB savings opportunity, the SmartImage prop-ordering fix from SW5 unblocks adoption without touching call sites.
5. **Schedule + Map ARIA polish** — Schedule table semantics (currently CSS-Grid, no `<table>`) and Map zoom/position URL-sync are both substantial follow-ups that didn't fit in Wave 112's "consistency-first" framing.
6. **Storybook coverage** — only `ThemeToggle` and `ConfirmDialog` have stories. Wave 112 wired Chromatic but the baseline collection is small; expanding stories for `EmptyState`, `AnimatedRing`, `ProgressRing`, `EventsCard`, `NewsCardView`, `ActivityTimeline`, `ScheduleHeaderCard`, `MapWeatherBadge`, `SkeletonMorph` would give visual-regression real teeth.

## Plan vs. reality

The original `idempotent-hatching-rabbit.md` plan called for 6 sub-waves with a single `feat(wave112-consistency)` commit covering "Unified feedback primitives + cross-page token drift audit + FoWT fix + URL-sync rollout". Reality:

  - **Feedback primitives** — already existed (`components/ui/EmptyState`, `components/feedback/LoadingState`, `components/feedback/OfflineFallback`). No-op.
  - **FoWT fix** — already in `index.html` lines 5–37 (reads `ue-mode` + `prefers-color-scheme` before any paint). No-op.
  - **Token drift audit** — found minor variation but no real bug (see "no-op finding" above). Documented here.
  - **URL-sync rollout** — split into two commits (`feat(wave112-url-sync)` for News+Activity, `feat(wave112-schedule-url)` for Schedule's bridge hook) because Schedule needed careful Zustand interaction.

So the plan's 6-step structure became 6 commits with different boundaries: foundation → activity → url-sync (news+activity) → schedule-url → a11y → perf. The audit report (this file) and CLAUDE.md / MEMORY.md updates land alongside this document.
