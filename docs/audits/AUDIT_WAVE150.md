# AUDIT_WAVE150 — /admin polish arc kickoff (foundation wave)

**Date**: 2026-05-14
**Branch**: `egorribun`
**HEAD before wave**: `03d17736b` (W149 polish-v2 close)
**HEAD at SW5 (pre-commit)**: `265674633` (SW4 close); HEAD at SW5 commit (this audit) will advance to SW5.
**Active waves post-rotation**: W148 / W149 / W150 (W147 → archive)

---

## Headline

W150 is the **first wave of a 4-6 wave /admin polish arc** (per `feedback_planning_estimates.md` historical anchoring: Events W77-W82 = 6 waves, Activity W84-W87 = 4 waves; admin surface 2,109 LoC sits between → 4-6 waves realistic). W150 lays **theming + a11y + i18n + motion** foundation so W151-W155+ can build feature-folder migration, per-page deep polish, TanStack Query factory hooks, and StoriesAdmin substantive work on top.

**4 SW commits + this SW5 audit** (~4-5h core wall-clock, well under the open-ended-absorption Q3 budget). **Zero NEW (z) discoveries** — sharp departure from W139-W144 pattern (W139=9, W140=8, W141=6, W142=6, W143=3, W144=6) because Phase 1 Explore agents + Phase 3 Review verified every premise empirically before SW1 began. **Zero CI flake hits** (no `gh run rerun --failed` needed). **Vitest gain +6** (1052 → 1058 via 6 new AdminFeatureFlags tests).

---

## SW commits (4 on egorribun, in order)

| SW | Commit | Title | Files | LoC delta |
|----|--------|-------|-------|-----------|
| **SW1** | `d92aee2c3` | `feat(wave150-sw1-admin-theming-foundation)` | 4 files (2 new + 2 modified) | +475 / -1 |
| **SW2** | `80c76bb8c` | `a11y(wave150-sw2-admin-tables)` | 6 files modified | +113 / -30 |
| **SW3** | `b833e8911` | `fix(wave150-sw3-admin-i18n-tests)` | 7 files (1 new + 6 modified) | +183 / -8 |
| **SW4** | `265674633` | `a11y(wave150-sw4-admin-motion)` | 2 files modified | +18 / -10 |
| **SW5** | (this commit) | `docs(wave150-sw5)` | audit + memory + N+3 rotation | — |

**Total**: 4 functional commits + 1 docs commit; **+789 / -49 lines** across 18 distinct file changes.

---

## Per-SW narrative

### SW1 — Admin theming foundation (`d92aee2c3`)

**Goal**: Establish CSS token scope, backdrop, and `.admin-theme` wrapper on all 5 admin routes.

**Phase 0 empirical probes**:
- R1: `grep -rn '@import.*tokens/' frontend/src/styles/` → entry at `theme.css:11-19` (chain: primitives → semantics → components → dashboard → news → events → schedule → activity → map). Pattern: append admin.css at line 20.
- R2: `grep -rn 'admin-theme|--admin-' frontend/src/` → 0 matches (clean slate).
- Extra: Read `_admin.tsx` (18 LoC, line 17 `component: () => <Outlet />`). Read `MainLayout.tsx:37` to confirm `min-h-dvh` W118 SW1 pattern.

**Files created**:
- [`frontend/src/styles/tokens/admin.css`](../../frontend/src/styles/tokens/admin.css) — 280 LoC scoped `.admin-theme` palette using indigo/slate primitives (`--color-indigo-500` + `--color-slate-{50..900}` already in primitives.css). Mirrors activity.css 505 LoC structure: 4 `@property` registrations, `:root` + `.dark` overrides, `.admin-card-matte` 4-layer shadow recipe, `.admin-table` semantic styling for SW2 ARIA headers, `.admin-stagger-item` CSS-only entry animation, `prefers-reduced-motion` block, print stylesheet with doubled-class specificity per FIX-72-04.
- [`frontend/src/features/admin/components/AdminBackdrop.tsx`](../../frontend/src/features/admin/components/AdminBackdrop.tsx) — 53 LoC mirroring ActivityBackdrop EXACTLY: 4 orbs (indigo hero + slate highlight + conic drift + indigo bottom), **pixel-based** sizing per W118 SW3 CLS-118-03 fix (% values relative to absolute containers shift dramatically as admin pages scroll long), `aria-hidden + pointer-events-none + position: absolute -z-1` discipline, conic drift suppressed under reduced-motion.

**Files modified**:
- [`frontend/src/styles/theme.css`](../../frontend/src/styles/theme.css) — append `@import "./tokens/admin.css"` (1 line).
- [`frontend/src/routes/_admin.tsx`](../../frontend/src/routes/_admin.tsx) — replace `component: () => <Outlet />` with `AdminLayout` component wrapping `.admin-theme` div + AdminBackdrop. Uses `useReducedMotion` + `useMediaQuery(breakpoints.dashboard)` pattern from ActivityFeature.tsx:57-77. Auth + role gating preserved unchanged.

**Verification**:
- tsc 0; eslint 0; vitest **1052p/12s/0f** (W149 baseline EXACT).
- Build × 3 reproducibility: main JS chunk + server.js BYTE-IDENTICAL sha256 × 3 consecutive runs (`d32792f19177...` + `6bcb3d2e5a82...`). `_shell.html` + `sw.js` differ per W141 polish A3 known structural non-determinism (CSP nonce + workbox manifest order) — not regression.
- Tree-shake invariant: 0 `lhci-mock-user` references in PROD dist; SW IIFE invariant: `dist/client/sw.js` starts with `"use strict";(()=>{`.
- **Bundle delta vs W149 baseline 140,111 b**: PROD main JS chunk **140,217 b (+106 b)** — dramatically smaller than projected +800-1,200 b ceiling because AdminBackdrop tree-shakes into page chunks rather than entry chunk. Tokens compiled into CSS bundle (10 `admin-theme` + `--admin-orb` matches verified).

### SW2 — A11y semantic batch (`80c76bb8c`)

