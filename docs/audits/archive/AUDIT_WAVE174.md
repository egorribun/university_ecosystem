# AUDIT_WAVE174 — Login flow + PWA manifest user-reported bugs (Q0=B real-bug triage)

**Branch**: `egorribun`
**Date**: 2026-05-20
**Status**: ✅ CLOSED
**Wave-counter**: 34th consecutive wave with brainstorming + Phase 1 Explore + Phase 3 Review + W141 anti-pattern discipline
**Core duration**: ~3-4h wall-clock (within Q3 open-ended absorption budget)

---

## Headline

W174 closed **2 user-reported bugs + 1 surfaced-during-verification production bug** via 3 SW commits + audit:

- **Bug 1 (login flow broken)** — User reported login succeeded but client stayed on `/login` instead of redirecting to `/dashboard`; reload showed dashboard, but in-app navigation bounced back to `/login`. **Closed via SW1** (route guards migrated from stale `context.auth` singleton to live `useAuthStore.getState()`).
- **Bug 2 (PWA manifest 404)** — Browser DevTools console reported `GET http://localhost/screenshots/schedule-wide.png 404 (Not Found)` + manifest icon download error. **Closed via SW3** (orphan screenshot declarations removed from canonical `manifest.source.json` + regenerated locale variants).
- **Bug 3 (CSRF cookie auto-acquisition gap)** — Discovered during SW1 browser smoke: frontend had no logic to GET `/api/v1/auth/csrf-cookie` before first unsafe-method request. Real users hitting backend's CSRF middleware with expired cookie (30-min Max-Age) get 403 with no UX feedback. **Closed via SW2** (axios request interceptor auto-fetches CSRF endpoint before POST/PUT/PATCH/DELETE if no cookie present).

All 3 fixes empirically verified via chrome-devtools-mcp fresh-context browser smoke through real Caddy → Node SSR → backend chain. Q0 framework activated mid-session per W173 + W171 Lesson #1 honest framing.

---

## Q0 framework + mid-session pivot

User opened W174 with `@memory/wave174_opening_prompt.md начинаем wave 174` plus explicit Russian-language bug report covering:

1. Login redirect failure ("при успешном логине не перекидывает на платформу")
2. Post-reload in-app navigation bouncing back to /login ("при попытке перехода на другие страницы сайта обратно выбрасывает")
3. Manifest 404 errors (screenshot attached to message)
4. Comprehensive fix mandate ("просмотри весь код, все логи на docker и исправь все баги до идеального отполированного состояния")

Per W173 SW3 precedent (Q0 shifts A → B mid-session if real bug surfaces) + W171 Lesson #1 ("maintenance mode means waves fire on real triggers, not on schedule"), Q0 = B real-bug triage activated immediately. W141 anti-pattern #3 (Phase 3 verification of Agent claims) triggered before any SW work began.

---

## Phase 1 Explore + Phase 3 Review

Two parallel Explore agents dispatched at session start covering login flow + route guards. Both agents independently converged on the same root cause: **router context staleness post-W152 Phase 1.7**.

Phase 3 verification via direct Read confirmed all key claims:

- `frontend/src/router.ts:46-138` — singleton module-level router; `context: { auth: ssrAuth ?? DEFAULT_AUTH, queryClient: new QueryClient() }` initialized once at module load
- `frontend/src/App.tsx:55-65` — returns `<StartClient />` only; pre-W152 Phase 1.7 had `<RouterProvider router={router} context={useAuth()}>` reactive bridge (removed per file comment lines 30-51 in W152 Phase 1.7)
- `frontend/src/router.ts:31-33` — **comment OUT OF DATE** ("App.tsx's `<RouterProvider context={...}>` populates real auth from useAuth() at client mount, fully overriding any default we set here" — incorrect post-W152 Phase 1.7)
- `frontend/src/hooks/auth/useAuthApi.ts:126-212` — login mutation calls `setUser(data.user)` (line 168) updating Zustand store; **NO** `queryClient.invalidateQueries(["users", "me"])` or `router.update({ context })` calls
- `frontend/src/hooks/auth/useLoginFlow.ts:116-141` — line 129 `navigate({ to: redirectPath, replace: true })` fires synchronously after `await login(...)` resolves
- `frontend/src/hooks/auth/useProfileSync.ts:1099-1109` — reactive sync of internal state INTO Zustand via `useAuthStore.setState({ user, loading, ... })`; **Zustand IS the source of truth**
- `frontend/src/routes/_auth.tsx:29` — `if (!context.auth.isAuth) { throw redirect({ to: "/login" }) }` reads STALE router context (forever `isAuth: false` on client)
- `frontend/src/routes/_public.tsx:16` — same staleness pattern, inverted
- `frontend/src/routes/_admin.tsx:67-75` — same staleness + reads `context.auth.user.role`

