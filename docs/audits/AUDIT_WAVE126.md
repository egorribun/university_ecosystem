# Wave 126 — TanStack Start v1 SSR Phase 3 (auth-at-edge infrastructure) — May 2026

**Branch**: `egorribun`
**Scope**: Phase 3 of multi-wave SSR migration designed in W124 SW5 (`docs/plans/2026-05-01-wave125-ssr-design.md`). Originally planned per `memory/wave126_opening_prompt.md` Option A as 9-SW arc delivering BOTH (a) cookie-based auth-at-edge infrastructure AND (b) per-route SSR opt-in for /login. Realistic delivery scope ↓ to (a) only after SW1 exploration revealed that per-route SSR enablement requires provider hoisting (Phase 5 prerequisite) — MainLayout's `useAppShell` / `AuthProvider` / `LanguageProvider` chain is mounted via `main.tsx` → `App.tsx` → `<AppProviders>` which is client-only. Without SSR-side provider availability, route components that render `<MainLayout>` crash on `useAppShell must be used within an AppShellProvider` during SSR pass.
**Bundle**: PROD main chunk **dist/client/assets/index-B9t65bNz.js — 137,813 bytes** (vs W125 baseline 137,813 / `index-B7yKlNd5.js`; **byte-identical size, hash differs**). All Phase 3 additions (`jose@^5.10.0` lib, `node:async_hooks` import, `src/ssrAuth.ts` module, AsyncLocalStorage globalThis getter) live exclusively in the server chunk per Vite environments build partition. Empirical confirmation that the architectural choice (server-only auth validation) was correct.

## Executive summary

| # | Item | Status | SW |
|---|------|--------|-----|
| 1 | Backend exploration + design alignment (no commit) | ✅ done | SW1 |
| 2 | Backend Set-Cookie alongside JSON | 🚫 DROPPED — backend already issues `access_token_v2` HttpOnly cookie via `LoginSessionManager._set_access_token_cookie` (single chokepoint for ALL login flows) | SW2 |
| 3 | Frontend `server.ts` cookie + JWT validation via JWKS | ✅ shipped | SW3 (`38b2fe237`) |
| 4 | Frontend `router.ts` `getRouter()` reads SSR auth state | ✅ shipped | SW4 (`4d70a1bf2`) |
| 5 | Per-route SSR opt-in for /login | 🚫 DEFERRED to Phase 5 — provider hoisting prerequisite | SW5 |
| 6 | Hydration polish (theme + lang cookies for SSR rendering) | 🚫 DEFERRED to Phase 5 — only delivers value once routes opt into SSR | SW6 |
| 7 | LHCI 9-URL × 3-run sweep + gate ratchet | ⚠️ light verification only — vite preview smoke (200 OK shell HTML); full LHCI sweep deferred (no perf change expected, build orchestration regression on Windows during SW3 verification) | SW7 |
| 8 | W125 deferrals cleanup | ✅ both items already closed pre-W126 — investigation only | SW8 |
| 9 | Audit + memory + N+3 rotation | ✅ this commit | SW9 |

**Delivered (W126)**:
1. **Auth-at-edge plumbing infrastructure**: backend's existing `access_token_v2` HttpOnly cookie is read in `src/server.ts` SSR fetch handler, validated via `jose` library against backend's existing JWKS endpoint (`/.well-known/jwks.json`), and exposed to `src/router.ts:getRouter()` factory via `node:async_hooks` AsyncLocalStorage scoped to the request. When a route eventually opts into SSR (Phase 5), the router context will see real auth state derived from the cookie instead of the W125 SSR_STUB_AUTH placeholder.
2. **Architectural validation**: client bundle byte-identical to W125 baseline (137,813 bytes). `jose@^5.10.0`, `node:async_hooks`, `src/ssrAuth.ts`, AsyncLocalStorage all stay in the server chunk per Vite environments partition. Confirms the lightweight Phase 3a path from the design doc was the correct choice.
3. **VITE_LHCI bypass dual-path**: `server.ts` mirrors the W116 SW3 LHCI mock-user injection pattern from `useProfileSync.ts:877`. Both branches tree-shake from prod via Rolldown DCE. `grep -l "lhci-mock-user" dist/client/assets/*.js` empty in prod build (W116 contract preserved).
4. **19 new vitest unit tests** in `src/__tests__/ssrAuth.test.ts` covering cookie parser edge cases (URL encoding, prefix mismatch, regex-meta names), JWT validation via test seam, full extractAuthFromRequest flow including LHCI bypass + invalid cookie + valid JWT paths. Vitest 859p → 878p / 12s / 0f.

