# Wave 125+ — SSR Pre-flight Design (TanStack Start v1 migration)

**Status**: DESIGN — written in W124 SW5 as pre-flight for W125+ own-wave execution.
**Author**: W124 SW5 (`docs(wave124-sw5-ssr-preflight)`)
**Plan source**: master plan W124 SW5 spec; W124 SW4 variance findings; CLAUDE.md gotchas catalog.
**Decision required pre-W125 kickoff**: user goes/no-goes (feature work vs perf priority).

---

## 1. Why SSR for Wave 125+

### Current state (post-W124)

Authenticated routes ship a SPA bundle that the browser:
1. Downloads HTML shell (essentially empty `<div id="root">`)
2. Downloads ~180 KB main JS chunk (`index-DU71Xr66.js`) + 47 modulepreload chunks (~600 KB total raw)
3. Parses + evaluates JS
4. React renders, Suspense kicks off lazy chunks (NewsDetail / EventDetail / Activity / Map)
5. Auth check runs (`_auth.tsx` beforeLoad), redirects to `/login` if unauthenticated
6. Authenticated routes fire useQuery → API → render with data
7. Hero image discovered after component mount → fetched → painted (LCP candidate)

**Measured cold-cache LCP on mobile (devtools throttling)** per W124 SW4:
- /, /dashboard: **~12.3-12.5 s** (best case 10.6-10.7 s warm cache)
- Cumulative work: HTML parse → JS download → JS parse → React render → API fetch → image fetch

This is **structurally bottlenecked** on round-trips (HTML → JS → API → image) that SSR collapses into a single server-rendered HTML payload with hero image inlined as `<link rel="preload">` from the route loader data.

### Target

- **LCP < 2.5 s on mobile (devtools throttling)** for authenticated routes — currently 12 s, ~5× improvement needed
- WCAG Good CLS preserved (≤ 0.1; current cross-session median 0.017 per W124 SW4 — well within budget)
- Perf score 0.80+ on `/`, `/dashboard`, `/news`, `/events` (current 0.46-0.49 per W124 SW4)
- **NO regression** on authentication flow, offline PWA, push notifications, e2e tests, axe a11y, Chromatic visual baselines

### Why NOT smaller perf wins (font preload, vendor splits, etc.)

Wave 117-124 already harvested the SPA-side perf wins:
- W117 SW3: OTEL deferred via requestIdleCallback (-41% main chunk)
- W117 SW5: picsum preconnect
- W122 SW1: image asset replacement (~875 KB savings)
- W122 SW2: vendor-pdf truly lazy (162 KB unused-JS savings)
- W124 SW1: LazyMotion+domAnimation (-56.6 KB on vendor-ui)
- W124 SW2: critical font preload (~50-150 ms FOIT win)

Cumulative SPA bundle: **~180 KB main + ~106 KB vendor-ui + ~75 KB vendor-sentry + ~106 KB vendor-otel async** = main critical path ~360 KB. Further SPA optimization yields diminishing returns (per W124 SW3 NO-OP audit).

The remaining ~10-12 s of LCP latency is **inherent to client-side rendering of authenticated content** — only SSR collapses the round-trip waterfall.

---

## 2. Approach options matrix