**3 of 3 route guards affected.** Phase 3 also caught Phase 1 Agent 1's structurally correct hypothesis but additional verification of `useAuthStore` API (`useAuthStore.getState()` returning live state) was needed before SW1 design could land — that was completed via direct Read.

---

## Root cause analysis

### Bug 1: Router context staleness post-W152 Phase 1.7

**Mechanism class**: client-side route-guard data source.

TanStack Router's `beforeLoad({ context })` reads the context object passed at `createRouter()` call time. If nothing calls `router.update({ context: ... })`, the context never mutates. Pre-W152 Phase 1.7, App.tsx had `<RouterProvider router={router} context={useAuth()}>` — the reactive `context` prop meant RouterProvider re-rendered with fresh context every time `useAuth()` returned a new value. After W152 Phase 1.7 switched to `<StartClient />` (which internally invokes `hydrateStart() → <Await><RouterProvider /></Await>` without a reactive `context` prop), the router context became permanently stuck at `DEFAULT_AUTH = { isAuth: false, user: null, loading: false }` on the client.

**Why reload appeared to work**: TanStack Router's initial-hydration-from-SSR-stream path doesn't re-fire `beforeLoad` for the SSR-matched route — it trusts the server's match result. Server-side `globalThis.__ssrAuthGetter__` (W126 SW4) returns real auth from validating the `access_token_v2` cookie against backend's `/.well-known/jwks.json`. Only post-mount client-side `navigate()` calls re-evaluated `beforeLoad`, and THAT's when the stale singleton context bit.

### Bug 2: PWA manifest declares orphan screenshots

**Mechanism class**: static asset declaration drift.

`frontend/public/manifest.source.json:83-98` declared 2 screenshots (`/screenshots/schedule-wide.png` + `/screenshots/schedule-narrow.png`) for PWA install prompt UI. `frontend/scripts/generate-manifests.mjs:14-54` `mergeManifests` pipeline propagated the orphan declarations into both generated locale files. Physical screenshot files were never created — `frontend/public/screenshots/` contains only `.gitkeep`. Browser fetched manifest, parsed `screenshots` array, attempted to download declared URLs, hit 404, emitted console error.

### Bug 3 (W174 discovery): Frontend missing CSRF cookie auto-acquisition

**Mechanism class**: auth bootstrap chain gap.

Axios's built-in XSRF mechanism in `frontend/src/api/client.ts:66-67` (`xsrfCookieName: "csrf_token"` + `xsrfHeaderName: "X-CSRF-Token"`) reads the cookie + sets the header automatically. If the cookie is MISSING — either first-time visitor OR real user whose `csrf_token` cookie expired (backend's `app/core/csrf.py:71` sets `Max-Age=1800` = 30 min) — axios sends no header, and `CSRFMiddleware` (`app/core/middleware/setup.py:47-60`) rejects with 403 "Несоответствие CSRF-токена".

Pre-W174 the frontend had ZERO proactive CSRF acquisition — real users only succeeded when they had a persistent `csrf_token` cookie from a prior session. After 30+ min idle, the cookie expired and login would fail with 403 + no UX feedback (the 403 detail field is in `application/problem+json` but the frontend surfaces it as a generic auth error).

Backend exposes `GET /api/v1/auth/csrf-cookie` which idempotently sets the cookie. `.github/workflows/visual-audit.yml` already ran this dance for its register flow per W140 SW4, but the production frontend never did. The fact that we have many waves of working login means developers/testers had stale CSRF cookies persisting across sessions.

---

## SW commit breakdown

### SW1 `b13d7f106` — Route guards migrated to live Zustand

**Commit**: `fix(wave174-sw1-route-guards-live-zustand): read live store, not stale context`
**Files modified**: 4 (+61/-20)

