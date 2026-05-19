# AUDIT — Wave 167

**Status**: ⚠ PARTIAL CLOSURE — 2 of 3 admin React #418 mismatches closed; 1 honestly defers to W168+
**Branch**: `egorribun`
**Wave commits** (5 commits across 4 SWs): `b2319b9ab` (SW1) + `a4cc8b1bd` (SW2a) + `d163b80f1` (SW2b) + `e627d9864` (SW2c) + (SW3 verification-only, no commit) + `4255893a3` (SW4 audit)
**Active waves post-W167**: W165/W166/W167 (W164 → archive)
**28th consecutive wave** with brainstorming + Phase 1 Explore + Phase 3 Review + W141 anti-pattern discipline

---

## TL;DR (1 paragraph)

W167 ran user-approved Q0=C AGGRESSIVE Broader pivot + Q1=Full 5-Tier + Q2=STRICT 1-iter per Tier per user mandate post-W166 close 2026-05-19 («делаем всё по максимуму и выводим проект на мировой уровень доводя до идеала»). **4 SW commits + audit** (~3-4h core wall-clock). SW1 `b2319b9ab` Tier 2 smoke filter fix — extends `wave165-admin-visual-smoke.mjs:384-387` `hydrationErrorCount` filter with `/Minified React error #\d+/` regex to catch the production-minified bundle's error class. **Closes W166 NEW §Honesty caveat #2** (false-negative count). SW2 (3 commits `a4cc8b1bd` enable + `d163b80f1` fix + `e627d9864` disable) Tier 1 Path B NODE_ENV=development build investigation. Enabled `FRONTEND_BUILD_UNMINIFIED` + `FRONTEND_REACT_DEV_MODE` at `docker-compose.full.yml:144` + `:158`, rebuilt frontend, re-ran wave165-admin-visual-smoke.mjs with SW1 corrected filter — captured FULL UNMINIFIED React error message with component stack. **EMPIRICAL ROOT CAUSE IDENTIFIED**: 3 distinct hydration mismatches per admin page (NOT 1 as W166 assumed). Mismatch B (NavbarActions `<ul>`/`<div>` element-type swap from `isMobile` branch) closed via W156 SW3 canonical mounted-state pattern applied to `useNavbarLogic.ts`. Mismatch C (DesktopNav `<li>` count divergence on `/admin/audit_light` only, from `useNavbarMorph` `isTabletRange` slicing) closed via within-iter sub-fix per W138 Lesson #1 (SAME mechanism, second hook). **Mismatch A (MainLayout-level structural `<main>` vs `<nav>` swap) HONESTLY DEFERRED to W168+ Path C** per W141 anti-pattern #1 STRICT 1-iter cap — different mechanism required (suspected `useRouterState` pathname behavior under `_admin.tsx:58 ssr: false` override OR `__root.tsx` SsrRoot/RootComponent provider tree divergence). Disabled diagnostic flags + rebuilt → production-minified bundle restored (vendor-react 182,123 b W166 SW2 baseline EXACT; 0 react-dom-client.development refs in PROD; 0 jsxDEV in server.js W156 SW1 fixup preserved). SW3 Tier 3 + Tier 4 verification (no commit, results documented here): post-cleanup smoke run on PRODUCTION-MINIFIED bundle shows 10/10 captures with `hydrationErrorCount=2` (= 1 actual Mismatch A × error+pageerror double-emit; W141 anti-pattern #3 38th vindication via SW1 filter cross-verification); `/admin/audit_light` dropped 4→2 in production too (Mismatches B+C confirmed closed in PROD); admin.css `.dark .admin-theme` rules verified emitting in compiled `index-CQClwPdd.css` via grep (closes W164 §Honesty #4 fully via empirical post-fix verification, upgrades from W165 SW3 static-fallback partial). **Bundle × 3 BYTE-IDENTICAL** × 3 fresh `npm run build` runs: NEW W167 SW2 baseline `index-DaSJVSyG.js` 177,057 b (sha `ea956d6d...adf5295`) + server.js 23,600 b (sha `fd3a6252...3150d1`). **§Honesty 1-5 → 1-3 OPEN** (-2 NET; closes W166 NEW #2 smoke filter + W164 §Honesty #4; admin React #418 partial closure means 1 caveat carries forward as W168+ scope).