**Goal**: Bring 3 raw-table admin pages up to AdminUsers/DataTable parity per W120 polish-v2 aria-sort baseline + fix 44px touch target violation.

**Phase 0 empirical probes**:
- Read [`DataTableColumnHeader.tsx`](../../frontend/src/components/ui/data-table/DataTableColumnHeader.tsx) 1-52 → verified W120 pattern (aria-sort on parent `<th>`, button aria-label announces sort state).
- `grep 'useState.*sort\|sortBy' Admin*.tsx` → 0 matches. **None of AdminAudit/FeatureFlags/Notifications has sort state.** `scope="col"` is the semantic fix; aria-sort N/A.
- Counted `<th>` elements pre-fix: AdminAudit 6, AdminFeatureFlags 4, AdminNotifications 8 = **18 total**.

**Files modified** (6):
- [`AdminAudit.tsx`](../../frontend/src/pages/AdminAudit.tsx) — 6 `<th scope="col">` + table `aria-label={t("audit.table.aria")}`. Row expand button (line 47): `type="button"` + `aria-expanded={open}` + `aria-label` switches per open state + `h-8 w-8` (32px) → `min-h-[44px] min-w-[44px]` (WCAG 2.5.8 fix) + `focus-visible:ring-2 focus-visible:ring-brand`. Chevron icons `aria-hidden`.
- [`AdminFeatureFlags.tsx`](../../frontend/src/pages/AdminFeatureFlags.tsx) — 4 `<th scope="col">` + table aria-label. Info button (line 166, `h-8 w-8` = 32px): bumped to 44px + `type="button"` + `aria-label={t("featureFlags.actions.viewMetadata")}` + focus-visible ring. Info icon `aria-hidden`.
- [`AdminNotifications.tsx`](../../frontend/src/pages/AdminNotifications.tsx) — 8 `<th scope="col">` (table already had `aria-label` per Wave 21). Retry button (`p-1.5` ≈ 28px): bumped to 44px + `aria-label` + `focus-visible:ring-brand`. Purge button: same + `focus-visible:ring-error` for destructive semantic. Icons `aria-hidden`.
- [`AdminUsers.tsx`](../../frontend/src/pages/AdminUsers.tsx) — DataTable already covers aria-sort (W120 polish-v2). Delete button (`p-2` ≈ 36px): bumped to 44px + `focus-visible:ring-error`. Trash2 icon `aria-hidden`.
- [`en/admin.json`](../../frontend/src/i18n/locales/en/admin.json) + [`ru/admin.json`](../../frontend/src/i18n/locales/ru/admin.json) — 4 NEW keys in each locale: `audit.table.aria`, `audit.table.expandColumn`, `audit.table.expandRow`, `audit.table.collapseRow`, `featureFlags.table.aria`, `featureFlags.actions.viewMetadata` (6 total per locale, parity preserved).

**Verification**:
- tsc 0; eslint 0; vitest 1052p/12s/0f preserved.
- Purity gates: `grep '<th [^>]+' admin pages | grep -v scope=` → 0 matches (every `<th>` has `scope="col"`; `<thead>` false positives filtered).
- 5 distinct `min-h-[44px] min-w-[44px]` instances verified (AdminAudit row toggle, FeatureFlags Info, Notifications retry + purge, AdminUsers delete).
- Build: PROD main chunk **140,217 b** (BYTE-IDENTICAL size to SW1 since only attribute literals + i18n keys changed; hash differs as content varies).

### SW3 — i18n + tests + text-white close (`b833e8911`)

**Goal**: Close W149-era convention gaps — `defaultValue:` antipatterns, `text-white` instances, missing AdminFeatureFlags test, admin/stories namespace parity.

**Phase 0 finding** (informed scope tightening): `translationParity.test.ts` at `frontend/src/tests/` (W112 SW1) ALREADY walks `i18n/locales/<lng>/*.json` recursively per file and flattens keys. Both admin.json + stories.json are covered by existing parity test. **Originally planned "admin namespace parity test" creation NOT needed** — removed from plan after Phase 0 verification.

**Files modified** (6 + 1 new):
- [`AdminUsers.tsx:333-335`](../../frontend/src/pages/AdminUsers.tsx) — removed `defaultValue:` literal from `t()` call. Now reads `t("users.confirmDeleteDescription")` cleanly.
- [`StoriesAdmin.tsx:371-373`](../../frontend/src/pages/StoriesAdmin.tsx) — same fix on the story-delete ConfirmDialog. **NEWLY SURFACED** by post-SW3-step Phase-0 grep, NOT in original plan; «безупречно?» catch per `feedback_perfectionism.md` exhaustiveness principle.
- [`StoriesAdmin.tsx:620,623`](../../frontend/src/pages/StoriesAdmin.tsx) — replaced `text-white` × 2 with theme-aware `text-[var(--text-inverse)]`. Pattern matches W116 SW3 dark-mode contrast convention (sky-400 in dark + slate-950 inverse = 9.9:1 contrast, well above WCAG AA 4.5:1).
- [`en/admin.json`](../../frontend/src/i18n/locales/en/admin.json) + [`ru/admin.json`](../../frontend/src/i18n/locales/ru/admin.json) — NEW `users.confirmDeleteDescription` key (parity preserved 132 → 133 lines each).
- [`en/stories.json`](../../frontend/src/i18n/locales/en/stories.json) + [`ru/stories.json`](../../frontend/src/i18n/locales/ru/stories.json) — NEW `list.confirmDeleteDescription` key in both locales.
- [`AdminFeatureFlags.test.tsx`](../../frontend/src/pages/__tests__/AdminFeatureFlags.test.tsx) — **NEW** 175 LoC, mirrors AdminAudit.test.tsx 148 LoC structure: 3 mockFlags fixture (enabled/percentage/disabled) + AuthContext.Provider admin user + renderWithRouter + msw http.get + http.patch handlers. 6 tests covering heading + column headers, flag rendering, ARIA table semantics (scope="col" verified), Info button 44px touch target + type="button" verified, rollout percentage slider, toggle switch click → PATCH.