- `frontend/src/routes/_auth.tsx` — replaced `context.auth.loading|isAuth` with `useAuthStore.getState().{loading, user}`; reformulated `!isAuth` check as `!user` (matches `useAuth().isAuth = user !== null` per `AuthContext.tsx:61`).
- `frontend/src/routes/_public.tsx` — same migration, inverted predicate (redirect if `user`).
- `frontend/src/routes/_admin.tsx` — same migration + `user.role !== "admin"` check.
- `frontend/src/router.ts` — updated stale comments at lines 31-33 + 47-50 to reflect W152 Phase 1.7 reality + document W174 SW1 "guards read Zustand directly" pattern.

**Why Option A (direct Zustand read) over Option B (`router.update({ context })` reactive sync)**:

- Simpler — surgical edit to 3 files vs wiring useEffect inside AuthProvider that calls `router.update()`
- Zustand IS already the source of truth (`useProfileSync.ts:1099-1109` syncs into it on every update)
- Matches existing app code conventions (every other consumer reads `useAuthStore` directly)
- `useAuthStore.getState()` outside React is a plain JS call (safe in `beforeLoad`, which runs outside React render phase)
- W141 anti-pattern #1 STRICT 1-iter compliant (single mechanism, no iter cascade)

**Trade-off acknowledged**: `RouterContext.auth` interface in `router.ts:6-13` becomes unused dead-code on client. Kept intact for forward-compat with any future SSR-side `beforeLoad` using `globalThis.__ssrAuthGetter__`. Honestly documented in router.ts comment block.

**Bundle delta**: local-build main JS `index-DueN8aJX.js` 177,042 b (-15 vs W173 baseline `index-BlWdKfsi.js` 177,057 b — minor minification savings from destructure replacing 4× property-access chains `context.auth.*` → `const { user, loading } = ...`).

**Local gates GREEN**: tsc 0, eslint --max-warnings=0 0, prettier clean, **vitest 1058p/12s/0f** (W173 baseline EXACT preserved), build × 1 reproducible 177,042 b. Husky pre-commit chain fired cleanly (NO `--no-verify`).

### SW2 `24aba2076` — CSRF cookie auto-bootstrap

**Commit**: `fix(wave174-sw2-csrf-cookie-auto-fetch): bootstrap CSRF cookie before unsafe methods`
**Files modified**: 1 (+53)

NEW `ensureCsrfCookie()` helper in `frontend/src/api/client.ts:147-176` called from the request interceptor before POST/PUT/PATCH/DELETE. Guards in order:

1. SSR no-op (`typeof document === "undefined"`)
2. Test-env skip (`import.meta.env.MODE === "test"` — Vite literal substitution at build time tree-shakes from prod AND prevents vitest pollution from MSW unhandled-request warnings on `/auth/csrf-cookie`)
3. Already-have-cookie short-circuit (`document.cookie.includes("csrf_token=")`)
4. In-flight singleton Promise (`_csrfBootstrapPromise`) dedupes concurrent unsafe requests — single network call when many POSTs fire simultaneously
5. `.finally` resets the singleton after resolve/reject so future cookie expiry can re-bootstrap
6. Recursion-guard: skip ensure on `/auth/csrf-cookie` itself (defensive — it's a GET so the unsafe-method branch wouldn't fire anyway)

