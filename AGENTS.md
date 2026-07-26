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
*FastAPI, SQLAlchemy 2.0, Python 3.14, Redis/Valkey, Postgres, Asyncio, Pydantic v2, Alembic, NATS Python*

#### Code Environment & Syntax
- **Python Version & Tooling**: Ruff target version `py314`; mypy `python_version = 3.14`. Ruff dev dep pinned `>=0.14.14,<0.15` (v0.15.x strips parens).
- **Except Syntax**: Always use Python 3 tuple form `except (A, B):`, NEVER Python 2 `except A, B:`. Enforced locally via `no-python2-except` pre-commit hook and CI regex gate.
- **Alembic Glob on Windows**: `**/alembic/versions/*.py` glob may fail on Windows shell; use `**/*alembic*/**/*.py`.
- **Ruff & Mypy Ignores**:
  - Ruff S105: False positive on field names containing "password" (enum values, API URLs); suppress via `pyproject.toml` `per-file-ignores`, not inline `noqa`.
  - Mypy: `type: ignore[return-value]` not needed when returning `self` from subclass.
- **OpenFeature SDK**: Optional dependency; `app.core.feature_flags` gracefully degrades when not installed.
- **Coverage Requirement**: `fail_under = 80` in `[tool.coverage.report]`.

#### Storage, Caching & Singletons
- **NullSessionBackend**: Fails closed in production; only dev/test/local environments allowed.
- **S3Storage**: All save/delete/read/exists operations must be guarded with `asyncio.timeout()`.
- **StaticFSStorage**: `_validate_resolved_path()` rejects symlinks and verifies `is_relative_to(base_dir)` to prevent path traversal.
- **Cache & Settings Validation**: `_validate_dependent_settings()` cross-checks `cache_backend` -> `redis_url`, pool size, and replica URL.
- **Cache Invalidation Decorator**: Use `@invalidates_cache(CacheTag.EVENT)` for automatic tag-based cache invalidation.
- **WsHubClient Singleton**: Use `threading.Lock` with double-checked locking for thread safety under Python free-threading.
- **WeakValueDictionary Cache**: Must hold a local strong reference before setting key: `lock = d.get(k); if lock is None: lock = asyncio.Lock(); d[k] = lock`. Storing direct weak references (`d[k] = asyncio.Lock()`) causes immediate CPython GC reclamation and `KeyError` on read-back.

#### SQLAlchemy & Database Rules
- **N+1 Prevention (`lazy="noload"`)**:
  - ALL SQLAlchemy relationships MUST explicitly set `lazy="noload"` (enforced in CI via MOD-30-01 gate; use `# noload-exempt: <reason>` if exempted).
  - MOD-30-01 regex gate is comment-blind: NEVER write `relationship (` in Python comments or the gate will falsely fail.
  - Adding a second FK between the same two models (e.g. two FKs from `Message` to `messages` or `chats`) breaks inferred joins -> requires explicit `foreign_keys=` parameter on `relationship(...)`.
- **Server Default & Mapped Columns**: Mapped columns with `server_default` MUST also set an explicit Python `default=` value on `mapped_column(...)`, otherwise async Pydantic DTO validation (`model_validate`) on un-refreshed instances triggers lazy DB refresh and raises `MissingGreenlet`.
- **Schema & DTO Fan-Out**:
  - `ChatResponse` is built at 5 separate service sites; adding a field to `ChatResponse` requires updating all 5 explicit constructor sites AND declaring the field in `ChatDTO`.
  - Schema-added fields on `MessageResponse` (e.g., `read_at`) must be explicitly passed in every `MessageResponse(...)` construction site.
  - Test fixtures using Pydantic `extra="forbid"` (e.g., `_mock_chat`) must explicitly define newly added schema fields.
- **PostgreSQL RLS & SQLite Integration Tests**: `GET /chats/{id}` calls `_set_rls_user` (`SET LOCAL app.current_user_id`), which SQLite rejects (`OperationalError`). DB-persisted effects must be tested in repository unit tests against `db_session`, not via HTTP `async_client` tests.