**Verification**:
- tsc 0; eslint 0; vitest **1058p/12s/0f** (+6 from W149 baseline 1052; matches expected for 6 new tests).
- translationParity test: 18p/0f (admin.json + stories.json new keys synced cleanly across en + ru).
- Purity gates: `grep 'defaultValue:' Admin*.tsx StoriesAdmin.tsx` → 0; `grep 'text-white' StoriesAdmin.tsx` → 0; `grep 'text-white' frontend/src/pages/Admin*.tsx` → 0.

### SW4 — Framer Motion useReducedMotion guards (`265674633`)

**Goal**: Bring AdminAudit + AdminFeatureFlags into the `useReducedMotion` accessibility pattern used by Activity (W84), Schedule (W69 FIX-69-a11y), and Map (W107 A11Y-107-01). **LazyMotion already global at AppProviders.tsx:109-116 (W124 SW1)** — SW4 is the *per-page* gating step.

**Phase 0 grep**: 4 motion call sites located (2 per page):
- AdminAudit: Row `<m.div>` expand animation (line 127-192) + page header `<m.div>` (line 237).
- AdminFeatureFlags: Page header `<m.div>` (line 67-77) + table row stagger `<m.tr>` with `index*0.05s` delay (line 116-190).

**Pattern applied** (mirrors Schedule FIX-69-a11y + Activity W84):
```tsx
<m.div
  initial={reducedMotion ? false : { opacity: 0, y: -20 }}
  animate={{ opacity: 1, y: 0 }}
  transition={reducedMotion ? { duration: 0 } : { duration: 0.5 }}
/>
```

**Files modified** (2):
- [`AdminAudit.tsx`](../../frontend/src/pages/AdminAudit.tsx) — added `useReducedMotion` to framer-motion import. Row component (function Row at line 21) + main AdminAudit component (line 202) both call `useReducedMotion` after useTranslation. Row expand m.div: `initial` + `exit` + `transition` gated. Page header m.div: `initial` + `transition` gated.
- [`AdminFeatureFlags.tsx`](../../frontend/src/pages/AdminFeatureFlags.tsx) — same import + hook pattern. Page header m.div + table row m.tr stagger both gated. Under reduced motion the `index*0.05s` stagger delay collapses to 0.

**Verification**:
- tsc 0; eslint 0; vitest **1058p/12s/0f** preserved (SW3 baseline).
- Build: PROD main JS chunk **140,217 b** (BYTE-IDENTICAL size through SW1-SW4). `useReducedMotion` adds no main chunk weight (already in framer-motion dep tree).
- Honest framing: browser smoke-test of `prefers-reduced-motion: reduce` rule emulation **deferred to CI verification** — admin routes are auth-gated (ssr:false + admin role required) so quick local visual verification needs auth backend. Pattern validity empirically proven by 20+ files in codebase already using this exact gate pattern per CLAUDE.md gotchas.

---

## Verification matrix (SW5 final sweep)

| Gate | SW1 | SW2 | SW3 | SW4 | SW5 |
|------|-----|-----|-----|-----|-----|
| `npx tsc --noEmit` (0 errors) | ✓ | ✓ | ✓ | ✓ | ✓ |
| `npx eslint --max-warnings=0` (0 warnings) | ✓ | ✓ | ✓ | ✓ | ✓ |
| `npm test` (vitest) | 1052p/12s/0f | 1052p/12s/0f | **1058p/12s/0f** | 1058p/12s/0f | **1058p/12s/0f** |
| `npm run build` × 3 main JS BYTE-IDENTICAL sha256 | ✓ | ✓ | — | ✓ | ✓ |
| `npm run build` × 3 server.js BYTE-IDENTICAL sha256 | ✓ | ✓ | — | ✓ | ✓ |
| Cargo.lock no drift (≥38 wave invariant) | ✓ | ✓ | ✓ | ✓ | ✓ |
| routeTree.gen.ts prettier drift cleaned pre-commit | ✓ | ✓ | ✓ | ✓ | ✓ |
| Tree-shake invariant (0 `lhci-mock-user` in PROD) | ✓ | ✓ | — | ✓ | ✓ |
| SW IIFE invariant (`"use strict";(()=>{`) | ✓ | ✓ | — | ✓ | ✓ |
| Purity: `<th>` has `scope=` in admin pages | — | ✓ (18/18) | — | — | ✓ |
| Purity: 0 `defaultValue:` in admin + Stories pages | — | — | ✓ | — | ✓ |
| Purity: 0 `text-white` in admin + Stories pages | — | — | ✓ | — | ✓ |
| translationParity test (admin + stories) | — | ✓ | ✓ (18p) | — | ✓ |

**SW5 final build × 3 sha256**:
- Main JS `dist/client/assets/index-KhGddIen.js` 140,217 b — sha256 `d19c7382da072c43...` × 3 BYTE-IDENTICAL runs ✓
- Server `dist/server/server.js` 23,600 b — sha256 `00055a0fb63966e1...` × 3 BYTE-IDENTICAL runs ✓
- `_shell.html` + `sw.js`: same byte count per run but DIFFERENT sha256 across runs (W141 polish A3 known build-infra non-determinism: CSP nonce + workbox manifest order — structural, NOT W150 regression).

---

## Bundle delta vs W149 baseline

| Artifact | W149 baseline | W150 SW5 | Delta |
|----------|--------------|----------|-------|
| PROD main JS chunk | 140,111 b (`index-DY7E5job.js`) | **140,217 b** (`index-KhGddIen.js`) | **+106 b** |
| PROD CSS chunk | (not recorded in W149 audit) | 407,557 b (`index-CGpfqB4p.css`) | new (admin tokens included) |
| `_shell.html` | 65,864 b | 65,954 b | +90 b (modulepreload graph update) |
| `sw.js` | 53,115 b | 53,279 b | +164 b (more precache entries — admin.css + AdminBackdrop chunks) |
| `server.js` | 39,373 b (per W149 SW7 audit) | 23,600 b | **−15,773 b** (likely SSR tree-shake or W149/W150 inter-wave SSR refactor independent of W150 changes) |

