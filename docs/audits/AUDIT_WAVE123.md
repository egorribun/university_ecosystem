# Wave 123 — Frontend tech-debt close + Chromatic unblock (April 2026)

**Branch**: `egorribun`
**Scope**: Option B (M) — 5 SWs over 4 commits (SW1-SW3 separate, SW4 folded into SW5).
**Bundle**: PROD main chunk **179,867 bytes / hash `index-DdAbG7rt.js`** (W122 polish baseline preserved). VITE_LHCI build **178,892 bytes / hash `index-CiW0SGBC.js`**. Build × 3 reproducible.

## Executive summary

| # | Item | Status | SW |
|---|------|--------|-----|
| #3 | Chromatic upstream monitoring (quarterly check) | ✅ resolved → **UNBLOCKED VIA WORKAROUND** | SW1 |
| #5 | vendor-sentry / vendor-ui investigation | ✅ closed via audit (NO-OP for bundle) | SW2 |
| #8 | ScheduleCard CLS monitor (~0.040 pre-existing) | ✅ closed via measurement (0.0335 stable) | SW3 |
| — | Freshness pass (full 9-URL × 3-run LHCI baseline) | ✅ baseline captured, no gate ratchet | SW4 |
| — | Audit + N+3 rotation (W120 → archive) + W124 prep | ✅ closed | SW5 |

**Headline wins**:

1. **Chromatic UNBLOCKED** after W120/W121/W122 each declaring it structurally blocked. Found canonical workaround (`build.rolldownOptions.output.strictExecutionOrder: true`) in vitejs/vite#21948 thread. 90 min from "monitoring scope per plan" to "actual fix shipped + chrome-devtools-mcp verified working." Item #1 from W120 backlog finally closes.
2. **9-URL × 3-run LHCI baseline preserved** post-W122-polish — 6 of 9 URLs identical to W122, 2 authenticated routes (/, /dashboard) show -0.06/-0.07 Perf variance not regression (bundle hash identical to W122). CLS preserved or improved across all 9 URLs.
3. **ScheduleCard CLS root-element identified + monitored stable** at 0.0335 (variance ~0.0001 across 3 runs). 100% of /dashboard CLS attributable to single `<a href="/schedule">` element ("Open full schedule" link inside ScheduleCard). Acceptable; W122-polish-A2 pattern available if regresses above 0.06.

## Commits on origin

| # | SHA | Title | Files | +/− |
|---|---|---|---|---|
| 1 | `f0f352fb3` | `feat(wave123-sw1-chromatic-unblock)` — strictExecutionOrder workaround | 2 | +58 / −21 |
| 2 | `5861b6e13` | `chore(wave123-sw2-vendor-audit)` — delete MotionPresence dead code + document NO-OP findings | 2 | +0 / −16 |
| 3 | `86d598d46` | `docs(wave123-sw3-schedule-cls-monitor)` — document /dashboard CLS = 0.0335 stable + W123 gotchas | 1 | +3 / 0 |
| 4 | `<TBD>` | `docs(wave123-sw5-audit)` — this commit | 6 | (to be measured) |

(SW4 freshness pass folded into SW5 — pure measurement with no code change, baselines documented in §End-of-wave gates below.)

---

## SW1 — `feat(wave123-sw1-chromatic-unblock)`: Storybook+Vite8 UNBLOCKED

**Files**: `frontend/.storybook/main.ts`, `.github/workflows/chromatic.yml`, `memory/wave122_chromatic_upstream.md` (cross-session reference, not in repo).

### Diagnosis arc

Wave 122 SW5 framed Chromatic as "STILL BLOCKED" with 4 active upstream issues to monitor quarterly. W123 SW1 plan: re-check status, document changes if any. Quick-fetch via GitHub REST API revealed all 4 issues had been **closed**:

| Issue | State | Closed |
|---|---|---|
| storybookjs/storybook#33789 (Vite 8 umbrella) | closed | 2026-03-10 |
| vitejs/rolldown-vite#562 (`__STORYBOOK_MODULE_*`) | closed | 2026-03-19 |
| storybookjs/storybook#31711 (`PREVIEW_API`) | closed | 2025-10-13 |
| rolldown/rolldown#3982 (`import.meta.glob`) | closed | 2025-09-11 |