#### Chat & Messaging Backend Mechanisms
- **Chat Types & Schema**: `Chat.chat_type` is `String(20)` with `CheckConstraint("chat_type IN ('dm', 'group')")`. Dual `default="dm"` and `server_default="dm"` required.
- **Group Membership & Cache Invalidation**:
  - Membership changes (`add_participant`/`remove_participant`) MUST invalidate `chat:{id}:participants` and presence audience caches post-commit.
  - Authz checks execute BEFORE 400/404 validation (do not reveal DM existence to non-participants). Owner-kick or self-leave allowed for removals.
  - `add_participant` uses check-then-insert (`if await self.check_participant(...): return False`), NOT PostgreSQL-only `pg_insert.on_conflict_do_nothing` (enables SQLite test compatibility).
- **Group Unread & High-Water Mark**:
  - DMs use `Message.read_status`; groups use per-recipient `ChatReadReceipt(chat_id, user_id, last_read_at)` timestamp high-water-mark.
  - `group_unread_cte` joins `ChatReadReceipt` and counts `sender_id != me AND (last_read_at IS NULL OR created_at > last_read_at)`.
  - `mark_messages_read` returns `(read_at, affected)`. Threads `chat_type` through both WS dispatcher and `ChatMaintenanceService.mark_read`.
- **Message Replies & Quotes**:
  - `Message.reply_to_message_id` self-FK (`remote_side="Message.id"`, `lazy="noload"`, `ondelete="SET NULL"`).
  - `send_message` validates target in-chat via `message_exists_in_chat`, loads `selectinload(replied_to)`, and serializes `ReplyPreview.from_message(replied_to)` (lean DTO).
- **Soft-Deleted Messages**: `MessageResponse.content` overrides `MessageBase` to remove `min_length=1` constraint (allows `content=""` tombstone).
- **Outbox & Domain Events**:
  - `handle_message_sent` outbox handler MUST explicitly fetch sender via `await db.get(User, message.sender_id)` because `Message.sender` is `lazy="noload"`.
  - Ephemeral events (`mark_read`, typing, presence) broadcast synchronously via `broadcast_to_chat`; domain events (`new_message`) pass through outbox.
- **NATS Python Core Broker (`publish_core`)**:
  - Payload serialization MUST use `orjson.dumps(payload, default=str)` for native UUID/datetime support.
  - NEVER trigger a connection attempt on the ephemeral hot path (`if self._nc is None or not self._nc.is_connected: return`).

### Frontend Domain
*React 19, Vite 8 / Rolldown, TanStack Router/Query, Valibot, Framer Motion, WCAG 2.2 AA, CSS Tokens, Storybook, Playwright/Vitest*

#### React 19 & React Compiler
- **Validation**: Valibot only (Zod completely removed).
- **Memoization & React Compiler**:
  - `React.memo()` forbidden in "infer" mode; use `memo()` ONLY when custom `areEqual` comparators are supplied.
  - Ref access during render panics React Compiler! Extract property primitives to local variables or state outside render (e.g., `const userId = user?.id`, `swipeDir` state not ref).
  - `"use no memo"` directive + `// eslint-disable-next-line react-compiler/react-compiler` required when components touch refs in render-adjacent closures (e.g. `Dashboard.tsx` tilt ref, `ReactionPill.tsx` floating-ui ref merging).
  - React 19 ref-as-prop: Use `ref` prop directly; do not use `forwardRef`.
- **SSR Hydration & Mounting**:
  - Mount Target: TanStack Start v1 SPA/SSR mounts at `hydrateRoot(document, <App />)` (Document level). Mounting at `<div id="root">` nests `<html>` inside `<div>`, causing React #418 error.
  - SSR Portals & Browser APIs: `createPortal`, `matchMedia`, or `localStorage` reads at render time MUST use `useState`/`useEffect` `mounted` pattern (render `null` on server and first client render, set `mounted=true` in `useEffect`).
  - Hydration Sentinel: `window.__APP_HYDRATED` boolean set in `AppProviders.tsx` `useEffect` post-mount.
  - Imperative DOM mutations post-hydrateRoot (e.g., rAF classList additions) race React 19 comparison phase -> emit attributes via SSR JSX or use `suppressHydrationWarning`.

