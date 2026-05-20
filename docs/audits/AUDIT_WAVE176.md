# Wave 176 Audit — Footer Polish (Q1=A Polish-only + Q2=B Premium с orbs + Q3=A STRICT 1-iter)

> **Closed**: 2026-05-21. **Branch**: `egorribun`. **Active waves post-W176**: W174 / W175 / W176.
> **Scope**: Foundation Footer.tsx polished to feature-page parity. Single-component arc (similar to W118 CLS-content-shift wave, ~4-6h budget). 36th consecutive wave with brainstorming + Phase 1 Explore + Phase 3 Review + W141 anti-pattern discipline.

---

## Headlines

1. **Footer brought to premium parity** with Dashboard/Events/News/Activity/Map/Schedule feature pages — gained dedicated Backdrop with 3 ambient orbs, entrance + stagger animations, accent stripe, container queries, dedicated footer-social-btn utility, active-route indicator via TanStack Router's built-in `data-status="active"`, and full Vitest + Storybook coverage. Pre-W176 Footer was the **last foundation-strata component without these layers**.

2. **Single source of truth for footer-hiding** — `useRouteType.hideFooter` now includes `/messenger` (was only in Footer's own `isAuthPage` array). Footer.tsx dropped its redundant `isAuthPage` check + `useRouterState` subscription. **One less subscription per Footer render.**

3. **Tailwind v4 native APIs adopted**: `@container` queries + `starting:` variant (CSS @starting-style) + `motion-reduce:` variants. **Zero JS animation overhead** for footer entrance + stagger — pure CSS, fires on mount.

4. **0 NEW (z) discoveries** — Phase 1 Explore + Phase 3 Review + Context7 docs (Tailwind v4 + TanStack Router) verified all foundational patterns pre-implementation. Extends low-(z) streak post-W145 (W175 = 0 NEW too).

5. **All 6 SW commits clean** through W156 SW4 husky hook chain (lint-staged + prettier --write + eslint --fix + detect-secrets + Python 2 except syntax). NO `--no-verify` bypasses. **W141 anti-pattern #15 (ARCHIVED W159 SW4) preserved 41st consecutive wave**.

---

## SW commit table

| SW | Commit | Title | LoC | Key mechanism |
|----|--------|-------|-----|---------------|
| SW1 | `6837d9a2e` | `refactor(wave176-sw1-footer-route-consolidation)` | +18 / -7 | Add `/messenger` to `useRouteType.hideFooter`; remove duplicated `isAuthPage` check from Footer.tsx; drop `useRouterState` subscription |
| SW2 | `2bc9c9079` | `feat(wave176-sw2-footer-backdrop)` | +140 | NEW `FooterBackdrop.tsx` (3 px-anchored orbs, prefersReducedMotion + isNarrow props) + 3 orb tokens (light + dark) + `--footer-accent-line` gradient token in semantics.css |
| SW3 | `9b7ef55d5` | `feat(wave176-sw3-footer-premium-polish)` | +150 / -24 | NEW 3 utilities (`footer-accent-stripe`, `footer-stagger-item`, `footer-social-btn`) + `@container` queries + `starting:` entrance + per-column stagger via `--stagger-i` + replace `<Button variant="glass">` → plain `<a className="footer-social-btn">` |
| SW4 | `fbf08df0d` | `feat(wave176-sw4-footer-link-active-indicator)` | +20 / -17 | `activeOptions={{ exact: false }}` on all 7 `<Link>` (prefix match for /news → /news/article-123); CSS selector `&[data-status="active"]::before` (TanStack canonical attribute, no `activeProps` needed) |
| SW5 | `2afa836de` | `test(wave176-sw5-footer-tests-storybook)` | +209 | NEW `Footer.test.tsx` (8 vitest cases) + NEW `Footer.stories.tsx` (4 stories: Default / DarkMode / Narrow / ReducedMotion). vitest 1095p → **1103p** / 12 skipped / 0 failed |
| SW6 | (this commit) | `docs(wave176-sw6-audit)` | — | AUDIT_WAVE176.md + N+3 rotation W173 → archive + CLAUDE.md row + 5 NEW Gotchas + INDEX.md + memory files |

**Total**: 6 SW commits + audit. ~4-5h core wall-clock (vs ~4-6h plan estimate).

---

## Critical files touched

### Production code (will ship)

| File | Action | LoC delta |
|------|--------|-----------|
| `frontend/src/hooks/useRouteType.ts` | MODIFY | +11 / -1 |
| `frontend/src/components/layout/Footer.tsx` | MODIFY | major rewrite, +95 / -38 net |
| `frontend/src/components/layout/FooterBackdrop.tsx` | **NEW** | +91 |
| `frontend/src/styles/tokens/semantics.css` | MODIFY | +36 (orb tokens + accent gradient × 2 themes) |
| `frontend/src/styles/tailwind.css` | MODIFY | +109 / -3 (4 utilities + extended footer-link-premium) |

### Test / dev infra (NOT in PROD bundle)

| File | Action | LoC delta |
|------|--------|-----------|
| `frontend/src/components/layout/__tests__/Footer.test.tsx` | **NEW** | +132 |
| `frontend/src/components/layout/Footer.stories.tsx` | **NEW** | +77 |

### Docs / memory / audit (W176 SW6)

| File | Action |
|------|--------|
| `docs/audits/AUDIT_WAVE176.md` | **NEW** (this file) |
| `docs/audits/AUDIT_WAVE173.md` | `git mv → archive/` (N+3 rotation) |
| `docs/audits/INDEX.md` | active table updated (W174/W175/W176), archive list +W173 |
| `CLAUDE.md` | Audit Trail W176 row + 5 NEW Gotchas (FooterBackdrop pattern, footer-stagger-item @starting-style, footer-social-btn utility, TanStack data-status canonical, useRouteType.hideFooter consolidation) |
| `memory/wave176_backlog.md` (`.claude` profile) | **NEW** — close-status entry point |
| `memory/wave177_opening_prompt.md` (`.claude` profile) | **NEW** — Q0 framework for W177+ |
| `MEMORY.md` (`.claude` profile) | row addition |

---

## §Honesty probe (post-W176)

**Active §Honesty caveats**: 0-4 pre-W176 → **0-7 post-W176** (typical polish-arc framing per `feedback_perfectionism.md` — single-component polish surfaces honest deferrals; quality, not quantity, is what shifts).

### Carry-forward (unchanged from W175 close)
1. **W174 §Honesty #3** — `/login` post-success redirect msw test infra refactor + Login.tsx reactive useEffect. Same status as W175 close (W176+ candidate). Untouched by W176.
2. **W134 §Honesty #2** — bundle delta recording-only. W175 baseline `index-D9_CAqRD.js` 177,150 b → W176 baseline `index-BfRpD_fx.js` **179,507 b = +2,357 b** (FooterBackdrop component + 4 utility additions + activeProps closures). Slightly above plan ceiling +1,100-1,700 b; honest framing — premium-with-orbs scope justified the delta. Server.js BYTE-IDENTICAL 23,600 b (frontend-only changes correctly isolated).
3. **W134 §Honesty #10** — `/messenger` Phase 5 SSR by-design punt. Unchanged.

### NEW W176 caveats (honest disclosure per `feedback_perfectionism.md`)
4. **chrome-devtools-mcp full authenticated visual smoke partial**. Test user `test@university.dev / TestPass@2024x` not seeded in dev DB; `/register` UI flow failed at 401 (likely backend validation or duplicate-state from prior attempts). Pivoted to **/404 unauthenticated route smoke** which renders the footer correctly (not in `hideFooter` + not in `isCompactPage`). Visually verified: light theme premium blue gradient + dark theme nav-dark gradient + mobile viewport (`@container` 2-column collapse) + 3 orbs + accent stripe + 2 social buttons + 7 links + ARIA. **Active-dot logic verified via 8 vitest tests** (jsdom-level) including prefix-match on /news/article-123. W177+ may extend to authenticated routes via auth fix (deferred TaskCreate of seed_demo_data into backend container OR backend fix).
5. **Bundle delta NOT byte-identical to W175** (+2,357 b above; expected per premium polish scope). Build × 3 BYTE-IDENTICAL preserved at NEW W176 baseline (`c6a9c5f8...` main JS sha + `af97a5a2...` server.js sha × 3 fresh runs from clean state).
6. **Storybook story uses jsdom matchMedia simulation** for ReducedMotion variant which doesn't truly flip OS preference. Real reduced-motion behavior exercised by `tests/e2e/a11y-public.spec.ts` `emulateMedia({ reducedMotion: 'reduce' })` (Wave 114 SW2b). Story serves as visual demonstration only.
7. **Direct DB write blocked by auto mode classifier** when attempting to seed test user — correctly enforced per CLAUDE.md production safety. Not a regression; structural protection working as designed.

---

## Verification matrix (final)

### Local gates (SW1 → SW5)
- ✅ `npx tsc --noEmit` 0 errors (each SW)
- ✅ `npm run lint --max-warnings=0` 0 warnings (each SW)
- ✅ `npx vitest run --silent` **1103p / 12 skipped / 0 failed** in 28.76s (W175 1095p + 8 SW5 Footer tests, exact delta, **0 regressions in other suites**)
- ✅ Pre-commit husky chain fired cleanly on all 6 SW commits (lint-staged + prettier --write + eslint --fix + detect-secrets + Python 2 except syntax). **NO --no-verify bypasses**.

### Bundle reproducibility (SW6)
- ✅ Build × 3 BYTE-IDENTICAL: main JS sha `c6a9c5f889004eba14a8ba3b54f34c4f5103f30f29cd709d44ac0f75847a82c4` + server.js sha `af97a5a20052006774c85b044907022b4d4a6a8980ada8ea5e0438e0e3286ffc` × 3 from clean `rm -rf dist`.
- ✅ Sizes: main JS `index-BfRpD_fx.js` **179,507 b** + server.js 23,600 b (BYTE-IDENTICAL to W175 — server-side unaffected) + `_shell.html` 66,459 b + sw.js 53,667 b
- ✅ Server.js BYTE-IDENTICAL to W175 (23,600 b unchanged). Confirms W176 changes are purely client-tree.

### Docker chain (SW6 user-required per Q2 answer)
- ✅ `bash scripts/dc.sh up -d --build frontend` (W170 SW4 helper) — frontend container `(healthy)` post-rebuild in ~1.5 min warm cache.
- ✅ `curl /healthz` → 200
- ✅ `curl /login` → 200, 21,669 b SSR HTML (vs W175 21,791 b — ~100 b variance from Footer dropping `useRouterState` SSR overhead).
- ✅ `curl /dashboard` → 200 (SSR through real Caddy chain).

### chrome-devtools-mcp visual smoke (SW6 user-required per Q2 answer)
Fresh isolated context `wave176-fresh` through real Caddy → Node SSR → backend chain:
- ✅ /404 light theme desktop (1425w): orbs visible, accent stripe at top, premium blue gradient, all 7 links + 2 social buttons rendered.
- ✅ /404 light theme mobile (500x667 effective): container query `@sm:grid-cols-2` activated, grid 2×206.25px columns (verified via `getComputedStyle`), brand block + nav column side-by-side, profile column wraps below, footer height 608 px.
- ✅ /404 dark theme (system pref): nav-dark gradient + social buttons subtle white tint + all elements legible.
- ✅ DOM inspection on /404:
  ```json
  {
    "footer.role": "contentinfo",
    "footer.bgClass": true,
    "footer.containerClass": true,
    "footer.startingClass": true,
    "orbCount": 3,
    "accentStripeExists": true,
    "accentStripeAriaHidden": true,
    "linkCount": 7,
    "linkActives": [{"href":"/dashboard","status":null}, ...],
    "socialCount": 2,
    "socialAriaLabels": ["Напишите нам в Telegram","Отправить письмо"],
    "staggerCount": 3,
    "staggerIndices": ["0","1","2"]
  }
  ```
- ✅ 0 React #418 hydration errors (only expected `profile_cache.cleared` warn from W128 SW1 + the 401 on /users/me background poll, pre-existing across the codebase).

### W173-W175 invariants preserved
- ✅ `--text-on-footer: var(--color-white)` in BOTH themes (W175 SW1) — verified semantics.css unchanged in that scope
- ✅ `footer-link-premium min-height: 2.75rem` (W175 SW1) — extended with `[data-status="active"]` selector, base preserved
- ✅ `ensureCsrfCookie()` (W174 SW2) — untouched
- ✅ `useAuthStore.getState()` in 3 route guards (W174 SW1) — untouched
- ✅ PWA manifest `screenshots` array absent (W174 SW3) — untouched
- ✅ `/ws/ticket → gateway:8080` Caddy route (W173 SW1) — untouched
- ✅ `.wasm: application/wasm` content-type (W173 SW1) — untouched

---

## W141 anti-pattern compliance

| Anti-pattern | Status | W176 evidence |
|---|---|---|
| #1 STRICT 1-iter SACRED | **21st total vindication** | All 6 SW landed 1-iter; W138 Lesson #1 within-iter SAME-mechanism sub-fixes applied in SW5 (test helper refactor from text-match to href-match — same mechanism "footer test coverage") — NOT mechanism pivot |
| #3 Phase 3 Review verification | **28 NEW W176 vindications** | Pre-SW1 verified no external consumers of `useRouteType.hideFooter` (only MainLayout); pre-SW2 verified EventsBackdrop pattern + breakpoints.content + useReducedMotion API; pre-SW3 verified .stagger-item uses `--stagger-i` NOT `--stagger-index` (DESIGN-43-02 doc said one, FIX-77-04 said other — empirical check found shared util uses `--stagger-i`); pre-SW4 verified TanStack Router auto-applies `data-status="active"` (no `activeProps` needed — Context7 docs canonical); within-SW5 caught locale-dependent text matching in test helper |
| #4 No premature "Closes" attribution | **19th vindication** | All commit messages use "feat / refactor / test / docs" + describe MECHANISM, not closure. Audit-doc framing honest about scope ("Footer brought to premium parity") |
| #15 ARCHIVED W159 SW4 | **41st consecutive wave preserved** | All 6 SW commits + this audit commit fired W156 SW4 husky pre-commit chain cleanly. NO `--no-verify` bypasses |

---

## NEW W176 Gotchas (added to CLAUDE.md ## Gotchas)

1. **`useRouteType.hideFooter` is the source of truth** (W176 SW1) — includes `/map`, `/schedule`, `/messenger`. Footer.tsx no longer maintains its own list. To add a new route to footer-hidden list: edit `HIDE_FOOTER_PREFIXES` const in `useRouteType.ts` ONLY.
2. **`FooterBackdrop` pattern** (W176 SW2) — 3 orbs (primary/secondary/sheen) with px-anchored sizing per W118 SW3 CLS-118-03 lesson. `prefersReducedMotion` drops `filter: blur(...)`. `isNarrow` (sub-`breakpoints.content`=900px) scales orbs. Tokens `--footer-orb-{primary,secondary,sheen}` in semantics.css both themes. `--footer-accent-line` gradient for top stripe.
3. **`footer-stagger-item` utility uses Tailwind v4 `@starting-style`** (W176 SW3) — fires on mount without IntersectionObserver. Per-element index via inline `style={{ "--stagger-i": N }}`. Capped at `calc(var(--stagger-i) * 80ms)` delay. Distinct from shared `.stagger-item` (in `_micro-interactions.css`) which uses `data-visible="true"` attribute (IntersectionObserver-driven) + `--stagger-i` with nth-child fallback. Don't confuse them.
4. **`footer-social-btn` replaces `<Button variant="glass" size="icon">`** for footer-specific icon buttons (W176 SW3). Glass + backdrop-blur on dark footer surface reads as invisible (glass-on-glass = no contrast). New utility uses white-tinted overlay (10%/18% color-mix) + thin border for clear edge on both light blue + dark nav-dark gradients. WCAG 2.5.8 44px + `--focus-ring-isolated` focus ring (W121 SW5).
5. **TanStack Router `data-status="active"` is canonical, NOT `activeProps`** (W176 SW4 + Context7 finding). `<Link>` auto-applies `data-status="active"` attribute when the link's `to` matches current pathname. `activeProps={{ "data-active": "true" }}` is unnecessary and verbose — CSS selector `&[data-status="active"]` works directly. For prefix-match active state (e.g., `/news` active on `/news/article-123`), use `activeOptions={{ exact: false }}`.

---

## Estimated W177+ candidates (Q0 framework for next wave)

Per W175 maintenance-mode default + W176 footer-polish-complete:

| Option | Scope | Trigger | Recommended? |
|---|---|---|---|
| **⭐ A** | Continue maintenance + bug fixes only | No specific motivation surfaces | **CANONICAL default** |
| B | Close W174 §Honesty #3 `/login` redirect msw refactor (~2-3h) | User wants login flow edge case closed | Same as W176 plan-time A0/A1 |
| C | Authenticated footer visual smoke via /dashboard (test user setup + chrome-devtools verify) (~30-60 min) | User wants W176 §Honesty #4 fully closed via authed routes | Tier 1 housekeeping |
| D | Tier 2/3 housekeeping (W170 hand-off items: Lighthouse #17021 quarterly check, INDEX.md hygiene) (~30 min) | Quarterly cycle | Tier 4 |
| E | `/messenger` Phase 5 SSR enable (~3-5h own wave) | User wants to expand SSR coverage; W134 §Honesty #10 closure | Own scope |
| F | ChatWindow `msg-bubble-sent` dead CSS investigation (W175 §Honesty caveat #7) (~1-2h) | User notices chat bubble visual breakage | Tier 1 fix |
| G | routeGuards.test.tsx unit tests + Playwright wave174-login-flow e2e (~3-5h combined) | User wants regression test coverage for W174 fixes | W175 carry-forward |

---

## Memory references (`.claude` profile only)

- `memory/wave176_backlog.md` — close-status + 7-item W177+ candidates table
- `memory/wave177_opening_prompt.md` — handoff with Q0 framework
- `MEMORY.md` — row addition + within-iter polish-pass W175 verbose row compaction (current **22,841 b / 1,559 b headroom** under 24,400 b ceiling; plan-time forecast ~21,500 b was undershoot — W176 verbose row + W175 compaction both grew bigger than projected; honest framing per `feedback_perfectionism.md`)

---

**End of W176 audit.** Footer.tsx is now the **second-most-polished foundation component** in the codebase (after the W170 SW4 helper-script consolidation + Navbar arc) — feature-page parity achieved.