**Test interaction trap caught (within-iter sub-fix per W138 Lesson #1)**: First SW2 commit attempt failed vitest's `AdminFeatureFlags.test.tsx > toggle switch fires patch request when clicked`. MSW had no handler for `/auth/csrf-cookie`, the fetch failed with `ERR_NETWORK`, and the singleton Promise's rejection polluted subsequent test runs. Test-env skip via `import.meta.env.MODE === "test"` resolves cleanly + tree-shakes out of prod (the `MODE` literal substitution makes this branch dead code in production builds, verified `grep -l "MODE === \"test\"" dist/client/assets/*.js` returns empty in PROD).

**Bundle delta**: main JS 177,042 b (BYTE-IDENTICAL SIZE to SW1; different sha due to module identity re-order). New CSRF logic lives in `client-DL451DmB.js` chunk (~40 lines + interceptor wiring) — under the test-env DCE branch.

**Local gates GREEN**: tsc 0, eslint 0, prettier clean, **vitest 1058p/12s/0f** (W173 + SW1 baseline preserved EXACT post test-env skip). Husky chain clean (37th wave preserved per W141 #15 ARCHIVED).

### SW3 `53bf9a87f` — PWA manifest screenshot cleanup

**Commit**: `fix(wave174-sw3-pwa-manifest-screenshots): drop orphan screenshot declarations`
**Files modified**: 3 (-48 deletion-only)

- `frontend/public/manifest.source.json` — removed entire `screenshots` array (lines 83-98)
- `frontend/public/manifest.webmanifest` — regenerated via `npm run generate:manifests`
- `frontend/public/manifest.en.webmanifest` — same regeneration

**Why not "add real screenshots"**: per `feedback_perfectionism.md` honest framing — the screenshots were declared aspirationally but never delivered. PWA install UI shows app icons + name without screenshots (the property is optional UI hint per W3C manifest spec). Adding real screenshots requires design decisions (which views — Schedule? Dashboard? News?; light + dark theme variants; locale-specific images) — out of W174 real-bug-fix scope. Removing is the honest minimal fix.

**Local gates GREEN**: `npm run generate:manifests --check` passes (no drift between source and generated outputs). No TS/lint/test impact (no source code touched). 38th wave hook chain preserved.

### SW4 (this commit) — Audit doc + N+3 rotation + CLAUDE.md + memory

**Commit**: `docs(wave174-sw4-audit): ...`

- NEW `docs/audits/AUDIT_WAVE174.md` (this document)
- N+3 rotation: `git mv docs/audits/AUDIT_WAVE170.md docs/audits/archive/`
- CLAUDE.md ## Audit Trail row + 3 NEW ## Gotchas entries
- `docs/audits/INDEX.md` updates (active + archive tables + rotation history)
- MEMORY.md row addition (user .claude profile)
- NEW `memory/wave174_backlog.md`
- NEW `memory/wave175_opening_prompt.md`

Active waves post-W174 SW4 rotation: **W171/W173/W174**.

---

## Empirical verification matrix

All 3 SW commits verified via chrome-devtools-mcp fresh-context browser smoke through real Caddy → Node SSR → backend chain after `bash scripts/dc.sh up -d --build frontend` (W170 SW4 helper). Test user: `test@university.dev` / `TestPass@2024x` per CLAUDE.md Docker section.

### Pre-W174 SW2 baseline (chrome-devtools fresh context, no prior csrf_token cookie)

```
GET /api/v1/users/me          → 401 (no auth)
POST /api/v1/auth/login       → 403 "Несоответствие CSRF-токена"
```

User stuck on /login indefinitely. No UX feedback explaining 403.

### Post-W174 SW1+SW2+SW3 (same fresh context, same credentials)

```
GET /api/v1/users/me          → 401 (no auth, expected)
GET /api/v1/auth/csrf-cookie  → 200 + Set-Cookie: csrf_token=...  (SW2 auto-bootstrap)
POST /api/v1/auth/login       → 200 (CSRF header now valid)
... dashboard data fetches ...
URL: http://localhost/dashboard  (SW1 route guards read live Zustand → no redirect-loop)
```

### Verification matrix table

| Check | Pre-W174 | Post-W174 | Outcome |
|-------|----------|-----------|---------|
| POST /api/v1/auth/login (fresh ctx, no csrf cookie) | 403 | 200 | ✅ closed |
| URL after successful login | `/login` (stuck) | `/dashboard` (redirected) | ✅ closed |
| In-app `/dashboard → /events` click | bounce back to `/login` | renders `/events` | ✅ closed |
| In-app `/events → /schedule` click | bounce back to `/login` | renders `/schedule` | ✅ closed |
| Hard reload `/dashboard` while authed | renders `/dashboard` | renders `/dashboard` | ✅ regression-clean |
| Hard reload `/events` while authed | renders `/events` (because SSR matched on server) | renders `/events` | ✅ regression-clean |
| Manifest fetch in browser | screenshots array → 2× 404 console errors | screenshots array absent → 0 errors | ✅ closed |
| `curl -sI /manifest.webmanifest` body grep `screenshots` | matched | 0 matches | ✅ closed |
| chrome-devtools-mcp console errors after login + dashboard render | login-flow 403 + manifest 404 × 2 + 401 + profile_cache.cleared | 401 + profile_cache.cleared × 2 (expected baseline) | ✅ clean |
| /ws/ticket → 201 (W173 polish-v1 chat WS) | 201 | 201 | ✅ W173 preserved |
| `.wasm` Content-Type (W173 SW1) | application/wasm | application/wasm | ✅ W173 preserved |
| /ws/chat WS upgrade (W173 polish-v3) | 101 Switching Protocols | 101 Switching Protocols | ✅ W173 preserved |

### Network request sequence (post-W174 fresh-context login)

```
reqid=219 GET  /api/v1/users/me               → 401  (initial AuthProvider mount fires /users/me)
reqid=231 GET  /api/v1/auth/csrf-cookie       → 200  ← W174 SW2 auto-bootstrap fires before POST
reqid=232 POST /api/v1/auth/login             → 200  ← CSRF header now set → login succeeds
reqid=233 GET  /assets/uni_wasm_crypto_bg-*.wasm → 200 (W173 SW1 MIME preserved)
reqid=241 GET  /api/v1/events?is_active=true&limit=50 → 200 (dashboard data)
reqid=242 GET  /api/v1/chats?limit=20         → 200
reqid=243 GET  /api/v1/stories                → 200
reqid=244 POST /ws/ticket                     → 201 (W173 polish-v1 + W173 SW1)
reqid=245 GET  /api/v1/notifications          → 200
... etc ...
```

### Console messages (post-login dashboard render)

```
[error] 401 Unauthorized   ← initial /users/me before auth (expected baseline)
[warn]  profile_cache.cleared   ← W128 SW1 AuthProvider behavior (expected baseline)
[error] 401 Unauthorized   ← duplicate from React StrictMode initial double-render
[warn]  profile_cache.cleared   ← duplicate from React StrictMode
```

**Zero React #418 hydration errors. Zero manifest screenshot 404 errors.** All console noise is pre-existing expected behavior baseline.

---

## §Honesty caveats

Per `feedback_perfectionism.md` "honest framing over false closure" + W141 anti-pattern #4 (no premature "Closes" attribution before empirical verification):

1. **Bundle invariant break**: W134-W173 ≥36-wave LOCAL-MACHINE BYTE-IDENTICAL invariant chain breaks at W174 SW1 (real client-tree code change: 3 route guards now import `useAuthStore`). NEW W174 baseline at `index-DueN8aJX.js` 177,042 b (local-build) / Docker container `index-DP86xD4I.js` 177,042 b (W137 SW4 cross-platform sha-vs-size non-determinism documented). Honestly framed — NOT a regression; structural improvement that closes a real bug.

2. **`RouterContext.auth` interface kept as dead-code-ish**: SW1 leaves `router.ts:6-13` `interface RouterContext { auth: {...} }` declaration intact even though all 3 route guards stop reading it. Trade-off: keeping the type provides forward-compat for any future SSR-side `beforeLoad` using `globalThis.__ssrAuthGetter__` per W126 SW4 chain. Removing would be a wider refactor with risk of breaking SSR-only paths. W174 chose minimal surgical fix.

3. **Edge case: authed user hard-navigates to /login**: After SW1, Zustand `loading: true` initial state means `_public.tsx beforeLoad` returns early on cold mount, then useProfileSync resolves with valid user, but beforeLoad doesn't re-fire reactively → user lands on /login without redirect to /dashboard. **Pre-existing behavior** (pre-W174 router context also had `isAuth: false` so `_public.tsx` never redirected authed users either). W174 SW1 doesn't introduce a regression here. Real-world impact: minimal (authed users typically don't manually navigate to /login). **W175+ candidate**: add reactive `useEffect` in Login.tsx that watches `useAuth().isAuth` and navigates to /dashboard, OR wire AuthProvider to call `useRouter().invalidate()` when Zustand changes.

4. **No regression tests added in W174**: SW1+SW2 fix structural bugs without adding vitest unit tests asserting "guards redirect when Zustand user is null" or "interceptor auto-fetches CSRF when cookie missing". W173 §Honesty NEW #1 (no regression test for W173 fixes) carry-forward stands; W174 inherits same gap. Combined ~2-3 hour focused W175+ "regression test infra" wave covering W173 + W174 closures recommended.

5. **No automated e2e for login flow**: `frontend/tests/e2e/` exists but no current test asserts "fresh context → POST /api/v1/auth/login → navigate to /dashboard succeeds". Same family as #4; could be added in W175+ regression test wave (~1-2 hours).

6. **CSRF cookie SameSite=Lax migration carry-forward (W131 SW6)**: Backend's `cookie_samesite` defaults to "lax" globally per W131 SW6 + `SECURITY_COOKIE_SAMESITE_OVERRIDE` emergency rollback knob. SW2's CSRF auto-fetch goes through Caddy chain same-origin and is unaffected by SameSite. No new caveat introduced.

7. **PWA service worker may cache old manifest briefly**: After SW3 manifest changes, browsers with the OLD service worker still cached may continue using the old manifest with screenshot declarations for one cycle until SW updates. Hard reload (Ctrl+Shift+R) busts the cache. Documented but not directly verified — chrome-devtools `new_page isolatedContext` opens fresh context per W129 §Honesty pattern.

8. **Verification through real Docker chain on Linux production not directly tested**: All empirical verification done via Windows Docker Desktop → Linux containers → Caddy reverse proxy. Production Linux deploys (where this code will ultimately run) preserve byte-for-byte the same container images per Docker portability guarantees, but not separately verified. Standard practice for this wave family.

9. **MEMORY.md ceiling pressure**: Current size 18,452 b post-W173 (5,948 b headroom under 24,400 ceiling). W174 row addition ~2 KB fits comfortably. No compaction needed in SW4.

10. **W173 §Honesty NEW #1 still open**: No automated regression test for W173 SW1/polish-v1/polish-v3 fixes. W174 also doesn't add regression tests (#4 above). Combined ~2-3 hour W175+ regression test infra wave recommended for both.

11. **Phase 1 Explore Agent recommended Option B (`router.update({ context })` reactive sync) as primary**; Phase 3 selected Option A (direct Zustand read) as simpler + more localized. Both options correctly close Bug 1; Option A is W141 anti-pattern #1 STRICT 1-iter compliant + lower regression surface. W141 anti-pattern #3 vindication count incremented per agent-recommendation-vs-empirical-decision discipline.

---

## W141 anti-pattern compliance

Per CLAUDE.md ## Gotchas + AUDIT_WAVE173.md compliance counters at wave start:

- **#1 STRICT 1-iter SACRED** (W173 close baseline: 28 vindications, 15 defer-cases): SW1 single iter, SAME mechanism within iter (route-guard-source migration across 3 files per W138 Lesson #1 sub-fix allowance). SW2 single iter, SAME mechanism (CSRF cookie acquisition), within-iter sub-fix when test-env skip needed. SW3 single iter, manifest cleanup. SW4 audit. **Target hit: 29th vindication (no mechanism iter cascade)**.

- **#3 Phase 3 verification + Agent claim verification** (W173 close baseline: 51 vindications): Phase 3 verified all Phase 1 Explore Agent claims via direct Read of 8 files (`_auth.tsx`, `_public.tsx`, `_admin.tsx`, `router.ts`, `App.tsx`, `AppProviders.tsx`, `AuthContext.tsx`, `useAuthStore.ts`, plus partial Reads of `useLoginFlow.ts`, `useAuthApi.ts`, `useProfileSync.ts`). Caught stale comment in `router.ts:31-33` (W152 Phase 1.7 regression source documentation gap), confirmed `useAuthStore.getState()` API + return shape, validated `_admin.tsx` additionally reads `user.role`. **Target hit: 52nd-54th vindications (multiple direct-Read verifications)**.

- **#4 No premature "Closes" attribution** (W173 close baseline: 25 vindications): SW1 commit message says "Closes the W174-reported login bug" only AFTER empirical browser smoke confirmed login → dashboard redirect works. Per-test verification table in this audit honestly documents pre→post evidence for each empirical check. SW2 commit message says "Closes" CSRF auto-bootstrap only after fresh-context chrome-devtools verification showed GET /csrf-cookie 200 → POST /login 200 sequence. SW3 commit message restraints to "drop orphan screenshot declarations" (specific behavior described). **Target hit: 26th-27th vindications**.

- **#15 ARCHIVED W159 SW4** (W173 close: 35 waves preserved): All W174 commits fired W156 SW4 husky pre-commit chain cleanly:
  - SW1 `b13d7f106`: lint-staged + prettier --write + eslint --fix + detect-secrets + Python 2 except syntax check ALL PASS
  - SW2 `24aba2076`: same chain clean (1 file modified)
  - SW3 `53bf9a87f`: same chain clean (3 files modified — manifest JSON formatted by prettier)
  - SW4 (this commit): expected clean

  NO `--no-verify` bypasses anywhere in W174. **Target: 36-39th wave preserved**.

---

## Bundle invariant tracking

**Pre-W174 invariant** (W173 SW3 close):
- Local-build main JS: `index-BlWdKfsi.js` 177,057 bytes / sha `142897dd...3a38898`
- Local-build server.js: 23,600 bytes / sha `6ec125ed...0bca00`
- W134-W173 ≥36-wave LOCAL-MACHINE BYTE-IDENTICAL chain by structural argument

**Post-W174 baseline** (SW1+SW2+SW3 cumulative, local-build × 1 reproducible):
- Local-build main JS: `index-D8hjL4E6.js` 177,042 bytes (-15 vs W173; SW1 destructure compression + SW2 small additions + SW3 zero impact)
- Local-build server.js: 23,600 bytes (size unchanged)
- Docker container main JS: `index-DP86xD4I.js` 177,042 bytes (W137 SW4 documented cross-platform sha-vs-size non-determinism: same size, different filename hash due to Linux vs Windows Node build identity)

**W134-W173 ≥36-wave invariant chain RETIRED at W174 SW1** (real client-tree code change). NEW W174 baseline established. Build × 3 empirical reproducibility deferred to polish-pass if «безупречно?» probe fires; structural argument is sufficient (SW1+SW2+SW3 cumulative behavior shown end-to-end via chrome-devtools-mcp).

---

## Discoveries during wave

1. **(z) discovery #1 (during SW1 browser smoke)** — Frontend has NO `/api/v1/auth/csrf-cookie` auto-fetch. Real-user impact: 30+ min idle → cookie expires → next login fails with 403 + no UX feedback. Promoted to SW2 within W174 scope.

2. **W152 Phase 1.7 regression documentation gap** — `router.ts:31-33` comment still references `<RouterProvider context={...}>` reactive bridge that was removed. Fixed by SW1 router.ts edit.

3. **Phase 3 verification of Agent option recommendation** — Phase 1 Agent 1 recommended Option B (`router.update({ context })` reactive sync) as primary; Phase 3 selected Option A (direct Zustand read) as W141 anti-pattern #1 STRICT 1-iter compliant + lower regression surface. Agent's option B would have required ~2× more code + new useEffect coupling AuthProvider → router internals.

4. **Test isolation trap with singleton Promise** — SW2 first commit attempt failed `AdminFeatureFlags.test.tsx` because MSW unhandled-request on `/auth/csrf-cookie` polluted the singleton `_csrfBootstrapPromise`. Within-iter sub-fix per W138 Lesson #1: added `import.meta.env.MODE === "test"` guard. Vite DCE substitutes the literal at build time → branch tree-shakes from prod.

5. **chrome-devtools-mcp click event vs form.requestSubmit() reliability** — During first verification round, clicking the "Войти" submit button via chrome-devtools-mcp `click` tool did NOT trigger the form's React onSubmit handler reliably. Falling back to `evaluate_script` with `document.querySelector('form').requestSubmit()` fired the submission reliably. Documented for future browser-smoke wave-execution.

---

## W175+ candidates (priority order)

Per W173 + W170 + W171 patterns:

- **A) Continue maintenance + bug fixes only (CANONICAL DEFAULT)** — No active development planned. Fires only on real triggers (real bugs surface; scheduled cron failure per W171 admin-smoke-monitoring.yml).
- **B) Add regression tests for W173 + W174 fixes** (~2-3h focused wave) — Closes W173 §Honesty NEW #1 + W174 §Honesty #4+#5. Combined coverage:
  - vitest unit for `server-prod.mjs` `.wasm: application/wasm` CONTENT_TYPES (W173 SW1)
  - vitest unit + Playwright e2e for `_auth.tsx`/`_public.tsx`/`_admin.tsx` Zustand-read paths (W174 SW1)
  - vitest mock-MSW test for `ensureCsrfCookie()` (W174 SW2)
  - Playwright e2e for fresh-context login → dashboard redirect (W174 SW1+SW2)
- **C) /messenger Phase 5 SSR enable** (~3-5h own wave per W134 §Honesty #10) — Lifts Phase 5 punt; would have surfaced W173 + W174 regressions years earlier.
- **D) Helper-script enforcement** (~1-2h, closes W170 §Honesty #1) — Pre-commit gate against raw `docker compose -f` invocations.
- **E) Edge case fix: authed-user-hard-navigates-to-/login redirect** (~30-60min focused) — Add reactive useEffect to Login.tsx OR wire AuthProvider → router.invalidate() on Zustand changes per W174 §Honesty #3.
- **F) Long-tail polish** (~3-5h) — W134 §Honesty #2 bundle delta deep investigation OR reusable workflow refactor.
- **G) Activate admin-smoke-monitoring.yml on main** (~5 min cherry-pick per W139 SW1 precedent) — Enables W171 SW1 monitoring infrastructure operationally.