#### TanStack Router & Query
- **Routing Structure**:
  - Layout vs Index routes: `news.tsx` = layout route (requires `<Outlet />`), `news.index.tsx` = index route (exact match). `events.index.tsx` and `events.$id.tsx` are siblings under `_auth`.
  - Path params syntax uses `$token` (e.g. `/reset/$token`), NOT `:token`.
  - Navigation: `navigate({ to: "/path" })` object syntax.
  - Search Param Schemas: Every route uses Valibot schema in `features/{page}/schema.ts`.
  - Numeric Search Params: TanStack Router's `stringifySearch` JSON-quotes string values that look like numbers (`?z="16"` -> `?z=%2216%22`). Schemas must use string/number unions (e.g. `v.union([v.number(), v.pipe(v.string(), v.transform(parseFloat))])`).
- **Route Guards & State**:
  - Route guards (`_auth.tsx`, `_public.tsx`, `_admin.tsx`) MUST read live Zustand state via `useAuthStore.getState()` inside `beforeLoad` (router context object is static/immutable client-side).
  - `_public.tsx` `PublicLayout` and `Login.tsx` use reactive `useEffect` watching `useAuthStore.user` with `redirectedRef` guard. `resolveRedirectPath()` handles open-redirect protection.
- **TanStack Query / React Query**:
  - `useSuspenseMyEventsQuery` used ONLY inside `<Suspense>` — do NOT use for offline-fallback hooks.
  - Infinite Query Data: `page.items` contains items array, NOT `page.data`.
  - Mutation Object Dependency Loop: NEVER put `useMutation` result object into `useCallback`/`useEffect` deps. Depend ONLY on referentially-stable `mut.mutate` method (`const m = mut.mutate; useCallback(..., [m])`).

#### Vite 8 & Rolldown
- **Configuration**: Use `build.rolldownOptions` (not `rollupOptions`), `manualChunks` function form ONLY. React Compiler configured via `@rolldown/plugin-babel`.
- **Module Preloading**: `build.modulePreload: { polyfill: false, resolveDependencies(...) }` MUST be inside `build:` block in `vite.config.mts`.
- **Assets Inline Limit**: Assets ≤ 4 KB base64-inlined into JS entry chunk.
- **Vendor PDF Lazy-Loading**: Dynamic `import("jspdf")` requires excluding pdf-lib chunks from modulepreload and PWA manifest (`globIgnores`).

#### Framer Motion, CSS Tokens & Layout
- **Reduced Motion**: All spring animations MUST check `useReducedMotion()` guard: `prefersReduced ? { duration: 0 } : { type: "spring", ... }`.
- **CLS & Animations**: Inline `style.transform` mutations count toward CLS. Use `min-h-[Xpx]` Tailwind classes and opacity-only variants. Avoid `filter: blur()` in Framer Motion transitions.
- **CSS Tokens & Contrast**:
  - Scoped token files (`tokens/dashboard.css`, `tokens/activity.css`, `tokens/map.css`, `tokens/events.css`, `tokens/news.css`, `tokens/admin.css`, `tokens/messenger.css`, `tokens/auth.css`).
  - Use `text-[var(--sched-on-accent)]` or `text-[var(--text-inverse)]` on brand/colored bgs, NOT `text-white` (in dark mode brand colors like sky-400 require dark text slate-950 for WCAG AA 4.5:1).
  - Double-Class Specificity: Override CSS rules use double-class selectors (e.g. `.sched-current-glow.sched-current-glow`) instead of `!important`.
  - Overflow: Use `overflow: clip` or `overflow-x-clip` instead of `overflow-x: hidden` (which auto-sets `overflow-y: auto`).
  - Sticky Positioning: Outer containers MUST NOT have `overflow` property, or `position: sticky` breaks.
  - View Transitions: `view-transition-name` creates layout containment; never place on elements with `before:absolute` overlays. Only ONE element may have `viewTransitionName: "news-hero"` at any time.
  - Flex Shrink Quirk: Avoid `w-full max-w-N` inside `flex-col items-center` parents -> use `self-stretch max-w-N mx-auto`.
  - Percent Heights: `height: 100%` does NOT resolve against parent `min-height: 100dvh` -> parent needs explicit height or `h-[calc(100dvh-...)]`.