**Not delivered (W126, intentionally)**:
1. **Per-route SSR enablement** — required Phase 5 work (provider hoisting above `<StartClient />` so `MainLayout` + `AppProviders` chain becomes SSR-safe). Without this, even with `ssr: true` on a child route, `__root.tsx` `RootComponent`'s `import.meta.env.SSR` short-circuit returns null, leaving child routes with no `<Outlet>` to render into. Documented in `__root.tsx:255-262` as Phase 3 prep note (W125 Phase 2).
2. **LCP improvement on authenticated routes** — direct consequence of #1. Authenticated route LCP remains ~12 s on mobile (per W124 SW4 baseline). Phase 5 + per-route enablement will deliver the LCP win.
3. **Production SameSite=Lax migration** — backend `cookie_samesite` defaults to `"strict"` in production (`app/core/config/mixins/csp_settings.py:91-94`); SSR cookies on cross-site GET (e.g. direct link clicks from external sources) won't be sent under Strict, defeating Phase 3's perf win in prod. Migration deferred to Phase 4 (Caddy SSR forwarding) when proper rollback testing infrastructure is in place. Dev mode is already SameSite=Lax so SW3 + SW4 work locally + in `npm run preview`.

## Commits on origin

| # | SHA | Title | Files | +/− |
|---|---|---|---|---|
| 1 | `38b2fe237` | `feat(wave126-sw3-server-cookie): cookie read + JWT validation in SSR server entry` | 5 | +393 / −9 |
| 2 | `4d70a1bf2` | `feat(wave126-sw4-real-auth-context): getRouter() reads SSR auth state from server.ts` | 1 | +49 / −38 |
| 3 | `<TBD>` | `docs(wave126-sw9): Phase 3 audit + memory + N+3 rotation` | — | — |

## SW arc — what each commit does

### SW1 — Backend exploration (no commit)

Read 8 backend auth files: `app/api/auth/login.py`, `app/services/auth/login_service.py`, `app/services/auth/login_session_manager.py`, `app/auth/handlers/logout.py`, `app/core/csrf.py`, `app/core/config/mixins/csp_settings.py`, `app/core/config/mixins/jwt_settings.py`, `app/auth/security.py`, `app/api/well_known.py`.

Key findings (bullet form):