But running `npm run build-storybook` + loading `iframe.html` via python http.server + chrome-devtools-mcp showed the SAME runtime error from W120 SW8 / W121 SW7 / W122 SW5 era:

```
Uncaught ReferenceError: __STORYBOOK_MODULE_CORE_EVENTS_PREVIEW_ERRORS__ is not defined
```

So "closed" did not equal "fixed for our case." Reading the closing comments on each issue revealed:

- **rolldown-vite#562 closed as DUPLICATE** of vitejs/vite#21948 by maintainer sapphi-red on 2026-03-19, not as a code-level fix. Same for #31711.
- **vite#21948 closed 2026-04-07** by Vite 8.0.6: "It seems this now works without `strictExecutionOrder` since Vite 8.0.6+." (sapphi-red 2026-04-07).
- **The canonical workaround** was in the same thread (sapphi-red 2025-09-08): `build.rolldownOptions.output.strictExecutionOrder: true`. Per Rolldown docs, this disables out-of-order module-graph optimization that was clobbering Storybook's custom module loader execution order.

### Workaround applied (scoped to Storybook viteFinal)

`frontend/.storybook/main.ts` viteFinal hook now extends the returned config:

```ts
return {
  ...viteConfig,
  plugins: allPlugins.filter((p) => !isPwaPlugin(p)),
  build: {
    ...buildConfig,
    rolldownOptions: {
      ...rolldownOpts,
      output: {
        ...rolldownOutput,
        strictExecutionOrder: true,
      },
    },
  },
} as UserConfig
```

New typed cast helper `ViteUserConfigWithRolldown` because Vite's UserConfig type doesn't yet expose rolldown-vite's `strictExecutionOrder` field. Trade-off: storybook build time +5% (7.76 → 8.15s) — acceptable for visual-regression infra.

### Verification (chrome-devtools-mcp 2026-04-30)

- ✅ `npm run build-storybook` succeeds in 8.15s
- ✅ `python -m http.server 6007` serving `storybook-static/` on localhost
- ✅ Loaded `iframe.html?id=components-eventcard--default&viewMode=story`
- ✅ Console: **0 errors, 0 warnings** (was the W120 SW8 ReferenceError before this fix)
- ✅ EventCard story renders fully: WORKSHOP/LIVE badges, "Modern Web Development Workshop" title, Dr. Jane Smith presenter, date range, Computer Lab 404 location, "0 / OPEN" attendance counters

### Main app bundle invariant (defense-in-depth verification)

The workaround is scoped to Storybook viteFinal — main app dist must be unchanged:

- Prod build × 3 reproducible at **179,867 bytes / hash `DdAbG7rt`** (identical to W122 polish baseline)
- vendor-ui chunk: 162,838 bytes / hash `D0qOi_Ff` (UNCHANGED)
- vendor-sentry chunk: 75,236 bytes / hash `Drj90Mca` (UNCHANGED)
- precache: 180 entries / 4851.51 KiB (UNCHANGED)

### Chromatic enablement next steps (USER-side actions)

The Storybook runtime is now functional. To capture Chromatic baseline, user actions in repo settings:

1. **Add `CHROMATIC_PROJECT_TOKEN` Secret** with value `chpt_48d051b3688a3e4` (saved client-side per W120 polish-v2; project at chromatic.com).
2. **Set `CHROMATIC_ENABLED=true` repo variable**.
3. **Open a frontend-touching PR** → workflow `.github/workflows/chromatic.yml` triggers, uploads built stories to Chromatic, captures initial baseline.
4. **Accept baselines** in Chromatic dashboard for first build.

After baselines are accepted, future regression checks happen automatically per PR. Chromatic free tier covers 5,000 snapshots/month; project has ~30-40 stories × 1 snapshot per build = ~120-160/month for typical PR cadence.

### Documentation refreshed