#### WCAG 2.2 AA & Accessibility
- **Touch Targets**: Minimum 44×44 px (`min-h-[44px] min-w-[44px]`) for interactive controls (WCAG 2.5.8). Inline text links use `inline-block min-h-[24px] px-2 py-1.5`.
- **Roles & ARIA**:
  - Dialogs: `role="dialog"`, `role="alertdialog"`, `aria-labelledby`, `aria-describedby`, `aria-modal="true"`. Focus trap via `useFocusTrap`.
  - Inputs: Helper text linked via `aria-describedby` + `role="alert"` on error.
  - Menus/Tables: `focus-visible:ring-2`, `aria-sort` on `<th>` column headers, `scope="col"`/`scope="row"` on table headers.
  - ARIA Grid: Rows use `<div role="row" style={{display: "contents"}}>`. Skeletons use `aria-busy="true"`. Charts render hidden `<table className="sr-only">`.
  - Chat & Logs: `ChatWindow` has `role="log"` + `aria-live="polite"`. Typing indicator uses `role="status"` + `aria-live="polite"`.
  - Radiogroups: Radio selectors use `role="radiogroup"` + `role="radio"` + `aria-checked` (NOT aria-pressed buttons).
  - Images & Icons: QRCodeSVG in labeled buttons needs `aria-hidden="true"`. MapLibre markers use `useStripMaplibreMarkerChrome` to strip wrapper `role="button"`.
  - Focus Not Obscured: Global CSS `scroll-margin-top` on `:focus-visible`.

#### MapLibre GL
- Single MapLibre GL mode (`react-map-gl/maplibre`).
- Coordinates: `campusBuildings.ts` stores `geoCoords: [lat, lng]` — MapLibre requires `longitude={coords[1]} latitude={coords[0]}`. NEVER swap indices!
- Lazy loading: `React.lazy(() => import("@/components/map/MapLibreMap"))` — maplibre-gl CSS+JS only loaded on `/map`.

#### Client Storage & Sanitation
- `localStorage`: Wrap all calls in try-catch for Safari private browsing compatibility.
- Cross-Tab Dedup: `BroadcastChannel("ecosystem.idempotency.dedup")`. Bookmarks use `BroadcastChannel("ecosystem.news.bookmarks")`.
- Optimistic Upload Blob URLs: NEVER create Blob URLs inline in render. Track URLs in `useRef<Set<string>>`, revoke on success/error/unmount (`URL.revokeObjectURL`).

#### Storybook & Vitest Testing
- `.stories.tsx` files MUST be excluded in `vitest.config.ts` `coverage.exclude`.
- Storybook config: `viteFinal` sets `build.rolldownOptions.output.strictExecutionOrder = true` and strips `vite-plugin-pwa`.
- Storybook MapLibre markers: Wrap in `<Map mapStyle={EMPTY_STYLE}>` with offline empty style.
- Vitest CLI `--silent` requires explicit `=true` syntax: `npx vitest run --silent=true`.
- Vitest setup polyfills: `ResizeObserver`, `Element.hasPointerCapture`, `scrollIntoView`.
- Test helpers: `renderWithRouter` in `src/tests/helpers/renderWithRouter.tsx` is canonical vitest mount helper.
- Store resets: `afterEach` must reset `useAuthStore.setState({ user: null, loading: true, ... })`.
- Flaky tests: Wrap with `describe({ retry: 2 }, ...)`.

