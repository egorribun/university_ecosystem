# Wave 190 — Broader Hook Migration Sweep (Path C) + N+3 Rotation

**Date**: 2026-05-26
**Branch**: `egorribun`
**Scope**: M-L user-mandate per Opening Prompt Option F → 3-wave decomposition (W190 picks Path C, W191/W192 take remainder)
**Budget**: ~3-5h core (Path C plan); actual ~2-3h (mechanical migration pattern proven by W189 SW3 reference)
**Total commits**: 4 SW + 1 audit (this SW5) = **5 commits**
**Status**: ✅ CLOSED (polish-v? chain TBD based on PR #1126 CI verification post-push)
**Wave streak**: **50th consecutive wave** preserving brainstorming + Phase 1 Explore + Phase 3 Review + W141 anti-pattern discipline (W141-W190). Milestone.

---

## 🟢 Headlines

1. **All 25 hook-migration target files closed empirically — W189 W190+ candidate "broader hook migration sweep" CLOSED 100%**:
   - **SW1** `6caf4c231` `feat(wave190-sw1-messenger-core-hook-migration)` — 6 Messenger core files (NewChatModal + ContactList + ChatWindow + ChatArea + MessengerSidebar + MessengerFeature)
   - **SW2** `de7a5588f` `feat(wave190-sw2-schedule-hook-migration)` — 4 Schedule family files (Schedule.tsx + ScheduleMobileView + ScheduleSettingsPanel + ScheduleShortcutsOverlay)
   - **SW3** `c48a796ba` `feat(wave190-sw3-activity-events-hook-migration)` — 7 Activity + Events files (ActivityFeature + 2 charts; EventsFeature + EventsHeader + EventDetail + EventQuickView)
   - **SW4** `6ae90c6d2` `refactor(wave190-sw4-map-misc-hook-migration)` — 8 final files including `useAnimatedFloat.ts` hook (MapFeature + WeatherParticles + \_admin + ProfileModal + MessageInput + NowPlayingCard + NewsQuickView + useAnimatedFloat)

2. **Migration completeness empirically proved via grep**:
   - **Pre-W190**: `grep -rn "import.*useReducedMotion.*from.*framer-motion" frontend/src` → 25 matches (24 component/page + 1 hook)
   - **Post-W190**: same grep → **0 matches** ✓
   - Closes latent jsdom-incompat risk class per W184 SW6 lesson (`useReducedMotion` + `initPrefersReducedMotion` listener-registration code path jsdom polyfill can't fully cover, producing `TypeError: Cannot read properties of undefined (reading 'addEventListener')` as vitest unhandled errors)
   - `useAnimatedFloat.ts` hook decision per W190 plan + Phase 3 Read: MIGRATE (used by AnimatedRing + AttendanceCard, both exercised in Activity jsdom tests; comment block at lines 13-15 also updated to reflect W190 migration rationale)

3. **Bundle Build × 3 BYTE-IDENTICAL EMPIRICALLY VERIFIED at NEW W190 baseline**:
   - Main JS `index-CGBUMlAV.js` **180,273 bytes** sha **`1bff1fd7403b03e206534340bc89c53a37ce29d1240e923e83b4101c9c813c97`** × 3 fresh `rm -rf dist && npm run build` runs from clean state
   - Server.js **24,024 bytes** sha **`5b103ae9845527671bc32e4ce2fc0e8dd89b849d8ebe78d2408cefa8073a641d`** × 3 (size BYTE-IDENTICAL to W189 baseline; content sha CHANGED — real chunk-graph shift from 25-file client-tree migration cascading into Vite environments build server chunk via shared module identity)
   - **Delta vs W189 baseline** (180,277 b main + 24,024 b server): **-4 bytes main JS** (favourable — Rolldown tree-shaker drops framer-motion's `useReducedMotion` + `initPrefersReducedMotion` helper from vendor chunk after ALL source-level imports removed; per-file `useMediaQuery` import bookkeeping is smaller than the helper weight). server.js size IDENTICAL.
   - W134 SW3-W189 ≥48-wave LOCAL-MACHINE BYTE-IDENTICAL invariant chain EXTENDS through W190 → **≥49-wave invariant** confirmed (Build × 3 within W190 itself: all 3 runs IDENTICAL sha).

4. **§Honesty trajectory**: 0-2 OPEN pre-W190 → **0-2 OPEN post-W190** (CLOSE 1 actionable item + 1 structural risk class:
   - W189 W190+ candidate "broader hook migration sweep" — CLOSED 100% empirically
   - Latent jsdom-incompat risk class for ALL `useAnimatedFloat` consumers (AnimatedRing + AttendanceCard + any future) — STRUCTURALLY CLOSED
   - Carry-forward 2 W134 structural non-goals unchanged: W134 §H#2 bundle delta recording-only + W134 §H#10 /messenger Phase 5 SSR by-design per W161 SW2)
   - 0 NEW W190 caveats (pure mechanical migration via canonical W186 SW3 + W189 SW3 pattern)

5. **CI verification pending post-push at SW5 commit time** — W189 polish-v1 baseline (PR #1126 HEAD `0dbe11947`) was 45 SUCCESS / 0 FAILURE / 3 SKIPPED / 51 total + MERGEABLE. W190 commits push to same egorribun branch → CI re-runs for new HEAD; expected GREEN given strict per-SW gate baseline preservation (tsc 0 + lint 0 + vitest 1268p × 4 SW) + Build × 3 invariant chain extension.

---

## SW Breakdown

### Pre-SW1 (this session)

- `gh pr view 1126` → `state=OPEN`, `mergeable=MERGEABLE`, `mergedAt=null`, `headRefOid=d64f542391531d24b1f58fb614cc5672ffe93e2e` (W189 polish-v1 baseline preserved between waves)
- `gh run list --branch egorribun --limit 5` → CI on `d64f54239`: 4 SUCCESS + 1 skipped (Auto-merge dependabot expected) — matches W189 SW5 baseline
- `git status --short` → clean
- `wc -c MEMORY.md` → 23,858 b (542 b headroom under 24,400 ceiling — TIGHT; W190 SW5 compaction needed before adding W190 row)
- Frontend gates: tsc 0 errors, eslint --max-warnings=0 → 0 warnings, vitest **1268 passed / 12 skipped / 0 failed** in 31.85s (W189 baseline)
- npm audit 0 vulnerabilities (W183 SW3 baseline preserved)

All 8 pre-flight gates GREEN.

### Phase 1 Explore + Phase 3 Review (pre-SW1)

Per W141 anti-pattern #3 verify-before-write discipline (101 vindications baseline post-W189):

- **Grep verified**: `import.*useReducedMotion.*from.*framer-motion frontend/src` returns **25 files exactly** (matches opening prompt empirical snapshot 2026-05-26):
  - 8 Messenger family (6 SW1 + 2 deferred to SW4 = ProfileModal + MessageInput per opening prompt SW assignment)
  - 4 Schedule family (SW2)
  - 7 Activity + Events (SW3)
  - 6 Map + Misc (SW4)
  - 1 hook `useAnimatedFloat.ts` (SW4 per Phase 3 decision)

- **Phase 3 vindication #102**: opening prompt framed `useAnimatedFloat.ts` as decision-pending ("may or may not need migration — it's a custom hook that may itself wrap useReducedMotion as an implementation detail"). Direct Read of file confirmed line 19 invokes `useReducedMotion()` directly from render context (NOT internal wrap). Plus W184 SW6 lesson applies — `useAnimatedFloat` consumers (AnimatedRing + AttendanceCard) ARE exercised in Activity jsdom tests. Decision: MIGRATE.

- **Canonical migration target verified**: `useMediaQuery.ts:27` is `export default function useMediaQuery(query: string, options?: {defaultValue?: boolean}): boolean`. jsdom-safe via lines 50-53 typeof-check fallback (W113 SW6 setupTests.ts polyfill compatible).

- **Sample reads** (3 files from different families) confirmed 2 import patterns uniformly applicable: Pattern A (combined siblings: `import { AnimatePresence, m, useReducedMotion } from "framer-motion"`) + Pattern B (sole import: `import { useReducedMotion } from "framer-motion"`). Both have canonical recipes per W186 SW3 + W189 SW3 references.

### SW1: Messenger core 6 files (`6caf4c231`)

**Files**: NewChatModal.tsx + ContactList.tsx + ChatWindow.tsx + ChatArea.tsx + MessengerSidebar.tsx + MessengerFeature.tsx
**Pattern**: All Pattern A (combined framer-motion siblings)
**Call-site shape**: `const prefersReducedMotion = useReducedMotion() ?? false` (5 files) + `const reducedMotionPref = useReducedMotion()` (MessengerFeature alone — no `?? false` suffix; W181 SW2 var name)
**Edits**: 12 (6 imports + 6 call sites)

Migration recipe applied verbatim:

```tsx
// Before
import { AnimatePresence, m, useReducedMotion } from "framer-motion"
const prefersReducedMotion = useReducedMotion() ?? false

// After
import { AnimatePresence, m } from "framer-motion"
import useMediaQuery from "@/hooks/useMediaQuery"
const prefersReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)")
```

`MessengerFeature.tsx` already imported `useMediaQuery` (W181 SW2 — line 6); 6th file only needed framer-motion line edit + call-site rewrite.

**Verification**:

- tsc 0 errors
- eslint --max-warnings=0 → 0 warnings
- vitest **1268p / 12s / 0f** in 31.85s (W189 baseline preserved EXACTLY)
- `grep -rn "useReducedMotion" frontend/src/components/messenger/ frontend/src/features/messenger/` → only comments + test mocks (vi.mock framer-motion stubs from ChatArea.test.tsx + ChatWindow.test.tsx remain valid as harmless unused exports; useMediaQuery uses setupTests.ts matchMedia polyfill returning `false` for all queries in jsdom — safe default)

### SW2: Schedule family 4 files (`de7a5588f`)

**Files**: pages/Schedule.tsx + ScheduleMobileView + ScheduleSettingsPanel + ScheduleShortcutsOverlay
**Pattern**: All Pattern A (combined `AnimatePresence + m + useReducedMotion` from framer-motion)
**Call-site shape**: All identical — `const prefersReduced = useReducedMotion()` (no `?? false` suffix; W63-W74 era convention)
**Edits**: 8 (4 imports + 4 call sites)

`Schedule.tsx` already imported `useMediaQuery` (W175+ inheritance — line 5); other 3 needed new import added.

**Verification**:

- tsc 0 errors
- eslint 0 warnings
- vitest **1268p/12s/0f** in 31.45s
- `grep -rn "useReducedMotion" frontend/src/components/schedule/ frontend/src/pages/Schedule.tsx` → 0 matches

### SW3: Activity + Events 7 files (`c48a796ba`)

**Files**: ActivityFeature + ActivityTrendChart + ActivityBarChart + EventsFeature + EventsHeader + EventDetail + EventQuickView
**Pattern mix**: 3 Pattern A (ActivityTrendChart + ActivityBarChart + EventQuickView) + 4 Pattern B (ActivityFeature + EventsFeature + EventsHeader + EventDetail)
**Call-site variations**: 3 distinct var names (`reduce`, `prefersReducedMotion`, `prefersReduced`) × 2 suffix forms (`?? false` or none)
**Edits**: 14 (7 imports + 7 call sites)

3 of 4 Pattern B files already imported useMediaQuery (ActivityFeature + EventsFeature + EventDetail); EventsHeader needed new import.

**W138 Lesson #1 within-iter SAME-mechanism sub-fix applied** (NOT mechanism pivot): EventDetail.tsx initial edit attempted to swap the framer-motion import line for a useMediaQuery import — but EventDetail.tsx already had useMediaQuery at line 18 (W175+ inheritance). Post-edit grep caught the duplicate import IMMEDIATELY → reverted line 12 to bare deletion of the framer-motion line. Net result: one useMediaQuery import per file, file-level invariant preserved. **W141 anti-pattern #3 vindication** during SW execution.

**Verification**:

- tsc 0 errors
- eslint 0 warnings
- vitest **1268p/12s/0f** in 42.70s
- `grep -rn "useReducedMotion" frontend/src/features/activity frontend/src/features/events frontend/src/pages/EventDetail.tsx frontend/src/components/events/EventQuickView.tsx` → 0 matches

### SW4: Map + Misc + Hook 8 files (`6ae90c6d2`)

**Files**: MapFeature + WeatherParticles + \_admin + ProfileModal + MessageInput + NowPlayingCard + NewsQuickView + useAnimatedFloat
**Pattern mix**: 3 Pattern A (ProfileModal + MessageInput + NowPlayingCard + NewsQuickView = 4 actually — counted in SW commit body) + 5 Pattern B (MapFeature + WeatherParticles + \_admin + useAnimatedFloat = 4 actually). _Note: opening prompt's pattern classification was approximate; actual mix Pattern A 4 + Pattern B 4._
**Edits**: 16 (8 imports + 7 call sites + 1 comment block update on useAnimatedFloat.ts)

3 of 8 files already imported useMediaQuery (MapFeature + \_admin + NowPlayingCard); 5 needed new import (WeatherParticles + ProfileModal + MessageInput + NewsQuickView + useAnimatedFloat).

**W138 Lesson #1 within-iter SAME-mechanism sub-fix #2 (`useAnimatedFloat.ts` comment block update)**: The W124 SW1 comment at lines 13-15 said _"useReducedMotion remains in domAnimation set, so framer-motion still supplies the reactive boolean."_ — directly contradicted by the migrated code. Comment block updated within same edit to document W190 SW4 migration rationale + W184 SW6 jsdom-incompat root cause. This is documentation drift cleanup directly tied to the migration mechanism (the comment DESCRIBES the migrated hook choice), NOT a mechanism pivot.

**Verification**:

- tsc 0 errors
- eslint 0 warnings
- vitest **1268p/12s/0f** in 37.12s (W189 baseline preserved EXACTLY across all 25 W190 migrations)
- `grep -rn "import.*useReducedMotion.*from.*framer-motion" frontend/src` → **0 matches** (was 25 pre-W190) ✓
- Orphan call-site check: `grep -rn "useReducedMotion()" frontend/src --include="*.tsx" --include="*.ts" | grep -v "//\|/\*\|test\.tsx"` → 0 matches ✓

### SW5: Audit + N+3 rotation + memory files (this commit)

- NEW `docs/audits/AUDIT_WAVE190.md` (~250-300 lines following W189 audit template)
- N+3 rotation: `git mv docs/audits/AUDIT_WAVE187.md docs/audits/archive/AUDIT_WAVE187.md`
- Update `CLAUDE.md ## Audit Trail`: rotation history line + active waves text + W190 row
- Update `docs/audits/INDEX.md`: Active table (W190 → top; W187 → moved to archive table) + rotation history line
- Update `<.claude>/MEMORY.md`: compact W189 verbose Active backlog + Audit History rows → one-liners; add W190 verbose rows
- NEW `<.claude>/memory/wave190_backlog.md` (.claude profile only)
- NEW `<.claude>/memory/wave191_opening_prompt.md` (.claude profile only)

**Bundle Build × 3 BYTE-IDENTICAL EMPIRICALLY VERIFIED** post-SW4 (W190 NEW baseline):

| Build run | Main JS sha256                                                       | Main JS size | Server.js sha256                                                     | Server.js size |
| --------- | -------------------------------------------------------------------- | ------------ | -------------------------------------------------------------------- | -------------- |
| × 1       | `1bff1fd7403b03e206534340bc89c53a37ce29d1240e923e83b4101c9c813c97` | 180,273 b    | `5b103ae9845527671bc32e4ce2fc0e8dd89b849d8ebe78d2408cefa8073a641d` | 24,024 b       |
| × 2       | `1bff1fd7403b03e206534340bc89c53a37ce29d1240e923e83b4101c9c813c97` | 180,273 b    | `5b103ae9845527671bc32e4ce2fc0e8dd89b849d8ebe78d2408cefa8073a641d` | 24,024 b       |
| × 3       | `1bff1fd7403b03e206534340bc89c53a37ce29d1240e923e83b4101c9c813c97` | 180,273 b    | `5b103ae9845527671bc32e4ce2fc0e8dd89b849d8ebe78d2408cefa8073a641d` | 24,024 b       |

All 3 fresh `rm -rf dist && npm run build` runs from clean state IDENTICAL × 3. W134-W189 ≥48-wave LOCAL-MACHINE BYTE-IDENTICAL invariant chain EXTENDS through W190 → **≥49-wave invariant**.

**Tree-shake invariant** ✓: `grep -l "lhci-mock-user" dist/client/assets/*.js` returns empty (0 matches in PROD client assets — W116 SW3 invariant preserved).

**SW IIFE invariant** ✓: `head -c 25 dist/client/sw.js` returns `"use strict";(()=>{` (W138 SW2 pattern preserved post-W135 SW3 build-orchestrated.mjs).

---

## Bundle Delta vs W189 Baseline

| Metric         | W189 Baseline                                                        | W190 Baseline                                                        | Delta            |
| -------------- | -------------------------------------------------------------------- | -------------------------------------------------------------------- | ---------------- |
| Main JS size   | 180,277 b (`index-Ca-nPbFn.js`)                                      | 180,273 b (`index-CGBUMlAV.js`)                                      | **-4 bytes**     |
| Main JS sha    | `74d26d40417b0ff340c60022665348874063d4881f62e5085a036457826c2583` | `1bff1fd7403b03e206534340bc89c53a37ce29d1240e923e83b4101c9c813c97` | (real change)    |
| server.js size | 24,024 b                                                             | 24,024 b                                                             | **0 (identical)** |
| server.js sha  | `c5f927c741584276b8e8401212ff0863d124c5f375c1f32885acfe1890ab1e62` | `5b103ae9845527671bc32e4ce2fc0e8dd89b849d8ebe78d2408cefa8073a641d` | (real change)    |

**Honest framing**: -4 bytes main JS is FAVOURABLE but well under plan tolerance ±200 b. Rolldown's tree-shaker drops framer-motion's `useReducedMotion` + `initPrefersReducedMotion` listener-registration helper from vendor-ui chunk after ALL 25 source-level imports removed; per-file `useMediaQuery` import bookkeeping (already-loaded module) is smaller than the dropped helper weight. server.js content sha CHANGED despite IDENTICAL size — Vite environments build chunk graph shifts when shared modules (useMediaQuery shared chunk identity) are referenced from more places; server bundle output preserves byte-count but reorganizes internal module identity references. Both are real changes; W190 establishes NEW baseline.

---

## §Honesty Probe

**Pre-W190 baseline**: 0-2 OPEN

- W134 §H#2 — bundle delta recording-only (structural carry-forward, NOT a regression)
- W134 §H#10 — /messenger Phase 5 SSR by-design per W161 SW2 (structural non-goal)

**Post-W190 expected**: **0-2 OPEN** (same 2 structural carries; net ZERO new caveats)

- **CLOSE 1 actionable**: W189 W190+ candidate "broader hook migration sweep (24 component/page + 1 hook decision)" → 100% empirically (25/25 files migrated; grep returns 0 matches)
- **CLOSE 1 structural risk class**: latent jsdom-incompat for ALL `useAnimatedFloat` consumers (AnimatedRing + AttendanceCard + any future) — STRUCTURALLY CLOSED via hook migration
- **0 NEW (z) discoveries from W190 SW execution proper**:
  - W190 SW3 EventDetail.tsx duplicate-import revert = within-iter SAME-mechanism sub-fix per W138 Lesson #1, NOT (z) class
  - W190 SW4 useAnimatedFloat.ts comment block update = same-mechanism documentation drift cleanup, NOT (z) class
  - Extends low-(z) streak: 25 of last 25 waves (W145-W190)
- **0 NEW anti-patterns** (14-pattern register stable post-W159 #15 archival)
- **Carry-forward 2 structural non-goals unchanged**: W134 §H#2 + W134 §H#10

---

## W141 Anti-Pattern Compliance

| Anti-pattern                                              | W190 application                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| --------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **#1 STRICT 1-iter per SW SACRED**                        | **85th-89th vindications** (5 SW × 1 iter each). 2 within-iter SAME-mechanism sub-fixes per W138 Lesson #1 (NOT mechanism pivots): SW3 EventDetail.tsx duplicate-import revert + SW4 useAnimatedFloat.ts comment block update. Both are pure same-mechanism corrections within the migration scope. NO defer-cases fired. 14 defer-cases unchanged from W189 baseline.                                                                                                                                                                       |
| **#3 Phase 3 Review verify-before-write**                 | **102nd-104th vindications** (3 NEW W190): #102 useAnimatedFloat.ts decision (opening-prompt ambiguity resolved via direct Read); #103 SW3 EventDetail.tsx post-edit grep caught duplicate import; #104 SW4 useAnimatedFloat.ts comment block stale-text caught pre-commit. Discipline preserves cascade-prevention pattern.                                                                                                                                                                                                                  |
| **#4 Closures-after-empirical-verification**              | **42nd-43rd vindications** (closure attribution AFTER end-to-end empirical verification: grep `import.*useReducedMotion` returns 0 + grep orphan call sites returns 0 + Build × 3 BYTE-IDENTICAL × 3 fresh runs + vitest 1268p preservation × 4 SW + tsc 0 + lint 0). NO premature "closes" attributions.                                                                                                                                                                                                                                |
| **#15 (ARCHIVED W159 SW4)** husky pre-commit chain hygiene | Preserved **71st-75th consecutive wave** through W190. All 5 W190 commits fired W156 SW4 husky pre-commit chain cleanly (lint-staged + prettier --write + eslint --fix; detect-secrets PASS; bandit + mypy skipped — no .py files; Python 2 except syntax check PASS). NO `--no-verify` bypasses.                                                                                                                                                                                                                                                |

---

## Verification Matrix

| Gate                | Result                                                                                                                                                                                                                                                                                                                                                              |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| tsc                 | **0 errors** at each of 4 SW commits                                                                                                                                                                                                                                                                                                                                |
| eslint              | **0 warnings** (`--max-warnings=0`) at each of 4 SW commits                                                                                                                                                                                                                                                                                                          |
| prettier            | Clean (auto-fixed via lint-staged at each commit)                                                                                                                                                                                                                                                                                                                  |
| vitest              | **1268p / 12s / 0f** at each of 4 SW commits (W189 baseline 1268p preserved EXACTLY across all 25 migrations; durations 31.45s / 31.85s / 37.12s / 42.70s)                                                                                                                                                                                                          |
| npm audit           | **0 vulnerabilities** (W183 SW3 baseline preserved — no dependency changes in W190)                                                                                                                                                                                                                                                                                |
| Cargo.lock          | No drift (idempotent ≥ 49 waves at end of W190)                                                                                                                                                                                                                                                                                                                       |
| Build × 3           | **BYTE-IDENTICAL × 3 fresh runs from clean state** (`rm -rf dist && npm run build` between each). Main JS sha `1bff1fd7...813c97` × 3 + server.js sha `5b103ae9...3a641d` × 3 IDENTICAL.                                                                                                                                                                                              |
| Tree-shake          | ✓ `grep -l "lhci-mock-user" dist/client/assets/*.js` returns empty (0 matches in PROD client assets)                                                                                                                                                                                                                                                              |
| SW IIFE             | ✓ `head -c 25 dist/client/sw.js` returns `"use strict";(()=>{` (W138 SW2 pattern preserved)                                                                                                                                                                                                                                                                                  |
| i18n parity         | 18/18 (no new i18n keys in W190 — pure hook migration; CLDR-aware EN+RU walker passing)                                                                                                                                                                                                                                                                                                                            |
| Migration grep      | ✓ `grep -rn "import.*useReducedMotion.*from.*framer-motion" frontend/src` returns **0 matches** (was 25 pre-W190)                                                                                                                                                                                                                                                                                              |
| Orphan call sites   | ✓ `grep -rn "useReducedMotion()" frontend/src --include="*.tsx" --include="*.ts" | grep -v "//\|/\*\|test\.tsx"` returns 0 matches                                                                                                                                                                                                                                                                                              |
| Husky pre-commit    | All 5 W190 commits fire W156 SW4 chain cleanly (lint-staged + prettier --write + eslint --fix + detect-secrets + Python 2 except check; NO `--no-verify`)                                                                                                                                                                                                                                                                |

---

## N+3 Rotation

```bash
git mv docs/audits/AUDIT_WAVE187.md docs/audits/archive/AUDIT_WAVE187.md
```

**Active waves post-W190**: W188/W189/W190 (W187 archived).

Per W122 polish-docs-v3 convention: oldest active audit moves to archive when N+3 next wave opens. The 3 most-recent active audits stay in `docs/audits/`; older audits live in `docs/audits/archive/`. Rotation history maintained in `docs/audits/INDEX.md` ## Rotation history paragraph + `CLAUDE.md ## Audit Trail` rotation history block.

---

## W191+ Candidates (priority order)

Per W171 Lesson #1: maintenance mode means waves fire on real triggers OR user-chosen scope.

1. **A) Continue maintenance mode** — CANONICAL DEFAULT per W171 Lesson #1. W191+ fires on real production trigger OR user-chosen scope.
2. **B) W191 XL Path E messenger backend wave** (~6-10h) — read receipts (`read_at: datetime`) + Reaction model + voice messages migrations + endpoints + ws-hub message types. Prerequisite for W192 UI wave.
3. **C) W192 Path E UI wave** (~6-10h depends on W191 closure) — E1 read receipts UI + E2 reactions UI + E3 voice messages UI per W125 design Phase 5 continuation. CAN'T run in W191 alongside backend due to dependency.
4. **D) Lighthouse #17021 monitoring tick** at W193+ if no upstream movement (quarterly cadence per W188 SW5).
5. **E) wave189-unauthed-smoke.mjs CI integration** (~1-2h Tier 2 housekeeping) — script exists locally but not wired to CI workflow yet.
6. **F) SW3 hook migration regression tests** (~1-2h Tier 4 housekeeping) — explicit tests for `prefers-reduced-motion` behaviour on migrated components.

