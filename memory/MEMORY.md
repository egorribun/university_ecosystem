# University Ecosystem — Project Memory
<!-- MEMORY.md target: < 24.4 KB to avoid auto-load truncation. Wave 134 SW3 compacted W115-W130 from verbose to one-line — full detail lives in `docs/audits/AUDIT_WAVE<N>.md` (active wave audits) + `docs/audits/archive/AUDIT_WAVE<N>.md` (post-N+3 rotation) + `memory/audit_history_archive.md` (W71-W114). The 3 most-recent waves keep verbose entries here. -->

## Collaboration feedback
- [User perfectionism standard](feedback_perfectionism.md) — user's "безупречно?" probe = call for honest self-audit + polish pass, NOT reassurance. Expect 60-90 min polish after claiming "done" on a wave.
- [User planning estimates style](feedback_planning_estimates.md) — when asked "сколько waves / how long until X", respond with structured framework (range estimates + historical anchoring + categorical breakdown + caveats + 3-wave-horizon recommendation), NEVER a single number. Anchored on historical per-page wave counts (Schedule 14, Map 23, Events 6, Activity 4, News 6, Dashboard 10).

## Active backlog
- [Wave 136 backlog](wave136_backlog.md) — **CLOSED** Tier 1 + Tier 2 + Tier 3 per user-approved 3-question AskUserQuestion (Q1=Tier 1+2+3, Q2=JWT (d) Hybrid, Q3a=Medium process._getActiveHandles trace, Q3b=Playwright real-Chrome path). 8 SW commits SW0-SW7 + SW8 audit. **Tier 1**: SW1 `b37e827e4` JWT is_active embed (closes W135 §Honesty #2 fast path); SW2 `6989637f0` session revocation broadcast via existing Redis pub/sub (closes #2 immediate effect, NO new NATS); SW3 `7bccb5ee7` Playwright real-Chrome alternative (closes W135 §Honesty #1 tool-level); SW4 `938c797a6` failed_login_attempts model+schema fix REPRODUCED in test SQLite (real model-level drift, not Docker-only — closes W135 §Honesty #3). **Tier 2**: SW5 `c67ac5cce` build-orchestrated trace agent identified MessagePort + Worker hang root cause + bonus mtime regression fix (closes W135 §Honesty #4 diagnosis-level + W135 SW3 reproducibility theatre); SW6 `3314364bd` PWA_INJECT_CONFIG single source + Linux CI workflow (closes W135 §Honesty #5 + #8/#11). **Tier 3**: SW7 `51139c2e7` delete obsolete frontend/nginx.conf (-148 LoC) + 3 healthchecks (imgproxy CLI, grafana wget, prometheus wget); 3 distroless services deferred honestly (file-processor, tempo, loki). Bundle PROD × 2 BYTE-IDENTICAL to W135 baseline (139,808 main + 65,864 _shell.html + 53,181 sw.js + 39,373 server.js + 209 files / 4.80 MB precached). 15 new tests (5 SW1 + 6 SW2 + 4 SW4) across 3 NEW test files. Wall-clock ~7-8h vs ~10-13h plan estimate (refined down by Explore-agent discovery of existing gateway revocation infrastructure). **Post-W136 § Honesty: 6 of 9 W135 caveats CLOSED + 3 NEW from W136 + 3 W135 carry = 6 remaining** (W134 #2 bundle delta carry, W134 #10 /messenger punted, W135 #9 curl-only verification, W136 NEW upstream hang fix, W136 NEW Tier 3 partial, W136 NEW Playwright /login screenshot fragility). Full detail in [AUDIT_WAVE136.md](docs/audits/AUDIT_WAVE136.md).
- [Wave 135 backlog](wave135_backlog.md) — **CLOSED + POLISHED** L scope: Aggressive cleanup + Docker chain verification + Option E orchestrator (per Q1=L + Q2=Aggressive + Q3=Path B full per user-approved AskUserQuestion 3-question flow). 2 commits + 1 docs + 1 polish: SW1 `6c5ada141` Aggressive cleanup (4 files +230/-34) — full AbortController removal in useProfileSync (queryClient.cancelQueries sole cancellation; isCancel(error) axios canonical replaces signal.aborted check); sessions factory exports updateSessionInCache + invalidateSessions; useSessionManagement mutation paths route through factory; 11 new sessions tests; vitest **1052p/12s/0f**. SW2 (no commit, /tmp/wave135-sw2-verification.md) Docker chain verification — chrome-devtools-mcp `take_snapshot` Windows wall hit (W132 polish round 2 family) → fallback to curl-only per plan. Curl 12 routes via Caddy chain proves W131 SW2 fast-path + W132 SW5 Server-Timing + W128 auth-at-edge + W131 SW6 SameSite=lax. Discovered 2 W136-candidate backend/gateway issues (gateway+backend JWT mismatch, failed_login_attempts NOT NULL). SW3 `d58b5c74b` Option E orchestrator (4 files +363/-42) — NEW `frontend/scripts/build-orchestrated.mjs` (~280 LoC, 6 steps); BUILD_SKIP_PWA env-flag gates VitePWA disable; subprocess vite build + kill-after-artifacts pattern; esbuild compiles sw.ts; workbox-build standalone (209 files / 4.80 MB); wave127-build-x3.sh DELETED. Build × 3 reproducible: `index-DqqHVXgy.js` 139,808 + `_shell.html` 65,864 (BYTE-IDENTICAL to W134) + `sw.js` 53,181 + 26s/run. SW4 audit + N+3 rotation (W132→archive). **Polish pass closed 2 caveats** (cross-session vitest 5/5 × 1052p clean + W134 §Honesty #6 MEMORY.md path norm: 17 broken `../../../../docs/audits/` → 21 clean text refs) + invariant verifications (commit-stats match, memory-links 21/21, archive 16 files, npm audit 0, Cargo.lock no drift). **Post-polish §Honesty: 6 CLOSED, 9 REMAIN** (was 12 caveats audit pre-polish: 1 dup consolidated + 2 closed). Full detail in [AUDIT_WAVE135.md](docs/audits/AUDIT_WAVE135.md).
- [Wave 134 backlog](wave134_backlog.md) — **CLOSED** Phase 5 polish + housekeeping (H + C + D combined per Q1+Q2+Q3): SW1 useProfileSync Bridge (`496eb5bbf`); SW2 /settings tab=N URL param + sessionsQueryOptions factory + conditional prefetch on tab=2 (`84487ed09`); SW3 MEMORY.md compaction; SW4 audit + N+3 rotation. Bundle PROD `index-AUQP2Hdb.js` 139,808b + `_shell.html` 65,864b. Vitest **1041p/12s/0f**. 10 §Honesty caveats (4 closed via polish; 6 remain). Full detail in [AUDIT_WAVE134.md](docs/audits/AUDIT_WAVE134.md).
- [Wave 133 backlog](wave133_backlog.md) — **CLOSED** Phase 5 SSR continuation Option C+D (SSR cookie forwarding + currentUserQueryOptions factory + /schedule + /profile + /settings SSR enable). 5 commits. SSR routes 6→8. Bundle 139,549/65,872. Vitest 1008p. Detail in [archive/AUDIT_WAVE133.md](docs/audits/archive/AUDIT_WAVE133.md) (rotated W136 SW8).
- [Wave 132 backlog](wave132_backlog.md) — **CLOSED** Phase 6 SSR canary rollout INFRASTRUCTURE (Caddy lb_policy + k8s rolling-update + Server-Timing + 447-line operator runbook). Bundle byte-identical W131. Detail in [archive/AUDIT_WAVE132.md](docs/audits/archive/AUDIT_WAVE132.md).
- [Wave 131 backlog](wave131_backlog.md) — **CLOSED + POLISHED** Phase 4 deploy infra: nginx → Node 24 Alpine SSR via custom server-prod.mjs. Caddy SSR routing + cookie SameSite Strict→Lax. 9 commits. Detail in archive AUDIT_WAVE131.md.
- [Wave 130 backlog](wave130_backlog.md) — **CLOSED + POLISHED** Phase 5 SSR: /schedule SSR + Weather TanStack Query refactor. 6 SSR routes total. 5 commits + polish `e7010a599` + polish-followup `5d5b742d0`. /schedule 70,847 SSR HTML (+577% vs shell). 24 new factory tests. Bundle 138,974 + 65,872. Detail in [AUDIT_WAVE130.md](docs/audits/archive/AUDIT_WAVE130.md).
- [Wave 129 backlog](wave129_backlog.md) — **CLOSED** Phase 5 SSR: /events + /events/$id + /news + /news/$id all SSR-enabled. 7 commits. NEW `lhci-linux.yml` workflow_dispatch. Bundle 138,845 + 65,778. Detail in [AUDIT_WAVE129.md](docs/audits/archive/AUDIT_WAVE129.md).
- [Wave 128 backlog](wave128_backlog.md) — **CLOSED + POLISHED** Phase 5 continuation: /dashboard SSR enablement (first per-route on W125-W127 foundation). 7 commits. /dashboard 75,086 SSR HTML (+598% vs shell). Bundle 138,125. Detail in [AUDIT_WAVE128.md](docs/audits/archive/AUDIT_WAVE128.md).
- [Wave 127 backlog](wave127_backlog.md) — **CLOSED** Phase 5 foundation: provider hoisting + cookie-mirror (ue-mode + ue:language → server.ts AsyncLocalStorage → globalThis getters → RootShell). 6 SW. Bundle 137,818. Detail in [AUDIT_WAVE127.md](docs/audits/archive/AUDIT_WAVE127.md).
- [Wave 126 backlog](wave126_backlog.md) — **CLOSED + POLISHED** Phase 3 auth-at-edge + /login per-route SSR. /login 20,320b form HTML. Detail in [AUDIT_WAVE126.md](docs/audits/archive/AUDIT_WAVE126.md).
- [Wave 125 backlog](wave125_backlog.md) — **CLOSED + POLISHED** TanStack Start v1 SSR Phase 1 + Phase 2 (Phase 1 isolation non-viable → Phase 2 pulled forward). Detail in [AUDIT_WAVE125.md](docs/audits/archive/AUDIT_WAVE125.md).
- [Wave 124 backlog](wave124_backlog.md) — **CLOSED + 2 POLISH PASSES** XL Mobile Perf + SSR pre-flight design doc. vendor-ui −56.6 KB / −34.8% via LazyMotion+domAnimation. Bundle 180,827. Detail in [archive/AUDIT_WAVE124.md](docs/audits/archive/AUDIT_WAVE124.md).
- [Wave 123 backlog](wave123_backlog.md) — **CLOSED + POLISHED** Frontend tech-debt; Chromatic UNBLOCKED via `strictExecutionOrder` workaround. Bundle 179,867. Detail in [archive/AUDIT_WAVE123.md](docs/audits/archive/AUDIT_WAVE123.md).
- [Wave 122 backlog](wave122_backlog.md) — **CLOSED + POLISHED** Image bandwidth + bundle/vendor-pdf lazy. ~875 KB image savings. Detail in [archive/AUDIT_WAVE122.md](docs/audits/archive/AUDIT_WAVE122.md).
- [Wave 121 backlog](wave121_backlog.md) — **CLOSED** Inherited tech-debt close. 7 commits + polish A1-A4. Detail in archive AUDIT_WAVE121.md.
- [Wave 120 backlog](wave120_backlog.md) — **CLOSED + POLISHED** ×2 (CLS arc closed at WCAG Good ceiling). Detail in archive AUDIT_WAVE120.md.
- [Wave 119 backlog](wave119_backlog.md) — **CLOSED** CLS arc complete + Renovate handlebars. Detail in archive AUDIT_WAVE119.md.
- [Wave 118 backlog](wave118_backlog.md) — **CLOSED** (closed via W119 SW1 + SW2-5).
- [Wave 117 backlog](wave117_backlog.md) — **CLOSED** (CLS content-shift addressed W118 + W119 SW1).
- [Wave 116 backlog](wave116_backlog.md) — **CLOSED**.
- [Wave 115 backlog](wave115_backlog.md) — **CLOSED**.

## Audit History (newest first)

Only the 3 most-recent CLOSED waves have full detail here. Older waves (W117-W132) live in `docs/audits/AUDIT_WAVE<N>.md` (currently active = W133/W134/W135) or `docs/audits/archive/AUDIT_WAVE<N>.md` (post-N+3 rotation = W117-W132). Historical Waves 71–114 + older Lessons Learned are in [`audit_history_archive.md`](audit_history_archive.md).

| Wave | Date | Status / Detail |
|------|------|--------|
| Wave 136 | 2026-05-07 | ✅ CLOSED — Tier 1 + Tier 2 + Tier 3 (JWT (d) Hybrid + Playwright + build-orchestrated trace + housekeeping). 8 SW commits SW0-SW7 + SW8 audit. Tier 1 (SW1+SW2+SW3+SW4) closes 3 W135 § Honesty TOP discoveries (gateway+backend JWT mismatch, chrome-devtools Windows wall, failed_login_attempts schema). Tier 2 (SW5+SW6) closes build-orchestrated arc + bonus mtime regression + PWA_INJECT_CONFIG single source + Linux CI. Tier 3 (SW7) deletes obsolete frontend/nginx.conf + 3 of 6 healthchecks (3 distroless deferred honestly). Bundle PROD × 2 BYTE-IDENTICAL to W135 baseline. 15 new tests across 3 NEW test files. Wall-clock ~7-8h vs ~10-13h plan estimate. **6 W135 caveats CLOSED + 3 NEW + 3 W135 carry = 6 remaining post-W136**. N+3: W133 → archive (active waves W134/W135/W136). Full detail in [AUDIT_WAVE136.md](docs/audits/AUDIT_WAVE136.md). |
| Wave 135 | 2026-05-07/08 | ✅ CLOSED + POLISHED — see Active backlog above for verbose detail. AbortController removal + sessions factory + Option E orchestrator. Bundle 139,808/65,864 BYTE-IDENTICAL W134. Detail in [AUDIT_WAVE135.md](docs/audits/AUDIT_WAVE135.md). |
| Wave 134 | 2026-05-08 | ✅ CLOSED + POLISHED — see Active backlog above. Phase 5 polish: useProfileSync Bridge + /settings tab=N URL + sessionsQueryOptions. Bundle 139,808/65,864 (+259 honest framing). [AUDIT_WAVE134.md](docs/audits/AUDIT_WAVE134.md). |
| Wave 133 | 2026-05-08 | ✅ CLOSED — Phase 5 SSR Option C+D: SSR cookie forwarding + currentUserQueryOptions + /schedule + /profile + /settings SSR. SSR routes 6→8. Bundle 139,549/65,872. [archive/AUDIT_WAVE133.md](docs/audits/archive/AUDIT_WAVE133.md). |

For Wave 117-132 detailed audit history, see `docs/audits/archive/AUDIT_WAVE<N>.md` (rotated waves; W132 newly archived in W135 SW4). Headlines preserved in Active backlog one-line entries above.

## Stack
- **Backend**: FastAPI + SQLAlchemy 2.0 async + Dishka DI + Pydantic v2 + PostgreSQL + Redis
- **Auth**: Argon2id (bcrypt removed Wave 21), JWT RS256/HS256, TOTP MFA, WebAuthn, SpiceDB authz
- **Frontend**: React 19 + TypeScript + Vite 8/Rolldown + TanStack Router + TanStack Start v1 SSR + TanStack Query + Zustand + Framer Motion
- **Infra**: MinIO (S3, dev), ClamAV, gRPC, OpenTelemetry, Prometheus, Pyroscope, Strawberry GraphQL
- **Go services**: ws-hub, file-processor, gateway. **Rust**: native/rust_ext (PyO3)

## Key Paths
- DI entry: `app/api/deps.py`
- Auth security: `app/auth/security.py` (Argon2, JWT, HIBP)
- CSRF middleware: `app/core/csrf.py` — cookie: `csrf_token`, header: `X-CSRF-Token`
- GraphQL schema + context: `app/graphql/schema.py`
- Rate limit: `app/core/rate_limit.py` (shim) → real impl in `app/core/ratelimit/`
- Frontend API client: `frontend/src/api/client.ts`
- CSP policy: `app/core/policies/csp.py`
- Trusted Types: `frontend/src/utils/trustedTypes.ts`
- WS hub auth invalidation: `app/services/ws_hub_client.py`
- DB engine config: `app/core/database.py`
- SSRF blocklist: `app/core/ssrf.py` (validate_url_not_internal)
- SSR auth: `frontend/src/ssrAuth.ts` (W126), `frontend/src/ssrTheme.ts` (W127), `frontend/src/server.ts` (4 AsyncLocalStorage chain)
- Per-request SSR factories: `frontend/src/api/hooks/{users,events,news,schedule,sessions,weather}.ts`

## Patterns / Conventions
- Navbar: `<nav>` is plain HTML (no Framer Motion) with `sticky top-0`, fixed 64px height. `NavbarPill` inside morphs visually. `vt-navbar` class on `<nav>` directly.
- Navbar morph: content (text↔icons, user name) switches instantly; only pill container animates (500ms ease-premium). Dynamic Island pattern.
- Navbar buttons: `.nav-link-premium` CSS class — iOS glass capsule with specular `::before`. Active via `data-active` attribute.
- Tailwind v4 CSS var pitfall: `text-(--my-var)` sometimes fails. Use plain CSS class with `color: var(--my-var)` for reliability.
- `--font-sf` (SF Pro) fallback on Windows = Arial. Use `--font-ui` (Inter) for cross-platform nav buttons.
- `_ensure_vary_header` is in `app/core/middleware.py` — import from there, not `app.main`
- LoginService constructor: `auth_repo` is first param (not `db`)
- GraphQL auth: always use `GraphQLTokenValidator`; never inline revocation logic in `schema.py`
- HIBP: `_get_hibp_client()` is async; await it
- Rate-limit test reset: call `reset_for_testing()` from `app.core.rate_limit`
- CSP dev mode: `require-trusted-types-for 'script'` IS enabled in dev (only skipped in `report_only`)
- ETag HMAC: signing key from in-memory `sessionSigningKey` only (never sessionStorage)
- WS message validation: all frames must pass `parseWsMessage()` from `@/api/schemas/wsMessage.ts`
- ws-hub cache invalidation: `await invalidate_ws_hub_cache(user_id, room_id)` after removing participant
- `_enforce_production_secrets`: use `os.environ.get("ENVIRONMENT")` directly in `@model_validator`
- `ChatCreationService` constructor: `(uow, session, cache)` — inject cache via `get_chat_creation_service` dep using `get_cache()`
- Pre-commit mypy hook: `^app/(auth|services|api|core|repositories|graphql)/` — expanded in Wave 18
- `_ALLOWED_WS_ORIGINS`: module-level frozenset; empty in dev, populated from `settings.frontend_url` in prod
- WS close `1008` (Policy Violation) for Origin rejection
- `RequestIDMiddleware`: pure ASGI; `request_id_ctx` ContextVar; sanitise client X-Request-ID (alphanum+`-_`, max 64)
- Idempotency key includes `user_id` to prevent cross-user replay
- WS upgrade ticket: `TICKET_KEY_PREFIX = "ott:ws:"`, TTL=15s, value=`{user_id}:{jti}` — GETDEL in Python + Go
- Redis key contracts: `contracts/redis-keys.md` is authoritative — update before adding new key patterns
- SSRF: `validate_url_not_internal()` init-time; `validate_url_not_internal_async()` per-request; `validate_and_resolve()` pinned IPs
- ws-hub client rate limit: `WS_CLIENT_MSG_RATE_LIMIT` (10), `WS_CLIENT_MSG_BURST` (20) via config
- Waves 26-32 conventions: documented in CLAUDE.md — Helm secrets, ws-hub limits, CSRF timing, React Compiler, CI gates
- Wave 134 SW1: useProfileSync auto-fetch routes through `queryClient.fetchQuery({...currentUserQueryOptions(), retry: false})` for cache identity with W133 SSR loaders. `currentUserQueryKey = ["users", "me"]` defined in BOTH useProfileSync.ts:58 AND users.ts:52 — drift would silently break the bridge.
- Wave 134 SW2: `/settings?tab=N` is the canonical URL form (deep-linkable). Validated via `settingsSearchSchema` Valibot at `frontend/src/features/settings/schema.ts`; `?tab=2` triggers conditional sessions prefetch via `sessionsQueryOptions(userId)` factory.
- Wave 135 SW1: AbortController removed from useProfileSync entirely. `queryClient.cancelQueries({ queryKey: currentUserQueryKey })` is the SOLE cancellation mechanism (was alongside controller in W134 SW1; W135 retires controller). axios `isCancel(error)` (canonical, sets `error.code === "ERR_CANCELED"`) replaces `controller.signal.aborted` in catch block. Future cancellation in this hook should use queryClient.cancelQueries only.
- Wave 135 SW1: sessions factory exports `updateSessionInCache(queryClient, userId, updated)` + `invalidateSessions(queryClient, userId)`. Mutation paths in useSessionManagement (revokeSession, revokeAllSessions) route through these; sessionsKey memo removed (factory derives key from primitive userId). Future mutation cache writes for the sessions slot should use these helpers, NOT inline setQueryData.
- Wave 135 SW3: `npm run build` invokes `frontend/scripts/build-orchestrated.mjs` (cross-platform, retires Windows-specific wave127-build-x3.sh). Sets `BUILD_SKIP_PWA=true` → vite.config.mts gates `VitePWA({disable: true})` (env-flag default off; CI Linux + dev mode unaffected). Subprocess vite build + kill-after-artifacts pattern: poll for `_shell.html` AND `dist/server/server.js` to exist + be stable for 4 × 500ms ticks (2s debounce), then SIGTERM. esbuild compiles `src/sw.ts` → `dist/client/sw.js` (53,181 bytes; respects tsconfig path aliases). workbox-build.injectManifest standalone replaces `self.__WB_MANIFEST` with actual manifest array (209 files / 4.80 MB). Build × 3 reproducible 26s/run. Honest §Honesty: kill-after-artifacts is improvement NOT structural fix; second hang point in tanstackStart-core remains W136 candidate. `npm run build:legacy` preserves run-build.mjs as rollback.

## Docker / Deployment
- `docker-compose.full.yml` is the dev compose (used by `start-docker.ps1`)
- `docker-compose.yml` is production compose (uses Valkey, Caddy, separate networks)
- `start-docker.ps1 -Build` builds + starts; `-Down` stops; `-Logs` follows logs
- `.env.docker` auto-generated by start-docker.ps1 with 12+ secrets (no BOM)
- `.env` must have vars used in compose `${VAR:?}` interpolation (ELASTIC_PASSWORD, NATS_USER/PASS, REDIS_PASSWORD, GRAFANA_ADMIN_PASSWORD)
- **`.env` and `.env.docker` must have identical POSTGRES_PASSWORD** — compose interpolation uses `.env`, env_file uses `.env.docker`
- **Never use `!` in passwords** — shell history expansion mangles `!` → `/!` inside Docker
- **POSTGRES_PASSWORD env var only sets password on first volume init** — ALTER USER needed if volume persists with old password
- Gateway/ws-hub: distroless images — no shell, no wget. Health checks via HTTP from host, not Docker HEALTHCHECK
- Dev + prod both use Valkey (not Redis) — `valkey-server`/`valkey-cli` commands, Python `redis` client compatible
- SpiceDB: `SPICEDB_INSECURE=true` for dev; `start-docker.ps1` auto-creates DB + runs `spicedb migrate head`
- NATS alpine: `sed` for config substitution (no `envsubst` in alpine)
- Gateway: unified `/api/v1/*path` wildcard with inline auth dispatch
- `WebSocketProvider` must wrap `MessengerProvider` in `AppProviders.tsx`
- Test user: `test@university.dev` / `TestPass@2024x` (student)
- Python 3.14 compat: pydantic >=2.13.0b2, strawberry >=0.283.2, redis >=6 — see `memory/wave41_docker_py314.md`
- Frontend Dockerfile: `rust:1.94.1-slim-bookworm` wasm-builder stage; W131 SW3 runtime now `node:24-alpine` (Node SSR via server-prod.mjs)
- W131 SW2: `/healthz` fast-path early-return in `frontend/src/server.ts` — Caddy `health_uri /healthz` + k8s livenessProbe/readinessProbe
- hey-api `buildUrl()` prepends `axios.defaults.baseURL` then sets `baseURL: ""` — interceptor must detect doubled `/api/v1/api/v1/`
- WS ticket (`/ws/ticket`): uses `api.post` with `baseURL: ""` — endpoint outside `/api/v1` prefix (Caddy `/ws/` block)
- Fingerprint validation: skipped in `development` env (FIX-44-03) — Accept-Language mismatch in Docker proxy layers
- `start-docker.ps1 -Rebuild` = `--no-cache` full rebuild; `-Build` = cached; no flag = start only
- `start-docker.ps1 -Logs -LogService backend` for single-service logs
- MinIO bucket creation: `minio/mc` container on `${project}_internal` network
- SpiceDB: `SPICEDB_GRPC_NO_TLS: "true"` required in dev compose
- Dockerfile.test must match backend Python version (3.14) and uv version (0.11.2)

## Frontend Maturity Assessment (Wave 43)
- **Overall: 10/10** — Every production file read line-by-line. All issues resolved.
- System Consistency (10/10): 354 CSS tokens, @property registered, calc()-stagger, zero undefined vars
- Layout & Responsiveness (9.5/10): Container queries, fluid typography, View Transitions
- Visual Hierarchy (10/10): Glass depth system, motion tokens, CVA variants, 5 orb @keyframes
- Code Quality (10/10): 0 tsc errors, 0 eslint errors, 0 Russian defaultValues, 0 dead code, eslint-plugin-security active
- Component Architecture: 6 feature folders (feedback/motion/media/search/pwa/layout) with barrel exports
- CSS: 4 token files + 3 behavior partials, @property registrations, Framer Motion→CSS for decorative anims
- Security: SafeHtml post-sanitization guard (RZ-43-01), Clipboard API (RZ-43-02), rateLimit object wrap (RZ-43-03)
- CI: token sync gate (MOD-43-01), eslint-plugin-security (MOD-43-02)

## Backend Maturity Assessment (Wave 33)
- **Overall: 100/100** — exhaustive line-by-line review of all 315 files (61,386 lines) completed
- Security (10/10), K8s/Helm (10/10), Resilience (10/10), CI/Tooling (9.8/10), DI/Architecture (10/10), Observability (9.8/10), Documentation (9.5/10)
- Wave 33 (7 commits): CRITICAL recovery code bug, 9 HIGH, ~115 MEDIUM, ~80 LOW — ALL code-level issues closed
- Remaining: infrastructure-only items (flagd, NATS NKey, Vault, Linkerd, backups)
- `ruff check app/` = 0 errors, all pre-commit hooks pass

## Still Pending / Deferred (Infrastructure-Only)
- **MOD-W17-03**: Gateway JWKS-based RSA key hot-reload — requires ADR for rotation
- **MOD-08 / MOD-W15-07**: OpenFeature flagd — provider decision by 2026-06-01
- **DEBT-07 / TD-W15-07**: NATS NKey auth (requires infra key generation)
- **MOD-W15-05**: External Secrets Operator — requires Vault/infra
- **MOD-W14-10**: Linkerd service mesh
- **MOD-W16-03 / MOD-W17-07**: Centralized logging (Loki/Fluent Bit) — requires ADR-010
- **MOD-W16-05**: K8s API server audit logging — requires cluster config
- **MOD-W16-06**: Automated backup strategy (WAL-G/pgBackRest + Redis RDB + MinIO)
- **MOD-W16-07**: Secret rotation documentation

## Design Preferences
- [Design feedback](feedback_design_preferences.md) — matte over glass, large fonts, tight spacing, btn contrast, segment control, no clipped glow

## Older Lessons Learned
Waves 29–114 lessons live in [`audit_history_archive.md`](audit_history_archive.md). Most are encoded as permanent conventions in `CLAUDE.md` (Code Conventions + Gotchas sections), the authoritative long-form reference. Per-wave reports `AUDIT_WAVE<N>.md` (W117 onward) live in `docs/audits/` (active) or `docs/audits/archive/` (post-N+3 rotation).

## Wave 33/34/43 Summaries
- Wave 43: frontend 10/10, 152 files — `memory/wave43_frontend_final_audit.md`
- Wave 33: backend 100/100 — `memory/audit_wave33_2026_03_26.md`
- Wave 34: CI 700→0 — `memory/wave34_ci_fixes.md`