### Go Services Domain
*ws-hub, file-processor, gateway, caddy, NATS Go, gRPC, Temporal Go SDK*

#### Gateway Service
- **Startup Error Handling**: Startup errors use channel-based error propagation, NOT `os.Exit` (ensures defers always execute).
- **gRPC RPC Timeout**: `WithDefaultServiceConfig` enforces default 30s timeout on all gRPC RPCs.
- **Rate Limit Fallback**: 3 req/60s per instance fallback (health probes exempt).
- **JWKS Refresher**: `StartJWKSRefresher(ctx, endpoint, interval, logger)` runs background polling and atomic key swap. Configured via `JWKS_ENDPOINT` and `JWKS_REFRESH_INTERVAL` (default 300s). Subscribes to `keys.rotated` NATS subject.
- **Gateway Gin Routing**: All `/api/v1/*path` routes handled in single Gin wildcard with inline auth dispatch to avoid tree conflicts. `ProxyOrFileHandler` intercepts `/files/process/sync` -> gRPC, proxies rest.

#### ws-hub Service (WebSocket Hub)
- **Auth Cache Eviction**: Empty `room_id` in NATS `cache.invalidate` triggers wildcard eviction.
- **Lock Hierarchy**: `Hub.mu` -> `Client.mu` (NEVER reverse).
- **Broadcast & Goroutines**: `NakWithDelay(5s)` prevents redelivery storm. Active goroutines tracked via `WaitGroup` + `ws_hub_active_goroutines` gauge. `WritePump` selects on `c.ctx.Done()` so goroutine exits when `ReadPump` cancels.
- **Ingress & Message Limits**: Oversized messages (>60 KB) dropped at ingress and broadcast; client notified with `message_too_large` error frame. `maxClients` pre-check in `HandleWebSocket` before HTTP upgrade. Incoming messages validated at parse boundary via `allowedMessageTypes` map.
- **Routing & Path Traps**:
  - WS Path Mismatch: ws-hub serves WS upgrade at `/ws` (`handlers.go`), whereas frontend requests `/ws/chat`. Requires Caddy rewrite: `handle /ws/chat* { rewrite * /ws; reverse_proxy ws-hub:8081 }`.
  - Caddy `/ws/ticket` Exception: `/ws/ticket` is a HTTP POST endpoint on backend (issues short-lived OTT), NOT a WebSocket endpoint on ws-hub! Caddy MUST handle `/ws/ticket` via reverse_proxy to `gateway:8080` BEFORE the general `/ws/*` rule to ws-hub:8081.
  - Room-Join Auth Endpoint: ws-hub calls backend internal check `/api/v1/chat/check-participant` (NOT `/api/internal/...`).
  - Redis OTT Auth Config: `REDIS_PASSWORD` env var MUST be passed to ws-hub in compose so L2 cache works for OTT (`ott:ws:<ticket>`) validation.
  - Allowed Origins: `ALLOWED_ORIGINS` env must include `http://localhost` (port 80 via Caddy) in compose, else gorilla/websocket `CheckOrigin` callback returns 403 Forbidden.

#### file-processor Service
- **Environment Variables**: All env vars require `FP_` prefix (e.g. `FP_GRPC_PORT`) per `SetEnvPrefix("FP")`.
- **gRPC Boundary Validation**: `sourceKey`/`destKey` path traversal rejected at gRPC boundary; max 1024 bytes. Options map bounded to 10 entries. Validated before Temporal workflow start.
- **GraphQL Engine**: Depth limit (10) + timeout (30s) middleware required. Escaped quotes handled in `estimateQueryDepth`.
- **GraphQL Schema & ID Types**: `schema.graphql` MUST be COPY'd to runtime Docker container WORKDIR `/app`. `graph-gophers/graphql-go v1.9.0+` requires strict `gql.ID` type returns on resolver methods (`File(args struct{ ID gql.ID })`, `FileResolver.ID() gql.ID`).
- **gRPC Health Probe Interceptor**: Selective auth interceptors (`selectiveUnaryAuth`/`selectiveStreamAuth`) MUST bypass auth for `/grpc.health.v1.Health/` method prefix, or `grpc_health_probe` fails with 401 Unauthenticated exit code.