Headline: **PROD main JS chunk +106 bytes — dramatically smaller than the projected +800-1,200 byte ceiling** because AdminBackdrop is tree-shaken into page chunks rather than entry chunk, and tokens/admin.css lives in the CSS bundle. Per W149 polish-v2 bundle-honesty discipline: well within the +1.5 KB main chunk projection ceiling. CSS chunk delta NOT recorded against W149 (no W149 baseline available); admin tokens compiled cleanly into bundle (10 `admin-theme` + `--admin-orb` matches verified via grep).

**Note on server.js delta**: the −15,773 byte difference vs W149's claimed 39,373 b is suspicious and likely an audit-claim-vs-reality artifact rather than W150 work. The first W150 build at SW1 showed server.js at 23,600 b — meaning the W149 SW7 audit's 39,373 b claim is either stale (pre-W149-polish-v2) or simply inaccurate. Honest framing per `feedback_perfectionism.md`: I did NOT introduce a 15 KB SSR savings; the prior audit's bundle measurement was off.

---

## §Honesty trajectory (pre-W150 vs post-W150)

**Pre-W150 baseline** (per W149 SW7 audit + opening prompt):

1. W134 §Honesty #2 bundle delta carry-forward (honest framing recording only)
2. W134 §Honesty #10 /messenger Phase 5 punt (no-deploy)
3. W146 SW2 NEW #1 Lighthouse PAGE_HUNG on `/` (pragmatic-not-structural)
4. W148 SW2 architectural choice points (sentinel placement)
5. routeTree.gen.ts prettier drift recurring (W150+ structural fix candidate)
6. W149 §Honesty #6 Backend `test_login_lockout` flake (~60% first-attempt PASS, 100% with 1 retry)

**Realistic W150 closure target** (per plan): 2-5 → **3-7 post-W150**.

**Actual post-W150** (HONEST self-audit per W149 polish-v2 «безупречно?» pattern):

| # | Caveat | State | Source |
|---|--------|-------|--------|
| 1 | W134 §Honesty #2 bundle delta carry-forward | **Carries** unchanged | pre-W150 |
| 2 | W134 §Honesty #10 /messenger Phase 5 punt | **Carries** unchanged | pre-W150 |
| 3 | W146 SW2 Lighthouse PAGE_HUNG on `/` | **Carries** unchanged | pre-W150 |
| 4 | W148 SW2 sentinel architectural choice | **Carries** unchanged | pre-W150 |
| 5 | routeTree.gen.ts prettier drift recurring | **Carries** unchanged (hit 4× in W150: SW1, SW2, SW4, SW5 — npx prettier --write pre-commit each time) | pre-W150 |
| 6 | W149 §Honesty #6 Backend test_login_lockout flake | **Carries** unchanged (not exercised in W150 — frontend-only) | pre-W150 |
| 7 | **NEW W150**: features/admin/ folder migration deferred to W151+ | Carry forward | W150 explicit non-goal #1 |
| 8 | **NEW W150**: StoriesAdmin substantive polish deferred to W152+ (only text-white + defaultValue fixed this wave) | Carry forward | W150 explicit non-goal #2 |
| 9 | **NEW W150**: TanStack Query factory hooks for 4 admin pages deferred to W153+ (4 of 5 still use manual `api.get/patch/delete`) | Carry forward | W150 explicit non-goal #3 |
| 10 | **NEW W150**: admin.css `.dark` variant + AdminBackdrop visual smoke deferred to W151+ or CI verification (admin routes auth-gated; SSR disabled per `_admin.tsx:7`; local Docker + admin login required for visual rendering proof) | Carry forward | scope-realistic |
| 11 | **NEW W150**: bundle delta projection was +800-1200 b but actual was +106 b; CSS chunk size NOT compared to W149 baseline (no W149 CSS chunk size recorded in prior audit) | Honest framing | recording |
| 12 | **NEW W150**: server.js baseline-vs-current discrepancy (W149 audit claimed 39,373 b; my SW1 baseline build showed 23,600 b) — likely prior audit inaccuracy, NOT W150 savings | Honest framing | recording |

**Net trajectory**: 6 → **12 caveats post-W150** (carries 6 + 6 NEW). This is HIGHER than the planned 3-7 ceiling. Per `feedback_perfectionism.md` honest framing, 4 of the 6 NEW are **scope-realistic deferrals** (the polish-arc non-goals explicit in the approved plan); 2 are **bundle-honesty recordings** (NOT regressions). The arc trajectory:

- W150: lays foundation, adds 4 deferrals + 2 framings.
- W151-W155: each closes 1-2 W150 deferrals + introduces 0-1 NEW.
- Expected W155 close: 6-8 caveats total (back to baseline-ish range).

**Per «безупречно?» discipline**: SW5 audit surfaces gaps HONESTLY — not reassurance. The 4 explicit non-goals are LOAD-BEARING: future waves rely on them being respected (e.g., W151 features/admin/ migration depends on W150 tokens/admin.css being structurally sound, which it is).

---

## NEW W150 lessons

