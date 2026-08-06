# AGENTS.md — University Ecosystem Platform

- [Project Structure](#project-structure)
- [Commands](#commands)
- [Code Conventions](#code-conventions)
- [Bypass policy](#bypass-policy)
- [Gotchas](#gotchas)
- [Audit Trail](#audit-trail)

## Project Structure

- Python backend: `app/` (FastAPI + SQLAlchemy 2.0 + Pydantic v2) — **Python >=3.13,<3.15**
- TypeScript frontend: `frontend/src/` (React 19 + Vite 8/Rolldown + TanStack Router + TanStack Query + Zustand + Framer Motion)
- Rust optimizer: `native/rust_ext/` (PyO3 FFI — schedule conflicts, partition management, HMAC)
- Go services: `services/` (ws-hub, file-processor, gateway, caddy)
- Alembic migrations: `alembic/versions/` (112 files; squash script: `app/management/squash_migrations.py`)
- Config: `app/core/config/` (15 classes, _NamespaceView composition Phase 2, 174+ fields)
- Feature flags: `app/core/feature_flags.py` (OpenFeature + flagd; K8s config: `k8s/flagd/`)
- Observability: OTEL tracing (Tempo), OTEL log bridge, Sentry, Prometheus, Pyroscope

## Commands

- `python -m ruff check app/` — lint backend (S104/S105 suppressed via per-file-ignores)
- `python -m ruff format app/` — format backend
- `cd frontend && npx tsc --noEmit` — typecheck frontend
- `python -m py_compile <file>` — quick syntax check
- Pre-commit runs: ruff, ruff-format, detect-secrets, bandit, mypy
- After detect-secrets hook: `git add .secrets.baseline` (always re-stage)

## Code Conventions

- Commit style: `feat(waveXX): description` — NEVER include `Co-Authored-By` trailer under any circumstances
- Testing & Waves Association: Testing coverage/roadmaps do NOT belong to waves (waves are strictly for main business features). Do not associate testing work with waves in logs or commits
- Branch: `egorribun`
- Exception handling: narrowed to specific types with `# RZ-20-04` / `# RZ-22-01` audit comments
  - DB/network: `(OSError, ConnectionError)`
  - File ops: `(FileNotFoundError, OSError)`
  - Redis: `(ConnectionError, TimeoutError, OSError)`
  - PyO3/Rust: `(RuntimeError, ImportError, OSError)`
  - SMTP: `(OSError, smtplib.SMTPException)`
  - Keep broad `except Exception` only for: re-raise-after-cleanup, convert-to-domain, handler-nak, fail-closed auth
  - ALL broad catches must be tagged: `# RZ-22-01-JUSTIFIED: <reason>` (Wave 22 completed: 147 justified, 29 narrowed)
  - Python 2 except syntax: always use `except (A, B):` tuple form, NEVER `except A, B:` (convention enforced since Wave 23)
- Models: ALL relationships must have explicit `lazy="noload"` — prevent N+1
- Settings: use `@cached_property` namespace accessors (settings.db, settings.security, etc.)
  - Phase 2 (Wave 21): accessors return `_NamespaceView` proxies, not `self`
- Frontend validation: **Valibot only** (Zod removed in Wave 21)
- Frontend debounce: `useDebounced` from `@/hooks/useDebounced` — strategy presets: `"search"` (200ms), `"default"` (300ms), `"validation"` (350ms) (PERF-23-04, Wave 23)
- Frontend sanitization fallback: SafeHtml strips HTML tags on WASM failure — never renders nothing (RZ-24-04)
- Frontend memo: `React.memo()` on list/grid/dashboard components
- GraphQL: 5 defense layers — QueryDepthLimiter, MaxTokensLimiter, QueryCostExtension, RequestTimeoutExtension, PersistedQueryExtension (prod only)
- Feature flags: `from app.core.feature_flags import is_enabled` (async) or `is_enabled_sync`
- Password hashing: Argon2id only — **bcrypt verification removed** (TD-21-04, Wave 21)
- Valkey eviction: `volatile-lru` (changed from allkeys-lru in Wave 21 — RZ-21-02)
- OTEL Metrics: bridge via `PrometheusMetricReader` in `configure_metrics()` — new metrics use OTEL API, legacy use prometheus_client (MOD-23-05)
- Suspense queries: `useSuspenseMyEventsQuery` for components inside `<Suspense>` — do NOT use for offline-fallback hooks (MOD-23-02)
- Bundle budget: main JS chunk must be <500 KB (enforced in CI via bundle-analysis job, MOD-23-06)
- L1 cache metrics: `cache_l1_hits_total`, `cache_l1_misses_total` Prometheus counters (TD-30-05)
- CI: `relationship(` without `lazy=` rejected by MOD-30-01 gate — use `# noload-exempt: <reason>` for exceptions
- Gateway: startup errors use channel-based propagation, not `os.Exit` — defers always execute (RZ-31-01)
- Gateway gRPC: 30s default per-RPC timeout via service config (RZ-31-05)
- ws-hub: oversized messages (>60 KB) send `message_too_large` error frame to client (RZ-31-02)
- ws-hub: `maxClients` pre-check in HandleWebSocket before upgrade (TD-31-05)
- Frontend `waitForRateLimitWindow`: accepts optional `AbortSignal` (RZ-31-04)
- Frontend idempotency dedup: cross-tab sync via `BroadcastChannel("ecosystem.idempotency.dedup")` (TD-31-04)
- K8s ingress: `${FRONTEND_HOST}`, `${API_HOST}`, `${TLS_SECRET_NAME}` — use envsubst before `kubectl apply` (TD-31-02)
- K8s secret-store: `${VAULT_URL}` — set via envsubst (TD-31-03)
- Go services: `.golangci.yml` with `exhaustive` linter — catches unchecked enum switch cases (MOD-31-01)
- OTEL: all Go services register composite propagator (TraceContext + Baggage) (MOD-31-02)
- Rate limit: `RedisCircuitBreaker` in `app/core/ratelimit/circuit_breaker.py` — 3-state machine with exponential backoff (PERF-30-01)
- Gateway L1 cache: XFetch probabilistic refresh via `shouldRefreshProbabilistic()` — prevents stampede (PERF-31-02)
- Gateway JWKS: `StartJWKSRefresher(ctx, endpoint, interval, logger)` — background polling + atomic key swap (MOD-W17-03)
- Gateway JWKS config: `JWKS_ENDPOINT` (empty=disabled), `JWKS_REFRESH_INTERVAL` (default 300s)
- Helm chart: `charts/university-ecosystem/values.yaml` fully parameterized — frontend, ingress (TLS), resources, autoscaling (MOD-30-04)
- ADR-012: Centralized logging — Grafana Loki + Fluent Bit (MOD-W16-03)
- ADR-013: Secret rotation — three-tier strategy, dual-key JWT window (MOD-W16-07)
- ChatService DI: fully migrated to Dishka narrow services — no monolithic wrapper (TD-30-01 verified Wave 32)
- DI: `NotificationService` provided by `ContentProvider` only — removed duplicate from `UserProvider` (TD-33-08)
- Thread-safe singletons: all module-level singletons use DCL pattern with `threading.Lock` (RZ-33-29)
- `cached()` decorator: `_l1_ttl` param now forwarded to TieredCache L1 layer (TD-33-09)
- `RedisClusterCache.invalidate()`: supports glob patterns via SCAN (TD-33-10)
- Go file-processor: env vars require `FP_` prefix (e.g. `FP_GRPC_PORT`) per `SetEnvPrefix("FP")`
- Pyroscope: `grafana/pyroscope:1.19.1` in docker-compose.observability.yml
- Tests: S105/S106 (hardcoded password) suppressed in `tests/` via pyproject.toml per-file-ignores

## Bypass policy

GitHub admin bypass on the main-branch ruleset is intentionally left enabled for
this single-maintainer repository. The accepted admin bypass risk is that a
false-positive gate or third-party outage can be bypassed to avoid a deadlock.
Any bypass merge must record a bypass reason in the PR description or merge commit message.

## Gotchas

> Active technical constraints and gotchas grouped by subsystem domain.

### Backend Domain
- `py314`, mypy `3.14`; Ruff `>=0.14.14,<0.15`; `fail_under = 80`; tuple `except (A, B):`(`no-python2-except`); `lazy="noload"` on all relationships (CI gate exempt `# noload-exempt: <reason>`)(`no-python2-except`); Alembic Windows glob `**/*alembic*/**/*.py`; Ruff S105 `per-file-ignores`; mypy `: ignore[return-value]` unneeded; OpenFeature optional; `NullSessionBackend` closed prod; `S3Storage` `asyncio.timeout()`.
- `StaticFSStorage._validate_resolved_path()` symlinks & `is_relative_to(base_dir)`; `_validate_dependent_settings()` `cache_backend` -> `redis_url`/pools/replicas; `@invalidates_cache(CacheTag.EVENT)`; `WsHubClient`: DCL + `threading.`; `WeakValueDictionary`: local strong ref (` lock = d.get(k); if lock is None: lock = asyncio.Lock(); d[k] = `); direct `d[k] = asyncio.Lock()` -> `KeyError`; `="noload"` all relationships (CI gate `# noload-: <reason>`); dual FKs `foreign_keys=`; `server_default` Python `=`, DTO `model_validate` -> `MissingGreenlet`.
- updating `ChatResponse` 5 sites + `ChatDTO`; `MessageResponse` fields (`read_at`) all sites; `extra="forbid"` fixtures; `_set_rls_user`  SQLite (`OperationalError`); test DB `db_session` ( `async_client`).; `Chat.chat_type`: `String(20)` + `CheckConstraint("chat_type ('dm', 'group')")` (`="dm"`, `server_default="dm"`); `add_participant`/`remove_participant` invalidate `chat:{id}:participants` & presence; authz 400/404; removals: owner-kick/self-leave; `add_participant` -then-insert (`if await self.check_participant(...): return False`); DMs: `Message.read_status`.
- groups: `ChatReadReceipt(chat_id, user_id, last_read_at)`; `group_unread_cte` `sender_id != me (last_read_at NULL created_at > last_read_at)`; `mark_messages_read` `(read_at, affected)`; `Message.reply_to_message_id` self-FK; `send_message` validates `message_exists_in_chat`, loads `selectinload(replied_to)`, serializes `ReplyPreview.from_message(replied_to)`; `MessageResponse.content` tombstone `content=""`; outbox `handle_message_sent` sender `await db.(User, message.sender_id)`; sync `broadcast_to_chat` `mark_read`/typing/presence; outbox `new_message`; `publish_core`: `orjson.dumps(payload, =str)`; : `if self._nc None self._nc.is_connected: return`.

### Frontend Domain
- Valibot; `React.memo()` forbidden infer; render ref access compiler -> primitives (`userId = user?.id`, `swipeDir` state); `" no memo"` + `// eslint-disable-next-line react-compiler/react-compiler` ref; `ref` directly; mount `hydrateRoot` (`<div id="root">` `<html>` -> React #418); portals/`matchMedia`/`localStorage` `mounted` pattern (`mounted=true` `useEffect`); `window.__APP_HYDRATED` `AppProviders.tsx`; -hydrate DOM mutations React 19 -> emit SSR JSX `suppressHydrationWarning`; `news.tsx` = layout (`<Outlet />`), `news.index.tsx` = index; `events.index.tsx` & `events.$id.tsx` `_auth`; params: `$token`; nav: `navigate({ to: "/path" })`; schemas `features/{page}/schema.ts`; `stringifySearch` numeric strings (`?z="16"` -> `?z=%2216%22`) -> schemas need string/number unions.
- guards (`_auth.tsx`, `_public.tsx`, `_admin.tsx`) read Zustand `useAuthStore.getState()` `beforeLoad`; `_public.tsx` `PublicLayout` & `Login.tsx` `useAuthStore.user` `redirectedRef` guard; `resolveRedirectPath()` open-redirect check; `useSuspenseMyEventsQuery` `<Suspense>` only; infinite query `page.items`; NEVER put `useMutation` result object in deps -> referentially-stable `mut.mutate`. `build.rolldownOptions`, `manualChunks`; React Compiler `@rolldown/plugin-babel`; `build.modulePreload`; assets <= 4 KB; dynamic `import("jspdf")` pdf-lib modulepreload & PWA manifest (`globIgnores`); `useReducedMotion()` guard (`prefersReduced ? { duration: 0 } : { type: "spring" }`); `style.transform` CLS; scoped token files; `text-[var(--sched- -accent)]`/`text-[var(--text-inverse)]` brand bgs; double-class selectors (`.sched-current-glow.sched-current-glow`) CSS `!important`.
- `overflow: clip`/`overflow-x-clip`; outer containers `overflow` (breaks sticky); `view-transition-name`; flex shrink: `self-stretch max-w-N mx-auto`; percent height: `height: 100%` `min-height: 100dvh`; controls min 44x44px; links `-block min-h-[24px] px-2 py-1.5`; dialogs: `role="dialog"`/`alertdialog`, `aria-labelledby`/`describedby`, `aria-modal="true"`, `useFocusTrap`; inputs: helper text `aria-describedby` + error `role="alert"`; menus/tables: `focus-visible:ring-2`, `aria-sort` `<th>`, `scope="col"`/`row`; ARIA Grid: `<div role="row" style={{display: "contents"}}/>`; skeletons: `aria-busy="true"`; charts: hidden `<table className="sr-only"/>`; chat: `role=""`, `aria-live="polite"`; typing: `role="status"`.
- radios: `role="radiogroup"`/`radio` + `aria-checked`; QRCodeSVG: `aria-="true"`; markers: `useStripMaplibreMarkerChrome`; focus: CSS `scroll-margin-top` `:focus-visible`; MapLibre GL; `campusBuildings.ts` `geoCoords: [lat, lng]` `longitude={coords[1]} latitude={coords[0]}`; load: `React.(() => import("@/components/map/MapLibreMap"))`; `localStorage`; cross-tab sync `BroadcastChannel("ecosystem.idempotency.dedup")` & `BroadcastChannel("ecosystem.news.bookmarks")`; NEVER create Blob URLs render -> `useRef<<string>>` &; exclude `.stories.tsx` `vitest.config.ts` `coverage.exclude`; Storybook: `viteFinal` `build.rolldownOptions.output.strictExecutionOrder = true` & `vite-plugin-pwa`; MapLibre markers `<Map mapStyle={EMPTY_STYLE}>`; Vitest CLI `--silent` `=true` (`npx vitest --silent=true`); polyfills: `ResizeObserver`, `Element.hasPointerCapture`, `scrollIntoView`.
- mount helper: `renderWithRouter` `src/tests/helpers/renderWithRouter.tsx`; `afterEach` resets `useAuthStore.setState({ user: null, loading: true, ... })`; tests: `describe({ retry: 2 }, ...)`.

### Go Services Domain
- errors channel propagation (no `os.Exit`); gRPC RPCs 30s timeout `WithDefaultServiceConfig`; rate limit : 3 req/60s per instance; `StartJWKSRefresher` +; Gin `/api/v1/*` auth dispatch; `ProxyOrFileHandler` intercepts `/files/process/sync` -> gRPC, proxies rest; empty `room_id` NATS `cache.invalidate` eviction.
- : `Hub.mu` -> `Client.mu`; `NakWithDelay(5s)` redelivery storm; goroutines: `WaitGroup` + `ws_hub_active_goroutines` gauge; `WritePump` `c.ctx.Done()`; >60 KB & `message_too_large` error frame; `maxClients` `HandleWebSocket` upgrade; incoming messages `allowedMessageTypes` map.
- WS upgrade `/ws` (`handlers.go`), frontend `/ws/chat` -> Caddy `handle /ws/chat* { * /ws; 8081 }`; `/ws/ticket` backend HTTP ( OTT), WS endpoint -> Caddy handle `/ws/ticket` `gateway:8080` general `/ws/*` rule ws-hub:8081; room-join backend `/api/v1/chat/-participant` ( `/api//...`); `REDIS_PASSWORD` env var ws-hub compose L2 OTT (`ott:ws:<ticket>`) validation; `ALLOWED_ORIGINS` `http://localhost` (port 80 Caddy) compose, else `CheckOrigin` 403.; Env vars `FP_` (`SetEnvPrefix("FP")`).
- `sourceKey`/`destKey` traversal gRPC; max 1024 bytes; options map <= 10 entries; GraphQL engine depth limit (10) + timeout (30s) middleware; escaped quotes `estimateQueryDepth`; `schema.graphql` 'd runtime container WORKDIR `/app`; `graph-gophers/graphql-go v1.9.0+` strict `gql.ID`.
- auth interceptors (`selectiveUnaryAuth`/`selectiveStreamAuth`) auth `/grpc.health.v1.Health/` `grpc_health_probe` 401; `.golangci.yml` `exhaustive` (unchecked enum switch cases) & `gosec`; all Go services register OTEL propagator.

### Docker / K8s / CI Domain
- `uv lock --check` PR locally `main` Dependabot bump -> `git merge origin/main`; `.secrets.baseline` commit; pre-commit any ruff error; Husky v9+: parent-dir paths (`.. allowed`); `setup-husky.cjs` `git config --local core.hooksPath .husky`; pre-commit shell scan raw `docker compose -f docker-compose.full.yml` -> `bash scripts/dc.sh` `pwsh scripts/dc.ps1`; all Actions SHA-; coverage: Py 80%, Go 60%; `actions/upload-artifact@v7` files ( `--files: true` `.lighthouseci/` dirs).
- `process.env.VAR` `""` empty `if (envVar) ...`; pre-staged `git mv` into next `git commit` even if unspecified (`git status --short`); successive pushes same branch -progress CI runs (`concurrency.- -progress: true`).; Backend: `python:3.14-slim-bookworm`; Frontend SSR: `node:24-alpine` port 3000; file-processor Dockerfile `grpc_health_probe` & `schema.graphql` WORKDIR `/app`; docker-compose `bash scripts/dc.sh` `pwsh scripts/dc.ps1`; backend compose healthcheck Dockerfile HEALTHCHECK `/health/ready` `service_healthy`; port mappings EXPOSE (`3000:3000` SSR).
- healthchecks: imgproxy (`imgproxy health`), grafana (`/api/health`), prometheus (`/-/healthy`), file-processor (`grpc_health_probe -addr=:50051`); Tempo/Loki curl; Temporal dev server bind `0.0.0.0` bridge network; `VITE_BACKEND_ORIGIN` build time, container env; `envsubst` `${FRONTEND_HOST}`, `${API_HOST}`, `${TLS_SECRET_NAME}`, `${VAULT_URL}`; backend: anti-affinity & `topologySpreadConstraints`; frontend : `seccompProfile: RuntimeDefault`, port 3000, `/tmp` `emptyDir`; `gateway.config.jwtSecret` Helm; `values.yaml` `DATABASE_URL` empty placeholder.
- Kyverno Policy 9 `disallow-latest-tag` empty/latest tags; Canary : Caddy `lb_policy weighted_round_robin 100 0` `frontend-stable` deployment; `lhci collect` Windows EPERM: `lhci-windows-fallback.mjs`; `npm lhci:windows`; LHCI `VITE_LHCI=true`; prod `VITE_LHCI=true`; static dist dir points `dist/client/`; Chrome `--disable-gpu` Linux CI screenshots `--headless=new`; Linux CI CLS `error@0.05`.
- Perf score Windows; `Promise.([server.close(), timeout])` + explicit `process.exit(0)` lingering Worker handles.

### Security / Auth / Cryptography Domain
- Argon2id (bcrypt removed); Argon2 concurrency 4 per worker; `docs/` files passwords `# pragma: allowlist secret` detect-secrets; Renovate crypto packages code review; secret : Three-tier strategy, dual- JWT window; ExternalSecret `refreshInterval: 1m`; Rust `Cargo.toml`: version pins security-critical dependencies; RS256 algorithm.
- private `.secrets/jwt_rs256.pem`; `LoginSessionManager.finalize_login` extra claim: `user.role.value`; `validateJwt` claims (`sub`, `exp`, `aud`, `role`) fallbacks; Gateway JWKS Refresher `/.well-known/jwks.json` (RS256 RSA keys `kty=RSA + n + e`) `keys.rotated` NATS subject; dual JWKS: `/.well-known/jwks.json` = RSA JWKS; `/api/v1/.well-known/jwks.json` = HMAC stub (`kty=oct`.; `access_token_v2` HttpOnly cookie `cookie_samesite="lax"`; `UserComplianceService._revoke_user_sessions` revoked JTIs Redis `session:revocations`.
- `secrets.token_hex(16)` timing normalization; anon nonce regex `_ANON_NONCE_RE`; frontend CSRF cookie (` /api/v1/auth/csrf-cookie`) `ensureCsrfCookie()` unsafe methods if missing; Structlog `_redact_pii` email (>=2-char TLD) & phone; NEVER tokens `globalThis.__ssrCookieGetter()`; WASM `strip_html`/`sanitize_rich_text`; `NewsDetailBody` ammonia strip `<script>`, tables, img, hr; Service worker `/users/me`, `/auth/*`, `/csrf`.
- traversal: `StaticFSStorage._validate_resolved_path()` symlinks & `is_relative_to(base_dir)`; Node SSR `server-prod.mjs` `startsWith(staticRoot)`; file-processor `sourceKey`/`destKey` gRPC; BOLA/Cross-Chat: Message snapshot `forwarded_from_name`; reply targets `message_exists_in_chat`; group `check_participant` 400/404; file upload XSS: `MessageInput` `image/svg+xml` & `.svg` (`endsWith(".svg")`), first 512 bytes `<svg`; `SPICEDB_MAX_TOLERABLE_DOWNTIME_SECONDS=45`.

## Audit Trail

> **Canonical Audit Index**: Full wave audit history and active wave reports are maintained in [`docs/audits/INDEX.md`](docs/audits/INDEX.md).
> Active wave audits: [`AUDIT_WAVE211.md`](docs/audits/AUDIT_WAVE211.md), [`AUDIT_WAVE210.md`](docs/audits/AUDIT_WAVE210.md), [`AUDIT_WAVE209.md`](docs/audits/AUDIT_WAVE209.md).
> Archived wave audits: [`docs/audits/archive/`](docs/audits/INDEX.md).