#### Go Tooling & Observability
- **Linters**: `.golangci.yml` enables `exhaustive` (catches unchecked enum switch cases) and `gosec` linters.
- **OTEL Trace Propagation**: All Go services register composite propagator (`TraceContext` + `Baggage`).

### Docker / K8s / CI Domain
*Helm, Kyverno, Dockerfiles, GitHub Actions, pre-commit, uv.lock, Caddyfile, docker-compose, LHCI*

#### Dependency Lockfiles & Pre-commit
- **uv.lock Gate Failure**: `uv lock --check` failure on PR when passing locally is almost always `main` ahead with an unmerged Dependabot dep bump (`pyproject.toml` drift). Diagnostic: `git fetch origin main && git log origin/main ^HEAD --oneline`. Fix: `git merge origin/main` into feature branch and regenerate `uv.lock`. NEVER run `uv lock --upgrade`.
- **Pre-commit Rules**:
  - Re-stage `.secrets.baseline` before retrying git commit. Pre-commit blocks on any ruff error.
  - Husky v9+: Rejects parent-directory paths (`.. not allowed`). Use Node setup script `setup-husky.cjs` to run `git config --local core.hooksPath .husky`.
  - Pre-commit shell scan: Rejects raw `docker compose -f docker-compose.full.yml` in code/scripts -> use helper scripts `bash scripts/dc.sh` or `pwsh scripts/dc.ps1`.

#### GitHub Actions & CI
- **Action Security & Quality**: ALL GitHub Actions MUST be SHA-pinned (no mutable tags). Python test coverage threshold 80%, Go test coverage 60%.
- **Action Artifacts v7**: `actions/upload-artifact@v7` strips hidden files/dirs by default! Must explicitly set `include-hidden-files: true` for `.lighthouseci/` or hidden build directories.
- **Workflow Input Trimming**: `process.env.VAR` receives `""` when workflow input defaults to empty string. Use explicit truthiness check `if (envVar) ...` rather than `?.` (which treats `""` as truthy).
- **Git Rename & Concurrency**:
  - Pre-staged `git mv` renames get bundled into the next `git commit` even if unspecified — check `git status --short`.
  - Successive pushes on the same branch cancel in-progress CI runs (`concurrency.cancel-in-progress: true`).

#### Docker & Container Infrastructure
- **Dockerfiles**:
  - Backend: Uses `python:3.14-slim-bookworm` in builder and runtime.
  - Frontend Node SSR: Uses `node:24-alpine`. Runs custom SSR wrapper `frontend/scripts/server-prod.mjs` on port 3000. `USER node` (UID/GID 1000). Healthcheck on `/healthz`.
  - file-processor: Multi-stage Dockerfile copies `grpc_health_probe` binary and `schema.graphql` into runtime WORKDIR `/app`.
- **Docker Compose Helpers & Service Health**:
  - ALWAYS invoke docker-compose via helpers `bash scripts/dc.sh` or `pwsh scripts/dc.ps1` to prevent cwd drift errors.
  - Backend compose healthcheck: Override Dockerfile HEALTHCHECK to use `/health/ready` (DB readiness) for `service_healthy`, not `/healthz` (full check including ES/SpiceDB/Tempo).
  - Port mappings: Must match container EXPOSE ports (e.g. `3000:3000` for Node SSR).
  - Service Healthchecks: imgproxy (`imgproxy health`), grafana (`/api/health`), prometheus (`/-/healthy`), file-processor (`grpc_health_probe -addr=:50051`). Tempo/Loki distroless services use curl sidecar containers.
  - Temporal dev server: Must bind `0.0.0.0` (drop `--ip 127.0.0.1`) so file-processor can connect across bridge network.
  - Build-time vs Runtime Env Vars: `VITE_BACKEND_ORIGIN` is baked at Vite build time (`frontend.build.args.VITE_BACKEND_ORIGIN`), NOT read from runtime container env.

