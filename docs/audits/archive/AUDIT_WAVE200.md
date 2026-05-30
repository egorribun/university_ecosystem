# AUDIT — Wave 200 (Storybook story-coverage campaign — formal close)

> **Status: CLOSED.** The W195→W199 Storybook story-coverage campaign reaches its natural end. W200 stories the **single remaining storyable component** (`BackToTop`), runs the verify-before-write **final sweep** (1 storyable of 29 uncovered → campaign formally exhausted), records the **permanent SKIP set**, and declares the W195→W199 arc closed. 60th consecutive wave with brainstorming + Phase 1 Explore + Phase 3 verify-before-write + W141 anti-pattern discipline. 2 SW (SW1 story + SW2 close).

## Headline

- **1 NEW story file** (`BackToTop.stories.tsx`) — story files 211 → **212**; build-storybook index 889 → **893** = 684 stories + **209 autodocs = +1 net-new file** (the authoritative integrity check) + 3 story variants. importPaths 210 → 211 (the 212-vs-211 gap is the pre-existing `routes/_admin/admin.stories.tsx` glob exclusion, W115 SW3 by-design).
- **Final sweep = campaign exhausted.** 238 component files vs 210 stories → 29 uncovered; **exactly 1 (BackToTop) is storyable-now**, the other 28 are justified permanent-SKIP: 9 `*Feature` orchestrators, 4 self-toggle (incl. MapWeatherBadge), 4 event-gated, 3 error boundaries, 3 layout shells, 2 providers + SEO (meta-only), 1 hook (EventFilterPopover), 1 barrel (SettingsUI). The genuinely-storyable CONTEXT set is now **formally exhausted**.
- **Bundle main JS BYTE-IDENTICAL × 3** to W134-SW3 → W199 `1bff1fd7…c97` (the critical app-bundle invariant; stories never enter the app entry graph). ≥58-wave LOCAL invariant **extends to ≥59-wave**. server.js sha `bd4a3402…` × 3 — ALSO unchanged from W199 close (no chunk-graph shift this wave; +1 story didn't perturb the server bundle). Cite content sha only — the filename hash drifts per Rolldown.
- **BackToTop = the W199-deferred candidate, now landed.** Scroll-gated (`window.scrollY > 420`); deterministically staged via a `ScrollGate` harness (redefine `window.scrollY` + rAF-dispatch a synthetic `scroll` event). Runtime smoke 3/3 confirms reveal (Default/DarkMode `fabPresent=true`) + hide (BelowThreshold `fabPresent=false`).

## Per-SW table

| SW | Commit | Work |
|----|--------|------|
| SW1 | `f600b18ab` | `BackToTop.stories.tsx` — scroll-mock decorator + static footer harness; 3 variants (Default / DarkMode / BelowThreshold) |
| SW2 | _(this)_ | final sweep + campaign close: audit + INDEX + CLAUDE.md row + NEW Gotcha + N+3 (W197→archive) + MEMORY.md + memory files |

## Harness patterns applied (no `.storybook` change)

- **`ScrollGate` harness (NEW pattern)** — a `useEffect` redefines `window.scrollY` via `Object.defineProperty(window, "scrollY", { value, configurable: true, writable: true })` + dispatches a synthetic `scroll` Event **deferred via `requestAnimationFrame`** (so BackToTop's own mount-effect `scroll` listener is registered first; cleanup restores `scrollY = 0`). This deterministically flips the value-readable scroll gate. Chromium (Chromatic + the runtime smoke both use it) permits redefining `scrollY`.
- **Static below-the-fold `<footer role="contentinfo">`** — BackToTop's footer-offset IntersectionObserver (`BackToTop.tsx:26-47`) is LAYOUT-driven, not value-driven (faking scrollY does NOT fire it). A static footer at `top: 140vh` exercises the observer's attach branch (it null-guards at line 28 otherwise) + reports not-intersecting → the FAB stays at its deterministic default `bottom: 24`. **Footer-aware repositioning is a deliberate non-goal** (real-scroll staging is Chromatic-flaky → violates 1-iter).
- **`themed(dark, scrolled)` factory** + `// eslint-disable-next-line react/display-name` + `LazyMotion features={domAnimation}` (BackToTop renders `<Magnetic>` → `<m.button>` in `<AnimatePresence>`) — the W199 SpotifyConnect template. `meta` uses `layout: "fullscreen"` (fixed-position FAB) + `chromatic: { pauseAnimationAtEnd: true }` (settle the AnimatePresence spring enter). Harness named `ScrollGate` (not `ScrollReveal`) to avoid shadowing the real `ScrollReveal` component in `motion/`.

## Verification (wave-close gates)

- SW1: `npx tsc --noEmit` 0 + `npx eslint src/components/motion/BackToTop.stories.tsx --max-warnings=0` 0 → commit (husky chain clean — lint-staged prettier+eslint, detect-secrets Passed, Python 2 except Passed; NO `--no-verify`).
- `npm run build-storybook` **SUCCESS**; index 889 → **893** (684 stories + **209 autodocs**); **+1 autodocs == 1 new file** (integrity exact). All 4 BackToTop entries present (`motion-backtotop--docs` + `--default` + `--dark-mode` + `--below-threshold`). importPaths 210 → 211.
- **Runtime smoke 3/3 clean** — real-Chrome (`channel: "chrome"`) over self-served `storybook-static`. `--default` + `--dark-mode`: `fabPresent=true` (reveal validated); `--below-threshold`: `fabPresent=false` (hide / `!show` null-render validated); 0 real console errors each. Temp script deleted after.
- **Build × 3** main JS sha `1bff1fd7403b03e206534340bc89c53a37ce29d1240e923e83b4101c9c813c97` × 3 (BYTE-IDENTICAL to W134-SW3 → W199); server.js sha `bd4a3402ca67df2af3d6a6122520616bd3f24815e411b03c6613f7ebdbc54885` × 3 (unchanged from W199 close). Tree-shake invariant holds (stories not in app graph); Cargo.lock no drift.
- `npm run i18n:check` **18/18** (no new keys — reuses `common:buttons.backToTop`); `npm audit --omit=dev` **0**; clean working tree.
- `npm run test:ci` (MANDATORY coverage gate per W198 lesson): **1270 passed / 12 skipped / 0 failed**; coverage functions **69.93%** (< 70%). **PROVEN non-regressive** — `git diff 3f2e6da61..HEAD --name-only -- frontend/src` is **only `BackToTop.stories.tsx`** (a coverage-excluded `.stories.tsx` per `vitest.config.ts:33`), so non-story coverage == W199 baseline. The 69.93% is the §6-documented local under-execution artifact (CI authoritative ~71.79%). CI's Frontend Tests / Unit Tests job is authoritative; verified post-push.

## §Honesty probe

1. **test:ci local 69.93% functions < 70%** — the documented §6 under-execution artifact (CI ~71.79%). PROVEN non-regressive (only a coverage-excluded `.stories.tsx` changed; structurally cannot move coverage). LOCAL gate exits non-zero; CI is authoritative. Identical to W199.
2. **Footer-aware FAB repositioning is a DELIBERATE NON-GOAL** — BackToTop's IntersectionObserver offset is layout-driven; deterministic staging would need real scroll (Chromatic-flaky → violates the 1-iter rule). The story renders the FAB at its default `bottom: 24` + a static footer for the observer's attach branch only. The repositioning behavior is NOT visually regression-covered. Honest scope boundary, not an oversight.
3. **`Object.defineProperty(window, "scrollY", …)` is a Chromium-permitted environment assumption** — works in Chromatic + the real-Chrome runtime smoke (both Chromium). A non-Chromium renderer that makes `scrollY` non-configurable would throw; out of scope (the project's visual infra is Chromium-only).
4. Carry-forward structural non-goals (NOT W200 scope): **W134 §H#2** bundle-delta recording-only, **W134 §H#10** /messenger Phase 5 SSR by-design (W161 SW2). The BackToTop story is net-positive coverage, not a §Honesty closure.

## (z) discoveries + anti-patterns

- **0 NEW (z) discoveries.** The scroll-gate-vs-layout-gate distinction was surfaced by Phase 1 verify-before-write reads (BackToTop.tsx + the SpotifyConnect template) BEFORE writing the story — the discipline working as designed, not a mid-implementation surprise. The naive "mock scrollY + scroll near the footer + snapshot the offset" plan would have been a fragile real-scroll mechanism; reading the two gates apart pre-empted it.
- **0 NEW anti-patterns** (14-pattern register stable post-W159 #15 archival).
- **W141 compliance**: #1 (SW1 landed 1-iter), #3 (Phase 1 final sweep empirically confirmed BackToTop is the ONLY storyable-now of 29 uncovered + the 2-gate distinction read from source, never from prose), #4 (closures attributed AFTER Build × 3 sha + 3/3 smoke + index counts + RUN test:ci), #15 ARCHIVED preserved (both commits fired the husky chain cleanly, NO `--no-verify`).

## NEW Gotcha (added to CLAUDE.md ## Gotchas)

**Storying a scroll-gated component** (W200): a component gated on `window.scrollY > N` via a `scroll` listener IS storyable — redefine `window.scrollY` (`Object.defineProperty(window, "scrollY", { value, configurable: true, writable: true })`) + dispatch a synthetic `scroll` Event (rAF-deferred so the component's own mount-effect listener attaches first; restore `scrollY = 0` on cleanup). But a SIBLING `IntersectionObserver` gate (layout-driven, e.g. a footer-offset) is NOT value-mockable — faking `scrollY` does not fire it, and real scroll is Chromatic-flaky. Render a static `[role=...]` target below the fold (`top: 140vh`) to exercise the observer's attach branch only, and treat the layout-driven behavior as a non-goal. Chromium-only: redefining `scrollY` requires `configurable: true` (Chromatic + the real-Chrome runtime smoke are both Chromium).

## Campaign arc — FORMALLY CLOSED

The W195→W199 Storybook story-coverage campaign is **complete**:

- **W195** (30 LEAF) + **W196** (21 LEAF + 6 CONTEXT) — LEAF tier done.
- **W197** (21) + **W198** (30) + **W199** (26) — CONTEXT tier.
- **W200** (1: BackToTop) — the final deferred candidate; the storyable CONTEXT set is **exhausted**.
- **Total: 212 story files · 893 build-storybook index entries (684 stories + 209 autodocs) · 211 importPaths.**

**Permanent SKIP set** (verify-before-write across W195–W200; never story): 9 `*Feature` orchestrators (Activity / Events / News / Map / Messenger + 4 Admin) · 4 self-toggle (SearchDialog, EventsShortcutsOverlay, NewsShortcutsOverlay, MapWeatherBadge — own their visible/open state via `useState` + a keypress/click; render null until triggered) · 4 event-gated (InstallPrompt `beforeinstallprompt`, LivePushToasts `push`, OfflineIndicator + SyncStatus `online`/`offline`) · 3 error boundaries (Feature/Page/Widget) · 2 providers (GlobalHapticsListener, LiveRegionProvider) + SEO (meta-only `<head>` tags) · 2 layout shells (MainLayout, PageLayout; Layout too) · EventFilterPopover (exports a hook `useEventFilterPopover`, not a component) · SettingsUI (barrel re-export) · `routes/_admin/admin.stories.tsx` (a TanStack Router route, glob-excluded by construction). **Module-mocking-gated logic cards** (would need MSW-in-Storybook — deliberately NOT built per the W120-W123 Storybook + Vite8/Rolldown service-worker fragility class) remain a non-goal unless a future infra wave enables it.

**W201 = maintenance mode** (W171 Lesson #1): the campaign is closed; waves fire only on real triggers — a user bug, CI red, a Renovate forced update, OR a user-chosen scope. Strongest pivot candidate now: **Chromatic visual-regression activation** — the 212 stories form a real baseline (needs `CHROMATIC_PROJECT_TOKEN` + `CHROMATIC_ENABLED=true`, user-side, + a first baseline PR; note the documented snapshot-drift sources: `Math.random()`/WebGL stories — WeatherParticles, MapLibreMap — + mobile-vs-desktop navbar at the iframe's <1350px width).

Memory references (`.claude` profile only): `memory/wave200_backlog.md`, `memory/wave201_opening_prompt.md`.
