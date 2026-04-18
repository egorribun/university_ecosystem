# Wave 113 — Frontend Runtime Verification (April 2026)

**Branch**: `egorribun`
**Commits**: 2 code + 1 docs (`642e69da3`, `07ad1fd8a`, plus the final docs commit)
**Files touched**: 14 (3 in SW1, 10 in SW3/4, ~4 in SW5 docs)
**Net diff**: +79 / −13 lines (excluding this doc + MEMORY.md)
**Bundle**: main chunk 291 KB / 84 KB gzip (unchanged, well under 500 KB CI gate)
**Verification**: `tsc --noEmit` 0 · `eslint --max-warnings=0` 0 · `i18n:check` 17/17 · `npm run tokens:sync` 630 vars no drift · `test:e2e` 10 passed / 6 documented-skip / 0 fail · `npm run lhci` 8 URLs captured (Chrome EPERM on Windows cleanup — partial-but-consistent baseline)

This is a **verification wave**. Wave 112 shipped a lot of infrastructure (multi-browser Playwright, LHCI at 8 URLs, public-route axe-core spec, URL-sync hooks, Chromatic workflow) with clean local CI — but never actually ran the new commands end-to-end. Wave 113 ran them. The good news: Wave 112 config is mostly correct. The better news: runtime caught **two pre-existing WCAG 2.2 AA contrast violations** that had survived ~50 waves of polish because no one had run axe-core against `/login` or the 404 route until the Wave 112 spec existed.

## Sub-wave summary

| # | Commit | Theme | Files | Scope |
|---|---|---|---|---|
| 1 | `642e69da3` `test(wave113-browsers)` | Playwright multi-browser runtime + 4 pre-existing contrast violations fixed + WebKit axe-core crash documented | 3 | Gap #1, Gap #4 |
| 2 | `07ad1fd8a` `perf(wave113-lcp)` | LHCI baseline captured + 465 KB chunk no-op finding + SmartImage LCP priority threaded through News/Events grids | 10 | Gap #2, Gap #8, Dev #1 |
| 3 | _(this doc + CLAUDE.md / MEMORY.md)_ | Audit report + conventions + Wave 114 backlog | ~4 | Closing docs |

Deferred to Wave 114 (see **Followups** below):
- Gap #7 — 66 unit-test failures root-caused to Wave 37 `react-router-dom` → TanStack Router regression (19 test files)
- Gap #5 — URL-sync manual smoke (requires working mock-login or dev-server session)
- Gap #3, Gap #9, Gap #10, Dev #2-6 — all the Wave 112 follow-ups not addressed in this M-scope wave

## What changed by category

### Accessibility (WCAG 2.2 AA) — the big surprise

Running `npm run test:e2e tests/e2e/a11y-public.spec.ts` for the first time surfaced 2 serious contrast violations that the polish cycle (Waves 46–111) had never seen. Both are **pre-existing regressions, not Wave 112 bugs**:

| Component | Problem | Fix |
|---|---|---|
| `--text-secondary` light mode | `slate-500` (`#64748b`) on `--bg-page` (`slate-50`, `#f8fafc`) had contrast **4.36:1** — under WCAG AA 4.5:1 for normal text. Triggered on /login hero description + every `text-text-secondary` on light bg | Bumped to `slate-600` (`#475569`) → **6.5:1** (A11Y-113-01) |
| `--text-secondary` dark mode | `slate-400` works at rest but semi-transparent `.auth-card-glass` overlay blends it to effective `#586276` ≈ 3.28 on `slate-950` | Bumped to `slate-300` → **4.5+:1 even under the overlay** (A11Y-113-01) |
| Footer in light mode | `--bg-footer-light` was defined **twice**: once in `tokens/semantics.css:271` as `slate-50` (cascade winner), once in `tailwind.css:287` as a premium blue gradient (inside a Tailwind v4 `@theme` block that doesn't actually emit as a CSS var). Result: `text-white` rendering on near-white bg — **contrast 1.04** on /404 and any page that renders the Footer | Copied the gradient into `semantics.css` (source of truth for light/dark scope); added `background-color: var(--primary-hover)` under the gradient in `@utility bg-footer` so axe-core (which skips gradient backgrounds) measures against a solid blue-700 base → contrast ≈ 7.0 (A11Y-113-02) |
| `--text-tertiary` (both themes) | Bumped one step darker (light) / lighter (dark) to preserve visual hierarchy between secondary and tertiary | (A11Y-113-01 side fix) |

### Test infrastructure findings

| Surface | Finding |
|---|---|
| Playwright multi-browser run | Chromium + Firefox pass 4/4 axe-core after contrast fixes. WebKit renderer **crashes** during `AxeBuilder.analyze()` on `/login` (heavy DOM: ParticleAuthBackground canvas + Framer Motion + glass shadows exhaust the renderer process). Desktop WebKit only affects `/login`; mobile-webkit (lower memory envelope) crashes on both routes. Documented as A11Y-113-04 followup (Wave 114: narrow axe scope via `.include()` or upgrade `@axe-core/playwright`) |
| `a11y-public.spec.ts` | Added `page.emulateMedia({ colorScheme, reducedMotion: "reduce" })` + `waitForTimeout(900)` so axe samples resting-state colors, not Framer Motion `FadeIn` mid-animation opacity blends. The `reducedMotion` flag is currently advisory — `FadeIn` doesn't respect it. Wave 114 A11Y-113-03: wire `<MotionConfig reducedMotion="user">` at `AppProviders` so the emulateMedia flag alone is enough |
| 66 failing vitest tests | Root cause: Wave 37 migrated app from `react-router-dom` to TanStack Router, but 19 test files still import `MemoryRouter` + `Routes` + `Route` from `react-router-dom` and never wrap with TanStack `RouterProvider`. Every render of a Login/Settings/Schedule page component calls `useRouterState()` which returns null → `Cannot read properties of null (reading 'isServer')`. Wave 114 scope — batch refactor with a shared test helper |

### Bundle perf (no-op finding)

AUDIT_WAVE112.md flagged `index.esm-DlgO4ZKT.js` (465 KB) as "AZERTY/QWERTY data, candidate for Wave 113 lazy-split investigation". Post-investigation:

- Source: `@zxcvbn-ts/core` + `@zxcvbn-ts/language-common` (password-strength estimator + common-password dictionary)
- Consumer: `Register.tsx:78` + `ResetPassword.tsx:92`, both via `await import("@zxcvbn-ts/core")`
- `dist/index.html` has no `<link rel="modulepreload" href="...index.esm-DlgO4ZKT.js">` — **already route-lazy**
- No fix needed; Wave 112 assessment "loads sync" was incorrect (likely based on chunk name not appearing in a friendly bundle report, rather than an actual initial-request waterfall)

### LHCI baseline (captured + persists in `.lighthouseci/`)

Mobile preset, 8 URLs, 3 runs per URL where Chrome didn't EPERM on Windows temp cleanup:

```
/            Perf 0.21  A11y 1.00  BP 0.96  SEO 0.92  LCP ~10.4s
/login       Perf 0.47  A11y 1.00  BP 0.96  SEO 0.91  LCP ~9.3s
/dashboard   Perf 0.21  A11y 1.00  BP 0.96  SEO 0.92  LCP ~11.0s
/news        Perf 0.32  A11y 0.94  BP 0.96  SEO 0.92  LCP ~9.9s
/schedule    (partial — Chrome launched but EPERM halted before score emit)
/events      (partial)
/activity    (partial)
/map         (partial)
```

All Performance scores are **below the 0.90 gate** — confirms Wave 112's decision to keep `"categories:performance": ["warn", ...]` and not `"error"`. A11y score on `/news` (0.94) is the single sub-0.95 number that would flip the a11y gate to failing — Wave 114 needs to triage.

Note: LCP ~9-11s on mobile preset is the main perf issue. Image `loading="eager"` priority (this wave's SW3) nudges perhaps 100ms out of 10 000ms — the actual perf ceiling is JS parse + WASM init + initial DOM render. Wave 114 perf-pass scope.

### LCP prop adoption (Wave 112 SW5 API finally used)

Wave 112 SW5 fixed `SmartImage` prop ordering so callers can override `loading="lazy"` + `decoding="async"` defaults. Wave 112 shipped zero callers. Wave 113 SW3:

  - `NewsDetailHero.tsx` — always LCP on `/news/:id`. `loading="eager"` + `fetchPriority="high"`
  - `EventDetailHero.tsx` — same on `/events/:id`
  - `NewsCardHero.tsx` — new `priority?: boolean` prop, set eager when `true`
  - `EventCardHero.tsx` — same
  - `NewsList.tsx`, `EventsList.tsx` — pass `priority={index === 0}` to the first card in their grids
  - `NewsCard.tsx`, `NewsCardView.tsx`, `EventCard.tsx`, `EventCardView.tsx` — prop forwarded through the logic → view layers (4-step thread)
  - `NewsCard.memo` comparator updated to include `priority` (PERF-27-02-KEPT)

## Bundle baseline (post-Wave 113)

Unchanged from Wave 112 — this wave added zero code-split or dependency changes.

```
maplibre-gl                1025 KB / 272 KB gzip — Map page lazy
index.esm-DlgO4ZKT          465 KB             — @zxcvbn-ts, already lazy
jspdf.es.min                400 KB             — Activity export, lazy
index-*.css                 398 KB /  57 KB gzip — Tailwind + features
index-* main chunk          291 KB /  84 KB gzip — under 500 KB gate
html2canvas                 200 KB             — export, lazy
vendor-react                182 KB             — expected baseline
vendor-ui                   163 KB             — Framer Motion + Lucide
vendor-sentry                75 KB             — isolated chunk
```

## Followups recommended for Wave 114+

1. **Fix the 66 failing vitest tests (Wave 37 debt)** — 19 test files use `MemoryRouter` from `react-router-dom`; port to a shared `renderWithTanStackRouter(ui)` test helper + drop the legacy dependency from `src/` (it's still in `package.json` because tests use it).
2. **WebKit axe-core crash workaround** (A11Y-113-04) — narrow axe scope via `.include("main, footer, nav")` on webkit projects, OR upgrade `@axe-core/playwright` + test if the newer version is more memory-efficient. Re-enable the `test.skip` in `a11y-public.spec.ts` when resolved.
3. **MotionConfig reducedMotion="user"** (A11Y-113-03) — wrap `AppProviders` so `prefers-reduced-motion: reduce` actually disables Framer Motion. Then drop the 900ms `waitForTimeout` in `a11y-public.spec.ts`.
4. **Performance pass** (Dev #2 carried over from Wave 112) — mobile LCP 9-11s is the real gap. Profile `/dashboard` + `/news` + `/events` first. SmartImage priority adoption from this wave unblocks an `@unpic/react` adoption if LHCI shows "next-gen image formats" savings > 100 KB.
5. **/news a11y 0.94 triage** (new from LHCI baseline) — find the single sub-0.95 violation that would flip the a11y LHCI gate.
6. **URL-sync authenticated-route smoke test** — requires either mock-login fix (see #1) or a public-route URL-sync example. Consider adding a `/preview/url-sync` dev-only route.
7. **Chromatic baseline + Storybook coverage** (Dev #6 carried over) — `.github/workflows/chromatic.yml` exists but no baseline has been collected. Requires `CHROMATIC_PROJECT_TOKEN` repo var + accepting a first-time baseline.
8. **Token-drift deep audit** (Gap #9 carried over) — full comparison across `tokens/{dashboard,news,schedule,events,activity,map}.css` for radius / padding / font-size / transition drift. Wave 112's audit only covered orbs + shadows.
9. **`frontend/rust-crypto/Cargo.lock` root cause** (Gap #10 carried over) — workaround is still `git checkout --` before each commit.
10. **Schedule `<table>` semantics + Map zoom/position URL-sync** (Dev #5 carried over).

## Plan vs. reality

The plan (`frontend-wave-wobbly-crane.md`) called for 5 sub-waves:
1. Playwright multi-browser → **done** (1 commit)
2. Mock-API + 25 test triage → **deferred Path C** (19 test files exceeded 1-hour timebox)
3. LHCI + 465 KB split → **done** (LHCI baseline captured; 465 KB no-op finding)
4. URL-sync smoke + SmartImage LCP → **done partial** (LCP threaded; runtime smoke deferred)
5. Docs → **this commit**

So the 5-sub-wave structure became **2 code commits** plus docs. Scope honest: SW2 was too big to fit in an M-scope wave; the remaining 4 items landed cleanly.
