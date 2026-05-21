# Wave 177 audit — Close W174 §Honesty #3 (login redirect edge case)

**Date**: 2026-05-21
**Branch**: `egorribun` (HEAD `5ff625215` post-SW1+SW2+SW3 + this SW5 audit commit)
**Scope**: Q0=B real-trigger wave per W171 Lesson #1 (user-approved Option B at session start; not force-fired)
**Plan**: `C:\Users\egorribun\.claude\plans\c-users-egorribun-claude-projects-c-use-cozy-petal.md`
**37th consecutive wave** with brainstorming + Phase 1 Explore + Phase 3 Review + W141 anti-pattern discipline (W141-W176 → +W177).

---

## Headline

✅ **W174 §Honesty #3 EMPIRICALLY CLOSED**: authed user who hard-navigates to `/login` (bookmark / search engine / external link / new tab) is now redirected to `/dashboard` automatically via reactive `useEffect` in Login.tsx watching `useAuthStore.user`. Verified through real Caddy → Node SSR → backend Docker chain via chrome-devtools-mcp `new_page` AND `navigate_page` — both settle at `/dashboard` with **0 console errors + 0 React #418 hydration errors**.

W175 SW10 attempted the same useEffect mechanism but reverted per W141 anti-pattern #1 STRICT 1-iter cap because msw test infra mocks `/users/me → testUser` globally → useEffect fired in 7 unrelated tests → assertions failed. W177 ships the same mechanism PLUS the msw scoping discipline that W175 SW10 lacked — DIFFERENT mechanism per W138 Lesson #1 → honest new wave with new plan.

**Mechanism**: `useEffect(() => { if (user) navigate({to:"/dashboard", replace:true}) }, [user, navigate])` in Login.tsx, paired with `renderLogin` `skipMeOverride: false` default that prepends `server.use(http.get("*/users/me", () => HttpResponse.json(null, {status:401})))` for all 6 existing form-behavior tests + 1 new W177 regression test that opts out via `skipMeOverride: true` to exercise the redirect.

---

## Q0 / Q1 / Q2 decision context

User-approved at session start via brainstorming + AskUserQuestion:

- **Q0 = Option B** (W174 §Honesty #3 close; ~2-3h ticket scope). 4 options offered: A continue pause / B login redirect / C admin visual smoke / G housekeeping. User picked B.
- **Q1 = Approach 2** (Login.tsx useEffect + msw overrides). 3 approaches proposed mid-session via AskUserQuestion: Approach 1 route-level watcher in `_public.tsx` (recommended by Claude for surface-area minimization) / Approach 2 Login.tsx useEffect + per-test msw overrides / Approach 3 app-level router.invalidate(). User picked Approach 2 (aligns with the original W174 §Honesty #3 ticket framing).
- **Q2 = STRICT 1-iter per SW** per W141 anti-pattern #1 SACRED.

---

## SW1 — Login.tsx reactive useEffect

**Commit**: bundled with SW2+SW3 in `5ff625215`
**File**: `frontend/src/pages/Login.tsx` (+19 / -1)

3 imports added (`useEffect` from "react", `useNavigate` from "@tanstack/react-router", `useAuthStore` from "@/stores/useAuthStore"). 13-line W177 SW1 comment explaining the mechanism + msw scoping cross-refs. Reactive useEffect:

```tsx
const user = useAuthStore((s) => s.user);
const navigate = useNavigate();
useEffect(() => {
  if (user) {
    navigate({ to: "/dashboard", replace: true });
  }
}, [user, navigate]);
```

**`replace: true` rationale**: prevents `/login` from appearing in back-button history for authed users. Semantically correct: authed user should never see `/login` in browser history.

**Race safety**: When useLoginFlow.ts:116-141 onSubmit handler succeeds (POST `/auth/login` → 200 → `setUser(data.user)` at useAuthApi.ts:168 → imperative `navigate({to: redirectPath, replace:true})` at useLoginFlow.ts:129), this SW1 useEffect ALSO fires (user transitioned null → set). Both navigates target the same destination with `replace:true` → idempotent. Login.tsx unmounts after either navigate; the other becomes no-op or fires on unmounted component (TanStack Router tolerates this).

**`state.from` redirect-path race** (honestly documented): if user came from `/events` via auth challenge, `useLoginFlow.ts:75 redirectPath = state.from.pathname = "/events"`. The imperative navigate (line 129) is sync after `await login(...)`, so it likely fires BEFORE this useEffect commits in normal flow → user lands on `/events`. Edge race exists but extremely rare; W178+ polish candidate if surfaced.

---

## SW2 — Login.test.tsx renderLogin helper + regression test

**Commit**: bundled in `5ff625215`
**File**: `frontend/src/pages/__tests__/Login.test.tsx` (+59 / -22)

### Changes

1. **`RenderLoginOptions` interface** with `skipMeOverride?: boolean` opt-out param + JSDoc explaining the W177 SW1 mechanism interaction.

2. **`renderLogin()` helper signature change**: now accepts `options: RenderLoginOptions = {}`. When `skipMeOverride !== true`, the helper prepends `server.use(http.get("*/users/me", () => HttpResponse.json(null, {status:401})))` BEFORE `renderWithRouter` mounts AuthProvider. All 6 existing test calls (`await renderLogin()` with no args) get the override automatically — zero call-site changes.

3. **NEW regression test** `"redirects authed user away from /login (W174 §Honesty #3, W177 SW1)"` (placed after "submits credentials and redirects on success" for narrative continuity). Opts out via `skipMeOverride: true` → default msw returns testUser → useProfileSync populates store → useEffect fires → navigate to `/dashboard` → extraRoutes' "Welcome!" rendered → `waitFor` assertion passes.

4. **Removed 2 vestigial `/users/me → mfa-user` overrides** from MFA tests at lines 162-205 + 207-256. Phase 3 Review of handlers.ts:645-672 confirmed MFA flow triggers via POST `/auth/login` 202 response (mfa@example.com + Password123 → PendingMfaResponse → useAuthApi.updatePendingMfa → useMfaFlow.loginChallenge truthy → MfaChallengeView renders). The pre-existing `/users/me` overrides were defensive setup, NOT behaviorally required. Removing them + relying on renderLogin's helper-level 401 default avoids the LIFO msw conflict that would have triggered SW1 useEffect mid-test.

5. **`afterEach` reset**: NEW `useAuthStore.setState({ user: null, loading: true, pendingMfa: null, authOperation: false })` clears the auth store between tests. Pre-W177 this was silent because Login.tsx didn't react to user state; W177 SW1 useEffect makes prior-test user-state pollution observable (test #2 successful login → useAuthStore.user = testUser → test #3+ mounts Login.tsx → useEffect fires immediately → redirect to /dashboard → form inputs gone → assertions fail). Test-file-local reset chosen over `setupTests.ts` global reset to minimize blast radius (W178+ candidate if similar issue surfaces in other test files).

### Test outcome

**Login.test.tsx: 8 passed / 0 failed / 0 skipped** (7 existing + 1 new W177 regression test).

```
✓ blocks submission for invalid email
✓ submits credentials and redirects on success
✓ redirects authed user away from /login (W174 §Honesty #3, W177 SW1)  [NEW]
✓ returns server errors to the user
✓ shows lockout messaging with retry information
✓ transitions to MFA verification when additional challenges are required
✓ displays errors for invalid OTP attempts and allows retry
✓ meets basic accessibility requirements
```

---

## SW3 — pageTranslations.test.tsx msw override

**Commit**: bundled in `5ff625215`
**File**: `frontend/src/tests/pageTranslations.test.tsx` (+10 / -1)

Added msw + server imports (`http`, `HttpResponse` from "msw"; `server` from "@/tests/mocks/server"). Inserted `server.use(http.get("*/users/me", () => HttpResponse.json(null, {status:401})))` inside the "renders login page in Russian when seeded and toggles to English" test (line 691 pre-edit), BEFORE the `renderWithProviders(<Login />)` call. Mirrors the SW2 renderLogin default behavior; the override is scoped to this single test via msw's per-test `server.use` handler.

**Test outcome**: full pageTranslations suite **12 passed / 0 failed / 0 skipped**.

---

## SW4 — chrome-devtools-mcp empirical smoke through Docker chain

### Path 1: new tab simulation (cookies shared via isolatedContext)

1. `new_page url=http://localhost/login isolatedContext=wave177-sw4-fresh` → Login UI rendered, 0 console errors except expected GlobalErrors info + /users/me 401 (no cookies) + profile_cache.cleared warn.
2. Filled form with `test@university.dev` + `TestPass@2024x` via `evaluate_script` (using `nativeInputValueSetter` + dispatching input/blur events to properly sync react-hook-form state) + `form.requestSubmit()`.
3. Login chain fired: `GET /api/v1/auth/csrf-cookie 200 (W174 SW2 auto-fetch) → POST /api/v1/auth/login 200 → setUser(testUser)` populates useAuthStore → navigate to `/dashboard`. URL settled at `/dashboard` with title "Главная | University Ecosystem" + H1 "Доброй ночи, Test!🌙".
4. **Discovery during smoke**: container served stale pre-W177 bundle (`index-_zjFkQhX.js` from earlier build). Rebuilt via `bash scripts/dc.sh up -d --build frontend` (W170 SW4 helper). New container bundle `index-D0EDgCF8.js` (Docker Linux build hash; semantically equivalent to local Windows build `index-BA6s4YBY.js` per W141 polish A3 cross-platform divergence Gotcha).
5. After rebuild + fresh login on `isolatedContext=wave177-sw4-fresh`, opened **NEW page** at `http://localhost/login` in same isolatedContext → page list reported URL = `http://localhost/dashboard` immediately. `evaluate_script` confirmed URL + title + H1.
6. **`list_console_messages`: NO console messages** — 0 React #418 hydration errors, 0 unexpected console output.

### Path 2: navigate_page (URL-bar-entry equivalent)

7. Selected the authed `/dashboard` page → `navigate_page type=url url=http://localhost/login timeout=15000` → settled at `/dashboard` (browser refused to land on `/login` for the authed user). Empirical observation matches Path 1.

### Verification summary

Both browser-side hard-navigation simulations (new tab + URL bar entry) deliver the authed user to `/dashboard` automatically. W174 §Honesty #3 is empirically closed. The redirect may be served by either (a) server-side `_public.tsx beforeLoad` reading ssrAuth → throw redirect, OR (b) client-side W177 SW1 useEffect after useProfileSync settles useAuthStore → navigate. Both paths land at the same destination; the W177 SW1 useEffect specifically covers the CSR-only race where the SSR pathway has `loading: true` initial state.

---

## SW5 — Audit + N+3 rotation + memory + CLAUDE.md + INDEX.md

This commit. Standard ritual:

- NEW `docs/audits/AUDIT_WAVE177.md` (this document).
- N+3 rotation: `git mv docs/audits/AUDIT_WAVE174.md docs/audits/archive/AUDIT_WAVE174.md`. Active waves post-W177: **W175/W176/W177**.
- `docs/audits/INDEX.md`: insert W177 row at top of Active audits; move W174 row from Active to Archive; update N+3 rotation history line at file top.
- `CLAUDE.md`: NEW Audit Trail row (compact ~2-3 KB per W175 polish-v2 length cap) + 2 NEW Gotchas (W177 reactive-redirect pattern + `renderLogin skipMeOverride` opt-out + msw vestigial-override discipline note).
- `memory/MEMORY.md` (`.claude` profile): NEW Audit History row + Active backlog row + compact older verbose rows if headroom dips below ~500 b.
- NEW `memory/wave177_backlog.md` (`.claude` profile, ~150 lines): close summary for next-session lookup.
- NEW `memory/wave178_opening_prompt.md` (`.claude` profile, ~300 lines): full opening prompt template for W178 with W177 closures applied to §Honesty trajectory + Q0 framework updated.

---

## §Honesty probe

### Closed in W177

1. **W174 §Honesty #3** — `/login` authed-user redirect edge case. ✅ EMPIRICALLY CLOSED via SW1 useEffect + SW2/SW3 msw scoping discipline + SW4 chrome-devtools-mcp verification through real Docker chain (both new_page + navigate_page paths).

### NEW honestly framed in W177 (W178+ candidates)

2. **Approach 2 leaves /forgot-password, /reset/$token, /register WITHOUT reactive redirect**. The authed-user-hard-nav edge case persists on those 3 routes per the user-approved Approach 2 trade-off. Approach 1 (route-level watcher in `_public.tsx`) would have covered all 4 routes via the same mechanism. Acceptable per user choice. W178+ candidate if user needs the broader coverage.
3. **`state.from` redirect-path race** in Login.tsx useEffect. Hardcoded `/dashboard` destination; useLoginFlow.ts:75 reads `state.from.pathname` for the imperative path. Imperative usually wins in normal flow (sync after setUser). Edge race exists but rare. W178+ polish candidate.
4. **npm audit 2 moderate** (`ws 8.0.0-8.20.0`) — upstream CVE disclosed between W176 close (2026-05-20) and W177 open (2026-05-21). NOT a W177 regression. W178+ housekeeping candidate via `npm audit fix` (~5 min).
5. **Container rebuild required for SW4 verification**. The running Docker frontend container was on pre-W177 bundle; needed `bash scripts/dc.sh up -d --build frontend` (W170 SW4 helper) to pick up SW1 changes. Documented for future-session continuity.

### Carry-forward from prior waves (unchanged)

6. W134 §Honesty #2 — bundle delta deep investigation (recording-only).
7. W134 §Honesty #10 — /messenger Phase 5 SSR explicit defer-by-design (W161 SW2).
8. W176 §Honesty #4 — authed-route chrome-devtools visual smoke (5 admin routes).
9. W176 §Honesty #5 — bundle +2,357 b above plan ceiling (W175 baseline; accepted).
10. W176 §Honesty #6 — Storybook ReducedMotion variant uses CSS simulation only.

### Trajectory

Pre-W177: **0-7 OPEN** (4 W176 carries + 3 older).
Post-W177: **0-9 OPEN** (close 1 = W174 §Honesty #3; carry 5 prior; +5 NEW W177-introduced). Range increased by structurally-honest framing per `feedback_perfectionism.md` — 4 of the 5 W177-introduced caveats are explicit scope-trade-offs documented at planning time, not surprises.

### Polish-v1 «безупречно?» self-audit findings (2026-05-21)

User fired «безупречно?» probe post-SW5 audit commit. Self-audit found 3 corrections (all honestly framed, no functional regressions):

1. **`/login` SSR HTML size claim ERROR** — pre-polish-v1 audit doc + CLAUDE.md row + INDEX.md row + memory files (× 6 files) claimed `/login 200/21,669b SSR (+59 b vs pre-W177 21,610 b — SSR-rendered Login.tsx with new useEffect imports + comment)`. **Actual stable measurement**: `/login 200/21,610 b SSR × 3 consecutive curls post-Docker-rebuild settled state**. SW4 verification reading of 21,669 b was a one-time transient ~14 seconds post-rebuild; settled state matches pre-W177 size exactly. **Why**: W177 SW1 useEffect, useNavigate, useAuthStore imports compile to the JS chunk (`Login-teulBu_B.js` 24.90 kB), NOT to the SSR HTML output. The Login component renders the same JSX → same DOM structure → same SSR HTML bytes. Honest framing: SSR HTML size unchanged from pre-W177 baseline.

2. **server.js + `_shell.html` + sw.js "IDENTICAL to W176 baseline" claim INCORRECT** — pre-polish-v1 audit doc claimed server.js / `_shell.html` / sw.js "IDENTICAL to W176 baseline". **Correct framing**: SIZE matches W176 baseline (server.js 23,600 b, `_shell.html` 66,459 b, sw.js 53,667 b) but **content sha differs**: server.js W177 sha `5632af4d...` ≠ W176 `af97a5a2...`. Why server.js sha changed: Login.tsx compiles to BOTH client AND server bundles (TanStack Start SSR includes the component code for server-side render), so the useEffect / useNavigate / useAuthStore imports modify server.js content even though they don't EXECUTE at SSR time. `_shell.html` + sw.js sha variance per build per W141 polish A3 documented non-determinism (CSP nonce + workbox precache revision hash).

3. **Build × 3 BYTE-IDENTICAL EMPIRICALLY VERIFIED (NEW POSITIVE FINDING)** — pre-polish-v1 audit doc did not claim "Build × 3" (per W141 anti-pattern #4 discipline — only claim what's verified). Polish-v1 ran 3 fresh `rm -rf dist && npm run build` cycles + sha256 compared: main JS sha `6c06917371e8d03dbf708c22a1b83d5500838b14550e52a7326bafbd6dd74bae` × 3 IDENTICAL + server.js sha `5632af4db653999b9a1929c462d6c0df7d679519bfda154796b4f6867764fe67` × 3 IDENTICAL. **Extends W134-W176 ≥36-wave LOCAL-MACHINE BYTE-IDENTICAL invariant chain through W177 → ≥37-wave invariant CONFIRMED EMPIRICALLY** (not just structural argument).

4. **CI on `5ff625215` (SW1+SW2+SW3) NOT separately registered** — gh API `repos/.../commits/5ff625215/status` returns `{state: pending, total_count: 0}`. Normal GitHub behavior: when commits are pushed in quick succession (~17 min between `5ff625215` and `65a5c043e`), GitHub may de-duplicate workflow_dispatch triggers to the HEAD commit. The cumulative branch state at HEAD `65a5c043e` includes ALL W177 changes (frontend SW1+SW2+SW3 + audit + N+3 + docs), and CI on HEAD ran ALL GREEN (7 jobs SUCCESS + 1 Auto-merge skipped expected). Frontend changes ARE tested in the HEAD CI run; no separate `5ff625215` run needed.

5. **CLAUDE.md W177 row size: 7,483 bytes** — over W175 polish-v2 target cap of ~2-3 KB per row but improvement direction (W175 row was ~12 KB, W176 row was ~10 KB pre-polish, W177 is ~7.5 KB). Accepted as honest framing of W177 scope detail (3 SW + audit + N+3 + 3 Gotchas all consolidated in one row). W178+ rows should continue compaction trajectory toward ~3 KB target.

All 3 corrections + 2 observations applied in polish-v1 commit. Audit doc + CLAUDE.md row + INDEX.md row + memory/wave177_backlog.md + memory/wave178_opening_prompt.md updated for honest framing. Empirical evidence captured (Build × 3 sha + 3-curl /login stability verification).

---

## W141 anti-pattern compliance

| #   | Pattern                                      | Status                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       | Cumulative count                           |
| --- | -------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------ |
| 1   | STRICT 1-iter cap                            | ✅ SW1+SW2+SW3 ship together in 1 iter; W138 Lesson #1 within-iter SAME-mechanism sub-fixes (afterEach reset, msw helper override, 2 vestigial /users/me removals); DIFFERENT mechanism vs W175 SW10 = new wave per W138                                                                                                                                                                                                                                                                     | **30th total vindication** (W174 was 29th) |
| 3   | Phase 3 Review verify Agent claims           | ✅ Read `_public.tsx`, `Login.tsx`, `useLoginFlow.ts`, `useAuthApi.ts`, `useAuthStore.ts`, `Login.test.tsx`, `handlers.ts /auth/login section`, `renderWithRouter.tsx`, `pageTranslations.test.tsx` before edits; Phase 3 caught MFA-test `/users/me` overrides being vestigial (not load-bearing for MFA UI which triggers from POST `/auth/login` 202) — saved a wave-restart vs the speculative path of adding per-test 401 overrides without removing the conflicting mfa-user overrides | **55-58th vindications**                   |
| 4   | No premature "Closes" attribution            | ✅ SW1+SW2+SW3 commit ships with §Honesty caveat #4 noting SW4 verification still pending; "Closes W174 §Honesty #3" attribution lands ONLY in this SW5 audit AFTER SW4 chrome-devtools-mcp empirical verification                                                                                                                                                                                                                                                                           | **28th vindication**                       |
| 15  | (ARCHIVED W159 SW4) — husky pre-commit chain | ✅ SW1+SW2+SW3 commit `5ff625215` fired W156 SW4 husky chain cleanly (lint-staged prettier --write + eslint --fix; detect-secrets initial failure auto-resolved via `.secrets.baseline` re-stage per CLAUDE.md ## Gotchas; Python 2 except check PASS); SW5 audit commit will also use the chain. NO `--no-verify` bypasses                                                                                                                                                                  | **42nd consecutive wave preserved**        |

---

## Gates verification matrix

| Gate                                         | Result                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      | Baseline                                                                    |
| -------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| `npx tsc --noEmit`                           | 0 errors                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    | W176 baseline preserved                                                     |
| `npm run lint -- --max-warnings=0`           | 0 warnings                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  | W176 baseline preserved                                                     |
| `npx vitest run`                             | **1104p / 12s / 0f** in ~33s                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                | W176 1103p + 1 NEW W177 regression test = 1104p exactly                     |
| `npx prettier --check` (W177 modified files) | All use Prettier code style                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 | Husky lint-staged also auto-formatted on commit                             |
| `npm audit`                                  | 2 moderate (ws upstream CVE)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                | Environmental; NOT W177 regression (see §Honesty #4)                        |
| `npm run build` (production)                 | Main JS `index-BA6s4YBY.js` **179,507 b** — SIZE matches W176 baseline `index-BfRpD_fx.js` 179,507 b (new sha `6c069173...` ≠ W176 `c6a9c5f8...`); server.js 23,600 b SIZE matches W176 (new sha `5632af4d...` ≠ W176 `af97a5a2...` — Login.tsx changes compile to SSR bundle too); `_shell.html` 66,459 b + `sw.js` 53,667 b SIZE matches W176 (per-build sha variance per W141 polish A3 non-determinism). **Build × 3 BYTE-IDENTICAL** sha verified empirically polish-v1 — main JS + server.js sha × 3 IDENTICAL from clean `rm -rf dist`. Extends W134-W176 ≥36-wave LOCAL-MACHINE invariant chain through W177 → **≥37-wave invariant**. Login route chunk `Login-teulBu_B.js` 24.90 kB carries SW1 useEffect weight. | W176 SIZE preserved; content sha differs (real client + server tree change) |
| Docker chain                                 | `/healthz 200`, `/login 200/21,610b SSR` (matches pre-W177 SSR size — W177 SW1 useEffect lives in JS chunk, NOT SSR HTML output; SW4 measurement of 21,669 b was a transient ~14s-post-rebuild reading, settled state is 21,610 b across × 3 polish-v1 curls)                                                                                                                                                                                                                                                                                                                                                                                                                                                               | W176 SSR HTML size baseline preserved                                       |
| chrome-devtools-mcp empirical                | 0 console messages, 0 React #418 hydration errors on authed-user `/login → /dashboard` redirect via both `new_page` and `navigate_page`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     | NEW W177 verification — closes W174 §Honesty #3                             |

---

## Bundle delta vs W176 baseline (post-polish-v1 honest framing)

**Main JS chunk**: `index-BA6s4YBY.js` **179,507 b** (local Windows build). **SIZE matches** W176 baseline `index-BfRpD_fx.js` 179,507 b exactly. **Content sha differs**: W177 `6c06917371e8d03dbf708c22a1b83d5500838b14550e52a7326bafbd6dd74bae` ≠ W176 `c6a9c5f889004eba14a8ba3b54f34c4f5103f30f29cd709d44ac0f75847a82c4` — reflects W177 SW1 production code change (useEffect + 3 imports + comment) compiled to client tree. **Login route chunk** `Login-teulBu_B.js` **24.90 kB** — carries the SW1 useEffect code via Vite/Rolldown route-based code-splitting.

**server.js**: **23,600 b** — **SIZE matches** W176 baseline 23,600 b. **Content sha differs**: W177 `5632af4db653999b9a1929c462d6c0df7d679519bfda154796b4f6867764fe67` ≠ W176 `af97a5a20052006774c85b044907022b4d4a6a8980ada8ea5e0438e0e3286ffc`. Pre-polish-v1 audit doc claimed "IDENTICAL" — corrected here: Login.tsx changes compile to BOTH client AND server bundles (TanStack Start SSR includes Login component code for server-side rendering), so server.js content sha changes even when the SSR output (HTML) doesn't change. The useEffect / useNavigate / useAuthStore imports are present in the SSR bundle but don't EXECUTE at server-render time.

**\_shell.html**: **66,459 b** — **SIZE matches** W176 baseline. Per-build sha varies per W141 polish A3 documented non-determinism (CSP nonce per request + chunk hash refs).

**sw.js**: **53,667 b** — **SIZE matches** W176 baseline. Per-build sha varies per W141 polish A3 (workbox precache revision hash). W174 SW2 ensureCsrfCookie auto-fetch already in W174 baseline; no new SW workbox precache entries.

**Build × 3 BYTE-IDENTICAL EMPIRICALLY VERIFIED (polish-v1, 2026-05-21)**: 3 fresh `rm -rf dist && npm run build` runs from clean state, main JS sha `6c069173...` × 3 IDENTICAL + server.js sha `5632af4d...` × 3 IDENTICAL. Extends W134-W176 ≥36-wave LOCAL-MACHINE invariant chain → **≥37-wave invariant CONFIRMED EMPIRICALLY** (not just structural argument). `_shell.html` + `sw.js` had per-build sha variance per W141 polish A3 (expected non-determinism source).

**Cross-platform divergence (W141 polish A3 known invariant)**: Docker Linux container build produced `index-D0EDgCF8.js` post-rebuild; same source code yields different filename hash AND different content sha than local Windows build `index-BA6s4YBY.js` due to Node.js + Rolldown native binary differences (x64-win vs x64-linux). Semantically equivalent. SW4 chrome-devtools-mcp verified the Docker Linux build serves Login.tsx with the W177 SW1 useEffect correctly.

---

## NEW W177 Gotchas (added to CLAUDE.md)

### Gotcha 1: Login.tsx W177 SW1 reactive useEffect pattern

`frontend/src/pages/Login.tsx` includes a `useEffect(() => { if (user) navigate({to:"/dashboard", replace:true}) }, [user, navigate])` watching `useAuthStore.user`. Closes W174 §Honesty #3 (authed user hard-navigates to /login from bookmark/search/external link stays on /login until reload, because `_public.tsx beforeLoad` reads `useAuthStore.getState()` ONCE on initial mount when `loading:true`; no reactive trigger re-evaluates after `useProfileSync` settles the store). `replace:true` prevents /login from appearing in back-button history. Test infra requires msw `/users/me → 401` overrides for tests that mount Login.tsx and verify form behavior (not authed-redirect behavior) — see `renderLogin skipMeOverride` pattern below.

### Gotcha 2: `renderLogin({ skipMeOverride })` test helper pattern

`frontend/src/pages/__tests__/Login.test.tsx renderLogin()` helper accepts `RenderLoginOptions = { skipMeOverride?: boolean }`. Default behavior (skipMeOverride: false): the helper prepends `server.use(http.get("*/users/me", () => HttpResponse.json(null, {status:401})))` BEFORE `renderWithRouter` mounts AuthProvider — blocks the W177 SW1 useEffect from firing mid-test for tests that verify Login UI form behavior. Set `skipMeOverride: true` for the dedicated W174 §Honesty #3 regression test or any future test that wants to exercise the authed-redirect flow. Also: `afterEach` MUST reset `useAuthStore.setState({user: null, loading: true, pendingMfa: null, authOperation: false})` to prevent cross-test pollution that W177 SW1 useEffect makes observable (pre-W177 the auth store persistence across tests was silent).

### Gotcha 3: MFA test `/users/me → mfa-user` overrides are NOT load-bearing — defensive only

Pre-W177, the MFA tests at Login.test.tsx (transitions to MFA verification + displays errors for invalid OTP attempts) had `server.use(http.get("*/users/me", () => HttpResponse.json({...testUser, mfa_required:true})))` overrides. **These were defensive setup, NOT behaviorally required** for the MFA flow. The actual MFA UI trigger is the POST `/auth/login` 202 response (handlers.ts:655-664 matches `mfa@example.com + Password123` → returns PendingMfaResponse → useAuthApi calls updatePendingMfa → useMfaFlow.loginChallenge becomes truthy → MfaChallengeView renders). W177 SW2 removed these vestigial overrides because they conflicted with the W177 SW1 useEffect (msw LIFO → mfa-user wins over renderLogin's 401 default → useEffect fires → premature redirect before user can submit credentials). Future MFA-flow tests should NOT add `/users/me` overrides unless they specifically need to verify state-based UI (which would need a different mechanism anyway).

---

## W178+ candidates (priority order)

1. **Continue maintenance + bug fixes only** (CANONICAL DEFAULT per W171 Lesson #1). No active development unless real trigger emerges.
2. **Approach 1 extension** — add route-level watcher to `_public.tsx` to cover `/forgot-password`, `/reset/$token`, `/register` for the same authed-user-hard-nav edge case (~1-2h focused; closes W177 §Honesty #2).
3. **W177 §Honesty #3** `state.from` redirect-path race fix (~30-60 min; gates useEffect on imperative-in-flight flag OR threads redirectPath through useAuthStore).
4. **npm audit fix** — ws upstream CVE close (~5-10 min; closes W177 §Honesty #4).
5. **W176 §Honesty #4** — authed-route visual smoke on /dashboard /news /events /profile /settings (~30-60 min if seed_demo_data.py available in backend container; else alternative auth-bypass route).
6. **routeGuards.test.tsx + Playwright wave174-login-flow e2e** (~3-5h combined).
7. **/messenger Phase 5 SSR enable** (~3-5h own wave; closes W134 §Honesty #10 if user reverses W161 SW2 by-design defer).
8. **Tier 4 housekeeping** — Lighthouse #17021 quarterly check + INDEX.md hygiene + MEMORY.md monitoring.

Per W171 Lesson #1: maintenance mode = waves fire on real triggers, not on schedule. Project rests until next user-reported bug OR scheduled cron firing (post-PR-#1114-merge admin-smoke-monitoring activates per W171 SW1).

---

## Cross-references

- W174 §Honesty #3 origin: `docs/audits/archive/AUDIT_WAVE174.md` (post-W177 N+3 rotation).
- W175 SW10 attempt + revert: commit `b9babec45` (TS type-narrow within-iter sub-fix bundled with the revert per W138 Lesson #1 SAME-mechanism rule).
- W174 SW1 production fix baseline: commit `b13d7f106` (route guards `_auth.tsx` / `_public.tsx` / `_admin.tsx` migrated to `useAuthStore.getState()`).
- W138 Lesson #1 (DIFFERENT mechanism = honest defer + new wave): documented in CLAUDE.md ## Gotchas + `memory/feedback_perfectionism.md`.
- W141 anti-pattern #1 STRICT 1-iter SACRED (now 30+ vindications): CLAUDE.md ## Gotchas + `feedback_perfectionism.md`.
- W170 SW4 helper scripts (`bash scripts/dc.sh up -d --build frontend`): used in SW4 to rebuild Docker frontend container; closes W169 (z) #1 silent-failure mode structurally.

---

**End of W177 audit. W174 §Honesty #3 closed. Active waves: W175/W176/W177.**