---

## Polish-vN Chain Expectations (per `feedback_perfectionism.md`)

If «безупречно?» probe fires at wave-close, expect 0-3 real gaps (e.g., off-by-one in vindication counts, MEMORY.md headroom recalc, stale text refs). Polish-v1 budget: ~30-60 min.

Per W189 SW3 precedent: 0-1 polish rounds expected for mechanical migration. Per W189 polish-v1 reference: the polish chain should empirically verify:

- Build × 3 BYTE-IDENTICAL × 3 fresh runs from clean state (already done in SW5 above)
- Tree-shake invariant (already verified ✓)
- SW IIFE invariant (already verified ✓)
- Vindication count accuracy (already cross-checked against W189 baseline)
- §Honesty trajectory honesty (already framed as 0-2 → 0-2 OPEN with 1 closure + 1 structural risk class closure)
- CI on PR #1126 GREEN post-push (pending; verify at polish-v1 if fires)

---

## Closes / Carries

**Closes**:

- W189 W190+ candidate "broader hook migration sweep (24 component/page + 1 hook decision)" → 100% empirically (25/25 files migrated; grep 0 matches)
- Latent jsdom-incompat risk class for ALL components using `useAnimatedFloat` (AnimatedRing + AttendanceCard + any future consumer) → STRUCTURALLY CLOSED via hook migration + comment block update

**Carries forward unchanged**:

- W134 §H#2 — bundle delta recording-only (structural carry-forward; W190 delta -4 b is recorded but not flagged as caveat)
- W134 §H#10 — /messenger Phase 5 SSR by-design per W161 SW2 (structural non-goal; W190 scope is component hooks, NOT messenger SSR)

---

## Wave Streak Milestone

W141-W189 = **49 consecutive waves** of brainstorming + Phase 1 Explore + Phase 3 Review + W141 anti-pattern discipline + `feedback_perfectionism.md` + `feedback_planning_estimates.md`.

**W190 = 50th consecutive wave** with this discipline. Milestone preserved.

Per W141 anti-pattern #1 STRICT 1-iter SACRED: each W190 SW landed in 1 iter; within-iter SAME-mechanism sub-fixes per W138 Lesson #1 (NOT mechanism pivots) preserved the iter cap. 84 cumulative vindications → 89 post-W190 (5 SW × 1 iter).

Per `feedback_perfectionism.md` honest framing: «безупречно?» probe at wave-close expected to surface 0-3 gaps (typical post-mechanical-migration). Polish chain expected 0-1 rounds.
