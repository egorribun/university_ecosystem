# AUDIT_WAVE152.md

**Wave 152 — Tier 1 SSR root-cause investigation (HONEST DEFERRAL)**

- **Branch**: `egorribun`
- **HEAD start**: `6dd3db76b` (W150 polish-followup-v2-polish-v1)
- **HEAD end**: `0f60c5de8` (W152 Phase 1.6 + 1.7 + 1.8 negative-result)
- **User-approved scope** (2026-05-14 AskUserQuestion):
  - **Q0**: User confirmed `/login` STILL blank in BOTH real Chrome + fresh Incognito (CONFIRMED PERSISTENT)
  - **Q1**: Tier 1 SSR root-cause + restore production SSR (~3-5h)
  - **Q2**: Phase 0 Empirical via `cd frontend && npm run dev` FIRST
  - **Q3**: Open-ended absorption (12th consecutive wave with this pattern)

---

## TL;DR (1 paragraph)

**W152 reached iter 5 of Phase 1 fixes — all structural improvements aligned with W125 design doc + best practices — but the user-facing `/login` blank PERSISTED across every attempted fix.** Phase 0 Empirical via `npm run dev` (W152 Q2) successfully exposed the unminified React error (Hydration mismatch at `<Matches><Suspense fallback={null}>`) which W150 polish-followup-v2's production-minified bundle had hidden, but this dev-mode error proved to be a SEPARATE problem from the production wedge (production correctly takes createRoot path per `<div id="root"><!--$--><!--/$--></div>` shell). **Phase 1 commit `4af884616`** (App.tsx Suspense removal + router.ts `defaultPendingComponent`) + **Phase 1.6+1.7+1.8 commit `0f60c5de8`** (sync `.ready` class + StartClient adoption + IDB-hydration negative-result revert) shipped 4 clean structural improvements. The production-side wedge (Chrome DevTools cannot even OPEN on `/login`, indicating V8 main thread fully wedged in sync code) was NOT root-caused — diagnostic tools failed (chrome-devtools-mcp profile-locked, Playwright CDP-backchannel timeouts, even DevTools panel can't initialize on the wedged renderer). **Per W141 anti-pattern #1 (2-3 iter cap on SW, honest defer at iter 4) + W138 Lesson #1 (5-min diagnostic over mechanism pivot)**: this wave HONESTLY DEFERS the user-facing scope to W153+ with explicit narrowing candidates documented below.

---

## Phase 0 Empirical findings (SUCCESS — exposed dev-mode bug)

**SW1** (Vite dev server launched on `:5173`):
- `npm run dev` ready in 1.4s
- `curl http://localhost:5173/login` returns 200 with 7,414 bytes
- Backend `127.0.0.1:8000` reachable directly (vite proxy ready)

**SW2** (Playwright navigation to dev `/login` + Phase 1 Explore agents):
- **React unminified error captured**: `Error: Hydration failed because the server rendered HTML didn't match the client.`
  - Component stack: `<App> + <Suspense> - <div className="flex min-h-dvh flex-col">`
- **Plus**: `Error: In HTML, <div> cannot be a child of <html>` (consequence of the hydration mismatch)
- **Plus**: `Failed to fetch current user CancelledError` (consequence of React aborting hydration → /users/me request cancelled)

**SW3** (Hypothesis narrowing):
- ❌ **H1 (useId reconciliation) DISPROVED**: 0 `useId()` callsites anywhere in `frontend/src/` (Phase 1 Explore Agent 1 grep)
- ❌ **H5 (CSP nonce SSR/client mismatch) DISPROVED**: Production HTML has NO `Content-Security-Policy` header (verified via `curl -I`); nonces never injected
- ❌ **H6 (sync-throw at module init) UNLIKELY**: Would surface as console error; user reports only `[GlobalErrors] Handlers registered`
- ✅ **H-Suspend (App.tsx:24 indefinite suspension) IDENTIFIED**: confirmed via dev mode error stack — server emits route tree directly into `<div id="root">`, client added Suspense markers from App-level wrapper

**KEY DEV-vs-PROD DIVERGENCE** (critical realization mid-wave):
- **Dev mode** (`npm run dev`): server SSRs routes despite `ssr: false` (manifest shows `ssr:!0` in dev output); main.tsx takes hydrateRoot path; hydration mismatch fires.
- **Production** (Caddy → Node SSR): correctly respects `ssr: false` (manifest shows `ssr:!1`); `<div id="root"><!--$--><!--/$--></div>` (only comment markers); main.tsx takes createRoot path; NO hydration; NO mismatch error in user's console (consistent with their report).

**Implication**: dev-mode hydration error is dev-only and DOES NOT explain user's production blank. They share App-level Suspense as a STRUCTURAL issue, but the actual user-facing wedge has a DIFFERENT cause.