| Option | Tech | Effort | Pros | Cons | Recommendation |
|--------|------|--------|------|------|----------------|
| **A** — `@tanstack/react-start` v1 full migration | TanStack Start v1 + Nitro server runtime | **30-50 h multi-wave** | Framework-supported (uses TanStack Router we already have); SSR + streaming + server functions; production-ready since March 2026; 6M weekly downloads; active maintenance; `ssr: 'data-only'` mode for browser-API routes (Map, Activity); compatible with Vite 8 / Rolldown | Multi-wave migration; AppProviders refactor; Caddy reverse-proxy config; new server runtime to deploy/monitor | **RECOMMENDED** — best ROI long-term, future-proof, matches existing TanStack Router foundation |
| **B** — `vite-prerender-plugin` partial (public routes only) | Vite plugin that pre-renders specified routes at build time | **6-10 h** | Simple; no server runtime change; closes /login + /404 LCP | Doesn't help authenticated routes (which is where the LCP pain actually IS — /login is already 0.56-0.57 Perf, NOT a problem); marginal ROI for the work invested | NO — solves the wrong problem |
| **C** — Custom Express SSR layer | Hand-written Express + react-dom/server.renderToPipeableStream | 20-40 h | Full control; no framework lock-in | Reinvents @tanstack/react-start with more risk; no streaming infrastructure; no built-in auth/session; loses TanStack Start's type-safe server functions | NO — strictly worse than A |
| **D** — Stay SPA, accept 12 s LCP | No change | 0 h | No work | Doesn't meet target; structurally bottlenecked; growing perception of slowness as competitor frameworks adopt SSR | NO — kicks the can perpetually |

**Recommended path: Option A** with phased multi-wave rollout.

---

## 3. Phase breakdown (each is a candidate own-wave)

### Phase 1 — Install + dual-build setup (~6-8 h)

**Goal**: TanStack Start plugin in vite.config.mts, both SSR + SPA mode building cleanly side-by-side. No runtime behavior change yet.

**Work**:
1. `npm install @tanstack/react-start nitro` (~3 deps, transitive includes server-runtime + handler stack)
2. `frontend/vite.config.mts` — add `tanstackStart()` plugin from `@tanstack/react-start/plugin/vite` alongside existing plugin chain (must coexist with VitePWA, withGeneratedManifests, withStrictCspNonce, withFontPreload)
3. Initial config in SPA mode (`spa: { enabled: true }`) — preserves current SPA behavior while validating plugin chain compatibility
4. Verify gates: `npm run build`, `npm run lint`, `npm run test`, `npm run build-storybook` all pass with plugin in chain
5. Verify VITE_LHCI mode still works (auth bypass + mock-user)
6. Document plugin order constraints (Storybook viteFinal interaction, withStrictCspNonce post-enforcement, etc.)

**Risks**:
- VitePWA + Nitro `injectManifest` SW patterns may conflict — needs validation
- Storybook + tanstackStart plugin combo unverified upstream (post-W123 strictExecutionOrder workaround needs re-validation)
- Vite 8 / Rolldown + tanstackStart compatibility unverified at scale (TanStack Start docs assume Vite 5/6/7 in most examples)

**Verification**: full SPA functional test pass; LHCI baseline preserved; build outputs identical hash modulo TanStack Start runtime addition; npm audit 0; bundle size accounted (Nitro adds ~50-80 KB to dev runtime, PROD should be similar or smaller via tree-shake).

### Phase 2 — Server entry + client entry refactor (~4-6 h)

**Goal**: Split `main.tsx` into `server.ts` (SSR entry) + `client.ts` (hydration entry). Switch `createRoot().render()` → `hydrateRoot(<StartClient />)`. Still SPA mode at runtime — proves entry split is correct without committing to SSR.

**Work**:
1. Create `frontend/src/server.ts` with `createServerEntry({ fetch(req) { return handler.fetch(req) } })` from `@tanstack/react-start/server-entry`
2. Refactor `frontend/src/main.tsx` → `frontend/src/client.ts` with `hydrateRoot(document, <StrictMode><StartClient /></StrictMode>)`
3. Move existing pre-render setup (initGlobalErrorHandlers, ensureTrustedTypesPolicies, theme detection script in index.html) into appropriate phases:
   - `initGlobalErrorHandlers` + `ensureTrustedTypesPolicies` — keep on client (browser-only APIs); should run pre-hydration in `client.ts`
   - Theme detection script in `index.html` — keep there (runs before any JS loads, sets html.classList.add('dark') before paint)
   - `static-shell-i18n.js` — keep, applies meta translations from localStorage at parse time
