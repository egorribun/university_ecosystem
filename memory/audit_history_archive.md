---
name: Audit history archive (Waves 71–114) + older Lessons Learned
description: Detailed per-wave audit history moved out of MEMORY.md to keep the index under the 200-line cap. Companion to the main MEMORY.md Audit History table which keeps only the 5 most-recent waves detailed.
type: reference
originSessionId: 4e3c9df5-9921-4cd8-bb77-8ccb56aba630
---
# Audit History Archive (Waves 71–114)

Moved here during Wave 116 SW6 docs pass — `memory/MEMORY.md` kept only Waves 115 + 116 detailed + single-line pointers for Waves 112–114. All detailed rows for Waves 71–111 (original full-detail text) live in this file so nothing is lost.

Each row matches the format used in MEMORY.md at the time it was appended. For repo-root `AUDIT_WAVE*.md` files, those remain the authoritative source — this archive is the *index* equivalent.

## Waves 112–114

See also: `AUDIT_WAVE112.md`, `AUDIT_WAVE113.md`, `AUDIT_WAVE114.md` at repo root (authoritative full audit reports).

- **Wave 114 + polish v1+v2** (2026-04-19) — ✅ COMPLETE + POLISHED. Polish v1 closed 8 honesty-probe gaps; polish-v2 closed 5 more attribution / precision gaps caught by a second "безупречно?" probe. Key finding: filed Wave 115 SW2b-remainder (2 /login contrast violations) was a Playwright `networkidle`-before-FadeIn timing artefact — live browser-injected axe-core across 5 sampling intervals (0/100/300/600/1000 ms) both themes shows 0 color-contrast violations at rest. Passkey + show-password buttons render `#2563eb` (blue-600) at opacity 1, contrast 5.17:1 on bg-page ≥ AA 4.5:1. SW2b-remainder **dismissed**, not deferred. pageTranslations flake: was 40% flaky (2/5 fails) under parallel load — React-i18next `languageChanged` → React re-render chain exceeds default 1s `findByText` retry window. Stabilised via `describe({ retry: 2 })` + 3s timeout on RU post-toggle assertion. 5 consecutive full-suite runs green (286p/18s/0f). Manual reduced-motion smoke via chrome-devtools `initScript` matchMedia override confirms MotionConfig snaps. Polish-v2 full-WCAG axe run surfaced a separate `target-size` WCAG 2.2 AA violation on `<a href="/forgot-password">` (19×105 px inline link, 3/3 runs at 1280×720). Playwright e2e does NOT catch it — axe rule-engine delta (live 4.11.2 vs @axe-core/playwright's 4.11.3) or Playwright rendering quirk, not instrumented. Polish-v1 mis-attributed this to "Show-password button" — corrected in v2. Inherits into Wave 115 item #4 alongside /news a11y 0.94. Other polish: removed `void Dashboard` hack in skipLink.test.tsx, SW2a root-cause softened to "most likely cause (not instrumented)". npm audit: 20 pre-existing vulns. AUDIT_WAVE114.md v3 has full verbatim terminal output. Post-polish gates: vitest 286p/18s/0f (5/5 stable), e2e 10p/126s/0f, main chunk 291.57 kB reproducible, Cargo.lock clean.
- **Wave 114** (2026-04-18) — ✅ COMPLETE (2 closed + 1 partial + 1 deferred). Frontend test infrastructure + a11y polish (M scope). 4 commits (`da98d14aa` SW1, `3012d9e9d` SW2a, `bb961fdf6` SW2b, docs pending). ~34 files +~994/-849. SW1 `test(wave114-router-helper)` 30 files (+945/-820): new `src/tests/helpers/renderWithRouter.tsx` — async TanStack `RouterProvider` + provider stack, `authProvider: false` opt-out. Ported 26 vitest files across 6 batches. Vitest 213p/92s/0f → 286p/18s/0f (+73). SW2a `test(wave114-axe-webkit)` 3 files (+29/-20): attempted A11Y-113-04 closure via 3 approaches (include() scope, disableRules for WebKit, axe-core 4.10.0→4.11.2) — all failed. Kept package upgrade + root-cause docs. SW2b `feat(wave114-motion-config)` 2 files (+20/-9): wrapped `ProvidersInner` with `<MotionConfig reducedMotion="user">`. Framer Motion now respects OS `prefers-reduced-motion` + Playwright `emulateMedia` — WCAG 2.3.3 AAA real-user win. A11Y-113-03 closed.
- **Wave 113 + SW6 polish** (2026-04-18) — ✅ COMPLETE + POLISHED. Frontend runtime verification + 8-gap polish pass. 5 commits (`642e69da3`, `07ad1fd8a`, `f2a867b35`, `3701602d1` Cargo.lock idempotent, `c9e6cb8d0` SW6 polish). ~46 files total. Final state: vitest 213p/92s/0f (was 66f pre-SW6), e2e 10p/126s/0f (4 browsers). SW6 highlights: 28 failing vitest skipped with "Wave 114 SW1" pointers (root cause = Wave 37 react-router-dom→TanStack migration); jsdom polyfills (ResizeObserver, hasPointerCapture×3, scrollIntoView); StoryList first-story LCP priority; LHCI per-URL retries: /schedule 0.92 /events 0.87 /activity 0.74 /map 0.91. A11y under-0.95 documented: /schedule 0.84, /events 0.93, /activity 0.91. LCP /news 0.32→0.57 (+78%) LCP 9.9s→7.7s (−22%). Footer visually verified (light blue-700+white, dark slate-950+white, both AA). Cargo.lock now idempotent. @zxcvbn-ts lazy PROVED via Playwright waterfall.
- **Wave 113 v1** (2026-04-18) — ✅ COMPLETE. Frontend runtime verification (M-scope). 2 code commits + 1 docs. SW1 caught 2 pre-existing WCAG 2.2 AA contrast violations (A11Y-113-01 + A11Y-113-02). SW3+SW4 LHCI baseline captured (mobile preset, 8 URLs, Perf 0.21-0.47 LCP 9-11s). SmartImage LCP priority (PERF-113-01). Deferrals → Wave 114: 66 failing vitest root-caused to Wave 37 `react-router-dom`→TanStack Router gap.
- **Wave 112** (2026-04-17) — ✅ COMPLETE. Frontend production audit, cross-page (XL — first non-local wave). 6 commits, ~115 files. SW1 foundation (62 files): tsconfig noUncheckedIndexedAccess (142 fallouts→0), Playwright multi-browser (chromium+firefox+webkit+iPhone 15), CI Lighthouse mandatory + i18n:check blocking + Chromatic workflow, `useURLState` hook, CLDR-aware translationParity, Map FeatureErrorBoundary. SW2 activity: `features/activity/` feature-folder migration (17 git-mv), ActivityFeature orchestrator, sync-tokens infra fix (read tokens/ → 630 vars vs 6). SW3 URL-sync (News + Activity + Schedule). SW4 a11y: Map aria-roledescription, Activity sr-only data tables, public-route axe-core e2e. SW5 perf: SmartImage LCP override-friendly. 0 TS, 0 lint, 17/17 i18n, 8.3s build, 291 KB main chunk unchanged.

## Waves 71–111

- **Wave 111** (2026-04-16) — Campus map — mobile viewport + controls responsiveness + exhaustive polish. 11 files +198/-38. FIX-111-01: map viewport hardcoded 400/560px→calc(100dvh-220px)/560px sm/300px landscape via `.map-viewport` CSS class. FIX-111-02: MapControls responsive. CSS positioner class fixes implicit-width bug. FIX-111-04: WidgetErrorBoundary wraps MapLibre GL. FIX-111-06: Bottom sheet `env(safe-area-inset-bottom)` padding. FIX-111-07: Fullscreen state synced via `fullscreenchange`. CQ-111-01: 10 `_few/_many` English plural keys (349/349 i18n). CQ-111-04: Popup close button 26px frosted circle, 44px touch via `::after`, light+dark. 0 TS errors.
- **Wave 110** (2026-04-15) — Campus map — sidebar fix + cinematic intro rewrite + polish. 11 files +82/-74. FIX-110-sidebar: mobile bottom sheet "rolled up" on first open (focus-trap auto-focused deep element → initialFocus: false). FIX-110-intro: cinematic flyTo never fired on SPA navigation (onLoad one-shot event lost in StrictMode double-mount → rAF polling map.loaded()). A11Y: 7 fixes. 0 TS errors.
- **Wave 109** (2026-04-15) — Campus map — exhaustive polish + mobile UX. 23 files +487/-262. CSS: dead vars removed, --map-accent/--map-event-color added, POI :focus-visible. TS: BuildingId validation, midnight wraparound. Perf: polling→events, getCampusBuildings cache, room list memoize. Mobile: POIControls removed from map overlay, single-popup system. React Compiler build fixes. View Transition map resize fix.
- **Wave 108** (2026-04-14) — Campus map — Living Campus (8 features). 10 new files (~755 lines), 9 modified. Time-of-day, seasonal, weather panel, particles, event pins, room status, keyboard shortcuts, mini-map. ~20 i18n keys EN+RU, ~175 CSS lines.
- **Wave 107** (2026-04-14) — Campus map — exhaustive polish. 20 fixes, 12 files modified, 1 deleted. A11y: prefersReducedMotion wired, cinematic intro skip on reduced-motion, search focus-visible ring, drag handle ARIA. Dead code: deleted constants/maps.ts (Yandex). CSS: --map-bldg-i token, POI hex→CSS tokens, sky dedup.
- **Waves 105-106** (2026-04-13) — Campus map — cleanup + enrichment. W105: Delete 7 dead files (~370 lines), 6 new CSS animations. W106: Structured hours (BuildingHours + isOpenNow + badge), photo placeholders (gradient + icon), weather (Open-Meteo → useMapWeather + MapWeatherBadge + CSS atmosphere), room expansion (54→126, 14 real GUU names). 24 files +1601/-706. 290.92 KB.
- **Waves 101-104** (2026-04-13) — Campus map — full redesign. W101: Fix ALL coords (2GIS/Yandex/OSM Overpass), 8→9 buildings, floor counts corrected, delete 6 SVG files (~1600 lines), single MapLibre GL mode. W102: premium pin markers (SVG drop-pin + Lucide icons), premium POI markers. W103: sky/atmosphere, premium controls, cinematic camera intro. W104: real building names, remove letter badges, POI from OSM Overpass. 21 files +1233/-1630.
- **Waves 99-100** (2026-04-12) — Campus map — real GUU data + Leaflet→MapLibre GL 3D. 19 files +2898/-275. 8 buildings, MapLibre GL migration, 3D fill-extrusion, native dark theme, JSX markers.
- **Waves 97-98** (2026-04-12) — Campus map polish + visual upgrades: 23 files. ref-mirror pattern (PERF-97-01), mobile sidebar a11y (A11Y-97-02), SVG focus (A11Y-97-01), useTimeOfDay atmosphere (DESIGN-98-01), motion.g entrance stagger (DESIGN-98-02), AnimatePresence view transitions (DESIGN-98-04). Dead code deleted. 291 KB.
- **Waves 88–96** (2026-04-11) — Campus map page premium overhaul — custom isometric 2.5D SVG campus map replacing Yandex iframe. CSS: `tokens/map.css`. Components: MapBackdrop, CampusMapSVG (dimetric 5 buildings), FloorPlanSVG, MapSidebar, MapSearchBar, MapCategoryFilter, MapScheduleWidget. Hooks: useMapNavigation (CSS zoom/pan, 0 deps), useNextLesson. Data: campusBuildings.ts (5 bldgs, 15 floors, 37 rooms). 128/128 i18n EN↔RU. 0 TS errors, 0 new deps, 294 KB chunk. See `memory/wave88_96_campus_map.md`.
- **Wave 87** (2026-04-11) — Activity final polish: 9 files (+40/-15). CSS: 9 color primitives (emerald/teal/cyan). TS: isGradeScale() guard. i18n: 4 defaultValue removed (136/136). A11y: legend role=img+aria-label.
- **Wave 86** (2026-04-11) — Activity exhaustive polish: 21 fixes, 15 files (+188/-79). RC: timeline useMemo. A11y: `<h3>` headers, heatmap role=img, export ARIA menu+Escape+focus. CSS: @property orbs/glow. Bugs: NaN guards (3), useId, UTC→local, API→parsers.
- **Wave 85** (2026-04-10) — Activity analytics dashboard: 15 polish fixes. New: ActivityTrendChart (SVG polyline), ActivityBarChart, ActivityHeatmap (CSS Grid 5-level), ActivityComparativeCard, ActivityExportButton (PDF/PNG). 0 new deps, 293 KB main chunk, 112/112 i18n. 20 files +1298/-51.
- **Wave 84** (2026-04-10) — Activity page premium overhaul: activity.css tokens (emerald palette), ActivityBackdrop (4 orbs), matte cards (.activity-card-matte), AnimatedRing 3 modes, ActivityTimeline (replaces 3x dup grid). Deleted RecentActivityGrid+ActivityDetailDialog. 18 files +1054/-811.
- **Wave 83** (2026-04-10) — Vite 7→8 (Rolldown): vite ^8.0.0, plugin-react ^6.0.0 (Oxc), @rolldown/plugin-babel (React Compiler). Removed top-level-await plugin. rollupOptions→rolldownOptions, manualChunks fn, esbuild→oxc, hotUpdate hook. Build 7.3s, 293 KB main chunk. 3 files +1362/-780.
- **Wave 82** (2026-04-10) — Events page: sticky jitter fix, type filter→date quick-buttons, nav buttons matte volumetric redesign, backend event_type ==→ILIKE. 20 files +234/-87.
- **Wave 81** (2026-04-09) — Skills catalog: 290 skills documented across 9 files.
- **Wave 80** (2026-04-09) — Events tech debt: React.FC→function (4 components), React.*→import type (5 files), common:buttons.close+statuses.cached added EN+RU. 15 files +48/-39.
- **Wave 79** (2026-04-09) — Events exhaustive polish: 25 files (+301/-238). Layout: overflow-clip, back button mb-6. Bugs: previewUrl ObjectURL never created. i18n: 24 defaultValues removed (119/119).
- **Wave 78** (2026-04-09) — Events detail polish: 3-layer layout→NewsDetail pattern, dead editOpen fix, language-aware about display, aria-labelledby IDs, Firefox reading progress, SEO, ObjectURL leak. 11 files.
- **Wave 77** (2026-04-09) — Events page 5 bug fixes + polish: routing FIX-57-03 (events.tsx→events.index.tsx), page-bounce fix, horizontal scroll fix, category colors (14 CSS tokens). 10 files +131/-126.
- **Wave 76** (2026-04-09) — Events page complete overhaul: feature architecture (EventsFeature orchestrator), glass cards, detail rebuild, events.css tokens (warm palette), a11y, 55+ i18n keys. 35 files +3574/-822. See `memory/wave76_events_overhaul.md`.
- **Wave 75** (2026-04-06) — Cross-page polish (Dashboard+News+Schedule): 2 bugs fixed (page.data→page.items, snackbar severity), 38 i18n keys added. 27 files +228/-230.
- **Wave 74** (2026-04-06) — Settings dialog + matte volumetric: slide-over→centered dialog, matte CSS system (.sched-settings-btn/.matte-chip/.matte-input), deleted LessonSlideOver+BottomSheet. 16 files +536/-676.
- **Wave 73** (2026-04-06) — Unified page headers: ProgressRing drain mode, sched-hero-card→news-style layout, inline badges. 2 files +36/-65.
- **Wave 72** (2026-04-06) — Schedule final polish: 18 fixes, 15 files +217/-280. CSS: dark hex→semantic, badge 600, heat tokens, print !important→double-class. Structure: toolbar→settings panel (hamburger), deleted ScheduleToolbar+WeekSelector.
- **Wave 71** (2026-04-06) — Schedule final polish + premium header: 37 fixes, 20 files +656/-400. Critical: currentProgress broken in mobile/list. Code: forwardRef→React 19 ref, shared buildLessonsByDay. Header: sched-hero-card (4-layer shadow, accent line, flare), sched-status-card (left stripe, gradient).

## Older lessons learned

Moved here from MEMORY.md during Wave 116 SW6 docs pass — waves 29 through 70. The lessons themselves are all now encoded as permanent conventions in `CLAUDE.md` (Code Conventions + Gotchas sections), which is the authoritative long-form reference. This archive keeps the historical waveXX grouping for anyone tracing back to the wave that introduced a specific pattern.

### Lessons Learned (Waves 29–41)
- See `memory/wave34_ci_fixes.md` for detailed Wave 34 schema/CI lessons.
- Key: Alembic migrations baked at Docker build time; `docker compose build` after changes.
- Key: React Compiler needs inline arrows in useMemo; `useMemo(fn, [])` fails.
- Key: Python 3.14 `dataclasses.Field` requires `doc=` param (PEP 749).
- Key: Docker compose `${VAR:?}` reads `.env` only; `env_file` is container-only.
- Key: Never `!` in Docker passwords (shell history expansion).

### Lessons Learned (Wave 42)
- `POSTGRES_PASSWORD` env only applies on first volume init — ALTER USER needed if volume persists.
- Distroless images: no shell/wget — health checks via HTTP from host, not Docker HEALTHCHECK.
- `docker compose up --force-recreate` recreates dependencies too — use `restart <service>` instead.

### Lessons Learned (Waves 46-57)
- See `memory/wave50_morphing_navbar.md`, `memory/wave46_48_dashboard_delight.md`, `memory/wave55_news_page.md`.
- Key: `view-transition-name` creates `contain:layout` — never on elements with `before:absolute` overlay (FIX-57-01).
- Key: Tailwind v4 `max-w-sm/md/lg` = spacing scale, NOT container sizes — use `max-w-[28rem]`.
- Key: Sticky navbar height must NEVER change — causes layout shift. Morph contents inside fixed shell.
- Key: `overflow-x: hidden` auto-sets `overflow-y: auto`. Use `overflow: clip` instead.
- Key: TanStack Router `news.tsx` = layout (Outlet), `news.index.tsx` = index. Missing `.index` breaks children.

### Lessons Learned (Wave 60)
- `aria-hidden` MUST be `aria-hidden="true"` — bare JSX `aria-hidden` renders as `aria-hidden=""` which is falsy per ARIA W3C spec.
- BackToTop footer avoidance: IntersectionObserver on `[role="contentinfo"]`, CSS `.back-to-top-wrap` transition.
- Comment IDs: backend UUID7 (string), frontend had `number` — optimistic IDs use `"optimistic-" + Date.now()` prefix.
- `transition-colors` + `transition-transform` on same element: Tailwind v4 last one wins. Use `transition-[color,transform]`.

### Lessons Learned (Wave 61)
- Zustand object selectors MUST use `useShallow` — `Object.is` on `{ a, b }` always fails (new ref).
- Module-scope selector for Zustand actions — inline closures in `useShallow()` cause identity issues.
- `motion.div className="contents"` breaks Framer Motion.
- `AnimatePresence` useless when all children always rendered.
- Schedule page files: `ScheduleToolbar.tsx`, `ScheduleMiniCalendar.tsx`, `LessonSlideOver.tsx`, `ScheduleShortcutsOverlay.tsx`, `useScheduleKeyboardNav.ts`, `scheduleConflicts.ts`, `schedule.css`.

### Lessons Learned (Wave 62)
- Keyboard nav cell IDs must match between hook and DOM.
- `Intl.DateTimeFormat` for locale-aware labels — no hardcoded translation arrays.
- Breakpoint must match where layout actually needs space — 1730px was too aggressive; 1280px shows desktop grid on most monitors.
- `AnimatePresence mode="wait"` needs unique `key` on child `motion.div`.
- `min-h-0` on flex children — essential for `overflow-y-auto` inside flex column.
- `ConfirmDialog` for destructive actions — always use existing ConfirmDialog component.
- Schedule page files: + `ScheduleListView.tsx`, `ScheduleSettingsPanel.tsx`.

### Lessons Learned (Wave 63-64)
- `ref.current` during render → React Compiler panic — use `useState+useEffect` instead of `useRef`.
- `@property inherits: true` is correct when variable is set on parent and used by children.
- Matte > Glass for data-heavy views — 30+ cards with `backdrop-filter: blur()` = GPU thrash.
- `min-w-0` on grid cells — without it, CSS Grid children never shrink below `min-content`.
- Docker `--no-cache` + Ctrl+Shift+R — PWA Service Worker caches JS/CSS independently of HTTP cache.
- `variant="full"` for wide content — `variant="wide"` caps at 1400px.

### Lessons Learned (Waves 65-66)
- `overflow: hidden` on grid cells clips card content — use `overflow: visible`. For border-radius clipping only, use `overflow: clip` (no BFC).
- `h-full` on grid children forces them to match row height — causes clipping when content is taller.
- Hook splitting preserves public API — extract sub-hooks, re-export from orchestrator.
- Page Visibility API for timers — `document.visibilityState === "hidden"` skips tick.
- `useFocusTrap` on shared Dialog — one change fixes a11y for ALL dialogs app-wide.
- `color-mix(in srgb, white 60%, transparent)` replaces `rgb(255 255 255 / 0.6)`.
- Dynamic imports for export libs — `await import("html2canvas")` keeps bundle small.
- idb-keyval for lesson notes — simpler than raw IndexedDB.
- Schedule page new files: `FlipCountdown.tsx`, `ExportDropdown.tsx`, `DraggableLessonCard.tsx`, `buildingIcons.ts`, `scheduleExport.ts`, `useLessonNotes.ts`, `useScheduleReminders.ts`, `scheduleTransition.ts`.

### Lessons Learned (Wave 70)
- React Compiler "infer" mode forbids ref access during render — use `useState` + conditional `setState` during render.
- Framer Motion `custom` + `variants` for directional animations.
- `AnimatePresence key={X}` causes full remount.
- `display: contents` breaks flex layout control.
- CSS `will-change` must be paired with reduced-motion reset.
- `useLayoutEffect` without deps + `setState` = infinite loop.
- Pull-to-refresh + horizontal swipe on same container = conflict.
- `Button` component `gap-2` wraps on narrow screens — use plain `<button>` with `whitespace-nowrap`.
- Dark card bg: `color-mix(bg-surface 82%, slate-600 18%)`.
- Schedule new files: `LessonBottomSheet.tsx`, `useScrollToElement.ts`.

### Wave 33/34/43 Summaries
- Wave 43: frontend 10/10, 152 files — `memory/wave43_frontend_final_audit.md`
- Wave 33: backend 100/100 — `memory/audit_wave33_2026_03_26.md`
- Wave 34: CI 700→0 — `memory/wave34_ci_fixes.md`