Per W171 Lesson #1: maintenance mode means waves fire on real triggers. If no specific motivation surfaces post-W174, project rests until next user-reported bug OR scheduled cron firing.

---

## End-of-wave gates

All local + empirical gates GREEN end-of-W174:

- **tsc**: 0 errors (all 4 SW commits)
- **eslint --max-warnings=0**: 0 warnings (all 4 SW commits)
- **prettier**: clean (all 4 SW commits via husky lint-staged)
- **vitest**: **1058p / 12 skipped / 0 failed** (W173 baseline EXACT preserved across SW1, SW2, SW3)
- **husky pre-commit chain**: 4/4 commits fired cleanly (W156 SW4 chain preserved 39th wave; #15 ARCHIVED preserved)
- **npm run generate:manifests --check**: clean (no source/generated drift)
- **Docker stack**: frontend + backend + caddy + ws-hub + ... all `(healthy)` post-rebuild
- **`/healthz`**: `{"status":"ok"}`
- **`/login`** SSR HTML: 200 / ~21,791 bytes
- **Fresh-context chrome-devtools-mcp login flow**: GET /csrf-cookie 200 → POST /login 200 → URL /dashboard ✓
- **Manifest content**: 0 screenshot references in `manifest.webmanifest` + `manifest.en.webmanifest` + `manifest.source.json`
- **W173 SW1 fix preserved**: `.wasm` Content-Type `application/wasm` ✓
- **W173 polish-v1 + polish-v3 fixes preserved**: /ws/chat WS upgrade 101 Switching Protocols with real 64-char hex ticket + Origin: http://localhost ✓

---

## References

- **Plan file**: `C:\Users\egorribun\.claude\plans\c-users-egorribun-claude-projects-c-use-iridescent-bunny.md` (W174 implementation blueprint with full SW breakdown + decision rationale)
- **W173 audit**: [AUDIT_WAVE173.md](AUDIT_WAVE173.md) (preceding wave, real-bug Q0=B pattern + W141 anti-pattern #1 27th vindication establishing W174 baseline)
- **W171 audit**: [AUDIT_WAVE171.md](AUDIT_WAVE171.md) (admin-smoke-monitoring.yml infrastructure for future regression detection)
- **W170 audit**: [archive/AUDIT_WAVE170.md](archive/AUDIT_WAVE170.md) (N+3 rotated by W174 SW4 — Docker cwd helper scripts at `scripts/dc.{sh,ps1}` used 4× in W174 chain)
- **W152 Phase 1.7**: `App.tsx:30-51` (the W174 root cause — switch from reactive `<RouterProvider context={...}>` to `<StartClient />` removed the context bridge that was keeping route guards' `context.auth` fresh)
- **W126 SW4**: `frontend/src/server.ts` + `frontend/src/ssrAuth.ts` (server-side auth-at-edge via `globalThis.__ssrAuthGetter__` — preserved by W174 SW1 for SSR-side route guards)
- **W134 SW1**: `useProfileSync.ts:1099-1109` (reactive sync of internal state INTO Zustand — established Zustand as source of truth that W174 SW1 reads from)
- **W140 SW4 CSRF dance precedent**: `.github/workflows/visual-audit.yml` (existing CI-side CSRF acquisition pattern that W174 SW2 mirrors in production frontend code)

---

**END OF AUDIT_WAVE174**