---

## SW commits shipped

### Phase 1 — commit [4af884616](https://github.com/egorribun/university_ecosystem/commit/4af884616)

`fix(wave152-phase1-suspense-fallback): App.tsx Suspense removal + router defaultPendingComponent`

**File changes** (2 files, +55/-6):
1. [`frontend/src/App.tsx`](frontend/src/App.tsx) — Removed outer `<Suspense>` wrapper around `<RouterProvider>` (was redundant — TanStack Router has internal Suspense for lazy routes; the outer wrapper had no `fallback` prop, defaulting to null = silent blank on suspend per W150 polish-followup hypothesis #7).
2. [`frontend/src/router.ts`](frontend/src/router.ts) — Added `defaultPendingMs: 0` + `defaultPendingComponent: () => <div>Loading…</div>` (visible fallback for TanStack Router's INTERNAL `<Matches><Suspense fallback={null}>` so indefinite suspension becomes observable instead of silent blank).

### Phase 1.6+1.7+1.8 — commit [0f60c5de8](https://github.com/egorribun/university_ecosystem/commit/0f60c5de8)

`fix(wave152-phase1.6+1.7): StartClient adoption + sync .ready + Phase 1.8 IDB strip negative result`

**File changes** (3 files, +57/-9):
1. [`frontend/src/main.tsx`](frontend/src/main.tsx) — Apply `.ready` class to `<div id="root">` SYNCHRONOUSLY after `createRoot.render()` (was rAF×2; if reconciler wedges, rAF never fires → `.ready` never added → `#root opacity: 0` invisible regardless of committed content).
2. [`frontend/src/App.tsx`](frontend/src/App.tsx) — Adopted TanStack Start v1's official `<StartClient />` client entry per the W125 design doc deferral ("Phase 3 (W126+) may switch to `<StartClient />`"). `<StartClient />` internally calls `hydrateStart()` which aligns client router state with the SSR-emitted TSR stream (`self.$_TSR.router = ...`).
3. [`frontend/src/routes/__root.tsx`](frontend/src/routes/__root.tsx) — Recorded the Phase 1.8 IDB-hydration diagnostic SWAP as a comment block. The swap (vanilla `<QueryClientProvider>` instead of `<PersistQueryClientProvider>`) was applied, user-tested in real Chrome, and reverted after returning NEGATIVE result (user-facing /login STILL blank, IDB hydration is NOT the wedge cause).

---

## Verification matrix

| Check | Status | Notes |
|------|--------|-------|
| `npx tsc --noEmit` | ✅ 0 errors | Each SW after every edit |
| `npx eslint --max-warnings=0` | ✅ 0 warnings | Across modified files |
| `npm run format:check` | ✅ Clean | Canonical CI scope (anti-pattern #15 prevention via routeTree.gen.ts prettier-write) |
| `AuthContext.bridge.test.tsx` (vitest canary) | ✅ 4p / 0f / 252ms | W134 SW1 bridge contract preserved |
| Docker build × 5 cycles (Phase 1 → 1.5 → 1.6 → 1.7 → 1.8 → revert) | ✅ Each completed exit 0 | Image rebuilt 5× during wave |
| Frontend container `(healthy)` after each rebuild | ✅ × 5 | `docker ps` confirms |
| `curl http://localhost/healthz` | ✅ "ok" | Node SSR healthy |
| `curl http://localhost/login` | ✅ HTTP 200 / 10,874 b | Server delivers shell + bundle hash references update per build |
| `curl http://localhost/api/v1/users/me` via Caddy | ✅ 401 in 4 ms | Backend chain healthy |
| User real-Chrome `/login` render (canonical close criterion) | ❌ **NOT CLOSED** | User reports STILL completely blank, DevTools won't open, across all 5 fix iterations |
| User Incognito `/login` render | ❌ **NOT CLOSED** | Implied by pre-W152 baseline (user reports both blank persistently) |

---

## §Honesty probe

**Following `feedback_perfectionism.md` discipline + W141 anti-pattern #4 (never claim closure pre-verification) + W138 Lesson #1 (5-min diagnostic over mechanism pivot at iter 4) + the W150 polish-followup-v2 Iron Law of verify-before-claim.**

### Closed (0 caveats)

NONE. The W150 polish-followup-v2 user-facing scope (§Honesty caveats #14 + #16 + #20) is **NOT closed** by W152.

### CARRY-FORWARD from W150 polish-followup-v2 (unchanged)

1. **§Honesty #14**: `__root.tsx ssr: false` dev fallback (load-bearing user-facing). Production deploys still need `ssr: true` restoration after root-cause identification.
2. **§Honesty #15**: `DEV_NO_SSR_SHELL=1` dev compose hack still present in docker-compose.full.yml:129 + frontend.Dockerfile.
3. **§Honesty #16 (refined)**: SW NetworkFirst stall on `/users/me` was mitigated structurally by W150 polish-followup-v2 `a26d1e7da` but NOT the user-facing blank-screen blocker.
4. **§Honesty #17**: `api/client.ts` runtime SSR detection brittleness (still present).
5. **§Honesty #18**: `__root.tsx` THEME_INIT_SCRIPT defaults all browsers to Russian (UX regression for first-visit English users).
6. **§Honesty #19**: Hydration mismatch / sync-throw / V8-wedge root cause still NOT identified. **W152 Phase 0 narrowed the dev-mode component but the production wedge is different**.
7. **§Honesty #20**: User-side verification of W150 polish-followup-v2 + W152 Phase 1.x fixes: BLANK across all iterations.
8. **§Honesty #21**: `a26d1e7da` commit message permanent over-claim (historical record only).

### NEW W152-introduced honest caveats (4)

9. **W152 §Honesty NEW #1**: **Phase 0 Empirical confirmed dev-mode hydration error but DID NOT identify the production wedge cause.** They share App.tsx Suspense as one structural issue, but production takes createRoot path (no hydration). The production wedge persists with ALL of: App.tsx Suspense removed, `<StartClient />` adopted, `defaultPendingComponent` set, `.ready` class synchronous, PersistQueryClientProvider replaced (diagnostic, reverted). Root cause still unknown.

10. **W152 §Honesty NEW #2**: **Diagnostic tooling failure on Windows-Chrome wedged renderer**. chrome-devtools-mcp profile-locked (cannot open new pages even with `isolatedContext`). Playwright MCP times out on `domcontentloaded` and on console-message retrieval (CDP backchannel saturation). The Claude Preview tool was usable on `npm run dev` (showed dev hydration error) but cannot test the production Caddy → Docker → Node SSR chain. **DevTools panel cannot OPEN on the wedged production renderer** (per user report) — strongest signal of synchronous V8 wedge but blocks all in-browser diagnostic paths.

11. **W152 §Honesty NEW #3**: **Phase 1.5 `defaultPendingComponent` fallback never observed**. User reported NO "Loading…" text visible on the wedged production page. Either (a) the wedge is BEFORE React reaches `<Matches>` Suspense (module init OR provider chain init synchronous), OR (b) React renders the fallback but `#root opacity: 0` makes it invisible (mitigated by Phase 1.6 sync `.ready` — but if reconciler wedges synchronously, the sync `.classList.add("ready")` line never executes either). The two hypotheses are indistinguishable without working DevTools.

12. **W152 §Honesty NEW #4**: **Phase 1.8 IDB-hydration negative result is a load-bearing diagnostic recording**. Future waves must NOT re-test this hypothesis without reading this audit + Phase 1.8 inline comments in __root.tsx.

### NOT counted as caveats but worth noting

- **Anti-pattern #15** (prettier polish-v1 recurring): proactively prevented this wave via `routeTree.gen.ts` prettier-write before each commit + `npm run format:check` (canonical CI scope, not narrower `src/**/*`).
- **routeTree.gen.ts** auto-regeneration: fired 4× this wave (each `tsc --noEmit` triggers it); manually prettier-fixed each time.
- **N+3 rotation**: W149 → archive scheduled but NOT executed in W152 SW0 (debug-first session focus); rotate in W153 SW0.

---

## W153+ candidates (ordered by recommendation strength)

### Tier 1 — Pre-existing user-facing /login blank closure (~3-6h, multiple branches)

**(a) Component-strip continuation** — Continue Phase 1.8-style binary diagnostics on remaining suspect providers:
   - `<WebSocketProvider>` in AppProviders chain (might have sync WS init issue)
   - `<MessengerProvider>` (depends on auth + WS state)
   - `<AuthProvider>`'s `useProfileSync` (might have render loop on auth state changes)
   - `<MainLayout>` (heaviest DOM; navbar + footer + bottom nav)

**(b) Pre-W150-polish-followup bisect** — Identify which commit introduced the wedge by reverting commits one-at-a-time + testing. Likely candidates: W149 SW2 (hydrateRoot adoption), W134 SW1 (Bridge mechanism), W128 SW3 (per-request QueryClient), W127 SW1 (provider hoist), W125 Phase 2 (tanstackStart migration).

**(c) NODE_ENV=development Docker build support** — Patch [`frontend/scripts/build-orchestrated.mjs`](frontend/scripts/build-orchestrated.mjs) to support `NODE_ENV=development` env propagation (currently hardcodes `MODE="production"`). Would enable Phase 0 Approach B (NODE_ENV=development Docker build) which is currently a NO-OP per W152 plan §"Build-system limitation discovered". ~30-60 min focused.

**(d) Cross-OS test** — Run the same Docker stack on a Linux host (CI runner or remote box) + test `/login` in headless Chrome via xvfb or Linux Chrome native. If Linux works but Windows wedges, it's a Windows-Chrome-specific issue. If Linux also wedges, code-level bug confirmed.

### Tier 2 — Housekeeping (~1-2h)

**(e) Husky pre-commit prettier hook** — anti-pattern #15 hit 3rd consecutive time (W149 + W150 + W150 polish-followup-v2 polish-v1). W152 prevented it this wave via manual prettier-write but the structural fix is automating via husky + lint-staged.

**(f) N+3 rotation** — `git mv docs/audits/AUDIT_WAVE149.md docs/audits/archive/`. Active waves becomes W150/W151-skipped/W152 → W150/W152/W153 once W153 opens.

**(g) Backend `test_login_lockout` flake** — W149 §Honesty #6 still open.

### Tier 3 — Per-page polish carry-forwards (~2-3h each)

- features/admin/ folder migration (W150 §Honesty #7, queued since W151+)
- StoriesAdmin substantive polish (705 LoC, own wave per W150 §Honesty #8)
- TanStack Query factories for 4 admin pages (W150 §Honesty #9)

---

## Anti-pattern register hits this wave

- **#1 (2-3 iter cap on SW, honest defer at iter 4)**: REACHED iter 5 of Phase 1, applied honest defer at iter 5 with explicit reasoning + W153+ next steps documented.
- **#3 (NONUPLE-vindicated: empirical verification BEFORE structural change)**: Phase 0 Empirical executed FIRST per W152 plan; correctly disproved 3 of 10 hypotheses + identified H-Suspend at App level as load-bearing for dev mode.
- **#4 (don't claim closure pre-implementation)**: Both W152 commits (`4af884616` + `0f60c5de8`) explicitly state "NOT a Closes §Honesty #X commit" + record what's structurally improved vs what's not closed.
- **#11 (Empirical diagnostic over mechanism iteration)**: Mixed result — Phase 0 was empirical-first ✅; Phase 1.6→1.7→1.8 became mechanism iteration ❌. Per W138 Lesson #1, should have stopped at iter 3 to add stronger diagnostic instead of pivot.
- **#15 (prettier polish-v1 recurring)**: PROACTIVELY PREVENTED this wave via routeTree.gen.ts prettier-write + npm run format:check.
- **#16 candidate (workbox NetworkFirst on auth-state-critical endpoints stalls indefinitely)**: NOT triggered this wave; W150 polish-followup-v2's structural fix held.

---

## Build × N reproducibility

Docker frontend image rebuilt **5 times** during wave (Phase 1 + 1.6 + 1.7 + 1.8 swap + 1.8 revert), each exit 0. Build product hash changes each rebuild (per W141 polish A3 strengthened invariant honesty framing — build is not byte-deterministic post-_shell.html postbuild step). Bundle main JS hash progression observable in production HTML modulepreload links.

---

## Bundle delta

| Build | Main JS hash | Phase changes |
|-------|--------------|---------------|
| W150 polish-followup-v2 (HEAD before W152) | `index-DfyirCI7.js` 140,217 b | baseline |
| Post Phase 1 (4af884616 Docker) | `index-pSXtDSgu.js` ~141 KB | App.tsx Suspense removed + router defaultPendingComponent |
| Post Phase 1.7 (StartClient) | DIFFERENT hash | App.tsx now `<StartClient />` |
| Post Phase 1.8 (IDB strip — REVERTED) | reverted | matches current HEAD |
| Final W152 (0f60c5de8) | per current Docker build | sync .ready + StartClient + PersistQueryClientProvider restored |

---

## Closing framing

**W152 is a HONEST DEFER wave.** It shipped 4 clean structural improvements (each individually defensible against W125 design doc OR best practices) but the user-facing /login blank PERSISTED. The Iron Law of verify-before-claim (W141 anti-pattern #4 + W150 polish-followup-v2 lesson) applied at every commit — no "Closes §Honesty #X" claim shipped. Phase 0 Empirical's success (exposing dev-mode React error in <10 seconds) was negated by production diverging in code path (createRoot vs hydrateRoot). Per `feedback_perfectionism.md`, scoping wins over premature closure: 4 structural improvements + 4 NEW honest caveats + 8 carry-forward caveats from W150 polish-followup-v2 + clear W153+ candidate list = honest wave outcome.

**W153 must pivot strategy** — continuing mechanism iteration in Phase 1 form is unlikely to close the bug without different diagnostic tooling OR structural attempt (component-strip on more providers, cross-OS verification, OR pre-W150-polish-followup bisect).