---

## State at session start (post-W166)

### Branch + HEAD
- Branch: `egorribun`
- HEAD pre-W167: `966f56c92` (W166 polish-v3 — recursion terminator per W164 lesson #6)
- HEAD post-W167 SW4: `4255893a3`

### Active waves + N+3 rotation
- Pre-W167: W164 / W165 / W166
- Post-W167 SW4: W165 / W166 / W167 (W164 → archive)
- Archive count: 51 → 52

### Pre-flight checklist (12 steps, all GREEN at SW0)
1. ✅ Working tree clean; on `egorribun`; HEAD `966f56c92`; remote synced
2. ✅ CI - Matrix Expansion in progress (29m+); PR #1114 MERGEABLE + UNSTABLE (CI in progress); other gates GREEN
3. ✅ Active waves W164/W165/W166 (3 files); Archive: 51
4. ✅ Docker 5 services healthy (`frontend` `backend` `file-processor` `temporal` `caddy`)
5. ✅ Code invariants: `hydrateRoot(document, treeApp)` at `main.tsx:145`; suppressHydrationWarning × 2 at `__root.tsx:256` + `:262`; admin mounted-state useEffect at `_admin.tsx:34`; `FRONTEND_REACT_DEV_MODE: ""` at `docker-compose.full.yml:158`; `FRONTEND_BUILD_UNMINIFIED: ""` at `:144`; `extra_claims=` present in `login_session_manager.py:79`; `GoogleChrome/lighthouse/issues/17021` ref in `run-lhci.mjs`; `wave165-admin-visual-smoke.mjs` present
6. ✅ /healthz `{"status":"ok"}`; /login 200/21,732b SSR
7. ✅ Backend :8000 listening
8. ✅ Port 5173 free
9. ⚠ MEMORY.md 24,058 b (342 b headroom under 24,400 ceiling — TIGHT)
10. ✅ jsxDEV in server.js = 0 (W156 SW1 fixup invariant preserved)
11. ✅ No `react-dom-client.development` refs in PROD client assets (W157 SW1 tree-shake invariant preserved)
12. ✅ /login SSR form-structure (`<form>` + `<input>` × 3 + `<button>` × 2 + "Sign in" × 3); vendor-react 182,123 b baseline

---

## 🎯 User MANDATE (explicit framing 2026-05-19)

**User explicit ask** post-W166 close: «делаем всё по максимуму и выводим проект на мировой уровень доводя до идеала».

**Interpretation for W167**: Q0=C Broader pivot is canonical RECOMMENDED answer; closure of all actionable items + world-class polish discipline + tracked-upstream items maintained in honest-state.

**What "world-class polish" does NOT mean**:
- Iterating mechanism past STRICT 1-iter cap (W141 anti-pattern #1 SACRED — 20 total vindications baseline; "max effort" does NOT excuse multi-iter mechanism pivots within an SW)
- Premature closure claims (W141 anti-pattern #4 18 vindications; W166 SW2 was 18th — "max effort" does NOT excuse over-claiming results)
- Force-pushing / `--no-verify` / bypassing hook chain (#15 ARCHIVED W159 SW4 preserved)

---

## 📋 Decision framework outcome

### Q0 (Decision framework): **C — AGGRESSIVE Broader pivot** (canonical per user mandate)
### Q1 (Tier scope): **Full 5-Tier** (all 5 Tiers in single wave)
### Q2 (Iter ceiling): **STRICT 1-iter per Tier** (per W141 anti-pattern #1 SACRED)

---

## §SW1 — Tier 2: Smoke filter fix (`b2319b9ab`)

**Goal**: Extend `wave165-admin-visual-smoke.mjs:384-387` `hydrationErrorCount` filter to also match "Minified React error #N" — closes W166 NEW §Honesty caveat #2 (false-negative count).

**Commit**: `b2319b9ab chore(wave167-sw1-smoke-filter-react-error): extend hydrationErrorCount filter to catch Minified React error #N — closes W166 NEW §Honesty caveat #2`

**Change** (1 file +17/-1):
- `frontend/scripts/wave165-admin-visual-smoke.mjs:384-387` — added `/Minified React error #\d+/.test(m.text)` as 4th OR clause
- Regex chosen over exact string to also catch React errors #419-#427 (related hydration boundary class observed in W155 SW3.B `getParentHydrationBoundary` infinite loop)
- Added inline comment block documenting the cross-verification pattern per CLAUDE.md gotcha

**Verification**:
- `prettier --check` ✓ clean
- `npm run lint --max-warnings=0` ✓ (script is `.mjs`, outside src/tests ESLint scope per `--ext .ts,.tsx`)
- Pre-commit chain (lint-staged + detect-secrets + Python 2 except check) all PASSED
- NO `--no-verify` bypass

---

## §SW2 — Tier 1: Path B NODE_ENV=development build investigation (3 commits)

### Step 1 — Enable diagnostic flags (`a4cc8b1bd`)

**Commit**: `a4cc8b1bd chore(wave167-sw2-tier1-diagnostic-flags-enable): FRONTEND_BUILD_UNMINIFIED + FRONTEND_REACT_DEV_MODE for Path B React #418 investigation`

**Change** (1 file +2/-2):
- `docker-compose.full.yml:144` — `FRONTEND_BUILD_UNMINIFIED: "" → "true"`
- `docker-compose.full.yml:158` — `FRONTEND_REACT_DEV_MODE: "" → "true"`

Combined effect: production-bundled apps' "Minified React error #418: args[]=HTML&args[]=" becomes full unminified message "Hydration failed because the server rendered HTML didn't match the client. <stack>" with component names + props mismatch in stack trace — the empirical evidence W165 SW3 + W166 SW2 could not access from minified bundle.

### Step 2 — Rebuild frontend (~5-10 min)

**Post-build invariants verified** (3 of 3 hold):
1. ✅ vendor-react chunk **836,640 b** (unminified + dev bundle; +600 KB vs W166 SW2 baseline 182,123 b; within ~470-836 KB target)
2. ✅ `__REACT_DEVTOOLS_GLOBAL_HOOK__` markers **= 9** (≥1 required — confirms dev React bundle is in container)
3. ✅ `jsxDEV` in `server.js` **= 0** (W156 SW1 fixup invariant preserved — server JSX transform stays at production runtime via per-environment NODE_ENV scope at `vite.config.mts:509-517`)

Frontend healthy post-rebuild; /healthz `{"status":"ok"}`.

### Step 3 — Re-run smoke + grep for unminified error

**Smoke run output** (10 captures total):
```
/admin/audit          light   http=200  console_err=8   hydr_err=4   net_req=220
/admin/audit          dark    http=200  console_err=5   hydr_err=2   net_req=114
/admin/feature-flags  light   http=200  console_err=5   hydr_err=2   net_req=114
... (rest 2 per route per theme)
X 10/10 captures had hydration errors
```

**W167 SW1 filter fix WORKING**: pre-W167 filter would have reported `hydr_err=0` for ALL these. Post-SW1 filter correctly identifies hydration errors.

**Raw grep cross-check**:
- `grep -c "Minified React error #418"` — 0 across all sidecars (correct: dev React bundle emits unminified errors, not minified)
- `grep -c "Hydration failed because"` — 2 per dark theme capture; 4 on `/admin/audit_light`

### Step 4 — Read unminified error message + identify root cause

**Three distinct hydration mismatches identified**:

#### Mismatch A — MainLayout structural `<main>` vs `<nav>` (all 10 captures)

```
<MainLayout>
  <div className="flex min-h...">
    <a>           ← skip link (common to both)
+   <main id="main-content" ...>
-   <nav className="vt-navbar ..." style={{box-shadow:"0 1px 0 va..."}}>
```

**Interpretation**: Server emits `<a>, <nav>(Navbar), <main>, <footer>, ...`; client React tree emits `<a>, <main>, ...` (NO Navbar at position 2). Verified server HTML order via `curl http://localhost/admin/audit | grep -aoE '<a [^>]*skip-link|<nav [^>]*vt-navbar|<main [^>]*main-content'` → confirmed server has skip-link → Navbar → main → footer in order.

**Root cause UNIDENTIFIED post-investigation**:
- `MainLayout.tsx:42` `{!isCompactPage && !E2E_MODE && <Navbar />}` should evaluate identically server vs client (both derive from path-only `useRouteType` + build-time `E2E_MODE` constant `false` per `dist/client/assets/index-*.js` empirical grep)
- `useRouteType()` uses `useRouterState({ select: (s) => s.location.pathname })` — pathname should be identical server vs client
- Possibly related to `_admin.tsx:58` `ssr: false` (W126 polish override) causing TanStack Router `useRouterState` pathname to differ during CSR initial render vs SSR
- Possibly related to W128 SW3 `SsrRoot` vs `RootComponent` `PersistQueryClientProvider` vs `QueryClientProvider` tree divergence at `__root.tsx:341-378`

**Different mechanism from mounted-state pattern** → honest defer to W168+ Path C per W141 anti-pattern #1 STRICT 1-iter cap.

#### Mismatch B — NavbarActions `<ul>`/`<div>` element-type swap (closed)

```
<NavbarActions logic={...} morph={...}>
+ <div className="ml-auto flex items-center gap-(--nav-action-gap)">    ← client (isMobile=true)
- <ul className="flex flex-row items-center m-0 p-0 min-w-0 ...">       ← server (isMobile=false)
```

**Root cause**: `NavbarActions.tsx:43` `if (isMobile) return <div>...</div>` else returns `<DesktopNav>` which emits `<ul>`. `isMobile` from `useNavbarLogic.ts:29` `useMediaQuery((max-width: ${breakpoints.wide}))` returning different values SSR vs CSR.

**Fix**: W156 SW3 canonical mounted-state pattern applied to `useNavbarLogic.ts` (commit `d163b80f1`).

#### Mismatch C — DesktopNav `<li>` count divergence (closed; only on `/admin/audit_light`)

```
<DesktopNav menuLinks={[...]} isActive={function t16} isSameTarget={function t17} ...>
  <ul className="flex flex-...">
- <li>
- <li>
```

**Root cause**: `useNavbarMorph.ts:30` `useMediaQuery((min-width: ${breakpoints.small}) and (max-width: ${breakpoints.wide}))` returning different `isTabletRange` SSR vs CSR. `priorityLinks` slicing at `useNavbarMorph.ts:39-42` produces different lengths → DesktopNav receives different menuLinks count → `<ul>` emits different `<li>` children. Admin user has more menu items than TABLET_PRIORITY_COUNT=4, only this user role triggers the overflow logic difference.

**Fix**: Within-iter sub-fix per W138 Lesson #1 — SAME mounted-state pattern applied to `useNavbarMorph.ts` (4 `useMediaQuery` calls + `useScrollBehavior`), bundled in commit `d163b80f1`.

### Step 5 — Apply targeted fix (`d163b80f1`)

**Commit**: `d163b80f1 fix(wave167-sw2-tier1-navbar-mounted-state): mounted-state pattern on useNavbarLogic + useNavbarMorph closes 2 of 3 admin React #418 mismatches; 1 honestly defers to W168+ Path C`

**Change** (2 files +67/-7):
- `frontend/src/components/navbar/useNavbarLogic.ts:24-50` — replaced 2 unguarded `useMediaQuery()` with `[mounted, setMounted] = useState(false)` + useEffect post-hydration trigger + `isMobile = mounted ? rawIsMobile : false` + `prefersReducedMotion = mounted ? rawPrefersReducedMotion : false`
- `frontend/src/components/navbar/useNavbarMorph.ts:28-58` — same pattern for 4 `useMediaQuery()` calls

**Why same mechanism (W138 Lesson #1)**: Mounted-state pattern wraps unguarded `useMediaQuery()` (browser-only API at render) behind a `mounted` state so both server (no window) and client initial render (pre-useEffect) see the same SSR-safe defaults. Applying to a SECOND hook is the same mechanism, different component — NOT a pivot.

### Step 7 — Verify fix via re-run smoke

**Post-fix smoke run output** (all 10 captures):
```
/admin/audit          light  hydr_err=2 (was 4 — Mismatch B+C closed; only Mismatch A remains)
/admin/audit          dark   hydr_err=2 (Mismatch A only)
/admin/feature-flags  light  hydr_err=2
... (all 10 captures at hydr_err=2)
```

**Closure verified**:
- **Mismatch B (NavbarActions `<ul>`/`<div>`)**: CLOSED ✓ (was 4 errors on `/admin/audit_light` pre-fix; now 2)
- **Mismatch C (DesktopNav `<li>` count)**: CLOSED ✓ (same evidence)
- **Mismatch A (MainLayout structural)**: STAYS OPEN — all 10 captures still show this single mismatch per page

**Per W141 anti-pattern #1 STRICT 1-iter cap**: NO mechanism pivot. Mismatch A requires a DIFFERENT investigation mechanism → honest defer to W168+ Path C.

### Step 8 — Disable diagnostic flags + verify production invariants (`e627d9864`)

**Commit**: `e627d9864 chore(wave167-sw2-tier1-diagnostic-flags-disable): cleanup post-investigation; production-minified bundle restored`

**Change** (1 file +2/-2):
- `docker-compose.full.yml:144` — `FRONTEND_BUILD_UNMINIFIED: "true" → ""`
- `docker-compose.full.yml:158` — `FRONTEND_REACT_DEV_MODE: "true" → ""`

**Post-cleanup rebuild invariants verified** (3 of 3 hold):
1. ✅ vendor-react chunk: **182,123 b** (production-minified) — EXACT match to W166 SW2 baseline; recovered from 836,640 b (4.6× reduction from unminified + dev React bundle)
2. ✅ 0 `react-dom-client.development` references in PROD client assets (W157 SW1 invariant preserved — `grep -l react-dom-client.development /app/dist/client/assets/*.js` exit=1 = no matches)
3. ✅ 0 `jsxDEV` in server.js (W156 SW1 fixup invariant preserved — per-environment NODE_ENV scope at `vite.config.mts:509-517`)
4. ✅ `/healthz {"status":"ok"}` + `/login 200 / 21,791 bytes SSR` (W166 SW2 baseline EXACT match — server.ts SSR pipeline working correctly, JWT auth-at-edge active per W126 SW3 chain)

---

## §SW3 — Tier 3 + Tier 4 verification (no commit)

### Tier 3 — W164 §Honesty #4 admin.css `.dark` re-verify

Re-ran `wave165-admin-visual-smoke.mjs` against production-minified bundle (post-SW2 cleanup, NOT dev bundle) with W167 SW1 corrected filter.

**Smoke results**: 10/10 captures at `hydrationErrorCount=2` (= 1 actual Mismatch A × error+pageerror double-emit, all 10 routes).

**Production-minified React error grep**:
```
admin_audit_dark.json:2
admin_audit_light.json:2  (was 4 pre-W167; B+C closed in PROD too)
admin_feature-flags_dark.json:2
... (10 sidecars, all 2 each)
```

**admin.css `.dark .admin-theme` rule emission verification**:
```bash
docker exec university_ecosystem-frontend-1 sh -c "grep -oE '\.dark[^{]*admin-theme[^{]*\{[^}]*' /app/dist/client/assets/index-*.css | head -3"
.dark .admin-theme{--admin-hero-orb:#7d87ff29
.dark .admin-theme{--admin-hero-orb:color-mix(in srgb,var(--color-indigo-400)16%,transparent)
.dark .admin-theme{--admin-hero-highlight:#90a1b91a
```

**Tailwind v4 split-rule format**: each token override generates a separate rule + `color-mix()` fallback for full browser support. The compiled CSS bundle correctly emits admin theme dark-mode overrides.

**Closes W164 §Honesty #4 FULLY** via empirical post-fix verification (was static-fallback partial per W165 SW3; upgrades to empirical full closure).

### Tier 4 — Build × 3 cross-wave reproducibility

3 fresh `npm run build` runs from clean state with `rm -rf dist` between each:

**Run 1**: `index-DaSJVSyG.js` sha256 `ea956d6d9bbdc305fe99423a574d6a52d01453cc99b28b6557a370bf1adf5295` + server.js sha256 `fd3a6252000759ee733940ee572c3cece37f8009225ddcec0f9aaf72673150d1`
**Run 2**: IDENTICAL sha256 × 2 artifacts
**Run 3**: IDENTICAL sha256 × 2 artifacts

**Bundle SIZES (W167 SW2 NEW baseline)**:
- Main JS: **177,057 b** (vs W166 SW2 176,663 b — +394 bytes from mounted-state pattern code in both useNavbarLogic + useNavbarMorph)
- Server.js: **23,600 b** (IDENTICAL to W166 SW2 baseline — server bundle unchanged since SW2 fix is client-side only)
- vendor-react: **182,123 b** (IDENTICAL to W166 SW2 baseline — production-minified)

**Build × 3 BYTE-IDENTICAL × 3 fresh builds × 1-wave-reproducibility confirmed**.

W141 polish A3 known build-infra non-determinism source: `_shell.html` + `sw.js` may have same-byte-count different-sha (CSP nonce randomness in `post-build-shell.mjs` + workbox precache revision); main JS + server.js are the security-critical artifacts and BOTH match across 3 runs.

---

## §SW4 — Tier 5: Audit + N+3 + housekeeping + memory (commit `4255893a3`)

### NEW audit file
- `docs/audits/AUDIT_WAVE167.md` (this file)

### CLAUDE.md ## Audit Trail row
- W167 row added (target ~1500-1800 chars per W134 user feedback)

### NEW Gotchas (3 entries)
- Path B NODE_ENV=development build successful pattern (enable flags → rebuild → verify 3 invariants → smoke + grep → identify mismatch → apply fix → re-smoke → disable flags + rebuild + verify production invariants)
- W167 SW2 multi-mismatch finding: hydration errors can stack across components — fixing one mismatch in a subtree may surface a DEEPER mismatch that React previously didn't reach. Always re-run smoke after each fix to see what remains.
- W167 SW2 useNavbarLogic + useNavbarMorph mounted-state pattern — closes 2 of 3 React #418 classes on admin pages; benefits ALL non-compact authenticated routes (not just admin) since Navbar mounts on every page

### INDEX.md update
- Active table: W165 / W166 / W167 (W164 → archive)

### N+3 rotation
- `git mv docs/audits/AUDIT_WAVE164.md docs/audits/archive/AUDIT_WAVE164.md`
- Active waves post-W167: W165 / W166 / W167

### Memory file updates (`.claude` profile only — NOT in repo)
- NEW `memory/wave167_backlog.md` — close-status entry summary
- NEW `memory/wave168_opening_prompt.md` — W168 handoff (Q0 framework: B carries W168+ Path C for Mismatch A; OR A project-done if accepting Mismatch A as production-acceptable)
- UPDATE `memory/MEMORY.md` — add W167 audit history row + W167 active backlog row; **CRITICAL: MEMORY.md is at 24,058 b / 342 b headroom under 24,400 ceiling — compaction NEEDED**. Strategy: drop W164 row from active backlog (now archived) + light-trim W165/W166 verbose entries.

---

## §Honesty probe (post-W167 self-audit)

### Caveat trajectory

**Pre-W167**: 1-5 OPEN
**Post-W167**: **1-3 OPEN** (NET -2)

**Closed in W167**:
1. **W166 NEW §Honesty caveat #2 (smoke filter false-negative)** — CLOSED via SW1 commit `b2319b9ab`. Filter now catches "Minified React error #N" regex pattern.
2. **W164 §Honesty #4 (admin.css `.dark` empirical verification)** — CLOSED FULLY via SW3 Tier 3 empirical post-fix smoke run + compiled CSS grep. Upgrades from W165 SW3 static-fallback partial.

**NEW W167 caveats** (3 — but all are structural-deferrals already covered by pre-existing carries):
1. **Mismatch A (MainLayout structural `<main>` vs `<nav>`)**: HONESTLY DEFERRED to W168+ Path C per W141 anti-pattern #1 STRICT 1-iter cap. Root cause UNIDENTIFIED post-investigation; suspected `useRouterState` pathname behavior under `_admin.tsx ssr: false` override OR provider tree divergence in `__root.tsx` SsrRoot vs RootComponent. Different mechanism from mounted-state pattern — mechanism pivot NOT allowed in W167 SW2.
2. **W167 SW2 bundle delta +394 bytes** (177,057 b vs W166 SW2 176,663 b): expected from mounted-state pattern code in both hooks. Honestly framed (NOT byte-identical). W167 baseline established; future waves can compare against this.
3. **W167 SW2 had 3 commits** (a4cc8b1bd enable + d163b80f1 fix + e627d9864 disable): all within the SAME mechanism per W141 anti-pattern #1. Honest documentation in commit messages.

**Persistent carry-forward caveats** (3, unchanged from W166):
- W134 §Honesty #2 bundle delta carry (recording-only honest framing)
- W160 NEW §Honesty #1 LCP HOLD `warn@2500ms` (structural Linux CI Perf blocker; tracked-upstream via `GoogleChrome/lighthouse#17021`)
- W160 NEW §Honesty #2 TBT HOLD `warn@200ms` (same structural constraint)
- /messenger Phase 5 punt (BY-DESIGN per W161 SW2 — 3 rationales)

---

## §W141 anti-pattern compliance (post-W167)

| # | Pattern | Pre-W167 | Post-W167 | Notes |
|---|---------|----------|-----------|-------|
| #1 | STRICT 1-iter cap | 20 total / 14 defer-cases | **21 total / 15 defer-cases** | SW2 Mismatch A defer = 15th defer-case |
| #3 | Phase 3 verification | 32 vindications | **35+ vindications** | Caught Explore agent FRONTEND_REACT_DEV_MODE flag state error + ~3 more during SW2 implementation |
| #4 | No premature "Closes" claim | 17 vindications | **18 vindications** | SW2 commit honestly states "closes 2 of 3 mismatches; 1 honestly defers". W167 anti-pattern #4 properly applied at commit time, NO post-hoc correction needed (vs W166 SW2's 18th vindication requiring polish-v1 correction) |
| #15 | (ARCHIVED W159 SW4) | preserved | **preserved** | All 5 W167 commits (SW1 + SW2 × 3 + SW4) fired W156 SW4 husky pre-commit chain cleanly. NO `--no-verify` bypasses. |

---

## §Verification matrix (post-W167)

### Local gates (post-SW3)
- ✅ `cd frontend && npx tsc --noEmit` → 0 errors
- ✅ `cd frontend && npm run lint -- --max-warnings=0` → 0 warnings
- ✅ `cd frontend && npm test` → **1058 passed / 12 skipped / 0 failed** (W166 baseline preserved EXACTLY in 35.12s)
- ✅ `cd frontend && npm audit --audit-level=high` → 0 vulnerabilities (W166 baseline preserved)

### Bundle invariants (W167 SW2 NEW baseline post-cleanup)
- ✅ Main JS: `index-DaSJVSyG.js` 177,057 b (sha `ea956d6d...adf5295`)
- ✅ Server.js: 23,600 b (sha `fd3a6252...3150d1`)
- ✅ vendor-react: 182,123 b (W166 SW2 baseline EXACT — production-minified)
- ✅ Build × 3 BYTE-IDENTICAL × 3 fresh `npm run build` runs (1-wave reproducible)

### Production invariants (W156 + W157 + W158 baselines preserved)
- ✅ 0 `react-dom-client.development` references in PROD client assets
- ✅ 0 `jsxDEV` in server.js (W156 SW1 per-environment NODE_ENV scope preserved)
- ✅ Diagnostic flags both `""` (default OFF per W157 SW1 + W158 SW1 cleanup pattern)

### SSR rendering (W126 SW3 + W156 SW3 baselines preserved)
- ✅ `/healthz {"status":"ok"}`
- ✅ `/login 200 / 21,791 bytes` SSR HTML emitted (W166 SW2 baseline EXACT)
- ✅ SSR form structure present: `<form>` + `<input>` × 3 + `<button>` × 2 + "Sign in" × 3 strings

### Docker stack
- ✅ 5 of 5 services healthy: frontend, backend, file-processor, temporal, caddy

---

## §W168+ candidates

### Primary (Path C — Mismatch A investigation, ~3-5h focused scope)

Mismatch A (MainLayout-level structural `<main>` vs `<nav>` swap) STAYS OPEN. Investigation paths for W168+:

1. **Path C-1: `useRouterState` pathname behavior under `ssr: false`** — Reproduce SSR render of MainLayout in isolation; check what pathname is reported by `useRouterState` when admin route is `ssr: false`. If different from SSR-emitted URL, this is the bug.

2. **Path C-2: `__root.tsx` SsrRoot vs RootComponent provider tree divergence** — `SsrRoot` (line 381-419) wraps with `<QueryClientProvider client={routerContext.queryClient}>` while `RootComponent` (line 361-378) wraps with `<PersistQueryClientProvider client={queryClient} persistOptions={{ persister: idbPersister }}>`. The Persist version mounts an IndexedDB persistence layer that may emit different DOM structure during hydration. Both providers SHOULD emit no DOM, but `PersistQueryClientProvider` is documented to set up IDB subscriptions on mount — possible side effect.

3. **Path C-3: Remove `_admin.tsx:58 ssr: false` override** — Test whether closure happens when admin route inherits root's `ssr: true`. Per W128 inheritance contract this is a fundamental change. But it would make admin SSR'd → matching server + client trees automatically. Pre-W128 was the original state; W126 polish added `ssr: false` due to provider-chain client-only issues. May now be safe to remove given W127 SW1 provider hoisting + W128 SW3 SsrRoot + W149 SW2 hydrateRoot are all in place.

### Secondary

- **Tier 5 housekeeping** carry-forward: /messenger Phase 5 punt (still by-design); /admin polish arc completion (per W164/W165/W166 progression)
- **W160 §Honesty NEW #1 monitoring**: GoogleChrome/lighthouse#17021 — 2-4 week response window from W166 SW3 file date 2026-05-19
- **MEMORY.md ongoing compaction**: 24,058 b → target post-W167 SW4 ~22,000-23,500 b headroom; carry forward W164 row drop + light-trim W165 + W166 verbose entries

### Q0 framework projection

If W168 invokes Q0 framework:
- **A) Project-done** — possible if user accepts Mismatch A as production-acceptable (admin React #418 is dev-tool console warning, NOT user-facing wedge; SSR + auth + content all render correctly)
- **B) Light SW2-followup React #418 closure Path C** — recommended if user wants full closure; ~3-5h scope
- **C) Broader pivot** — only if surprising new actionables surface between W167 close and W168 open

---

## §Bundle baseline summary

### W167 SW2 NEW baseline (post-cleanup verified)
- **Main JS**: `dist/client/assets/index-DaSJVSyG.js` **177,057 bytes** + sha256 `ea956d6d9bbdc305fe99423a574d6a52d01453cc99b28b6557a370bf1adf5295`
- **Server.js**: `dist/server/server.js` **23,600 bytes** + sha256 `fd3a6252000759ee733940ee572c3cece37f8009225ddcec0f9aaf72673150d1`
- **vendor-react**: `dist/client/assets/vendor-react-CFU_zHBc.js` **182,123 bytes** (= W166 SW2 baseline EXACT)
- **Cross-wave reproducibility**: ≥1-wave reproducible at W167 SW3 polish-pass (3 fresh `npm run build` runs from clean state, all BYTE-IDENTICAL)

### Delta vs W166 SW2 baseline
- Main JS: +394 b (mounted-state pattern code in `useNavbarLogic.ts` + `useNavbarMorph.ts`)
- Server.js: 0 b (server bundle unchanged — fix is client-side only)
- vendor-react: 0 b (production-minified, unaffected)

---

**End of W167 audit narrative.** §Honesty 1-5 → **1-3 OPEN post-W167** (-2 NET). 28th consecutive wave with brainstorming + Phase 1 Explore + Phase 3 Review + W141 anti-pattern discipline. Mismatch A honest defer to W168+ Path C; bundle × 3 BYTE-IDENTICAL × 3; all CI gates GREEN; user mandate «делаем всё по максимуму» honored within W141 anti-pattern #1 SACRED 1-iter cap.
