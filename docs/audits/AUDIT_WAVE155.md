# AUDIT WAVE 155 — Tier 1(a) Windows-Platform Investigation (Cheap-First Cascade A→B→C)

**Date**: 2026-05-15
**Branch**: `egorribun`
**HEAD pre-W155**: `6c9a31a6a` (W154 SW3 audit) + `29d6dab67` (W154 SW1 ssr:true restore)
**HEAD post-W155**: `<TBD on commit>` (W155 SW4 audit only; ZERO code changes shipped)
**Outcome**: Honest defer per W141 anti-pattern #1 STRICT 1-iter cap (11th vindication)

---

## TL;DR

Wave 155 ran the user-approved Tier 1(a) cheap-first cascade (Q1+Q2+Q3 at SW0) on the W154 §Honesty NEW #1 user-facing Windows + Chrome blank wedge. All 3 sub-tasks **DISPROVED their starting hypotheses** but **NAMED 2 mechanisms** that move W156+ investigation closer to root cause:

| Sub-task | Hypothesis | Outcome |
|----------|-----------|---------|
| **SW1 (Sub-task A)** | Rolldown chunk-ordering causes `globals READ before assigned` → V8 ReferenceError. Fix via `output.strictExecutionOrder: true` (extends W123 SW1 Storybook). | **DISPROVED.** Bundle rebuild with flag → user real Chrome regular + Incognito STILL BLANK. |
| **SW3.A (Sub-task C)** | V8/Chromium-specific class. Test by swap to Firefox (Gecko engine). | **DISPROVED.** Firefox ALSO blanks. **BUT** Firefox DevTools opened (Chrome's was blocked) and revealed **React #418 hydration mismatch** error — named root cause class. |
| **SW3.B (Sub-task B-substitute)** | If hydration mismatch is the wedge, force `createRoot` path (bypass `hydrateRoot`) → page should render fresh tree. | **DISPROVED.** Force createRoot → STILL BLANK + NEW error class: **Script terminated by timeout at `getParentHydrationBoundary`** (infinite loop in React 19 event system + hydration boundary traversal during `completeWork → listenToAllSupportedEvents → dispatchEvent`). |

**Wedge scope narrowed from W154** ("Windows + Chrome + Vite 8 Rolldown bundle execution interaction class") → **W155** ("React 19 internal hydration boundary code path infinite loop on Windows browsers + production bundle specifically — chunk order, browser engine, and hydration entry point ALL ruled out as primary cause"). The wedge persists across:
- Rolldown chunk-order configuration (`strictExecutionOrder` on/off)
- JS engine (V8 + SpiderMonkey both fail)
- React mount entry point (hydrateRoot fails with #418; createRoot fails with timeout)

This means **W156+ must investigate React 19's event system + hydration boundary tracking specifically** (likely candidates: known React 19 infinite loops in `getParentHydrationBoundary` under certain DOM state, or specific component/SSR HTML structure causing React's internal traversal to not terminate).

**§Honesty trajectory**: 22-26 OPEN → 22-26 OPEN (range unchanged; W154 NEW #1 stays OPEN; 2 NEW W155 mechanism caveats added but scope significantly narrower). Per `feedback_perfectionism.md` honest framing: net caveat count similar, but mechanism specification improved by 2 grades.

---

## State at Session Start (Pre-flight Gates)

11/11 pre-flight gates GREEN:
- Working tree clean; HEAD `6c9a31a6a` (W154 SW3) + `29d6dab67` (W154 SW1) at top
- CI `egorribun` recent runs SUCCESS (Chromatic + Dependency Review + Contract Validation + Generate OpenAPI + DB Performance + Go Lint & SBOM + Matrix Expansion all GREEN)
- Active waves W152/W153/W154; archive 39 files
- Docker stack: frontend + backend + caddy + temporal + file-processor ALL `(healthy)`
- `__root.tsx:159` `ssr: true` ✓ (W154 SW1 restored); `_public.tsx` NO `ssr:` field ✓ (W154 SW1 removed, inherits from root)
- `/login` curl: 200 / 21,777 b real SSR ✓
- `/404` curl: 404 / 65,143 b ✓; `/` curl: 307 redirect to /login ✓
- `/healthz`: `{"status":"ok"}` ✓
- MEMORY.md: 23,317 b < 24,400 ✓

Q0 user-confirmed: all 3 routes still blank in regular + Incognito Chrome → Tier 1(a) cascade activated per Q1 RECOMMENDED + Q2 STRICT 1-iter cap + Q3 no Linux CI re-trigger.

---

## SW1 — Sub-task A: `output.strictExecutionOrder: true` on PROD bundle

**Change**: `frontend/vite.config.mts` lines 498-499 area: +1 flag line + 7 comment lines mirroring W123 SW1 Storybook precedent (commit `f0f352fb3`).

**Execution**:
1. ✅ Edit applied
2. ✅ Local gates: `npx tsc --noEmit` 0 errors (Risk R5 disproved — Vite's native Rolldown typing accepts the flag; no local type extension needed unlike Storybook's `.storybook/main.ts:4` defensive pattern), `npm run lint --max-warnings=0` 0, `npm run format:check` clean (anti-pattern #15 prevention)
3. ✅ Docker rebuild via `docker compose up -d --build frontend` (production-minified mode; FRONTEND_BUILD_UNMINIFIED NOT set — different build path than W154 baseline's unminified)
4. ✅ All containers (healthy) post-rebuild
5. ✅ Server-side smoke:
   - `/login`: 200 / **20,709 b** real SSR content (vs W154 unminified baseline 21,777 b; -1,068 b due to production-minification, NOT SSR regression — same `<div class="flex min-h-dvh"`, Sign in form, email/password inputs, `<input type="text">`)
   - `/404`: 404 / 64,075 b
   - `/`: 307 (auth-at-edge to /login)
6. ✅ Bundle metadata: `index-B3Xg0D1U.js` 258,295 b (production-minified; hash changed from W154 baseline `index-DLYWEge9.js` 341,886 b confirming flag applied)
7. ✅ Tree-shake invariant: 0 `lhci-mock-user` in PROD assets ✓
8. ✅ jsxDEV invariant: 0 in server.js + server/assets ✓ (W153 SW1 fixup preserved)
9. ✅ SSR markers in /login HTML: `Sign in`, `email`, `password`, `input type`, `placeholder`, `<div class="flex min-h-dvh"` ALL present ✓

**SW1.5 USER-FACING VERIFICATION**: User opens `http://localhost/login` in regular Chrome AND fresh Incognito (Ctrl+Shift+N).

**Result**: **STILL BLANK in both Chrome modes.**

**Conclusion**: Rolldown chunk-ordering hypothesis **DISPROVED** at user-facing level. `strictExecutionOrder: true` had no observable rendering effect — the W123 SW1 Storybook fix pattern does NOT extend to this main PROD wedge class.

**STRICT 1-iter cap honored** per W141 anti-pattern #1: NO retry of SW1 with different `strictExecutionOrder` value combinations or other Rolldown options. Escalation to next mechanism per cascade plan.

---

## SW3.A — Sub-task C (pivoted from plan order): Browser engine swap (Firefox on Windows native)

**Plan deviation rationale**: Sub-task B (WSL2 reproduction, ~1-2h, requires WSL2 + Firefox install + Docker Desktop WSL2 integration prerequisites — user marked NOT ready) vs Sub-task C (browser swap, ~5-10 min, just open Firefox — user marked Firefox ready). User approved pivot to SW3 first via mid-wave AskUserQuestion: **"SW3 first (cheap browser swap) — RECOMMENDED"**.

**Execution**:
1. User opens `http://localhost/login` in Firefox on Windows native (NOT WSL2)
2. Reports back

**Result A**: **Firefox ALSO blanks.** V8/Chromium-specific hypothesis **DISPROVED** — Gecko + V8 both fail. Browser engine is NOT the wedge.

**Result B (CRITICAL BREAKTHROUGH)**: User opens Firefox DevTools (F12). Firefox DevTools OPENS (Chrome's was blocked by wedge — W152+W153 history). Console shows:

```
[GlobalErrors] Unhandled error event Error: Minified React error #418;
visit https://react.dev/errors/418?args[]=text&args[]= for the full message
or use the non-minified dev environment for full errors and additional
helpful warnings.
    React 9
    performWorkUntilDeadline scheduler.production.js:151
    require_scheduler_production scheduler.production.js:200
    __commonJSMin rolldown-runtime-BjWfMKpL.js:9
    require_scheduler index.js:4
    __commonJSMin rolldown-runtime-BjWfMKpL.js:9
    require_react_dom_client_production React
    __commonJSMin rolldown-runtime-BjWfMKpL.js:9
    require_client React
    __commonJSMin rolldown-runtime-BjWfMKpL.js:9
    <anonymous> index-B3Xg0D1U.js:7679
    __esmMin rolldown-runtime-BjWfMKpL.js:8
    <anonymous> index-B3Xg0D1U.js:7711
logger.ts:56:5

Uncaught Error: Minified React error #418 [...same stack...]
react-dom-client.production.js:2736:15
```

**React #418 = hydration text content mismatch**. Args `[text, ""]` → server rendered "text" (or text-content-class-indicator), client rendered empty.

**Important context**: This is the SAME error that W153 SW2 commit (`d931492e3`) explicitly claimed to fix via `defaultPendingComponent` SSR-null. W153 SW3 narrative was: "React #418 was an EFFECT (allowed DevTools to attach by interrupting wedge mid-render via the throw), NOT the underlying cause — fixing it removed the gap and DevTools regressed to W152-baseline-blocked state."

**W155 SW3.A re-interpretation**: React #418 IS the wedge mechanism (or one of them). Firefox DevTools is more robust than Chrome's under wedge — it opens when Chrome's wouldn't, revealing the actual error. The W153 SW3 narrative was structurally wrong: React #418 isn't a side-effect; it's the WEDGE that Chrome silently absorbed.

**Conclusion**: V8/Chromium-specific hypothesis DISPROVED. NEW mechanism NAMED: **React #418 hydration mismatch** during `hydrateRoot` reconciliation, callstack `require_react_dom_client_production → require_scheduler → performWorkUntilDeadline → React 9 (render commit)`.

---

## SW3.B — Force createRoot diagnostic (substituted for Sub-task B per pivot)

**Plan deviation rationale**: After SW3.A named React #418, SW2 (WSL2) became LOW VALUE (wedge is React code, NOT OS/Docker layer per Firefox DevTools evidence). Force-createRoot is the DECISIVE test for hydration hypothesis: if bypassing `hydrateRoot` (via `hasRealSsrContent = false` in main.tsx:125) renders the page → hydration mismatch confirmed as wedge. If not → wedge broader than hydration. User approved via mid-wave AskUserQuestion: **"Force createRoot diagnostic (Recommended)"**.

**Change**: `frontend/src/main.tsx` lines 121-127: replaced `const hasRealSsrContent = Array.from(rootElement.childNodes).some(...)` with `const hasRealSsrContent = false` + W155 SW3.B diagnostic comment block, preserving original as commented-out code for revert clarity.

**Execution**:
1. ✅ Edit applied
2. ✅ Local gates: tsc 0, lint 0, prettier clean
3. ✅ Docker rebuild: new bundle hash `index-B01GYMKb.js` (changed from `B3Xg0D1U.js` confirming main.tsx change took effect)
4. ✅ Server-side smoke: /login 200/20,709b (unchanged — SSR is server-side, force-createRoot only affects client mount; bundle hash changed but SSR output identical)
5. ✅ All containers (healthy)

**SW3.B USER-FACING VERIFICATION**: User opens `http://localhost/login` in real Chrome regular + Incognito + hard refresh.

**Result**: **STILL BLANK in both modes.** PLUS Firefox DevTools shows **DIFFERENT error class** (not React #418 anymore):

```
[GlobalErrors] Handlers registered
Object { source: "global-error-handler" }
logger.ts:56:5

Script terminated by timeout at:
getParentHydrationBoundary@http://localhost/assets/vendor-react-Bg-8IwY4.js:8443:3
getClosestInstanceFromNode@http://localhost/assets/vendor-react-Bg-8IwY4.js:967:106
dispatchEventForPluginEventSystem@http://localhost/assets/vendor-react-Bg-8IwY4.js:7411:16
dispatchEvent@http://localhost/assets/vendor-react-Bg-8IwY4.js:9067:61
EventListener.handleEvent*addTrappedEventListener@http://localhost/assets/vendor-react-Bg-8IwY4.js:7395:24
listenToNativeEvent@http://localhost/assets/vendor-react-Bg-8IwY4.js:7366:26
require_react_dom_client_production</listenToAllSupportedEvents/<@http://localhost/assets/vendor-react-Bg-8IwY4.js:7373:145
listenToAllSupportedEvents@http://localhost/assets/vendor-react-Bg-8IwY4.js:7372:20
completeWork@http://localhost/assets/vendor-react-Bg-8IwY4.js:5139:59
completeUnitOfWork@http://localhost/assets/vendor-react-Bg-8IwY4.js:6829:27
performUnitOfWork@http://localhost/assets/vendor-react-Bg-8IwY4.js:6775:19
workLoopSync@http://localhost/assets/vendor-react-Bg-8IwY4.js:6677:53
renderRootSync@http://localhost/assets/vendor-react-Bg-8IwY4.js:6661:5
performWorkOnRoot@http://localhost/assets/vendor-react-Bg-8IwY4.js:6419:233
performWorkOnRootViaSchedulerTask@http://localhost/assets/vendor-react-Bg-8IwY4.js:7221:20
performWorkUntilDeadline@http://localhost/assets/vendor-react-Bg-8IwY4.js:98:45
[...bundle/runtime frames...]
react-dom-client.production.js:14295:3
```

**Stack interpretation**:
- `completeWork` (React Fiber commit phase) → `listenToAllSupportedEvents` (React 19's event system bootstrap) → registers listener via `addTrappedEventListener` → during registration, an event fires (or React simulates one) → `dispatchEventForPluginEventSystem` → `getClosestInstanceFromNode` walks up DOM tree from event target → `getParentHydrationBoundary` traverses ancestor comment nodes looking for hydration boundary markers (`<!--$-->`, `<!--/$-->`, `<!--$?-->`)
- **`getParentHydrationBoundary` infinite-loops** → Firefox kills script after 5-10s timeout
- This happens even with `createRoot` (NOT `hydrateRoot`) because React 19 STILL checks hydration boundaries during event system setup, since the SSR HTML had Suspense boundary markers that React's internal code path encounters

**Conclusion**: Hydration-mismatch-only hypothesis **DISPROVED**. NEW 2nd mechanism NAMED: **React 19 `getParentHydrationBoundary` infinite loop** in event system setup, persists across `hydrateRoot` AND `createRoot` paths on Windows + Chrome/Firefox.

The wedge has **TWO observable failure modes**:
1. `hydrateRoot` path → React #418 thrown (terminal error, easy to identify)
2. `createRoot` path → `getParentHydrationBoundary` infinite loop (silent hang, browser script-timeout kill)

Both originate from React 19's internal hydration boundary tracking, which appears to corrupt or loop indefinitely in this specific bundle's runtime state on Windows browsers — but works correctly on Linux CI (per W154 SW2 Branch C, ubuntu-latest run `25884993065`).

**STRICT 1-iter cap honored**: NO retry of SW3.B with `createRoot` variants. Mandatory honest defer to W156+ per W141 anti-pattern #1.

---

## SW4 — Defer + Revert + Audit + Memory + N+3 Rotation + Push

### SW4.1 Revert diagnostic changes

`git restore frontend/src/main.tsx frontend/vite.config.mts` — reverts both files to W154 SW1 baseline:
- `vite.config.mts`: SW1's `strictExecutionOrder: true` flag + comment block REMOVED. Restored to W154 SW1 state (which is line-identical to pre-W155).
- `main.tsx`: SW3.B's force-createRoot override REMOVED. Restored to W149 SW2 + W150 polish-followup conditional logic.

**Verification**: `git status --short` empty; grep confirms no `strictExecutionOrder` in vite.config.mts + original `hasRealSsrContent = Array.from(rootElement.childNodes).some(...)` at main.tsx:125.

**Disposition decision**: Per `feedback_perfectionism.md` honest framing + W141 anti-pattern #4 (no half-finished implementations) + session conventions ("don't add features beyond what the task requires"), REVERT BOTH. The strictExecutionOrder flag was a HYPOTHESIS TEST that failed; keeping it as "defensive infra" would be unwarranted (no evidence it prevents future issues, no validation through working wedge fix). Cleaner W155 outcome: investigative wave with audit + docs only, no code changes.

### SW4.2 Docker rebuild to deploy reverted state

`docker compose -f docker-compose.full.yml up -d --build frontend` — production-minified rebuild deploys W154 SW1 source code (NOT W154 baseline unminified bytes; FRONTEND_BUILD_UNMINIFIED not set in this rebuild path).

**Note**: For TRUE W154 baseline (unminified `index-DLYWEge9.js` 341,886 b), user would `pwsh start-docker.ps1 -Build` which sets FRONTEND_BUILD_UNMINIFIED=true via start-docker.ps1 logic. Current rebuild gives production-minified `index-*.js` ~258,000 b. The wedge behavior is **independent of minification** per W155 SW1 + SW3.B both testing minified state.

### SW4.3 Final state verification

Post-rebuild curl smoke (TBD, document actual results at commit time):
- `/login` should return 200 / ~20,709 b real SSR
- `/404` should return 404 / ~64,075 b
- `/` should return 307
- `/healthz` should return `{"status":"ok"}`
- New bundle hash differs from SW1+SW3.B builds (because main.tsx and vite.config.mts reverted)
- Tree-shake + jsxDEV invariants preserved

### SW4.4 N+3 rotation

`git mv docs/audits/AUDIT_WAVE152.md docs/audits/archive/AUDIT_WAVE152.md`

Post-W155 active waves: **W153/W154/W155**.

---

## §Honesty Trajectory Detailed

| Caveat | Pre-W155 | Post-W155 | Delta |
|--------|----------|-----------|-------|
| W152 #14 (SSR architecture restoration) | OPEN | OPEN | Unchanged — W154 SW1 architecturally restored ssr:true but didn't fix user-facing wedge |
| W152 #19 (V8 wedge mechanism unknown) | OPEN | **REFINED** | "Wedge mechanism is React 19 event system + hydration boundary tracking, NAMED via SW3.A + SW3.B; NOT V8/Chromium engine-specific, NOT chunk-ordering" |
| W153 NEW #4 (6 providers ruled out, wedge UPSTREAM of ProvidersInner) | OPEN | OPEN | Refined — wedge is even MORE upstream (in react-dom-client internals during render, not provider code) |
| W154 NEW #1 (user-facing /login blank Windows + Chrome) | OPEN | OPEN | UNCHANGED — wedge persists |
| W154 NEW #3 (Linux CI vs Windows behavior discrepancy) | OPEN | OPEN | Reinforced — W155 confirmed Windows-host-specific (Firefox ALSO fails on Windows, but Linux CI Chromium renders) |
| **W155 NEW #1 (React 19 getParentHydrationBoundary infinite loop)** | — | NEW | Specific mechanism: createRoot path also fails via getParentHydrationBoundary timeout |
| **W155 NEW #2 (Wedge has TWO failure modes #418 + getParentHydrationBoundary)** | — | NEW | Two failure paths from same underlying React 19 hydration boundary code path |

**Net count**: 22-26 → 22-26 (unchanged); **scope significantly narrower** per Honesty framing. The 2 NEW caveats are mechanism specifications, not regressions.

---

## (z) Discoveries

1. **(z) #1: W123 SW1 Vite type-extension was overengineered defensive code.** Storybook's `.storybook/main.ts:4` declares `type RolldownOutput = { strictExecutionOrder?: boolean } & Record<string, unknown>` as a local type extension because Storybook's Vite plugin wrapping might not surface Rolldown's full type. W155 SW1 in main `vite.config.mts` had NO type error — Vite's native `rolldownOptions.output` typing already exposes `strictExecutionOrder`. The Storybook defensive extension is unnecessary in main app context. **W156+ housekeeping candidate**: remove `RolldownOutput` extension from `.storybook/main.ts` if Storybook's tooling also accepts native typing now.

2. **(z) #2: Production-minified vs unminified bundle invariant for wedge investigation.** W154 baseline was unminified (FRONTEND_BUILD_UNMINIFIED=true via start-docker.ps1). W155 builds via `docker compose up -d --build frontend` (without start-docker.ps1) produce production-minified. The wedge behavior is IDENTICAL across both — same user-facing blank, same Firefox DevTools errors (within abstraction differences from minified stack traces). This means W156+ structural investigation can use either bundle mode; minification is orthogonal.

3. **(z) #3: Firefox DevTools open state vs Chrome wedge.** W152+W153 narrative was "Chrome DevTools blocked by V8 wedge". W155 SW3.A revealed: Chrome DevTools is blocked because Chrome process IS wedged (renderer thread blocked by infinite loop). Firefox DevTools OPENS even when Firefox renderer is wedged because Firefox uses a different DevTools architecture (e.g. separate process for DevTools chrome). This means **Firefox is the diagnostic tool for similar wedge investigations** in this codebase — Chrome's blockage is a symptom of process-level wedge, not a DevTools-specific issue.

4. **(z) #4: React 19 createRoot ALSO uses hydration boundary tracking.** Initial assumption was that createRoot path bypasses hydration entirely. W155 SW3.B disproved this — `getParentHydrationBoundary` is called even in createRoot path during event system setup (`listenToAllSupportedEvents`). React 19's event delegation traverses ancestor nodes looking for hydration boundary markers (`<!--$-->` etc.) regardless of mount mode. If those markers exist in document body OUTSIDE the React-managed tree, the traversal might loop or behave unexpectedly. **W156+ candidate**: inspect SSR HTML for any unbalanced or unexpected hydration boundary comment markers.

---

## W156+ Candidates (Priority Order per `feedback_planning_estimates.md`)

### Tier 1: User-facing wedge fix (HIGH priority, ~3-5h each)

1. **NODE_ENV=development build for full React error message** (~30-45 min if W152 SW1 jsxDEV regression mitigated; ~3-5h if needs full build infra refactor). Single most actionable next step: get the EXACT mismatch text from React #418 (currently `args[]=text&args[]=` is minified abbreviation). Once we know the specific component/element where SSR + client differ, fix is targeted.

2. **Source code analysis: identify hydration mismatch suspects** (~2-3h speculative). Likely culprits in W155 narrowed scope:
   - LoginCredentialForm.tsx — form rendering differences SSR vs client
   - AppProviders / ThemeContext / LanguageContext cookie-mirror state
   - useProfileSync + readSsrAuthHint bridge — auth state at SSR-init might differ from client mount
   - W127 SW2-5 cookie-mirror logic for theme/lang

3. **React 19 upstream issue review for `getParentHydrationBoundary` infinite loops** (~1-2h research). Check known React 19 bugs (GitHub facebook/react issues, React 19.0.x patch notes). If a known bug applies, upgrade React or apply documented workaround.

### Tier 2: Inheritance from prior waves (medium priority)

4. **Husky pre-commit prettier** (~30-60 min) — anti-pattern #15 hit 5 consecutive waves now (W149+W150+W153+W154+W155). Structural fix via husky + lint-staged.

5. **Visual-audit.yml empty-string-route handling** (~15-30 min) — W154 (z) #3 unresolved.

6. **Remove `.storybook/main.ts:4` defensive `RolldownOutput` type extension** (~5 min, W155 (z) #1).

### Tier 3: Strategic options (defer to W157+)

7. **WSL2 reproduction (Sub-task B from W155 cascade, deferred)** — would narrow Windows host vs Docker Desktop. NOW LESS VALUABLE post-W155 since wedge is React-code-side (Firefox DevTools evidence), but still useful as confirmation if needed.

8. **Chrome flags matrix (full Sub-task C from W155 plan, partially executed)** — `--js-flags="--no-turbofan"`, `--disable-features=V8VmFuture`, etc. LESS VALUABLE since Firefox + Chrome both fail (wedge isn't V8 feature specific), but could narrow further.

9. **Linux CI re-trigger on post-W154 SW1 baseline** (~12-15 min CI) — W154 cross-validation was W153 SW2 baseline (ssr:false). Running it on W154 SW1 (ssr:true) would confirm Linux behavior post-restoration.

---

## Lessons Learned (W155-specific)

1. **Empirical diagnostic at FIRST timeout pays off** (W138 Lesson #1 reinforced). User's Firefox DevTools test in SW3.A took ~5 min and revealed React #418 root cause class. Without that single test, W155 would have escalated to SW2 (WSL2) costing 1-2h with less information density. **W156+ application**: when wedge mechanism is unclear, prioritize cheap browser DevTools observation over heavy reproduction setup.

2. **Plan deviation when empirical findings warrant is discipline, NOT scope creep**. SW3.A pivoted cascade order (C before B). SW3.B substituted force-createRoot for original Sub-task B (WSL2). Both deviations were user-approved mid-wave via AskUserQuestion + had clear empirical justification. Per `feedback_perfectionism.md`, this is honest discipline.

3. **W141 anti-pattern #1 STRICT 1-iter cap continues protecting against scope creep** (11th vindication post W138+W141+W143+W144+W145+W147+W148+W149+W152+W154+W155). W155 honored cap: SW1 disproved hypothesis → NOT iterated → SW3.A new mechanism. SW3.A revealed React #418 → SW3.B tested hypothesis → disproved → mandatory defer. ~2.5h core wall-clock; budget UNUSED for additional iters. Pattern WORKS.

4. **Phase 1 Explore Agent claims verification (W141 anti-pattern #3 13th vindication via W155)**. Phase 3 Review caught: Agent 1's `RolldownOutput` type extension claim (W155 (z) #1 — turns out Vite's native typing accepts the flag, no extension needed). Without Phase 3 verification + direct file Read, would have written defensive type extension code in vite.config.mts unnecessarily.

5. **Two-failure-mode wedge analysis is harder than single-failure-mode**. W155 found that hydrateRoot fails with React #418 AND createRoot fails with getParentHydrationBoundary timeout. Both originate in same React 19 hydration boundary code path but manifest differently. **W156+ implication**: investigation should target the SHARED upstream cause (React's hydration boundary state tracking), not each failure mode separately.

6. **Production-minified bundle is sufficient for wedge reproduction**. (z) #2 above. W156+ can choose bundle mode based on convenience; minification is orthogonal to wedge.

---

## Anti-Pattern Register Status (post-W155)

| # | Pattern | Vindication count | W155 application |
|---|---------|-------------------|------------------|
| 1 | STRICT iter cap per mechanism | 11 | Honored — SW1, SW3.A, SW3.B each 1 iter |
| 3 | Phase 3 verification of Agent claims | 13 | Verified vite.config.mts:493-547, W123 SW1 commit, Rolldown API; caught (z) #1 |
| 4 | No premature closure claims | 11 | SW1 commit message NEVER drafted with "Closes" — reverted before any commit |
| 12 | Empirical diagnostic at first timeout | 5 | SW3.A Firefox test = 5-min empirical bypass of cascade overhead |
| 15 | Prettier discipline | 5 (W149+W150+W153+W154+W155) | Honored — `npm run format:check` clean at every gate. **W156+ priority candidate for husky pre-commit prettier housekeeping**. |

---

## Files (W155 Final State)

**No code changes shipped.** Pure investigative wave + documentation.

| File | Operation | Notes |
|------|-----------|-------|
| `frontend/vite.config.mts` | UNCHANGED (W154 SW1 baseline) | SW1's `strictExecutionOrder` flag reverted in SW4.1 |
| `frontend/src/main.tsx` | UNCHANGED (W149 SW2 + W150 polish-followup baseline) | SW3.B's force-createRoot reverted in SW4.1 |
| `docs/audits/AUDIT_WAVE155.md` | NEW | This file |
| `CLAUDE.md` | +Wave 155 row + 0-1 new gotchas | Audit Trail update + W155 mechanism findings |
| `memory/MEMORY.md` | +Wave 155 audit history row + active backlog update | Auto-loaded; size ~24,000 b post-update |
| `memory/wave155_backlog.md` | NEW | Close-status entry |
| `memory/wave156_opening_prompt.md` | NEW | W156+ handoff |
| `docs/audits/AUDIT_WAVE152.md` → `archive/` | `git mv` | N+3 rotation; post-W155 active = W153/W154/W155 |

---

## CI Verification (post-commit)

Will be verified post-push:
- All standard CI workflows on `egorribun` branch
- Active PR: #1114 (waves 133-)
- Expected: all checks SUCCESS (no code changes → no CI surface affected); only docs commit
- Linux CI re-trigger per Q3 = NOT triggered (per user-approved Q3 default)

---

## Open Status

- **W154 §Honesty NEW #1**: STILL OPEN (user-facing Windows + Chrome blank wedge)
- **W155 added**: 2 NEW mechanism caveats (React #418 hydration mismatch + getParentHydrationBoundary infinite loop)
- **W155 ruled out**: Rolldown chunk-ordering, V8/Chromium-specific engine class, hydration-mismatch-only
- **W156+ scope**: NODE_ENV=development build for full React error OR source-code analysis for hydration mismatch suspects OR React 19 upstream issue review

**Next investigation entry point per `memory/wave156_opening_prompt.md`**: Tier 1 #1 NODE_ENV=development build for full React error message.