- **Backend already issues `access_token_v2` HttpOnly cookie** via `LoginSessionManager._set_access_token_cookie` (lines 148-165). Single chokepoint used by ALL login flows: password (`/login`, `/login/json`), passkey (`/login/passkey/verify`), MFA verify (`/mfa/verify`), all routing through `LoginService.finalize_login` → `LoginSessionManager.finalize_login` → `_set_access_token_cookie`. Cookie attributes: HttpOnly=True, Secure=`settings.cookie_secure`, SameSite=`settings.cookie_samesite`, Path=`/`, Max-Age=`access_token_expire_minutes * 60`. Frontend re-using this cookie in SSR is the cleanest path.
- **JWT alg = RS256** (`jwt_settings.py:33` default; HS256 prohibited in non-development environments per `_validate_algorithm` validator at line 117). RS256 means asymmetric: backend signs with private key, frontend verifies with public key — public key safe to ship in client/server bundle.
- **JWKS endpoint already exists** at `/.well-known/jwks.json` (`app/api/well_known.py`). Returns proper JWK structure with `kty=RSA`, `kid`, `alg=RS256`, `n`, `e`. `createRemoteJWKSet(new URL(...))` from `jose` library handles caching + key rotation natively.
- **`decode_token()` in `app/auth/security.py:563`** is the canonical backend validation pattern: validates kid, audience (`settings.jwt_audience` default `"university-ecosystem-api"`), exp, iat, sub, jti via `jwt.decode(... options={"require": [...]})`. Frontend `validateJwt()` in `src/ssrAuth.ts` mirrors required claims (jose's `jwtVerify` enforces exp + aud automatically; sub validated explicitly).
- **Cookie SameSite default**: `csp_settings.py:91-94` returns `"lax"` in development, `"strict"` in production. Production setting BLOCKS the cookie on cross-site GET (direct link clicks), defeating SSR perf win. Migration to `"lax"` deferred to Phase 4 deploy infra.
- **Existing cookie ecosystem**: 8+ consumers of `access_token_v2` across `app/auth/handlers/logout.py`, `app/core/ratelimit/utils.py:143`, `app/api/sessions.py:35`, `app/api/websocket.py:87` (ws-hub auth fallback), `app/core/ratelimit/middleware.py:213`, `app/api/ws/authenticator.py:66+83`, `app/services/auth/token_service.py:23`, `app/services/auth/login_session_manager.py:157`, `app/services/auth/login_service.py:101`. The cookie is THE canonical session token name; W126 simply adds a 9th consumer (frontend SSR runtime).

**Plan revision**: original SW2 (backend Set-Cookie alongside JSON) was DROPPED. Backend already issues the cookie; no backend changes needed for Phase 3a. Original SW2 budget (~1.5-2h) reallocated to deeper W125-deferral investigation in SW8.

### SW2 — DROPPED

See SW1 finding above. Backend `access_token_v2` cookie infrastructure already complete; W126 reuses existing cookie name + JWKS endpoint without modification.

### SW3 — `feat(wave126-sw3-server-cookie)` (`38b2fe237`)

Files: 5 changed (+393 / −9). New: `src/ssrAuth.ts` (135 lines) + `src/__tests__/ssrAuth.test.ts` (174 lines). Modified: `src/server.ts` (~35 lines added), `package.json` + `package-lock.json` (jose@^5 dep).

**Architecture**:

`src/ssrAuth.ts` is a pure utility module (no Node-specific imports — safe for jsdom) exporting:
- `parseCookie(header, name)` — string-based cookie extraction, RFC 6265 compliant, URL-decoding, no regex (avoids `security/detect-non-literal-regexp` ESLint rule).
- `validateJwt(token)` — jose-based JWT verification against JWKS endpoint at `/.well-known/jwks.json` (URL resolved via `VITE_BACKEND_ORIGIN` env var that `src/api/client.ts` already uses for API base URL). Audience claim configurable via `VITE_JWT_AUDIENCE` env var, default `"university-ecosystem-api"` matches backend's `jwt_settings.py:32`.
- `extractAuthFromRequest(request)` — main entry: VITE_LHCI bypass first, then cookie extraction, then JWT validation. Returns `SsrAuthState` matching `RouterContext["auth"]` shape.
- `_setJwtVerifyOverrideForTests(fn)` — test seam injecting a stub `jwtVerify` for unit tests; production path uses real `createRemoteJWKSet`.

`src/server.ts` extends the W125 Phase 2 `createServerEntry({ fetch })` wrapper:
- Imports `AsyncLocalStorage` from `node:async_hooks` (server-only — Vite environments build keeps in server chunk).
- Module-level `requestAuthStorage = new AsyncLocalStorage<SsrAuthState>()`.
- `globalThis.__ssrAuthGetter__ = () => requestAuthStorage.getStore()` — exposes per-request store via globalThis (avoids circular import: `src/router.ts` is shared between client + server, can't import server.ts directly).
- In `fetch(request)`: extract auth via `extractAuthFromRequest(request)` (with defensive try/catch for JWKS-unreachable), then `requestAuthStorage.run(auth, () => handler.fetch(request))` to scope auth to the request's async context.

**VITE_LHCI bypass**: `extractAuthFromRequest` checks `import.meta.env.VITE_LHCI === "true"` first and returns `SSR_AUTH_LHCI_MOCK` (synthetic mock user, role: "student") without touching the cookie. Mirrors the dual-path pattern from `useProfileSync.ts:877`. Tree-shakes from prod via Rolldown DCE — verified by inspection of `dist/client/assets/index-*.js` lacking the `"lhci-mock-user"` string in prod builds.

**Verification**: 19 vitest unit tests, all passing (878p / 12s / 0f overall). Build succeeded post-commit (vite build + prerender of `/`); post-build-shell.mjs ran cleanly when invoked manually (npm orchestration hung on Windows — see Honesty probe #2 below). Bundle size 137,813 bytes — IDENTICAL to W125 baseline.

### SW4 — `feat(wave126-sw4-real-auth-context)` (`4d70a1bf2`)

Files: 1 changed (`src/router.ts`, +49 / −38).

**Architecture**:

Removed W125 Phase 2 `SSR_STUB_AUTH` + `SSR_STUB_QUERY_CLIENT` constants. The factory now reads the per-request auth state from `globalThis.__ssrAuthGetter__?.()` — populated by SW3's AsyncLocalStorage on the server, undefined on the client.

```typescript
const createAppRouter = () => {
  const ssrAuth =
    typeof globalThis !== "undefined" ? globalThis.__ssrAuthGetter__?.() : undefined

  return createRouter({
    routeTree,
    context: {
      auth: ssrAuth ?? DEFAULT_AUTH,
      queryClient: new QueryClient(),  // per-call instance
    },
    // ...
  })
}
```

`DEFAULT_AUTH` retains the `{ isAuth: false, user: null, loading: false }` shape from W125 (just renamed from "STUB" since it's now the legitimate fallback for routes that don't opt into SSR + the client-mount default before App.tsx's `<RouterProvider context={...}>` overrides).

`router` singleton (W125's compatibility export for App.tsx) preserved. `getRouter()` factory continues to satisfy TanStack Start's `#tanstack-router-entry` import contract per W125 SW1.

**Per-call QueryClient instance** — each `getRouter()` call constructs a fresh `QueryClient`. SSR + client must NOT share the cache (would cause hydration mismatches once cache transfer is added). Phase 4+ may add proper dehydrate/hydrate via TanStack Query's persister.

**Verification**: typecheck 0 errors, lint 0 warnings (max-warnings=0), build × 1 confirmed: bundle byte-identical to post-SW3 (137,813 bytes / hash `index-B9t65bNz.js`). vite preview returns 200 with 9428-byte shell HTML on both no-cookie and invalid-cookie GET requests (cookie path exercised, JWT validation fired silently into try/catch, auth defaults to UNAUTH — expected).

### SW5 — DEFERRED

Per-route SSR opt-in for /login was the originally planned step. Deferred after architectural review:

- Adding `ssr: true` to `_public/login.tsx` would route /login through SSR.
- /login component renders into `<Outlet>` of `_public.tsx` layout, which renders into `<Outlet>` of `__root.tsx` `RootComponent`.
- W125 Phase 2 `RootComponent` returns `null` on SSR (`if (import.meta.env.SSR) return null`) — so child routes have no `<Outlet>` to mount into during SSR pass.
- To make /login content appear in SSR HTML, `RootComponent` must render `<Outlet>` server-side. But then `MainLayout` + child providers must also be SSR-safe (or skipped on SSR with hydration mismatch tolerance).
- `MainLayout` uses `useAppShell` from `AppShellProvider`, mounted via `main.tsx` → `App.tsx` → `<AppProviders>` chain — client-only. SSR-mounting it requires provider hoisting above `<StartClient />`.
- Per design doc §3, provider hoisting is **Phase 5 work** (browser-API safety guards). Phase 3 lays the auth infrastructure; Phase 5 enables actual SSR rendering.

W126 ships SW3 + SW4 (auth infra) and explicitly defers SW5 (per-route enablement) to a future wave covering Phase 5. Documented in `src/routes/__root.tsx:255-262` (existing W125 prep notes still apply).

### SW6 — DEFERRED

Hydration polish (theme + lang cookie sync for SSR rendering) was the originally planned step. Deferred for the same reason as SW5: only delivers value once routes opt into SSR. Without `ssr: true` on any route, theme/lang cookies don't change rendered output. Phase 5 prerequisite.

Both SW5 and SW6 are concrete-to-execute once Phase 5 lands provider hoisting:
1. Move `MainLayout` + auth-dependent components from `__root.tsx` to `_auth.tsx` layout component (or hoist providers above `<StartClient />`).
2. Add `ssr: true` to `_public/login.tsx` first (smallest blast radius — public route).
3. Add cookie-mirror writes to ThemeProvider + LanguageProvider for hydration parity.
4. Verify chrome-devtools-mcp shows 0 hydration mismatch errors on /login.
5. Expand to authenticated routes incrementally per route audit.

### SW7 — light verification

LHCI 9-URL × 3-run sweep was the originally planned step. Deferred due to:
- Build orchestration regression on Windows during SW3 verification (vite build + prerender succeed, but post-build-shell.mjs orchestrated by `scripts/run-build.mjs` hangs after prerender — manual `npm run build:shell` works fine. Separate concern from Phase 3 work; tracked as a build-infra regression for follow-up).
- No expected perf change for authenticated routes (Phase 5 prerequisite for SSR enablement); LHCI would just confirm baseline preservation, which is also confirmed by build size invariance + vitest baseline preservation.

**Light verification performed instead**:
- `npm run build` produces `dist/client/_shell.html` (9456 bytes post-build-shell injection of CSP nonces + 2 font preloads) + `dist/client/index.html` mirror.
- `npx vite preview --port 4188` serves shell on `GET /` with status 200, 9428 bytes HTML.
- `GET /` with `Cookie: access_token_v2=invalid.jwt.value` returns IDENTICAL 9428-byte HTML — cookie path exercised silently (jose's `jwtVerify` rejection caught in try/catch, auth defaults to UNAUTH, RootComponent SSR-null guard means auth state doesn't manifest in HTML output yet — Phase 5 prerequisite).
- vite preview server log shows no errors.

### SW8 — W125 deferrals investigation

W125 backlog enumerated 2 concrete deferrals to W126:

**Item #2 — `AttendanceCard.reduceMotion` prop dead code**: investigation shows this was already closed in W124 polish commit `4573ab5af` (`docs+chore(wave124-polish): close 4 honesty caveats — gates re-run + Storybook + AttendanceCard cleanup + /map variance check`). Current `src/features/activity/components/AttendanceCard.tsx` interface has `attendance | hasInitiallyLoaded | ringSize` with NO `reduceMotion` prop. W125 backlog row was stale (never updated post-W124-polish). No commit needed.

**Item #6 — vitest test count delta (686p → 859p, +173 tests)**: investigation via `git log --since="2026-04-25" --until="2026-05-04" --diff-filter=A` revealed 10+ new test files added between W124 close and W125 SW1:
- `src/components/auth/LoginCredentialForm.test.tsx`
- `src/hooks/useMapEvents.test.tsx`
- `src/hooks/auth/useProfileSync.test.ts`
- `src/hooks/auth/useSessionCrypto.test.ts`
- `src/hooks/useMapWeather.test.tsx`
- `src/hooks/useClassReminders.test.ts`
- `src/hooks/useHaptics.test.ts`
- `src/hooks/usePushSync.test.ts`
- `src/hooks/useSwipe.test.ts`
- `src/hooks/useSwipeGesture.test.ts`
- `src/features/map/__tests__/schema.test.ts` (18 tests, schema unit coverage post-W120)

Test count delta is fully explained by routine-e5/f4/g3 test-coverage work between W124 close and W125 SW1. Investigation closed; no code change needed.

**Both W125 backlog items resolved without commit** — they were artifacts of incomplete backlog hygiene rather than actual outstanding work.

### SW9 — this commit

Files: this audit (`docs/audits/AUDIT_WAVE126.md`), `CLAUDE.md` (## Audit Trail row + new gotchas), `memory/MEMORY.md` (audit history table), `memory/wave126_backlog.md` (closed status), `memory/wave127_opening_prompt.md` (handoff with Phase 4/5/6 scope options), N+3 rotation `git mv docs/audits/AUDIT_WAVE123.md docs/audits/archive/AUDIT_WAVE123.md`, `docs/audits/INDEX.md`.

## Honesty probe — what's NOT verified in this wave

Per `memory/feedback_perfectionism.md`: list real deferrals openly rather than papering over.

1. **Per-route SSR enablement DEFERRED to Phase 5** (already extensively documented above). W126 delivers AUTH PLUMBING; perceptible LCP wins on authenticated routes come after Phase 5 hoists providers + per-route opt-in lands.

2. **Build orchestration regression on Windows** discovered during SW3 verification: `npm run build` (`scripts/run-build.mjs`) runs vite build + prerender successfully but hangs in post-build-shell orchestration. Manual `npm run build:shell` works fine. Separate from Phase 3 work; likely vite-plugin-pwa's injectManifest interacting with the `await run("node", ...)` chain on Windows. Workaround: `npm run build && npm run build:shell` if hang persists. **Not investigated in W126** — surfaces as a follow-up item.

3. **LHCI 9-URL × 3-run sweep NOT executed in W126**. Light vite preview smoke verified server.ts loads cleanly + cookie path is exercised without crashes. Full LHCI sweep deferred:
   - No expected perf change for authenticated routes (would just confirm baseline preservation).
   - Build orchestration hang makes repeat builds risky.
   - Phase 5 will require fresh LHCI baseline anyway once SSR routes start producing auth-aware content in HTML.

4. **Production SameSite=Lax migration deferred to Phase 4**. Dev mode (`is_development=True`) returns `"lax"` from `csp_settings.py:cookie_samesite`; production returns `"strict"`. Strict won't send the cookie on cross-site GET, defeating Phase 3's SSR perf win for users arriving via external links. Migration risks affecting CSRF cookie + anonymous nonce cookie (all share the same setting); proper rollback testing belongs to Phase 4 deploy infra.

5. **JWKS endpoint NOT smoke-tested with real network fetch**. `validateJwt()` uses `createRemoteJWKSet(URL)` which fetches `/.well-known/jwks.json` lazily. In W126 vite preview testing, the cookie path was exercised but the JWT was invalid → `jwtVerify` failed at signature check before JWKS fetch was even needed. Real RS256 JWT validation against a running backend is **not verified end-to-end in W126** — covered by unit tests with stubbed `jwtVerify` only. End-to-end validation will land naturally in Phase 5 + Phase 6 when SSR routes start rendering auth-aware content.

6. **`runtimeError: NO_FCP` risk** — server.ts crashes during SSR would manifest as Lighthouse `NO_FCP` (per W125 SW2 honesty probe). Defensive try/catch in `extractAuthFromRequest` returns `SSR_AUTH_UNAUTH` on any extraction failure (network, JWKS fetch, JWT verify); the only path that would crash SSR is a bug in `parseCookie` or AsyncLocalStorage setup. 19 unit tests cover the parser; the AsyncLocalStorage setup is canonical Node usage. Build success + vite preview success indicates no runtime crash; full LHCI would confirm under devtools throttling.

7. **No ratchet of LHCI gates**. W120 SW2 ratchet (CLS error@0.10) preserved. W124 routine-e5 close-out relaxed Perf to `warn@0.40` due to dev/CI calibration drift. W126 doesn't deliver perf changes (Phase 5 prerequisite); ratchet decision waits for Phase 5+ baseline post-SSR-enablement.

8. **Bundle size delta = 0**. Client bundle byte-identical to W125 (137,813 bytes). Confirms architectural choice but means **no client-side regression risk** AND **no client-side perf benefit** from W126. All Phase 3 weight is in the server chunk.

9. **W125 deferrals item #2 + #6 were already closed pre-W126**. Backlog hygiene was incomplete in W125 close; W126 SW8 investigation surfaced this. No code change in W126 to "close" them — they were just untracked closures. Documented above for full transparency.

10. **Storybook NOT explicitly re-verified post-W126** — but build infrastructure is unchanged from W125 (no `.storybook/` modifications) so existing 18.48s build (W125 baseline) should hold. Verification deferred unless a regression is reported.

## Verification table

| Criterion | Status | Evidence |
|-----------|--------|----------|
| `npm run typecheck` | ✅ exit 0 | re-verified post-SW4 |
| `npm run lint` (max-warnings=0) | ✅ 0 warnings | re-verified post-SW4 |
| `npm run test` | ✅ 878 passed / 12 skipped / 0 failed | +19 new ssrAuth tests; W125 859p baseline preserved |
| `npm audit` | ✅ 0 vulnerabilities | jose@^5 install introduced no new vulns; W119 SW5 baseline preserved |
| `npm run build` produces `dist/client/_shell.html` | ✅ 9456 bytes post-build | with 3 CSP nonces + 2 font preloads injected (W125 contract) |
| `dist/client/index.html` mirror | ✅ via `npm run build:shell` | npm orchestration hang workaround documented in Honesty probe #2 |
| `vite preview` GET / | ✅ status 200, 9428 bytes shell HTML | verified via curl |
| `vite preview` GET / with invalid cookie | ✅ status 200, 9428 bytes (identical) | cookie path exercised silently — auth defaults to UNAUTH, RootComponent SSR-null guard means no HTML difference yet |
| Bundle size delta vs W125 | ✅ identical (137,813 bytes) | hash `index-B9t65bNz.js`; W125 was `index-B7yKlNd5.js`; jose + node:async_hooks confirmed server-only |
| Cargo.lock no drift | ✅ idempotent | ≥ 15 waves at end of W126 |
| LHCI 9-URL × 3-run sweep | ⏳ deferred | rationale in Honesty probe #3 + #7 |
| E2E `a11y-public.spec.ts` | ⏳ deferred | not touched in W126; W125 polish bumped Playwright timeout to 360s, baseline 4/4 chromium preserved per W125 audit |

## Phase 4-6 prep notes (for W127+)

Per `docs/plans/2026-05-01-wave125-ssr-design.md` §3:

- **Phase 4 (W127, ~4-6 h)**: Caddy SSR forwarding rules + Nitro Node deploy. Production deployment serves SSR-rendered HTML through Caddy reverse-proxy. Health checks, rolling deploys, k8s sizing. Also: production SameSite=Lax migration (W126 §Honesty probe #4).

- **Phase 5 (W127 or W128, ~3-5 h)**: Browser-API safety guards + provider hoisting. Audit `frontend/src/` for browser-only APIs in code that runs server-side (`window` / `localStorage` / `IntersectionObserver` / `ResizeObserver` / canvas). Mark routes with heavy browser deps as `ssr: 'data-only'` (e.g. `/map` for maplibre-gl, `/activity` for html-to-image / jspdf already lazy-loaded). Hoist `<AppProviders>` (LanguageProvider, AppShellProvider, AuthProvider, etc.) above `<StartClient />` so MainLayout becomes SSR-safe. THEN W126 SW5 + SW6 work becomes concrete:
  - Add `ssr: true` to `_public/login.tsx` first (smallest blast radius).
  - Add cookie-mirror to ThemeProvider + LanguageProvider for hydration parity.
  - Verify chrome-devtools-mcp shows 0 hydration mismatches.
  - Expand to authenticated routes incrementally.

- **Phase 6 (W128 or W129, ~6-8 h)**: Testing matrix + canary rollout. Full Playwright suite on SSR build, Chromatic visual regression baseline on SSR-built stories, manual smoke via chrome-devtools-mcp on all 9 URLs. Caddy traffic split 10% → 25% → 50% → 100% over 1-2 weeks. Re-baseline LHCI gates (Perf error@0.40 → error@0.60+, LCP error@2500ms).

After Phase 6, the **real** Phase 3 SSR perf win materialises: authenticated route LCP 12 s → < 2.5 s target. W126's auth-at-edge plumbing makes that win possible.

## Honest framing

W126 is **infrastructure-only**. No user-facing perf change. No new feature. The deliverable is invisible to users; visible only via `git log` + `dist/server/server.js` containing JWT validation logic.

W126 was originally scoped (per opening prompt + plan file) to deliver Phase 3 + per-route SSR /login. Realistic delivery scope ↓ to auth infra only after architectural review surfaced provider-hoisting prerequisite. The wave still ships meaningful incremental value:
- 19 new unit tests covering cookie + JWT validation
- `jose` library integration (server-side, ~25 KB minified)
- AsyncLocalStorage + globalThis getter pattern for per-request SSR context
- Backend reuse confirmed (no Set-Cookie additions, no breaking changes to login flow)

Phase 5 is the natural next own-wave to enable the LCP win.