#### Kubernetes & Helm
- **Ingress & Secrets**: Use `envsubst` variables (`${FRONTEND_HOST}`, `${API_HOST}`, `${TLS_SECRET_NAME}`, `${VAULT_URL}`), not hardcoded values.
- **Pod Security & Topology**: Backend uses pod anti-affinity (hostname) and `topologySpreadConstraints` (zone). Frontend pod has `seccompProfile: RuntimeDefault`, ingress port 3000, and writable `/tmp` `emptyDir`.
- **Helm**: `gateway.config.jwtSecret` is required (empty string fails template rendering). `values.yaml` `DATABASE_URL` is empty placeholder.
- **Kyverno**: Policy 9 `disallow-latest-tag` rejects empty or latest image tags.
- **Canary Rollout Architecture**: Caddy `lb_policy weighted_round_robin 100 0` with `frontend-stable` deployment (`RollingUpdate`, `maxUnavailable: 0`).

#### Lighthouse CI (LHCI)
- **Windows EPERM Flake**: `lhci collect` hits EPERM on chrome-launcher cleanup. Use `npm run lhci:windows` (`lhci-windows-fallback.mjs`), which writes JSON before cleanup and uses embedded vite preview server.
- **Build Mode**: LHCI build uses `VITE_LHCI=true` (suppresses push panel & enables mock user `lhci-mock-user`). Prod build MUST NOT set `VITE_LHCI=true` (Rolldown DCE eliminates mock user).
- **Static Dist Dir**: Points to `dist/client/` under TanStack Start.
- **Linux CI Perf Metric Null**: Chrome `--disable-gpu` flag blocks screenshot collection on Linux CI under `--headless=new`, leaving composite Perf score null. Individual metrics (CLS, LCP, TBT) measure fine via CDP. Linux CI gates on CLS `error@0.05`; canonical Perf score measured via Windows fallback wrapper.
- **Process Cleanup**: Use `Promise.race([server.close(), timeout])` + explicit `process.exit(0)` to prevent lingering Worker thread handles from hanging process exit.

### Security / Auth / Cryptography Domain
*Argon2id, CSRF, JWT/JWKS, PII Redaction, Secret Rotation, WASM Sanitizer, RLS, BOLA, Rate Limiting, Input Validation*

#### Password Hashing & Secrets
- **Password Hashing**: Argon2id only — bcrypt verification removed. Argon2 concurrency capped at 4 concurrent hashes per worker (128 MiB peak).
- **Secrets Management**:
  - `docs/` files with example passwords require `# pragma: allowlist secret` for detect-secrets.
  - Renovate crypto packages (cryptography, pyjwt, argon2-cffi) require manual code review.
  - Secret rotation: Three-tier strategy, dual-key JWT window (ADR-013). ExternalSecret `refreshInterval: 1m`.
  - Rust `Cargo.toml`: Exact version pins for security-critical dependencies.

#### JWT, JWKS & Session Security
- **RS256 Algorithm**: RS256 default algorithm. Private key stored at `.secrets/jwt_rs256.pem`.
- **JWT Claims**: `LoginSessionManager.finalize_login` threads `extra_claims={"is_active": bool(user.is_active), "role": user.role.value}`. `UserRole` MUST use canonical bare string value (`user.role.value`), NOT qualified repr (`str(user.role)`).
- **Frontend JWT Validation**: `validateJwt` checks claims (`sub`, `exp`, `aud`, `role`) with safe default fallbacks for backward compatibility.
- **Gateway JWKS Refresher**: Gateway polls `/.well-known/jwks.json` (RS256 RSA keys `kty=RSA + n + e`) and subscribes to `keys.rotated` NATS subject.
- **Dual JWKS Endpoints**:
  - `/.well-known/jwks.json`: Public RSA JWKS endpoint (`kty=RSA + n + e`).
  - `/api/v1/.well-known/jwks.json`: Internal HMAC metadata stub (`kty=oct` — DO NOT fetch for RSA token validation!).
