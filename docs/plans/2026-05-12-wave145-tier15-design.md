# Wave 145 Tier 1 + Tier 5 — design

**Date**: 2026-05-12
**Branch**: `egorribun`
**Base HEAD**: `44199590f docs(wave144-polish-v1): close 7 §Honesty gaps surfaced by "безупречно?" probe`
**Scope**: NO-DEPLOY continued (W125–W144 SSR migration arc + local + structural)
**User-approved 4-question (2026-05-12)**: Q1 Tier 1 + Tier 5 combo (~3-4h) + Q2 Per-step + Promise.race (first iter) + Q3 Open-ended absorption (7th consecutive) + Q4 /messenger × 2 polish arc (Tier 5 retirement decision)
**Wall-clock budget**: ~4-6h core (Q1 estimate + Q3 absorbs (z) cascade)
**Expected §Honesty caveat band post-W145**: 2-9 (best case both Tier 1 SW close) / 5-12 (most likely: Tier 5 closes + Tier 1 SW1 fast-fail diagnostic identifies hang but doesn't fully close axe coverage; 1 NEW caveat for alternative injection strategy)

---

## Context

Wave 144 closed 2026-05-12 (HEAD `44199590f` — SW0 `b6996bf11` + SW1 iter1 `b2c3036a5` + SW1 iter2 `37466b00f` + SW2 files `9e4870435` + SW2 runtime `1cce99aed` + SW7 `a56dd4645` + polish-v1 `44199590f`) with **3 §Honesty caveats CLOSED at runtime** (W137 #5 + W140 NEW #6 + W142 (z) #10) via plain `temporalio/server:1.30.2` runtime swap + 5-(z) cascade #16-#20 mitigated in single commit `1cce99aed`. **Polish-v1 closed 7 "didn't measure" / "stale doc" / "overclaimed framing" gaps** surfaced by "безупречно?" probe (vitest 1052p/12s/0f re-verified empirically, eslint 36 errors PRESERVED, MEMORY.md compacted to 23,994 bytes under 24,400 limit, (z) #10 framing softened to "most plausible" with A/B isolation note).

Two outstanding items now ready for W145:

1. **W140 §Honesty NEW #5 — axe coverage 0/8 routes** (60s timeout cap fires across all 8 SSR routes since W140). W144 SW1 iter 2 pivoted to Path A2 (npm-bundled axe-core + `page.evaluate(eval(550KB))`) which structurally eliminated CSP-block as failure mode (Phase 1 Agent 1 source-code chain VERIFIED in W144 SW0), but CI run `25739831369` HUNG 24 min on /login → W144 NEW (z) #21 (different failure mode, suspects: 550 KB IPC serialization / eval() under headless Chromium memory pressure / page.goto load event hung).

2. **Tier 5 carry-forward (12 consecutive waves W134-W144)** — explicit decision on /messenger × 2 polish arc OR /admin polish arc OR punt as "production-as-is". User chose **/messenger × 2 polish arc** to retire the carry-forward.

W145 attacks both with **2 + 1 SW structure** combined per user-approved Q1+Q4 = Tier 1 axe + Tier 5 messenger × 2 polish.

---

## Phase 1 Explore findings (light, ~10 min direct grep + Read)

Per user opening prompt note + W144 SW1 lesson: "Phase 1 Explore agents МОГУТ быть skipped — W144 SW1 iter 2 logs already provide strong diagnostic evidence ... per-step diagnostic + Promise.race wrapper is concrete code work, not hypothesis exploration." Light direct exploration replaces 3-agent parallel investigation.

### Finding 1 — wave138-visual-audit.mjs unwrapped eval step (CRITICAL for SW1)

Source read at [frontend/scripts/wave138-visual-audit.mjs:380-430](../../frontend/scripts/wave138-visual-audit.mjs:380):

| Line | Code | Promise.race wrapper? |
|---|---|---|
| 384-390 | `page.evaluate((src) => { eval(src) }, AXE_SOURCE)` (axe global injection, 550 KB source) | **NO** ← suspected (z) #21 hang location |
| 413-429 | `Promise.race([page.evaluate(...axe.run(...)), setTimeout(reject, axeTimeoutMs)])` | YES (60s for compact routes, 90s for heavy /dashboard, /map, /activity per HEAVY_ROUTES set at line 376) |

**Implication**: W144 SW1 iter 2 added Promise.race only at the axe.run() execution step (line 413), NOT at the prior eval injection step (line 384). If the 24-min hang is at injection, a 30s injection-step Promise.race wrapper closes the hang structurally (no more 24-min CI hangs even if injection ultimately fails — fast-fail with `axe-inject-timeout-30s` sidecar).

### Finding 2 — Messenger structure (light Glob + Read)

| Path | Status |
|---|---|
| `frontend/src/routes/_auth/messenger.tsx` | list route, `ssr: false` (W128 SW2 opt-down), lazy-imports `@/pages/Messenger` |
| `frontend/src/routes/_auth/messenger.$chatId.tsx` | detail route, `ssr: false` (W128 SW2 opt-down), lazy-imports `@/pages/Messenger` (same component for both routes) |
| `frontend/src/pages/Messenger.tsx` | 125 LoC page wrapper, uses `useMessengerController()` |
| `frontend/src/features/messenger/index.ts` | barrel re-exports useChatWebSocket + chat API only — **NO MessengerFeature.tsx orchestrator** |
| `frontend/src/hooks/features/useMessengerController.ts:29` | `useParams({ strict: false }) as { chatId?: string }` — `as` cast bypasses type safety |
| `frontend/src/components/messenger/{ChatArea,ChatWindow,ContactList,MessageInput,MessengerSidebar,NewChatModal,ProfileModal}.tsx` | rendered components, use `m` from framer-motion (W123 SW2 LazyMotion pattern preserved) |

**Convention drift**: features/messenger lacks the W112 SW2 `<Feature>.tsx` orchestrator + `FeatureErrorBoundary` wrap that events / news / activity / map all have. SW2 fixes this drift.

### Finding 3 — SW2 refactor safety (Grep verification)

Grep `from\s+["']@/pages/Messenger["']` across `frontend/src` → **0 matches outside the 2 route files**. No tests, no other consumers. Mechanical refactor.

### Finding 4 — Test coverage for useMessengerController

`frontend/src/hooks/features/**/*.test.{ts,tsx}` — not verified pre-SW2 (deferred to SW2 implementation grep to confirm).

### Finding 5 — visual-audit.yml workflow infra (Wave 139 SW1)

[.github/workflows/visual-audit.yml](../../.github/workflows/visual-audit.yml) — workflow_dispatch only with `routes` input. Caddy + backend + frontend Node SSR on Linux runner. RS256 keypair via openssl. Test user via /register POST. 8 default SSR routes; messenger NOT in default list (SW3 adds).

---

## Approach per SW

### SW0 — Design doc commit (THIS DOC)

**Goal**: persist Phase 1 Explore findings + W145 design as `docs/plans/2026-05-12-wave145-tier15-design.md` (mirror of W144 SW0 `b6996bf11` pattern, 1 file +~280 LoC). Provides audit-trail evidence per W141 anti-pattern #1.

**Files**: NEW `docs/plans/2026-05-12-wave145-tier15-design.md` (this file).

**Commit message**: `chore(wave145-sw0): design doc + memory backlog scaffolding`

---

### SW1 — Tier 1 axe A2 step-diagnostic + Promise.race injection wrapper

**Goal**: close W144 NEW (z) #21 (24-min CI hang) AND identify exact hang step for W140 NEW #5 axe coverage. Two-layer fix:

#### Layer (a) — Promise.race wrapper on injection step

Modify [frontend/scripts/wave138-visual-audit.mjs:384-390](../../frontend/scripts/wave138-visual-audit.mjs:384):

```js
// Before (W144 SW1 iter 2):
await page.evaluate((src) => {
  eval(src)
}, AXE_SOURCE)

// After (W145 SW1):
const INJECT_TIMEOUT_MS = 30_000
await Promise.race([
  page.evaluate((src) => {
    eval(src)
  }, AXE_SOURCE),
  new Promise((_, reject) =>
    setTimeout(() => reject(new Error(`axe-inject-timeout-${INJECT_TIMEOUT_MS / 1000}s`)), INJECT_TIMEOUT_MS)
  ),
])
```

Mirrors the axe.run() Promise.race pattern at lines 413-429 exactly.

#### Layer (b) — Per-step console.log markers

Inside `auditRoute()` ([line 301](../../frontend/scripts/wave138-visual-audit.mjs:301)), add 8 markers around each blocking step with route prefix:

```js
console.log(`[${routePath}] before-goto`)
const resp = await page.goto(...)
console.log(`[${routePath}] after-goto status=${httpStatus}`)

console.log(`[${routePath}] before-waitTimeout`)
await page.waitForTimeout(1500)
console.log(`[${routePath}] after-waitTimeout`)

console.log(`[${routePath}] before-evalInject src-bytes=${AXE_SOURCE.length}`)
await Promise.race([...])  // Layer (a) injection
console.log(`[${routePath}] after-evalInject`)

console.log(`[${routePath}] before-axeRun`)
const results = await Promise.race([...])  // existing axe.run wrapper
console.log(`[${routePath}] after-axeRun violations=${results?.violations?.length ?? 0}`)
```

#### Three CI outcomes (per Risk register #2)

- **Outcome A (~70% likely)**: `before-evalInject` logged, `after-evalInject` NOT within 30s → injection Promise.race fires → `axe-inject-timeout-30s` sidecar → axe still 0/8 BUT no more 24-min hangs; W146+ pivot to page.addInitScript() alternative.
- **Outcome B (impossible)**: `after-evalInject` logged but `before-axeRun` NOT — they're sequential immediate-next-line. Excluded.
- **Outcome C (~10% lucky)**: all markers log + axe succeeds → W140 NEW #5 + (z) #21 BOTH CLOSED.

3-iter CI cap per Q3 open-ended (honest defer at iter 4).

**Files**: modify `frontend/scripts/wave138-visual-audit.mjs` (~30 LoC delta).

**Verification**: `gh workflow run visual-audit.yml -f routes=login` (no leading slash per W144 (z) #15 MSYS-mangle gotcha); CI run number baked into SW1 closure commit message per W141 anti-pattern #1.

---

### SW2 — Tier 5 #1: Messenger feature orchestrator + URL-typed params + error boundary

**Goal**: align messenger with W112 SW2 features/<page>/<Feature>.tsx convention.

#### Steps

(a) **NEW [frontend/src/features/messenger/MessengerFeature.tsx](../../frontend/src/features/messenger/MessengerFeature.tsx)** — mirror events / news / activity / map orchestrator shape:

```tsx
import { FeatureErrorBoundary } from "@/components/error/FeatureErrorBoundary"
import Messenger from "@/pages/Messenger"  // temporary; deleted in step (e)

export default function MessengerFeature() {
  return (
    <FeatureErrorBoundary>
      <Messenger />
    </FeatureErrorBoundary>
  )
}
```

Then merge `pages/Messenger.tsx` content into `MessengerFeature.tsx` directly (eliminates 1 component layer).

(b) **Modify [frontend/src/features/messenger/index.ts](../../frontend/src/features/messenger/index.ts)**: add `export { default as MessengerFeature } from "./MessengerFeature"` alongside existing re-exports.

(c) **Modify [frontend/src/routes/_auth/messenger.tsx](../../frontend/src/routes/_auth/messenger.tsx)** + **[frontend/src/routes/_auth/messenger.$chatId.tsx](../../frontend/src/routes/_auth/messenger.$chatId.tsx)**: change `lazy(() => import("@/pages/Messenger"))` → `lazy(() => import("@/features/messenger/MessengerFeature"))`. Preserve `ssr: false`.

(d) **Modify [frontend/src/hooks/features/useMessengerController.ts:29](../../frontend/src/hooks/features/useMessengerController.ts:29)**:

```ts
// Before:
const { chatId } = useParams({ strict: false }) as { chatId?: string }

// After:
const params = useParams({ from: "/_auth/messenger/$chatId", shouldThrow: false })
const chatId = params?.chatId
```

`shouldThrow: false` returns `undefined` if route doesn't match (e.g., on `/messenger` list view), preserving optional-chatId semantics WITHOUT `as` cast.

(e) **DELETE [frontend/src/pages/Messenger.tsx](../../frontend/src/pages/Messenger.tsx)** — content fully migrated to `features/messenger/MessengerFeature.tsx`.

(f) Pre-SW2-implementation grep: `grep -r "useMessengerController" frontend/src/hooks/features/__tests__/` — if any test references useMessengerController, verify type-safe useParams change doesn't break it.

**Files**: NEW `MessengerFeature.tsx`, modify 4 files, DELETE `pages/Messenger.tsx`.

**Verification**: `tsc 0 errors`, `eslint --max-warnings=0` on modified files, vitest preserved at 1052p/12s/0f, build × 1 reproducible (bundle hash will change minor — bake new hash into SW2 commit).

---

### SW3 — Tier 5 #2: Messenger visual smoke + a11y baseline

**Goal**: establish messenger axe a11y baseline (empty-state DOM coverage; closes the "messenger has never been audited" gap).

**Modify [frontend/scripts/wave138-visual-audit.mjs](../../frontend/scripts/wave138-visual-audit.mjs)** `DEFAULT_ROUTES` constant — add `/messenger` + `/messenger/placeholder-chat-id`. Placeholder chatId triggers detail route render; `useMessengerController` handles "no real chat data" gracefully (empty state).

**Verification path depends on SW1 outcome**:

- **Outcome C** (SW1 fully closes axe): `gh workflow run visual-audit.yml -f routes=messenger,messenger/placeholder-chat-id` — sidecar JSON shows HTTP 200 + AUTHED + axe violations (or 0).
- **Outcome A** (SW1 fast-fail injection timeout): messenger routes hit `axe-inject-timeout-30s` deterministically; sidecar shows structural verification (HTTP + console + hydration) but no axe scan. Documented baseline: "structurally verified, axe coverage W146+ pending injection fix."
- **Outcome SW1 honest defer**: SW3 pivots to manual `chrome-devtools-mcp` local Docker chain navigation + console verify (not formal axe, but visual + console sanity).

**Files**: modify `frontend/scripts/wave138-visual-audit.mjs` (~5 LoC).

---

### SW6 — Tier 3 housekeeping (CONDITIONAL — likely SKIP)

W144 polish-v1 already closed all candidate housekeeping items (MEMORY.md 23,994 bytes, W141 row collapsed, verification matrix re-measured). SW6 SKIPS unless something surfaces during SW1+SW2+SW3 execution. Documented as SKIP in SW7.

---

### SW7 — Audit + memory + N+3 rotation

(a) NEW [docs/audits/AUDIT_WAVE145.md](../../docs/audits/AUDIT_WAVE145.md) (~250 lines, mirror of W144 SW7 audit shape).

(b) Modify [CLAUDE.md](../../CLAUDE.md) ## Audit Trail — add W145 row (concise per W134 SW3 readability convention, ~1.5 KB max).

(c) Modify [docs/audits/INDEX.md](../../docs/audits/INDEX.md) — add W145 entry to reverse-chronological listing.

(d) NEW `memory/wave145_backlog.md` with close-status entry + §Honesty list + commit references.

(e) NEW `memory/wave146_opening_prompt.md` for W146 session start.

(f) **N+3 rotation**: `git mv docs/audits/AUDIT_WAVE142.md docs/audits/archive/AUDIT_WAVE142.md`. Active waves post-W145: W143/W144/W145.

(g) Update [memory/MEMORY.md](../../memory/MEMORY.md) ## Active backlog (W145 entry) + ## Audit History (W144→W145 entry promotion).

---

## Files modified / created summary

### NEW
- `docs/plans/2026-05-12-wave145-tier15-design.md` (SW0 — this file)
- `frontend/src/features/messenger/MessengerFeature.tsx` (SW2)
- `docs/audits/AUDIT_WAVE145.md` (SW7)
- `memory/wave145_backlog.md` (SW7)
- `memory/wave146_opening_prompt.md` (SW7)

### Modified
- `frontend/scripts/wave138-visual-audit.mjs` (SW1 + SW3)
- `frontend/src/features/messenger/index.ts` (SW2)
- `frontend/src/routes/_auth/messenger.tsx` (SW2)
- `frontend/src/routes/_auth/messenger.$chatId.tsx` (SW2)
- `frontend/src/hooks/features/useMessengerController.ts` (SW2)
- `CLAUDE.md` (SW7)
- `docs/audits/INDEX.md` (SW7)
- `memory/MEMORY.md` (SW7)

### Deleted
- `frontend/src/pages/Messenger.tsx` (SW2)
- `docs/audits/AUDIT_WAVE142.md` → archive via `git mv` (SW7 N+3 rotation)

---

## Verification matrix

| Gate | Pre-W145 baseline | Per-SW expectation |
|---|---|---|
| tsc | 0 errors | 0 errors each SW |
| eslint --max-warnings=0 | 36 errors (W144 polish-v1 baseline; preserved by SW1 disable-comment hygiene) | 36 errors preserved each SW |
| vitest | **1052p / 12s / 0f** (W144 baseline) | 1052p preserved (no test changes expected) |
| pytest backend slice | 255p baseline preserved (no backend changes) | preserved |
| npm audit | **0 vulnerabilities** | preserved |
| Cargo.lock | no drift (idempotent ≥ 34 waves) | preserved |
| Build reproducibility | hash `index-CWDZt5WS.js` 138,125 bytes (PROD; W128 base) — verify hash unchanged for SW0+SW1 (no src/ touches); SW2 changes hash minor (rebake) | per-SW |
| Docker stack | temporal + file-processor `(healthy) × 2` | preserved |
| file-processor JWT auth chain | "Attached Temporal service token" + "Connected to Temporal addr=temporal:7233" + "Started Worker Namespace default TaskQueue FILE_PROCESSING_TASK_QUEUE" | re-verify via docker logs in SW7 |
| Tree-shake: lhci-mock-user | 0 matches in PROD dist | preserved |
| Tree-shake: data-e2e-stub | 0 matches in PROD dist | preserved |
| SW IIFE invariant | `head -c 25 dist/client/sw.js` → `"use strict";(()=>{` | preserved |
| jwtKeyProvider in config.yaml | matches (NOT tokenKeyProvider — W141 anti-pattern #3) | preserved |
| MEMORY.md size | 23,994 bytes (< 24,400) | < 24,400 |
| Active audit waves | W142/W143/W144 (W141 archived in W144 SW7) | W143/W144/W145 post-W145 SW7 |
| Archive audit count | 30 | 31 post-W145 SW7 |
| CI run number baked | — | SW1 + SW3 commit messages reference CI run number |

---

## Risk register

1. **(z) cascade absorption** per Q3 open-ended budget. SW1 has 3-iter cap. SW2 small surface (5 files); 0 prior wave context (first messenger-touching wave since W128 SW2 opt-down). Ceiling ~4-6h core wall-clock.

2. **SW1 Outcome A vs C divergence**:
   - Outcome A (~70%): injection Promise.race fires → fast-fail → axe still 0/8 but no 24-min hangs. Net W140 NEW #5 OPEN + (z) #21 RESOLVED. -1 closure but +1 NEW caveat (alternative injection strategy needed). Net delta 0.
   - Outcome B (impossible — sequential lines).
   - Outcome C (~10%): both close. -2 closures. Net delta -2.
   - SW1 honest defer (~20%): both stay open + 1 NEW (z). Net delta +1.

3. **W141 anti-pattern #3 protection at SW1 code-write time**: re-Read [wave138-visual-audit.mjs:384-390](../../frontend/scripts/wave138-visual-audit.mjs:384) immediately before Edit to confirm injection step still has no Promise.race wrapper (file may have been modified between plan + commit, though unlikely in same session).

4. **SW2 vitest cascade**: minimal (0 pages/Messenger imports outside routes). Pre-SW2-impl grep verifies test coverage for useMessengerController + chrome-devtools-mcp manual smoke verifies type-safe useParams change.

5. **SW3 CI dependency on SW1**: pre-defined fallback (manual chrome-devtools-mcp on local Docker chain).

6. **MSYS-mangle on outgoing `gh` CLI args** (W144 (z) #15): SW1 + SW3 verification commands use `gh workflow run ... -f routes=login` (no leading slash).

7. **Phase 1 verified-reference protection**: this design was written from direct source-code Read at wave138-visual-audit.mjs:380-430, features/messenger/* file structure, useMessengerController.ts:29. NOT Context7 prose inference.

---

## §Honesty caveats projection for W145

| Scenario | Probability | Caveats CLOSED | Caveats NEW | Net delta | Post-W145 band |
|---|---|---|---|---|---|
| **A** (SW1 Outcome C — full axe closure) | ~10% | 3 (W140 #5 + (z) #21 + Tier 5 retired) | 0 | -3 | 2-9 |
| **B** (SW1 Outcome A — fast-fail injection; MOST LIKELY) | ~70% | 2 ((z) #21 resolved via fast-fail + Tier 5 retired) | 1 (alternative injection strategy W146+) | -1 | 5-12 |
| **C** (SW1 honest defer + NEW (z) cascade) | ~20% | 1 (Tier 5 retired) | 1-2 (axe stays + new (z)) | 0 to +1 | 5-13 |

### Universal carry-forwards (regardless of scenario)
- W134 §Honesty #2 bundle delta recording (honest framing)
- W134 §Honesty #10 /messenger Phase 5 SSR enable punted (carry continues; W145 closes Tier 5 polish but NOT SSR enable)
- Procedural (z) like MSYS-mangle (W144 (z) #15) — convention, not code fix

### W146+ candidates
- Alternative axe injection strategy if SW1 Outcome A (page.addInitScript() OR chunked injection per W145 Q2 sub-paths (ii)(iii))
- /messenger SSR enable when ws-hub structurally supports SSR-side cookie forwarding
- /admin polish arc (deferred since user chose /messenger; W146+ candidate)

---

## Anti-patterns to avoid

1. **W141 anti-pattern #1** (CI verification IS closure criterion): SW1 + SW3 closure commits bake CI run numbers.

2. **W141 anti-pattern #2** (Runtime/CI verification IS the step): per-step markers ARE diagnostic; tsc + vitest ARE SW2 verification.

3. **W141 anti-pattern #3 quintuple-vindicated** (verified-reference mandate): plan written from direct source-code reads, NOT Context7 prose.

4. **W141 anti-pattern #4** (don't claim closure pre-implementation): SW1 outcome is empirically determined by CI; plan describes probabilities not assertions.

5. **W144 polish-v1 lesson** (empirically re-measure gates post-implementation): SW7 must re-run ALL gates, NEVER assume hold.

6. **W138 Lesson #2** (include "(z) something we haven't thought of" as explicit hypothesis path): risk register #1 covers this.

7. **W144 (z) #15** (MSYS-mangle on outgoing `gh` CLI args): SW1 + SW3 verification commands omit leading slash.

8. **2-3 CI iter cap on SW1** (W140 anti-pattern #1): honest defer at iter 4.

9. **"безупречно?" probe budget**: anticipate 0-1 polish round (~15-30 min if needed).

---

## References

- W144 SW0 design doc: [docs/plans/2026-05-12-wave144-tier123-design.md](2026-05-12-wave144-tier123-design.md)
- W144 SW1 iter 2 commit: `37466b00f feat(wave144-sw1-iter2): Path A2 npm-bundled axe-core + page.evaluate(eval)`
- W144 polish-v1 commit: `44199590f docs(wave144-polish-v1): close 7 §Honesty gaps surfaced by "безупречно?" probe`
- W128 SW2 messenger ssr: false opt-down (line 8-12 of messenger.tsx + messenger.$chatId.tsx)
- W112 SW2 features/<page>/<Feature>.tsx orchestrator convention
- W139 SW1 visual-audit.yml workflow_dispatch infra
- User opening prompt: `memory/wave145_opening_prompt.md`
- AUDIT_WAVE144.md: [docs/audits/AUDIT_WAVE144.md](../audits/AUDIT_WAVE144.md)
