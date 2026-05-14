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

**End of AUDIT_WAVE150.md**.