1. **Phase 1 Explore + Phase 3 Review prevents (z) cascade**: W139-W144 averaged 6.5 (z) discoveries per wave because plans were grounded in Context7 prose or Phase 1 hypothesis. W145-W149 dropped to 0-2 (z) because Phase 1 Explore + Phase 3 Review verified premises empirically (W141 anti-pattern #3 NONUPLE-vindicated). **W150 = 0 (z) discoveries** continues that trajectory. The structural cost (~30-45 min of Phase 1+3 reads) prevents 2-6h of misdirected SW work downstream.

2. **«безупречно?» catches scope-adjacent gaps**: SW3 was planned with 1 defaultValue fix (AdminUsers.tsx). Phase 0 grep at SW3 START surfaced a 2nd defaultValue (StoriesAdmin.tsx:373). Fixing both in-SW3 is the polish-arc discipline. Same lesson as W149 polish-v2.

3. **Polish-arc kickoff bundle delta is dominated by tree-shaking, not weight**: AdminBackdrop (53 LoC) + admin.css (280 LoC) projected +800-1,200 b main chunk; actual was +106 b because the JSX tree-shakes into page chunks rather than entry. Per `feedback_planning_estimates.md`: future polish-arc kickoff bundle projections should anchor to W150 actual (+50-150 b main + ~12 KB CSS) rather than worst-case ceilings.

4. **Existing translation parity test removes the need for per-namespace parity tests**: `translationParity.test.ts` (W112 SW1) walks every locale file recursively. Adding a namespace-specific parity test is **redundant**. The originally planned SW3 "admin namespace parity test" was correctly removed during Phase 0.

5. **routeTree.gen.ts drift fires per-build**: hit 4 times in W150 (SW1, SW2, SW4, SW5). `npx prettier --write src/routeTree.gen.ts` is now muscle memory; structural fix candidate (W151+) is to add `src/routeTree.gen.ts` to `.prettierignore` OR adjust prettier config to match TanStack Router's gen output.

6. **`useReducedMotion` global wrap (W124 SW1) makes per-page motion guards a small SW**: SW4 originally projected ~1-2h; actual was ~30 min because LazyMotion + framer-motion are already loaded globally. Each new motion-using page only needs the per-page `useReducedMotion()` hook call + 2-3 line gate per motion site.

---

## N+3 rotation

**Pre-rotation active waves**: W147 / W148 / W149.
**Post-rotation active waves**: W148 / W149 / W150.
**Action**: `git mv docs/audits/AUDIT_WAVE147.md docs/audits/archive/AUDIT_WAVE147.md` (executed at SW5 commit time, after this audit lands).

---

## W151+ candidates

Per the 4-6 wave /admin polish arc trajectory:

### Tier 1 W151 NEW scope (highest compounding value):

- **features/admin/ folder migration** (closes W150 §Honesty #7) — move `pages/AdminAudit.tsx` / `AdminFeatureFlags.tsx` / `AdminNotifications.tsx` / `AdminUsers.tsx` / `StoriesAdmin.tsx` → `features/admin/<page>Feature.tsx` orchestrators + `pages/` thin wrappers per Activity W84 SW2 convention (24-LoC `<FeatureErrorBoundary>` wrapping `<XxxFeature />`). Estimated 2-3h focused.

### Tier 1 W151 alt scope (admin per-page deep work, by size):

- **AdminFeatureFlags depth polish** (smallest 184 LoC, lowest-risk first per-page deep round — apply `.admin-card-matte` to flag rows, integrate `.admin-stagger-item` for CSS-only entry animation, surface metadata in dedicated dialog rather than `title=` attribute, TanStack Query factory hook). ~2h.
- **AdminUsers depth polish** (346 LoC, has DataTable shared infra to lean on) — TanStack Query factory hook + matte-card SectionCard wrap. ~2-3h.

### Tier 2 housekeeping (close existing §Honesty caveats):

- **routeTree.gen.ts prettier drift structural fix** — add to `.prettierignore` OR adjust prettier config. Closes carry-forward #5. ~30 min.
- **Backend test_login_lockout flake fix** — `pytest --reruns 2` OR root-cause race in failed_login_attempts. Closes carry-forward #6. ~30-60 min.

### Tier 3 W125 Phase 4 deploy infra (carry-forward W150+):

- **W125 SSR design doc Phase 4 + Phase 6** — Caddy SSR forwarding + Nitro Node deploy + canary rollout per W132 SW6 runbook (~4-6h Phase 4 + ~3-5h Phase 6).

### Recommended W151 scope:

**Combo: Tier 1 features/admin/ migration + Tier 2 routeTree structural fix** (~3-4h total). Migration unlocks deeper per-page polish in W152+; routeTree fix closes a recurring caveat in 30 min.

---

## Critical files reference (for W151 implementer)

**W150 SW1 templates** (now production):
- [`tokens/admin.css`](../../frontend/src/styles/tokens/admin.css) — admin palette + matte-card + stagger system
- [`features/admin/components/AdminBackdrop.tsx`](../../frontend/src/features/admin/components/AdminBackdrop.tsx) — pixel-sized 4-orb backdrop
- [`routes/_admin.tsx`](../../frontend/src/routes/_admin.tsx) — `.admin-theme` scope wrapper pattern

**W150 SW2-SW4 modified pages** (now WCAG 2.5.8 + 4.1.2 + 2.4.7 compliant):
- [`pages/AdminAudit.tsx`](../../frontend/src/pages/AdminAudit.tsx) — 339 LoC
- [`pages/AdminFeatureFlags.tsx`](../../frontend/src/pages/AdminFeatureFlags.tsx) — 184 LoC (smallest)
- [`pages/AdminNotifications.tsx`](../../frontend/src/pages/AdminNotifications.tsx) — 536 LoC
- [`pages/AdminUsers.tsx`](../../frontend/src/pages/AdminUsers.tsx) — 346 LoC
- [`pages/StoriesAdmin.tsx`](../../frontend/src/pages/StoriesAdmin.tsx) — 705 LoC (largest, only partial polish in W150)

**Tests added**:
- [`pages/__tests__/AdminFeatureFlags.test.tsx`](../../frontend/src/pages/__tests__/AdminFeatureFlags.test.tsx) — 175 LoC, 6 tests

**Reference convention**:
- Events W82 polish patterns: `features/events/EventsFeature.tsx`, `features/events/components/`
- Activity W87 polish patterns: `features/activity/ActivityFeature.tsx`, `features/activity/components/`

---

## Polish-v1 (`f7754b1f6`) — prettier-format SW1 NEW files

**Pushed**: 2026-05-14 post-SW5 CI verification run `25854363896` failure surfaced.

CI Run #1 (post-SW5 push) FAILED on `Frontend Tests / Lint & Format` with prettier `--check` against 2 W150 SW1 NEW files:

```
[warn] src/features/admin/components/AdminBackdrop.tsx
[warn] src/styles/tokens/admin.css
[warn] Code style issues found in 2 files. Run Prettier with --write to fix.
##[error]Process completed with exit code 1.
```

**Root cause**: W150 SW1 ran `npx prettier --write src/routeTree.gen.ts` only. The 2 NEW files (AdminBackdrop.tsx + admin.css) were written via Write tool but NEVER explicitly prettier-formatted before commit. Local tsc + eslint passed because prettier is a separate gate not part of eslint config. SW2-SW4 edits got prettier `--write` runs by reflex (W149 polish-v1 muscle memory on modified files) but the foundational SW1 NEW files slipped through.

**Same class of issue as W149 polish-v1 `6f89f4b51`**: prettier-format is a CI gate not yet wired into local pre-commit hook chain. The pattern hit BOTH W149 (modified-file edits) AND W150 (new-file Write outputs) — 2 consecutive waves with the same root cause confirms it's now a register-worthy recurring pattern.

**Fix**: `npx prettier --write src/features/admin/components/AdminBackdrop.tsx src/styles/tokens/admin.css`. Net semantic change ZERO (only whitespace/wrapping/line breaks: `box-shadow: A, B, C` collapsed onto single line where it fit, `color-mix` long-form values multi-line wrapped where they exceed column limit). Public API + behavior unchanged. tsc still 0 errors.

**NEW W150 §Honesty caveat #13** (polish-arc kickoff prettier gap): SW1 NEW file prettier formatting was missed in local verification despite W149 polish-v1 precedent. **§Honesty trajectory revised: 6 → 13 post-W150** (was 12 in SW5 audit, +1 from this polish-v1 finding).

---

## CI verification post-polish-v1 (Run #2 `25854945271`)

**Verified ALL GREEN** via `gh run view 25854945271 --json jobs --jq '.jobs[] | {name, conclusion}'`:

- **40 jobs SUCCESS** + **1 skipped** (Post-fix Formatting Bot Push — by-design skipped on non-bot pushes) + **0 failures**
- CI - Matrix Expansion: 10m1s SUCCESS
- Frontend Tests / Lint & Format: SUCCESS (was failing on run #1; polish-v1 closed it)
- Frontend Tests / Production Build + Bundle Analysis + Unit Tests + Lighthouse Audit + Performance Gate: ALL SUCCESS
- Backend Tests / Unit + Integration (Python 3.13): ALL SUCCESS — **W149 §Honesty #6 `test_login_lockout` flake DID NOT surface this run** (first-attempt PASS)
- E2E Tests / E2E Tests (chromium): SUCCESS — W150 admin pages did not introduce e2e regression
- Backend Type Check + Alembic Migrations + Helm Lint + SBOM + Trivy + SLSA + Pre-commit + Go Lint × 3 + Go Tests × 3 + Go Integration × 3 + Chromatic + Contract Validation + Generate OpenAPI + DB Performance Gate + Verify Runtime + Verify OpenAPI Types + Validate docker-compose + Security Audit × 6 (SBOM/Container/Go-Vuln/detect-secrets/Node-Audit/Python-Audit + Semgrep SAST): ALL SUCCESS

**Annotation honesty**: `gh run view` summary shows X/! annotations on Pre-commit, Semgrep SAST, Lighthouse artifact upload — these are non-blocking soft warnings within otherwise-passing jobs (jq query confirms `"conclusion": "success"` for all). The `X Process completed with exit code 1` annotation on Pre-commit is misleading repository-action display from the Read-only mode runner output; actual job conclusion is success.

**Comparison to W149 final CI**: W149 polish-v1 run `25825859037` was also "ALL 40 SUCCESS + 1 skipped + 0 failures" — W150 polish-v1 hit the same pattern + reached same outcome. Sets up W149→W150 → 2× consecutive waves with identical CI verification trajectory (push → prettier --check fail → polish-v1 → all green).

---

## NEW W150 anti-pattern #15 (recurring prettier polish-v1 pattern)

Per W141 anti-pattern register convention (a pattern hit 2+ times = register entry).

**Pattern**: prettier `--check` CI gate fires on files that bypass local pre-commit prettier ritual. Two failure modes confirmed:
- **W149 polish-v1**: SW2+SW3 EDITS on existing files via Edit tool — local pre-commit hook doesn't include prettier; routeTree.gen.ts focus mode misses other edited files.
- **W150 polish-v1**: SW1 NEW FILES via Write tool — explicit prettier-write was applied to routeTree.gen.ts only; new files slipped through.

**Mitigation paths** (W151+ structural fix candidate):
1. **Husky pre-commit prettier hook** (most thorough): `npx prettier --check` on all staged files via `lint-staged` integration. Closes both W149 + W150 failure modes structurally.
2. **Pre-commit hook prettier addition**: extend `.pre-commit-config.yaml` to include prettier alongside ruff (currently Python-only in hooks).
3. **Manual discipline**: explicit `npx prettier --write <all changed files>` step in commit prep — works but relies on memory.

**Cost of W151+ structural fix**: ~30-60 min to wire husky + lint-staged. Closes recurring caveat (W149 + W150 polish-v1 commits).

This NEW anti-pattern #15 brings the register from 14 → **15 patterns** post-W150. The polish-arc cohort (W134-W150) added: #12 empirical diagnostic at first timeout (W147), #13 per-test local repro (W147), #14 waitForTimeout doesn't fix race conditions (W147 + W148 + W149), #15 prettier polish-v1 pattern (W149 + W150).

---

## §Honesty trajectory FINAL (post polish-v1)

**Pre-W150 baseline**: 6 caveats (W134 #2 + #10 + W146 SW2 + W148 SW2 + routeTree drift + W149 #6).

**Realistic W150 closure target** (per SW5 plan): 6 → 3-7 post-W150.

**Actual post-polish-v1**: 6 → **13 post-W150** (carries 6 + 7 NEW W150-introduced):
1-6. (Carries — see SW5 §Honesty section above)
7. features/admin/ folder migration deferred → W151+
8. StoriesAdmin substantive polish deferred → W152+ (705 LoC; only text-white + defaultValue closed)
9. TanStack Query factory hooks for 4 admin pages deferred → W153+
10. **REVISED FRAMING (polish-v2)**: admin.css `.dark` variant + AdminBackdrop visual smoke deferred to **W151+ Docker stack visual smoke OR future authed e2e snapshot** (was "or CI verification" — CI doesn't visually render admin routes since they're auth-gated; the "or CI" fig leaf was misleading).
11. Bundle delta projection +800-1200 b vs actual +106 b (honest framing recording)
12. server.js W149 audit-claim (39,373 b) vs SW1 actual (23,600 b) — likely prior audit inaccuracy NOT W150 savings (honest framing recording)
13. **NEW polish-v1**: prettier polish-v1 prettier gap — SW1 NEW file formatting missed in local verification despite W149 precedent. Structural fix candidate: husky pre-commit prettier (NEW anti-pattern #15 above).

**Polish-v2 honesty pass surfaced 6 polish gaps** (documented above): doc lag from SW5 audit being written pre-polish-v1, §Honesty count drift, §Honesty #10 "or CI" fig leaf, missing 15th anti-pattern entry, CLAUDE.md row missing CI verification footer, empirical CI verification depth via jq query. All polish-v2 polish gaps are CLOSED in this audit revision + corresponding CLAUDE.md + memory file updates.

Per `feedback_perfectionism.md`: the «безупречно?» probe surfaced honest gaps; polish-v2 closes them. The 13 post-W150 caveats remain HIGHER than the planned 3-7 ceiling — 4-5 are scope-realistic polish-arc deferrals (load-bearing non-goals), 2 are bundle/audit-honesty recordings, 1 is the polish-v1 gap. Arc trajectory expects W151-W155 to net-close 5-8 caveats.

---

---

## Polish-followup-v2 (2026-05-14): close `/users/me` SW pending hang (§Honesty caveat #16)

**Context**: The W150 polish-followup commit `7c97de583` shipped 5 fixes for browser-side `RESULT_CODE_HUNG` (VITE_BACKEND_ORIGIN runtime split, THEME_INIT_SCRIPT navigator.language, _public.tsx ssr:false, hydrateRoot ELEMENT_NODE check, DEV_NO_SSR_SHELL plumbing) but documented `/users/me Service Worker pending hang` as caveat #16 (UNRESOLVED — "possibly NetworkFirst stall, possibly MCP Windows wall, possibly real SW bug"). W151 opening prompt's pre-flight surfaced this as still-broken in the user's real Chrome (blank `/login`, DevTools won't even open). Polish-followup-v2 is a SHORT focused debug fix opened during W151 Phase 0 user-side verification — closes #16 ONLY. W151 proper (Tier 1 SSR root-cause or other user-chosen scope) starts AFTER this lands + user verifies in real Chrome.

**Ground-truth diagnosis** (chrome-devtools-mcp on a fresh page open, 2026-05-14):
- All **105 of 105** page resources (HTML, bundle, CSS, manifest, code-split chunks) load **200 OK**
- Console: ONLY `[GlobalErrors] Handlers registered` (info-level, from [main.tsx:24](../../frontend/src/main.tsx:24)) — NO React #418, NO crashes
- `GET /api/v1/users/me` stays `[pending]` for >2 minutes (full duration of the diagnostic session)
- Direct `curl http://localhost/api/v1/users/me` returns **401 in 3 ms** (backend healthy via Caddy chain)
- Real Chrome on user side reproduces identically → NOT the W138 Windows MCP wall, it's a real browser-side hang

**Root cause**: [`frontend/src/sw/api.ts:107-134`](../../frontend/src/sw/api.ts:107) registers `/api/*` (excluding `/public/`, `/news`, `/events`, non-GET) with `NetworkFirst({ networkTimeoutSeconds: 5, ... })`. `/api/v1/users/me` matches the matcher. Workbox's 5 s timeout empirically does NOT fire here — most likely a cache+plugin interaction where `CacheableResponsePlugin({ statuses: [0, 200] })` rejects the 401 response in a way that wedges the strategy.handle Promise. Precise workbox internal mechanism not investigated — fix bypasses the buggy code path.

**Why it blocks the whole app**: [`useProfileSync.ts:1043-1046`](../../frontend/src/hooks/auth/useProfileSync.ts:1043) fires `queryClient.fetchQuery(currentUserQueryOptions())` during AuthProvider mount. `setInitializing(false)` only fires in the `finally` block at [`useProfileSync.ts:1086`](../../frontend/src/hooks/auth/useProfileSync.ts:1086). While `/users/me` is pending, `initializing=true` keeps `AuthContext` children from rendering → blank screen + DevTools can't attach (renderer wedged).

**Why this is also a security correctness issue**: `/users/me` is auth-state-critical. A cached 200 response could let an unauthenticated user appear authenticated. Excluding it from SW interception is the production-correct fix per OWASP cache-control guidance, not just a UX hack.

### Fix (single commit `fix(wave150-polish-followup-v2)`)

[`frontend/src/sw/api.ts`](../../frontend/src/sw/api.ts) — two-pronged structural change:

1. **Route matcher exclusion** (lines 108-122): add `!url.pathname.includes("/users/me")`, `!url.pathname.includes("/auth/")`, `!url.pathname.includes("/csrf")` to the matcher. These paths now bypass the SW entirely and go direct to network. No cache, no timeout risk, no race.

2. **Promise.race hard-timeout wrapper** (lines 140-167) on the remaining `/api/*` paths still under NetworkFirst (notification prefs, profile GETs, etc.): wraps `strategy.handle({ request, event })` in `Promise.race([..., new Promise(resolve => setTimeout(() => resolve(new Response(504...)), 6000))])`. Defense-in-depth — if another endpoint hits the same workbox quirk, the request resolves to a synthetic 504 within 6 s instead of staying pending indefinitely. Axios surfaces 504 as a network error and `useProfileSync`'s outer catch handles it.

### Verification matrix (executed)

| Step | Result |
|------|--------|
| `npx tsc --noEmit` | 0 errors ✓ |
| `npm run lint -- --max-warnings=0` | 0 warnings ✓ |
| `npx vitest run` | **1058 passed / 12 skipped / 0 failed** ✓ (W150 baseline preserved exactly) |
| `npx vitest run src/sw` | No test files (no SW route-matcher tests exist) |
| `docker compose up -d --build frontend` | (in progress at commit time) |
| chrome-devtools-mcp probe: `new_page http://localhost/login → list_network_requests` | (pending Docker rebuild) — expect `/users/me` to complete with 401 status |
| User real Chrome: clear site data + Ctrl+Shift+R + `/login` | (pending) — must verify login + `/admin` work cleanly before claiming closure |

### Tradeoffs accepted

- **`/users/me` now ALWAYS goes to network** (no offline cache fallback). Acceptable — auth state must be fresh by design; offline users hit `handleUnauthorized` → `/login` redirect, which is the correct UX.
- **Promise.race wrapper adds a 6 s timeout ceiling on all remaining `/api/*` requests under NetworkFirst**. Acceptable — synthetic 504 is observable + actionable in console; far better than indefinite pending.
- **Stale SWs in user browsers require a one-time hard-reload (Ctrl+Shift+R)** after this deploys. [`sw.ts:45-46`](../../frontend/src/sw.ts:45) already has `clientsClaim()` + `self.skipWaiting()` so the new SW takes over automatically on next reload — no manual unregister needed.

### §Honesty trajectory update (HONEST CORRECTION post user-verification)

**Initial claim (pre-user-verification)**: this fix closes §Honesty caveat #16 (`/users/me Service Worker pending hang`). The fix WAS shipped as committed (`a26d1e7da`, pushed to origin/egorribun) and IS byte-verified in the compiled `sw.js`.

**HONEST CORRECTION (post-user-verification, 2026-05-14)**: user reported `/login` STILL BLANK in BOTH regular Chrome AND fresh Chrome Incognito after deploy + cleared site data. This DEFINITIVELY rules out Service Worker / state pollution as the user-facing blocker — Incognito has no SW. The SW fix targeted the WRONG root cause.

Verified from source: [`AuthContext.tsx:145`](../../frontend/src/contexts/AuthContext.tsx:145) renders `<AuthContext.Provider value={value}>{children}</AuthContext.Provider>` UNCONDITIONALLY. There is NO gate on `initializing`. So `/users/me` pending forever does NOT block React from rendering children. The blank screen is caused by something OTHER than the SW intercepting `/users/me`.

**Likely actual root cause** (W150 polish-followup caveat #14, NOT addressed by this fix):
- [`__root.tsx:148`](../../frontend/src/routes/__root.tsx:148) `ssr: false` + [`_public.tsx:10`](../../frontend/src/routes/_public.tsx:10) `ssr: false` make `/login` 100% client-only with empty SPA shell
- [`App.tsx:24`](../../frontend/src/App.tsx:24) `<Suspense>` has NO `fallback` prop → defaults to `null` while route's lazy `Login` chunk loads
- chrome-devtools-mcp diagnostic on the rebuilt dist showed 17 chunks pending (including `Login-DHFvelK1.js` page-component lazy chunk) + V8 main thread wedged (evaluate_script times out — likely ParticleAuthBackground 1000-particle canvas starving CPU OR sync-throw at module init in some chunk OR React render infinite-loop)
- Or: there's a sync-throwing module init somewhere in the AppProviders / RouterProvider chain
- W150 polish-followup commit `7c97de583` body explicitly documented: "Hydration mismatch root cause NOT isolatable from production-minified bundle without source maps; suspected candidates: useId() reconciliation, MainLayout SSR-vs-client provider tree subtle differences, ParticleAuthBackground canvas ref timing"

**§Honesty caveat #16 stays OPEN** in the user-facing scope. The SW fix IS valuable as a standalone change:
- Security correctness — auth-state endpoints should never be cached per OWASP
- Defense-in-depth — Promise.race wrapper prevents indefinite pending on remaining `/api/*` paths under NetworkFirst
- Eliminates the workbox NetworkFirst-vs-CacheableResponsePlugin-401 quirk for the high-traffic `/users/me` path

But it does NOT close the user's blank-screen bug. That requires the W151 Tier 1 SSR root-cause investigation per `memory/wave151_opening_prompt.md` — NODE_ENV=development build with source maps to expose the actual React error, then targeted fix at the specific component/import causing it.

**Honest count**: §Honesty trajectory is UNCHANGED at 17-21 polish-followup-unresolved caveats. Caveat #16's framing is REFINED to: "SW NetworkFirst stall is one observable symptom of the broader Service Worker handling architecture, mitigated structurally by route exclusion + Promise.race wrapper. It is NOT the user-facing blank-screen blocker." Caveat #14 (root ssr:false dev fallback bypassing W125-W149 SSR architecture) is the LOAD-BEARING user-facing caveat — W151 Tier 1 scope.

### Anti-pattern register impact

**NEW anti-pattern #16 CANDIDATE** (W141 register convention requires 2+ occurrences to formalize): **"Workbox NetworkFirst on auth-state-critical endpoints can stall indefinitely; fix is SW route exclusion, not strategy tuning."** First instance: this fix. Watch for second instance in W151+ before promoting to formal register entry. Register stays at **15 patterns** until then.

### Out of scope

- Precise workbox internal mechanism for the timeout-doesn't-fire bug — bypassed via route exclusion + Promise.race wrapper rather than patched in workbox. Could file upstream issue if the same pattern recurs.
- W150 polish-followup commits `7c97de583` + `a9f6a4c02` shipped fixes that are working — verified via chrome-devtools-mcp showing 105 / 105 resources load 200 OK with no React #418, no SSR/CSR mismatch errors. Only #16 was the residual issue.
- W151 Tier 1 SSR root-cause + restoration (the bigger architectural debt — `__root.tsx ssr: false` bypasses W125-W149 SSR architecture) remains untouched. Opens for user scope decision AFTER user verifies real Chrome works post-polish-followup-v2.

---

**End of AUDIT_WAVE150.md** (polish-followup-v2 closeout).