4. Service worker registration moves to `client.ts` (browser-only API)
5. PersistQueryClientProvider + ThemeProvider tree wraps `<StartClient />` instead of `<App />`
6. ErrorBoundary continues to wrap

**Risks**:
- Hydration mismatches: theme (light/dark) + language (ru/en) detected from localStorage which doesn't exist server-side. SSR must use cookie-based fallback (set by middleware on first request) OR render with neutral defaults + flash on hydration
- React 19 hydration rules stricter than React 18 (suppressHydrationWarning needed where browser-only data drives render)
- ErrorBoundary fallbacks must work both server + client side

**Verification**: SPA mode still functional + LHCI baseline preserved; entry refactor doesn't change bundle hash beyond expected delta; tests still 686p/12s/0f.

### Phase 3 — Auth at edge / cookie-session migration (~6-10 h)

**Goal**: Server can validate auth before rendering — no more `_auth.tsx beforeLoad` redirect-from-client. Authenticated content renders server-side.

**Two approaches**:

**3a — Lightweight: keep AuthContext + decode JWT in server entry**
- Server reads JWT from `Cookie` header, validates against backend's secret/JWKS
- Populates initial AuthContext value via React Context default (server-side)
- Client hydrates with same value (no mismatch if JWT is in cookie that's available both sides)
- Backend FastAPI continues to be source of truth for auth; server just validates cookie before render
- **Pros**: Minimal disruption to existing auth code; backend unchanged
- **Cons**: Cookie-based JWT (must adjust login flow to set cookie alongside or instead of localStorage)

**3b — Heavy: migrate to TanStack Start `useAppSession`**
- Replace `useAuthStore` Zustand + AuthProvider with TanStack Start's built-in `useSession`
- Login/logout become `createServerFn({ method: 'POST' })` server functions
- Cookie-based session managed by TanStack Start's encrypted-cookie session store
- **Pros**: Type-safe end-to-end; built-in session helpers; can co-exist with backend auth (backend validates cookie)
- **Cons**: Major refactor; touches every auth touchpoint (Login.tsx, Register.tsx, ResetPassword.tsx, useProfileSync.ts, _auth.tsx, _public.tsx, _admin.tsx, Settings.tsx)

**Recommended: 3a** — minimal disruption, achieves SSR goal, leaves room for 3b in later wave if benefits warrant.

**Risks**:
- WebSocket connection (chat) requires JWT in URL or first message — server can pre-warm but real WS handshake remains client-initiated; no SSR for chat content (acceptable — chat is interactive after first paint)
- VITE_LHCI bypass currently in `_auth.tsx` beforeLoad → needs equivalent in server entry (env-gated bypass that returns mock user)
- Service worker / push notifications continue client-side
- Auth refresh token flow needs server-side handling (or stays client)

**Verification**: e2e tests pass on SSR + SPA modes; login flow unchanged for users; LHCI shows authenticated routes load with content already in HTML.

### Phase 4 — Caddy SSR forwarding rules (~4-6 h)

**Goal**: Production deployment serves SSR-rendered HTML through Caddy reverse-proxy.

**Work**:
1. Build pipeline: `npm run build` produces `dist/_server/` (Nitro server bundle) + `dist/client/` (client bundle + HTML shell)
2. Server runtime selection: Nitro can target Node, Bun, Deno, Cloudflare Workers, etc. — recommend **Node** (matches existing infra) or **Bun** (faster cold start)
3. Caddy config (`services/caddy/Caddyfile`):
   - `/api/*` → FastAPI backend (unchanged)
   - `/ws/*` → ws-hub (unchanged)
   - `/static/*`, `/media/*` → file-processor (unchanged)
   - `/_server/*` (or `/api/__server-fn/*`) → TanStack Start server functions (NEW)
   - All other routes → Nitro SSR (NEW; was previously served as static SPA)
4. Health check endpoint: Nitro server should expose `/_server/healthz` for Caddy/k8s probes
5. Service worker scope: must continue to register at `/sw.js` from same origin (already configured)

**Risks**:
- Cold-start latency on Node SSR (~100-300 ms) — acceptable; mitigate via pre-warmed pool
- Memory footprint per Node SSR worker (~50-150 MB) — sizing for k8s
- Caddy + Nitro health-check coordination during deploys (k8s rolling update)
- ws-hub continues separate (TanStack Start doesn't replace it; they coexist)

**Verification**: Caddy config validates; SSR-served pages have content in HTML response (curl from server); k8s deploy passes health checks; PWA installability preserved.

### Phase 5 — Browser-API safety guards (~3-5 h)

**Goal**: SSR doesn't crash on `window` / `localStorage` / `IntersectionObserver` / `ResizeObserver` / canvas usage in components.

**Work**:
1. Audit `frontend/src/` for browser-only APIs in code that runs server-side:
   - `window` — must guard with `typeof window !== 'undefined'` OR `useEffect`
   - `localStorage` / `sessionStorage` — same guard
   - `IntersectionObserver` (used by ScrollReveal, useCountUp post-W124 SW1) — check if these run during SSR render path
   - `ResizeObserver` (used by useSlidingIndicator post-W124 SW1) — same
   - `<canvas>` (ParticleAuthBackground, WeatherParticles) — must defer to client
   - `maplibre-gl` (Map page) — already React.lazy'd per W116 INFRA-100-04, won't load server-side
2. Mark routes with heavy browser dependencies as `ssr: 'data-only'`:
   - `/map` — maplibre-gl + many browser APIs
   - `/activity` — html-to-image / jspdf for export (lazy-loaded; safe)
   - Plain text routes (/news, /events, /dashboard, /schedule, /profile) → full SSR
3. Theme + language hydration: render with cookie-detected default OR neutral state + apply post-hydration without flash (see Phase 2 risks)
4. `static-shell-i18n.js` adapted for SSR — server applies translations directly
5. `LazyMotion` (W124 SW1) is React-friendly — confirm SSR-safe (Framer Motion docs say yes for `domAnimation` features)

**Risks**:
- ParticleAuthBackground canvas — already gated via `VITE_E2E_MODE` per W115 SW1; add SSR gate too
- Service worker registration runs only client-side (already in `setupServiceWorker()` async fn)
- IndexedDB (TanStack Query persister, idb-keyval) — client-only; ensure no server-side cache hits attempt to access IDB

**Verification**: SSR routes render without errors; client hydration matches; no double-render flash in `<head>` theme detection; e2e tests pass against SSR build.

### Phase 6 — Testing matrix + rollout (~6-8 h)

**Goal**: Confidence that SSR deployment matches SPA behavior + measurable LCP improvement.

**Work**:
1. **LHCI baseline diff**: 9-URL × 3-run sweep on SSR build vs SPA build
   - Expected: Perf 0.46 → 0.80+ on authenticated routes
   - Expected: LCP 12 s → 2-4 s
   - CLS preserved (≤ 0.1)
   - A11y preserved (1.00)
2. **e2e tests**: full Playwright suite on SSR build (a11y-public, url-state-persistence, axe-cdn, etc.) — adapt webServer.command for SSR if needed (`npm run start` instead of `npm run preview`)
3. **Storybook visual regression**: Chromatic baseline on SSR-built stories (should be identical to SPA — Storybook is build-time static)
4. **Manual smoke**: chrome-devtools-mcp visit all 9 URLs on SSR build, verify no console errors, no hydration mismatches
5. **Rollout strategy**:
   - Phase 6a: Internal staging (separate domain) — internal QA for 1-2 weeks
   - Phase 6b: Canary 10% traffic via Caddy `weighted_rr` — monitor errors, latency, push subscription continuity
   - Phase 6c: Ramp 25% → 50% → 100% over 1-2 weeks
   - Rollback plan: Caddy config flip to serve old SPA build on issues
6. **Monitoring**: Sentry transactions for SSR routes (already have OTEL via `vendor-otel` chunk); add Server-Timing header for Caddy + Nitro
7. **Post-rollout**: re-baseline all LHCI gates (Perf, CLS, LCP, TBT) at SSR levels

**Risks**:
- Hydration mismatches surfacing in production on edge cases not caught in staging
- Push subscription storage (browser-only) interaction with cookie session
- Service worker upgrade path — old clients with cached SPA shell might mix old + new
- Memory leaks in long-running Nitro process

**Verification**: post-rollout LHCI sweep confirms LCP < 2.5 s on /, /dashboard, /news, /events; Sentry shows no spike in errors; user-facing latency metrics improve.

---

## 4. Total estimate

**30-50 h across 4-6 own-waves**:
- Phase 1: 6-8 h (Wave 125)
- Phase 2: 4-6 h (Wave 125 or 126)
- Phase 3: 6-10 h (Wave 126)
- Phase 4: 4-6 h (Wave 126 or 127)
- Phase 5: 3-5 h (Wave 127)
- Phase 6: 6-8 h (Wave 128 — rollout staging through canary)

**NOT a single 6-8 h wave** as the W121-123 backlog "Mobile perf XL" optimistically claimed. Master plan W124 SW5 spec corrected this to 30-50 h estimate.

Per-phase commits enable graceful pause + multi-week pacing. User can prioritize between SSR push and feature work between phases.

---

## 5. Risk inventory

### Architectural

1. **WebSocket compat** — chat/realtime uses ws-hub via WebSocket; SSR can't initialize WS server-side. Acceptable: chat is interactive, not LCP-critical; first paint can be without chat data
2. **Service Worker coordination** — `skipWaiting + clientsClaim` (current config in `vite-plugin-pwa`) must coordinate with SSR HTML delivery so SW intercepts only post-hydration. Mitigation: SW skips navigation requests until after first user interaction
3. **Hydration mismatches** — theme + language detection happens client-side via localStorage (`<script>` block in index.html sets `html.classList.add('dark')` before any React loads). SSR must either: (a) read cookie equivalent, (b) render neutral + apply post-hydration with `suppressHydrationWarning`
4. **Dev/prod parity** — SPA dev server vs SSR prod runtime — must validate behavior matches across modes; consider running Nitro dev server too
5. **Suspense boundaries with server data** — TanStack Router's `loader:` integrates cleanly; existing `useQuery` patterns may need adjustment to avoid double-fetch

### Operational

6. **Cold-start latency** on Node Nitro SSR (~100-300 ms first request) — k8s warm pool mitigates; Caddy has connection-keepalive
7. **Memory footprint** per SSR worker (~50-150 MB) — k8s sizing, autoscaling
8. **Deployment complexity** — adds Nitro server runtime to existing FastAPI + ws-hub + file-processor + Caddy mesh. New monitoring + alerting needed
9. **Backend coupling** — SSR fetches data from FastAPI; if backend is slow, SSR LCP suffers. Need to validate backend latency budget under SSR load
10. **VITE_LHCI bypass** in _auth.tsx + useProfileSync.ts (W116 SW3) — must port equivalent gate to server entry, OR refactor LHCI measurement methodology to use real auth

### Migration

11. **Test infrastructure** — Playwright webServer.command currently builds + previews SPA; needs option for SSR mode. Existing renderWithRouter helper (W114 SW1) tests components in isolation — should still work but doesn't test SSR rendering path
12. **e2e a11y suite** assumes static HTML serve — should still pass (axe runs on rendered DOM regardless of SSR/SPA)
13. **Chromatic visual** captures Storybook frames (build-time, no SSR) — unaffected
14. **Sentry stack traces** — SSR errors need source maps for both server + client bundles; current Sentry setup (W117 SW3) deferred to client only — needs server-side init in `server.ts`
15. **Push notifications** — webpush requires service worker registration which is browser-only; flow unchanged but user must hit the page client-side first to register

---

## 6. Alternative paths if XL too aggressive

### A1 — Critical CSS inlining only (~4-6 h, marginal LCP win on already-fast routes)

`vite-plugin-critters` or similar — extracts above-the-fold CSS, inlines in HTML, defers rest. Closes 100-300 ms LCP on `/login` + `/404` (already fast routes). Doesn't address authenticated route LCP.

**Verdict**: NOT recommended as standalone — wrong target. Could be Phase 0 of SSR work for incremental polish.

### A2 — Resumable React via Qwik-style approach (NOT viable in 2026)

React 19 has no resumability primitives. Would require Qwik framework migration (touches every component). Out of scope.

### A3 — Pre-rendering at build time for static routes only (~6-10 h)

`vite-prerender-plugin` or similar — pre-renders `/login`, `/404`, marketing pages at build. Authenticated routes stay SPA.

**Verdict**: NOT recommended — same problem as Option B above. Authenticated routes are the LCP pain.

### A4 — Backend-rendered HTML shell (~10-15 h)

Have FastAPI server-render basic page structure + meta tags via Jinja2; React hydrates as SPA. Backend gains template-rendering responsibility.

**Verdict**: NOT recommended — duplicates routing/templating logic between FastAPI and React; loses TanStack Router type-safety; not future-proof.

---

## 7. Decision criteria for Wave 125 kickoff

**Go-ahead conditions** (any of):
1. User explicitly prioritizes perf improvement on authenticated routes
2. Real-user LCP metrics (RUM) confirm authenticated route latency is impacting engagement (currently unknown — would need Sentry transactions or web-vitals collection on prod)
3. Competitive pressure (other GUU systems showing faster page loads)

**Hold conditions** (any of):
1. Active feature work needs the ~30-50 h budget
2. Backend changes coming that would interfere with SSR (e.g., auth refactor, schema migration)
3. Team capacity constrained (single-developer multi-wave migration is tractable but needs sustained focus)

**Recommended kickoff timing**: After all W124 honesty caveats closed (W124 polish pass) and before any feature work that would touch auth, routing, or AppProviders. Estimated kickoff window: any time post-W124-polish.

---

## 8. Hand-off notes — files needing extra care during migration

Per CLAUDE.md "Critical files (DO NOT touch unless explicit reason)":

| File | Why critical | SSR-migration consideration |
|------|--------------|------------------------------|
| `frontend/.storybook/main.ts` viteFinal hook (W123 SW1) | strictExecutionOrder workaround for Vite8/Rolldown+Storybook | Must coexist with `tanstackStart()` plugin; verify Storybook still builds post-migration |
| `frontend/scripts/lhci-windows-fallback.mjs` (W120 SW1 + W121 SW8) | Windows EPERM workaround + Lighthouse 13.1.0 default | LHCI methodology unchanged; verify SSR build is what wrapper measures |
| `frontend/scripts/run-lhci.mjs` (gate config) | Perf error@0.40, CLS error@0.10 | Re-baseline gates at SSR levels post-Phase 6 |
| `frontend/vite.config.mts` | `build.modulePreload.resolveDependencies` filter (W122 SW2 vendor-pdf lazy) + `injectManifest.globIgnores` (W122 SW2) + `withFontPreload()` (W124 SW2) | All must coexist with `tanstackStart()` plugin |
| `frontend/src/main.tsx` Sentry deferred init via requestIdleCallback (W117 SW3) | Already optimal for SPA | Phase 2 split into server.ts + client.ts; deferred init stays client-only |
| `frontend/.github/workflows/chromatic.yml` (W123 SW1 unblock) | Chromatic enabled by user pre-W124 | Stories build-time, no SSR change needed |
| `frontend/src/router.ts` defaultViewTransition VITE_LHCI gate (W117 SW1) | LHCI-mode VT disable | Same gate works in SSR; verify integration with TanStack Start |
| `frontend/src/_auth.tsx` + `frontend/src/hooks/useProfileSync.ts` VITE_LHCI bypass (W116 SW3) | Auth bypass for LHCI authenticated route measurement | Phase 3 — port bypass to server entry equivalent OR refactor LHCI to use real auth flow |

Per CLAUDE.md gotchas relevant to migration:

- **LazyMotion strict catches regressions on render path only** (W124 SW1 gotcha 1) — SSR-side LazyMotion behavior must match client; verify `useReducedMotion` works server-side
- **Test mock must expose `m`** (W124 SW1 gotcha 3) — SSR tests need same mock pattern
- **renderWithRouter must wrap with LazyMotion** (W124 SW1 gotcha 4) — SSR test helper needs same
- **TanStack Router default stringifySearch JSON-quotes strings** (W120 SW5 gotcha) — SSR-rendered URLs same
- **Map URL-sync user-vs-programmatic gate** (W120 SW5 gotcha) — client-only behavior, SSR doesn't trigger map navigation
- **Picsum preconnect** (W117 SW5) — keep in HTML head, SSR-rendered
- **`withFontPreload()` Vite plugin** (W124 SW2) — keep, SSR-rendered HTML benefits from same preload
- **Schedule ARIA grid `display: contents` rows** (W120 SW3) — render-side same, no SSR impact

---

## 9. Open questions for Wave 125 kickoff

1. **Hosting**: stay on existing k8s cluster + Caddy, OR consider edge platform (Cloudflare Workers via Nitro Cloudflare preset)? Cloudflare Workers offers <50 ms cold start globally but locks into platform.
2. **Auth approach**: 3a (lightweight, keep AuthContext) or 3b (TanStack Start session)? Recommend 3a for first attempt; 3b if session UX needs polish later.
3. **Route prioritization**: SSR all authenticated routes simultaneously, OR phase by route (start with /news + /events as content-heavy + cacheable, hold off on /map + /activity)? Recommend incremental — easier debugging.
4. **Caching strategy**: SSR responses cacheable in Caddy (per-user via cookie key)? Or always SSR-render fresh? Depends on content freshness requirements.
5. **Service worker compatibility**: SW currently uses NetworkFirst for HTML — need to ensure compatible with SSR HTML responses (probably yes; SW caches the whole response).
6. **Internationalization (RU/EN)**: SSR must detect language at server — likely cookie-based (currently localStorage). Need bilingual SSR rendering or default-to-RU + JS-toggle.

---

## 10. Sources

- [TanStack Start Overview (latest docs)](https://tanstack.com/start/latest/docs/framework/react/overview) — framework architecture
- [TanStack Start v1 Release Candidate (TanStack Blog)](https://tanstack.com/blog/announcing-tanstack-start-v1) — v1 announcement
- [TanStack Start: A New Meta Framework Powered by React or SolidJS (InfoQ)](https://www.infoq.com/news/2025/11/tanstack-start-v1/) — production-readiness coverage
- [TanStack Start v1.0: Type-Safe React Framework 2026 (byteiota)](https://byteiota.com/tanstack-start-v1-0-type-safe-react-framework-2026/) — 2026 ecosystem state
- [TanStack Start vs Next.js: Server Components Compared 2026 (kunalganglani.com)](https://www.kunalganglani.com/blog/tanstack-start-vs-nextjs-server-components) — comparison context
- TanStack Start docs queried via Context7 MCP (`/websites/tanstack_start_framework_react`, ~1004 snippets, benchmark 83.43)
- W124 SW4 variance findings (`f012087e6`) — Perf baseline data informing target gates
- W124 backlog (`memory/wave124_backlog.md`) — original "mobile perf XL" deferral context
- Master plan `c-users-egorribun-claude-projects-c-use-robust-eclipse.md` SW5 section — design doc spec