- **Cookie Security**: `access_token_v2` HttpOnly cookie. `cookie_samesite` defaults to `"lax"` in both dev and prod (emergency rollback knob: `SECURITY_COOKIE_SAMESITE_OVERRIDE`).
- **Session Revocation Broadcast**: `UserComplianceService._revoke_user_sessions` calls `revoke_sessions_matching` which publishes revoked JTIs to Redis pub/sub `session:revocations`. Gateway listens and invalidates active tokens.

#### CSRF Protection & Headers
- **Timing Normalization**: `secrets.token_hex(16)` always called to normalize timing; anonymous nonce validated via compiled regex `_ANON_NONCE_RE`.
- **Proactive CSRF Acquisition**: Frontend auto-acquires CSRF cookie via `ensureCsrfCookie()` (`GET /api/v1/auth/csrf-cookie`) before unsafe HTTP methods (POST/PUT/PATCH/DELETE) if `csrf_token` cookie is missing.

#### PII Redaction & Logging
- `_redact_pii` structlog processor strips email/phone from log events. Email regex requires ≥2-char TLD; phone regex has negative lookahead/lookbehind.
- NEVER log raw session tokens, access tokens, or `globalThis.__ssrCookieGetter()` return values!

#### WASM Sanitizer & Content Security
- **WASM Sanitizer**: `strip_html` / `sanitize_rich_text` try-catch with regex fallback when WASM pkg not compiled.
- **HTML Sanitization**: `NewsDetailBody` uses ammonia HTML sanitizer (`sanitizeArticleHtml()`) to strip unsafe tags (`<script>`, tables, img, hr) before rendering.
- **Service Worker Route Exclusions**: Service worker MUST NOT intercept `/users/me`, `/auth/*`, `/csrf` to prevent caching authenticated user state or CSRF tokens.

#### BOLA, Path Traversal & Input Validation
- **Path Traversal Defense**:
  - `StaticFSStorage`: `_validate_resolved_path()` rejects symlinks and verifies `is_relative_to(base_dir)`.
  - Node SSR `server-prod.mjs`: Verifies `path.resolve(staticRoot, requested).startsWith(staticRoot)`.
  - file-processor: Rejects path traversal on `sourceKey`/`destKey` at gRPC boundary.
- **BOLA & Cross-Chat Protection**:
  - Message Forwarding: Snapshot copy into dest chat with `forwarded_from_name`, NOT a self-FK cross-chat link. Dual-chat authz-first check (dest participant -> source participant -> message existence).
  - Reply Targets: `message_exists_in_chat(reply_to_message_id, chat_id)` ensures reply is within the same chat.
  - Group Operations: Authz check (`check_participant`) BEFORE 400/404 errors (never reveal chat existence to non-participants).
- **File Upload XSS Defense**: `MessageInput` rejects `image/svg+xml` MIME type AND `.svg` file extension (`endsWith(".svg")`). Sniffs first 512 bytes of image uploads for `<svg` tags.

#### SpiceDB Downtime
- `SPICEDB_MAX_TOLERABLE_DOWNTIME_SECONDS = 45`.

## Audit Trail

> **Canonical Audit Index**: Full wave audit history and active wave reports are maintained in [`docs/audits/INDEX.md`](docs/audits/INDEX.md).
> Active wave audits: [`AUDIT_WAVE211.md`](docs/audits/AUDIT_WAVE211.md), [`AUDIT_WAVE210.md`](docs/audits/AUDIT_WAVE210.md), [`AUDIT_WAVE209.md`](docs/audits/AUDIT_WAVE209.md).
> Archived wave audits: [`docs/audits/archive/`](docs/audits/INDEX.md).