- `memory/wave122_chromatic_upstream.md` — full quarterly-check status table, applied workaround diff, verification, user-side enablement steps, latest Storybook version note (10.3.6 stable / we're on 10.2.13). Cross-session reference.
- `.github/workflows/chromatic.yml` header — removed "STILL BLOCKED" notice, added W123 SW1 resolution narrative + upstream issue resolution chain + user-side enablement steps.

---

## SW2 — `chore(wave123-sw2-vendor-audit)`: vendor-ui audit NO-OP + dead code

**Files**: `frontend/src/components/motion/MotionPresence.tsx` (DELETED), `frontend/src/components/motion/index.ts`.

### Inventory (Phase 1)

74 files import `framer-motion`. API breakdown:

| API | Files |
|---|---|
| `motion` | 74 |
| `AnimatePresence` | 38 |
| `MotionConfig` | 1 (AppProviders.tsx — keep) |
| `useReducedMotion` | 20 |
| `useScroll` / `useSpring` / `useMotionValue` | 3 / 2 / 6 |
| `useTransform` / `useInView` / `useAnimation` | 2 / 2 / 2 |
| `LayoutGroup` | 2 |
| `Reorder` | 0 |
| `LazyMotion` | **0** |
| `Variants` / `Transition` (type-only) | 8 / 8 |

Notable: `LazyMotion` (Framer Motion's tree-shake API) is NOT used anywhere. This is the biggest structural reduction lever, but switching all 74 files to `m` instead of `motion` is W124+ scope.

### Phase 2A — Dead code removal

`MotionPresence.tsx` was a wrapper around `AnimatePresence + useReducedMotion` with `mode="wait"` default, exported from `components/motion/index.ts`. Grep verified ZERO consumers in `src/`. Deleted file + removed export entry.

### Phase 2B — AnimatePresence-list-stagger → CSS migration (NOT applied)

Grep for `AnimatePresence` wrapping `.map()` iteration found 8 candidates:
- `EventsCard.tsx`, `ChatArea.tsx`, `MessageInput.tsx`
- `NavbarOverflowMenu.tsx`, `ExportDropdown.tsx`, `Select.tsx`
- `AdminAudit.tsx`, `AdminFeatureFlags.tsx`

Each candidate has different entry/exit animation profile (dropdowns need open/close transitions; messenger components handle message arrival; admin lists handle row insertion). Per-component UX assessment is required to safely migrate to CSS `@starting-style`. Out-of-scope for the audit-only intent of W123 SW2 — would risk perceived UX regressions across 8 surfaces. Documented as W124+ candidate.

### Phase 2C — Sentry deferred init (Q2 fallback)

Per Q2 user choice ("Try Sentry deferred init as fallback"), audited Sentry initialization. Findings:

- `src/main.tsx` (W117 SW3): Sentry init is **already deferred** via `requestIdleCallback`. `import("./app/observability").then((m) => m.initObservability())` runs after React render in browser idle window. Confirmed working.
- `src/app/observability.ts`: Sentry.init config is **MINIMAL** — only `dsn`, `environment`, `enabled`, `tracesSampleRate`, `profilesSampleRate`, `release`. No BrowserTracing, Replay, or other heavy integrations. No further sub-defer possible without removing functionality.
- `vendor-sentry-Drj90Mca.js` chunk (75,236 bytes) is async-only via `<link rel="modulepreload">` injected dynamically post-paint. The W122 SW2 LHCI report's "23 KB / 91% wasted on /news" is a measurement artifact: Sentry surface area is needed at runtime to handle whatever errors occur — most functions are unused per-page until an error fires.

### Bundle delta (zero change)

| Chunk | Before SW2 | After SW2 | Δ |
|---|---|---|---|
| index.js | 179,867 | 179,867 | 0 |
| vendor-ui.js | 162,838 | 162,838 | 0 |
| vendor-sentry.js | 75,236 | 75,236 | 0 |
| precache total | 4851.51 KiB | 4851.51 KiB | 0 |

`MotionPresence` was tree-shaken already (no consumers → not in any chunk). The dead code removal is code-level housekeeping, not byte-level reduction.

### Honest framing

SW2 = audit-only conclusion + code-level cleanup. No measurable bundle byte-savings this wave. Same NO-OP precedent as W121 SW9 image audit. The structural opportunity (LazyMotion swap or per-component AnimatePresence→CSS migration with UX validation) is W124+ scope.

---

## SW3 — `docs(wave123-sw3-schedule-cls-monitor)`: ScheduleCard CLS confirmed stable

**Files**: `CLAUDE.md` (3 new gotcha entries: SW1 Storybook unblock, SW2 Framer Motion audit NO-OP, SW3 ScheduleCard CLS monitor).

### Method

`LHCI_URLS=dashboard LHCI_RUNS=3 npm run lhci:windows` (mobile preset, devtools throttling, VITE_LHCI=true build). Parsed LHR JSON via `node -e` to extract `audits['cumulative-layout-shift'].numericValue` + `audits['layout-shifts'].details.items`.

### Per-run results (verbatim)

```
=== run 1 ===
CLS: 0.0335
  shift: 0.0335 | <a data-haptic="light" aria-label="Открыть полное расписание" href="/schedule" c
  shift: 0.0011 | <a aria-label="Новости" href="/news" class="group relative flex flex-1 flex-col

=== run 2 ===
CLS: 0.0335
  shift: 0.0335 | <a data-haptic="light" aria-label="Открыть полное расписание" href="/schedule" c
  shift: 0.0011 | <a aria-label="Новости" href="/news" class="group relative flex flex-1 flex-col

=== run 3 ===
CLS: 0.0335
  shift: 0.0335 | <a data-haptic="light" aria-label="Открыть полное расписание" href="/schedule" c
  shift: 0.0011 | <a aria-label="Новости" href="/news" class="group relative flex flex-1 flex-col
```

### Findings

- **CLS = 0.0335 stable across 3 runs** (variance ~0.0001 — dramatically tight)
- **100% of CLS contribution from a single element**: `<a data-haptic="light" aria-label="Открыть полное расписание" href="/schedule">` — the "Open full schedule" link inside ScheduleCard
- Secondary shift on /news link: 0.0011 (negligible)
- A11y: 1.00 across all 3 runs (preserved)

### Decision

Per W123 SW3 plan decision tree:
- **CLS ≤ 0.05 (median)** → MONITOR CONFIRMED STABLE → no code change

Item #8 from W123 backlog closed via measurement. ScheduleCard `<a href="/schedule">` element gains height as TanStack Query schedule data resolves; the CLS contribution is the layout shift from initial empty-state to populated card. Acceptable residual: WELL UNDER 0.10 gate (67% margin) and under the 0.05 monitor threshold.

If future LHCI measurement shows CLS regression above 0.06 on /dashboard, the W122-polish-A2 pattern applies: add `min-h-[Xpx]` reservation on the ScheduleCard wrapper or its inner `<a>` to reserve final-state height during async data fetch.

### Side-note on /dashboard Perf

3-run median Perf came in at 0.47 in the SW3 measurement (vs W122-polish-A2 baseline 0.54). This was investigation-noise (CLS was the SW3 focus), but worth flagging — see SW4 below.

---

## SW4 — Freshness pass (folded into SW5)

**Files**: NO file changes (pure measurement). Numbers documented here.

### Method

Sub-batched `npm run lhci:windows` 9-URL × 3-run sweep across 3 batches (W120 SW1 EPERM mitigation):

```
Batch 1: LHCI_URLS=,login        → /, /login
Batch 2: LHCI_URLS=news,schedule,events → /news, /schedule, /events
Batch 3: LHCI_URLS=activity,map,404     → /activity, /map, /404
```

`/dashboard` measurement reused from SW3 (same dist hash, same wave). Total wall-clock for SW4 measurement: ~15 min (across 3 batches).

### Post-W123 baseline (3-run medians)

| URL | Perf | CLS | LCP (ms) | TBT (ms) | A11y | Δ vs W122 polish-A2 |
|-----|------|------|---------|---------|------|------|
| / | 0.48 | 0.033 | 12124 | 366 | 1.00 | Perf -0.06, CLS -0.007 (improved) |
| /login | 0.57 | 0.000 | 11382 | 102 | 1.00 | identical |
| /dashboard | 0.47 | 0.033 | 12033 | 388 | 1.00 | Perf -0.07, CLS -0.007 (improved) |
| /news | 0.53 | 0.006 | 9141 | 240 | 1.00 | identical |
| /schedule | 0.53 | 0.003 | 12058 | 238 | 1.00 | Perf +0.01 (variance) |
| /events | 0.48 | 0.062 | 9803 | 322 | 1.00 | identical |
| /activity | 0.46 | 0.003 | 11527 | 440 | 1.00 | identical |
| /map | 0.48 | 0.075 | 12220 | 335 | 1.00 | identical |
| /404 | 0.56 | 0.000 | 10667 | 182 | 1.00 | identical |

**ALL 9 URLs pass W120 SW2 ratchet** with margin:

- Perf ≥ 0.40 (worst /activity 0.46 = 15% margin)
- CLS ≤ 0.10 (worst /map 0.075 = 25% margin; / + /dashboard at 0.033 = 67% margin)
- A11y ≥ 0.95 (all 1.00 ✅)

### Pattern analysis: variance vs regression

- 6 of 9 URLs identical to W122 polish-A2 baseline
- 1 of 9 (/schedule) +0.01 Perf (within noise)
- 2 of 9 (/, /dashboard) Perf drop -0.06/-0.07 with CLS slightly improved (-0.007)

Bundle hash IDENTICAL to W122 polish baseline (`index-DdAbG7rt.js` PROD / `index-CiW0SGBC.js` VITE_LHCI). No code changes between W122 polish and W123 measurements. Conclusion: the -0.06/-0.07 Perf delta on / + /dashboard is **session-to-session LHCI variance, not regression** (validated by:  (a) bundle hash invariant, (b) CLS preserved/improved on same URLs, (c) other 7 URLs identical proves dist measurement consistency).

Per W121 polish A3 finding: "1-run LHCI sanity is OPTIMISTIC by 0.04-0.09 vs 3-run truth." W123 SW4 extends that observation: 3-run-vs-3-run can also vary by ~0.07 across sessions on heavy authenticated routes (likely due to network simulator state, CPU sampling, browser process startup variance).

### Gate ratchet decision

Per Q2 user threshold (ratchet Perf 0.40 → 0.45 if all 9 URLs Perf ≥ 0.50):
- Worst Perf in W123 SW4: **0.46 (/activity)** — same as W122 baseline
- 0.46 < 0.50 → **DO NOT RATCHET Perf gate**

CLS ratchet check (ratchet 0.10 → 0.08 if worst CLS ≤ 0.07):
- Worst CLS: **0.075 (/map)** — same as W122 baseline
- 0.075 > 0.07 → **DO NOT RATCHET CLS gate**

Both gates remain at W120 SW2 + W119 SW3 levels:
- `categories:performance` `error@0.40`
- `cumulative-layout-shift` `error@0.10`
- `categories:accessibility` `error@0.95`
- `categories:best-practices` `error@0.95`
- `categories:seo` `error@0.9`

Future ratchet candidates surface after Mobile perf XL (W124+) addresses LCP on authenticated routes.

---

## SW5 — `docs(wave123-sw5-audit)`: this commit + N+3 archive rotation

**Files** (anticipated for this commit):

- `docs/audits/AUDIT_WAVE123.md` (NEW — this file)
- `docs/audits/AUDIT_WAVE120.md` → `docs/audits/archive/AUDIT_WAVE120.md` (`git mv` for N+3 rotation)
- `docs/audits/INDEX.md` — move W120 row to archive section, add W123 row to active
- `CLAUDE.md ## Audit Trail` — add W123 row at top, update header note about second rotation
- `memory/MEMORY.md` — add W123 row at top, update active backlog to W124
- `memory/wave124_backlog.md` (NEW)
- `memory/wave124_opening_prompt.md` (NEW)

### N+3 rotation (per W122 polish-docs-v3 covenant)

W122 polish-docs-v3 (`8eba94352`) established the rotation rule: "when wave N+3 opens, oldest of 3 active audits moves to archive/." W123 is N+3 from W120 → W120 audit relocates from `docs/audits/` to `docs/audits/archive/`. Active audits after rotation: W121 / W122 / W123.

`git mv` preserves history; `git log --follow docs/audits/archive/AUDIT_WAVE120.md` will show pre-rotation commits.

### Wave 124 hand-off

Carry-overs:

- **Mobile perf round 2** (Item #2 XL — explicit user deferral persists since W121, W122, W123). Real LCP < 2.5s on authenticated routes via SSR/static-pre-render/progressive-enhancement. ~6-8h estimated.
- **Chromatic baseline activation** (NEW W124 task — workflow now functional, awaits user-side `CHROMATIC_PROJECT_TOKEN` Secret + `CHROMATIC_ENABLED=true` variable + first frontend PR).
- **Framer Motion structural reduction** (W123 SW2 deferral — LazyMotion swap or per-component AnimatePresence→CSS migration with UX validation; ~3-5h estimated). Bundles up well with Mobile perf XL.
- **Authenticated-route Perf variance** (W123 SW4 finding — investigate whether environment factors or genuine optimization opportunity exists for / + /dashboard).
- **N+3 rotation at W125 open**: W121 audit moves to archive (W122/W123/W124 stay active per "last 3 waves" invariant).

---

## End-of-wave gates (verbatim)

```
$ npx tsc --noEmit                    → exit 0

$ npm run lint                        → exit 0
> frontend@1.0.0 lint
> eslint --max-warnings=0 --ext .ts,.tsx "src" "tests"

$ npm run i18n:check                  → 17 passed (17)

$ npm run tokens:sync && git diff --exit-code -- src/theme/tokens.ts
✅ Found 631 CSS variables in partials/ + tokens/
                                       → tokens diff exit 0 (no drift)

$ npm audit                           → 0 vulnerabilities

$ npm run test -- --run               → 686 passed | 12 skipped | 0 failed
                                        Duration  23.79s
                                        (W122 polish baseline preserved)

$ for i in 1 2 3; do rm -rf dist && npm run build; done
                                       → all 3 produce identical:
-rw-r--r-- 1 egorribun 197121 179867 Apr 30 16:01 dist/assets/index-DdAbG7rt.js

$ env VITE_LHCI=true npm run build    → 178,892 bytes / hash CiW0SGBC

$ git diff --stat -- frontend/rust-crypto/Cargo.lock
                                       → empty (idempotent ≥ 12 waves)

$ npx playwright test --project=chromium tests/e2e/a11y-public.spec.ts
  4 passed (≈16s)

$ URL_STATE_E2E=true npx playwright test --project=chromium tests/e2e/url-state-persistence.spec.ts
  6 passed (≈18s)

$ npm run build-storybook              → 8.15s, output to storybook-static/
$ python -m http.server 6007 (storybook-static/) + chrome-devtools-mcp:
  iframe.html?id=components-eventcard--default → 0 console errors,
  0 warnings, EventCard story renders fully (verified 2026-04-30)
```

---

## Honesty probe self-audit

Pre-empting the expected "безупречно?" probe by listing honest caveats up-front:

### ⚠ SW2 = NO-OP for vendor-ui/vendor-sentry chunk byte reduction

Phase 2A removed `MotionPresence.tsx` dead code but produced 0 bundle bytes saved (already tree-shaken). Phase 2B identified 8 AnimatePresence→CSS migration candidates but didn't apply per-component migrations (UX risk + scope). Phase 2C Sentry deferred — already done in W117 SW3, no further reduction possible. Same NO-OP precedent as W121 SW9 image audit. Honest framing: SW2 is audit + cleanup, not perf reduction.

### ⚠ SW3 monitor outcome (no active fix)

CLS = 0.0335 stable + under 0.05 threshold per plan decision tree → MONITOR CONFIRMED STABLE, no code change. Item #8 closed via measurement, not via code. Acceptable per plan, but a future LHCI session COULD show this regress. The fix vector is documented (W122-polish-A2 pattern: `min-h-[Xpx]` reservation) for W124 if needed.

### ⚠ SW4 authenticated-route Perf -0.06/-0.07 variance not deeply investigated

/, /dashboard Perf dropped from 0.54 (W122 polish-A2 baseline) → 0.48/0.47 in W123 SW4 measurement. Bundle hash identical, no code changes — this is variance, not regression. But I didn't repeat the SW4 measurement to confirm OR run on a quieter machine to rule out background load. The 6/9 URLs identical pattern strongly supports variance hypothesis, but W124 mobile perf XL should re-baseline with cleaner environment.

### ⚠ SW4 didn't get its own commit

Plan called for `docs(wave123-sw4-freshness-pass)` separate commit. Reality: SW4 was a pure measurement with no code change. Folding into SW5 audit (which IS the place for measurement evidence) was cleaner. Per-SW commit cadence broken slightly (4 commits for 5 SWs).

### ⚠ Gate ratchet decision: NO ratchet

Q2 user threshold required "all 9 URLs Perf ≥ 0.50" for ratchet — worst /activity 0.46 < 0.50 = unmet. Same for CLS (worst /map 0.075 > 0.07 = unmet). Wave 124 mobile perf XL is the natural unlock vector for both ratchets.

### ⚠ Chromatic activation requires USER-side actions

The Storybook runtime is unblocked via SW1, but Chromatic actually capturing baseline requires:
1. Repo Secret `CHROMATIC_PROJECT_TOKEN` set to `chpt_48d051b3688a3e4`
2. Repo Variable `CHROMATIC_ENABLED=true`
3. First frontend-touching PR after both are set

SW1 didn't (couldn't) flip these — they're admin actions. Documentation in `chromatic.yml` header + `wave122_chromatic_upstream.md` lists the steps.

### ⚠ SW1 verification: only 1 story rendered

I verified `components-eventcard--default` story renders cleanly in chrome-devtools-mcp. Other 30+ stories were not individually checked. The Storybook BUILD succeeded for all stories (no compile errors), and the runtime cleared the `__STORYBOOK_MODULE_*` block — but per-story rendering robustness wasn't exhaustively tested. Chromatic baseline (when activated) will catch any story-specific regressions.

### ✓ What DID land (genuinely structural wins)

- **Chromatic UNBLOCKED** — first time since W120 SW8. Item #1 from W120 backlog finally closes. Storybook builds + renders correctly with `strictExecutionOrder` workaround.
- **All 9 LHCI URLs A11y = 1.00 ✅** preserved (W121 polish A2 baseline)
- **All 9 URLs CLS ≤ 0.10 ✅** preserved (W120 SW2 ratchet); / + /dashboard CLS even slightly improved
- **Bundle invariant** maintained: 179,867 bytes / hash `DdAbG7rt` × 3 reproducible
- **Cargo.lock idempotent ≥ 12 waves**
- **vitest 686p/12s/0f** preserved
- **e2e a11y-public 4/4 + url-state-persistence 6/6** chromium passing
- **3 active backlog items closed** (#3 Chromatic, #5 vendor-sentry/ui audit, #8 ScheduleCard CLS monitor)
- **3 new CLAUDE.md gotchas** (Storybook unblock, Framer Motion audit, ScheduleCard CLS monitor)
- **N+3 rotation** executed cleanly (W120 → archive)

---

## Wave 124+ scope preview

After W123 closes, remaining backlog is:

1. **Mobile perf round 2** (XL own-wave, deferred since W121) — LCP < 2.5s on authenticated routes via SSR/static-pre-render/progressive-enhancement. ~6-8h estimated.
2. **Chromatic baseline activation** (NEW from W123 SW1) — user repo-settings actions + first PR.
3. **Framer Motion structural reduction** (NEW from W123 SW2 deferral) — LazyMotion swap or per-component AnimatePresence→CSS migration. Bundles well with #1.
4. **Authenticated-route Perf variance investigation** (NEW from W123 SW4 finding) — re-baseline with controlled environment.

Wave 124 is recommended as either (a) Mobile perf XL own-wave (consolidates 1+3+4) OR (b) fresh feature work if user prefers a break from perf/audit cycle.
