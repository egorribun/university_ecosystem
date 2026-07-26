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

> **Canonical Audit Index**: Full wave audit history and reports are maintained in [`docs/audits/INDEX.md`](docs/audits/INDEX.md).
>
> **Audit files location convention (Wave 122 polish-docs-v3, `8eba94352`)**: Active audits (most recent 3 waves: **W209/W210/W211**) live in [`docs/audits/`](docs/audits/INDEX.md), while archived audits live in [`docs/audits/archive/`](docs/audits/INDEX.md). Under the N+3 promotion rule, when wave N+3 opens, the audit file for wave N is promoted to `docs/audits/archive/AUDIT_WAVE<N>.md` and referenced in `docs/audits/INDEX.md`.
>
> **Memory Files**: Per post-W138 policy, wave backlog and memory files canonically live in the `.Codex` profile directory (`C:\Users\egorribun\.Codex\projects\C--<repo-slug>\memory/`). Detailed wave history is canonically documented in `docs/audits/AUDIT_WAVE<N>.md` (active & archived).

- Wave 211 (Forwarding (F) end-to-end + Group UI **G4: display + create + manage**; user Q0=**G4+F**, sequence **F-first** (W211→W212 span accepted), forward model **snapshot-copy** (privacy-safe, no cross-chat leak), depth **single message** (endpoint 1..N for forward-compat); **71st consecutive wave** with brainstorming + Phase 1 Explore + Plan-agent design + Phase 3 verify-before-write + W141 discipline; 2026-06-01): **F = SW1-SW7 + attribution fix; G4 = SW8-SW10; SW11 (seen-by-N) + combined FE-UI live smoke carried to W212.** **F (forwarding)** — snapshot-copy a message into another chat. SW1 `56bcc07ec` `Message` += `forwarded_from_name String(128)` + `forwarded_from_chat_id`/`forwarded_from_message_id` (FK SET NULL; only the message-id indexed) + alembic `202605300007` (down_revision `202605300006`; idempotent; **LIVE up→down→up on real PG**); **AmbiguousForeignKeysError fix** caught by `configure_mappers()` after the model edit — `forwarded_from_chat_id` is a SECOND `Message→chats.id` FK breaking `Chat.messages`/`Message.chat` (the Plan flagged only the second-self-FK `replied_to`) → added `foreign_keys="Message.reply_to_message_id"` to `replied_to` + `foreign_keys="Message.chat_id"` to BOTH `Chat.messages` + `Message.chat`. SW2 `292a5fdfa` `MessageDTO`/`MessageResponse` += `forwarded_from_name` + `ForwardMessages{source_chat_id, message_ids min_length=1 max_length=50}`. SW3+SW4 `a39828725` `ChatMessageDispatcher.forward_messages` — **dual-chat authz-first**: dest participant 403 → SOURCE participant 403 (the cross-chat-leak gate, BEFORE any source read) → per-id `message_exists_in_chat` 404 (ALL before any create); snapshot-copies content + attachments + denormalized `forwarded_from_name`; one timestamp bump + single commit; POST `/chats/{dest}/forward`; `serialize_message` += scalar `forwarded_from_name`; the 3 field-by-field `MessageResponse` sites set it (2 spread sites auto-carry). SW5 `d3d994437` FE `chatApi.forwardMessages` + `Message += forwarded_from_name?` + vitest (coverage-included `src/api/`). SW6 `48604bcbf` Forward button on every bubble → NEW `ForwardModal` dest-picker (NewChatModal a11y) + "Forwarded from X" chip + `forwardMutation` + handlers. SW7 `cdda32f08` NEW `tests/test_wave211_forward.py` (9) + 3 integration tests. **Attribution fix `d37c21d34`** (live-verify-surfaced — W205 §H#5 / W210 lesson: mocked DTOs hide the real ORM→DTO path): `forwarded_from_name` came back None — `MessageDTO.sender.full_name` maps from the bare `User` (`selectinload(Message.sender)`), but `full_name` is on `UserProfile`, NOT `User` (W207 SW5 gotcha) → structurally None; NEW batched `ChatRepository.get_user_display_names(user_ids)` (profile-loaded, ONE SELECT no N+1) + the integration test now asserts `forwarded_from_name == "Source Author"` (the missing real-repo assertion that let the bug ship). **G4 (group UI)** — SW8 `b477db9c6` NEW `chatDisplay.ts` (`chatDisplayInfo` single source of truth, branches DM vs group) + `GroupAvatar` (Lucide Users in the `--messenger-send-bg` violet→pink gradient + CONSTANT `--color-white` glyph — theme-independent gradient, W175 `--text-on-footer` rationale) + group label/avatar everywhere (ContactList glyph + no presence dot; ChatArea header "{n} members"; `Contact += isGroup?/memberCount?`; contacts memo typed `Contact[]` so the inferred prop shape keeps the optional fields; `activeChatDisplay` + forward-compat `onOpenGroupInfo`) + i18n `group.untitled`/`group.members`/`unknownUser`. SW9 `eee3b4154` NewChatModal DM/Group mode toggle (only when `onCreateGroup` wired → DM-only otherwise, backward-compatible) + group-name field + selected-member chips + multi-select rows (Check + `aria-selected`) + create CTA disabled until name + ≥2 selected (backend ≥3 total incl. auto-included creator) + `createGroupMutation`. SW10 `8218e44fc` NEW `GroupInfoPanel` (ProfileModal a11y) opened from the group header — authz mirrors backend (W209): rename + add = any member; **KICK = owner only** (`created_by === currentUserId`); **LEAVE = always**; `renameChat`/`addParticipant`/`removeParticipant` mutations (invalidate `["chats"]` + `["chats", id]`; self-removal → close + navigate `/messenger`); kick/leave via `confirmDialog`. **LIVE PROOF (F, real Caddy→SSR→backend→PG chain, CSRF dance, 3 seeded accounts):** forward 200 + snapshot `"W211 from-anna snapshot"` + **`forwarded_from_name: 'Анна Петрова'`** (the ORIGINAL sender via the real PG profile join) while `sender_id` is the forwarder; **HEADLINE cross-chat-leak 403** (userC in dest, NOT in source → blocked). **Gates:** **FULL `uv run pytest --ignore=tests/contracts/test_ws_hub_contract.py` 3000 passed / 25 skipped / 0 failed** (W210 2988 + 12 = exact, no-cascade — W203 §H#5); OpenAPI superset (no regen); tsc 0; lint 0; i18n parity 18/18; **`npm run test:ci` 1385 passed / 12 skipped / 0 failed, functions 70.28% ≥ 70%** (W198 coverage-gate discipline); **Build × 3 BYTE-IDENTICAL — main `index-BzDbycBp.js` 180,274 b sha `371266a1db4abb8e24b505d585a952a4b368ca28a8837f140acf1444d3c38bd2` + server.js 24,024 b sha `b95af1ab35df45c547d033999b11919e1f8d81322c4983e366a8bf4a4145958b`** (+6 b vs W210; the F+G4 client code lives in the route-lazy `Messenger-j_QGE7HF.js` chunk = 135,518 b, the main entry shifts only by import-bookkeeping per W193 SW5/W202 — **NOT byte-identical to W210**, expected for real FE runtime, not a regression); tree-shake ✓ (0 lhci-mock-user in PROD), SW IIFE ✓; husky clean every commit (NO `--no-verify`). **§Honesty 0-3 OPEN:** carry `live-in-DEV-only` (prod ws-hub/NATS user-deferred) + W134 §H#2 bundle-delta (moot, +6 b) + W134 §H#10 /messenger Phase 5 SSR by-design; NEW **SW11 (seen-by-N read marker) DEFERRED to W212** (the plan's accepted W211→W212 span — groups are fully usable now; the "Seen by N of M" marker on W210's per-recipient read receipts is additive) + **FE-UI live smoke DEFERRED to W212** (the running frontend image is stale pre-W211; a combined live smoke needs a frontend rebuild — W137 Windows-wall risk on cold rust-crypto WASM — so it folds into W212's SW11 rebuild, ONE rebuild not two; backend F live-verified, FE comprehensively unit-tested) + G4 add-member forward-looking for long-lived groups. **1 NEW (z)** — the **MOD-30-01 `lazy=noload` gate is comment-blind** (CI-only, surfaced post-push): it greps `relationship\s*\(` whole-file, so the SW1 comment `…traversed by a relationship (privacy).` matched the literal `relationship (` → false-flagged; local gates GREEN (the gate runs in the "Validate docker-compose.yml" CI job, NOT husky — W210-class CI-surfaced); fixed by rewording to "a mapped link (privacy)" + a AGENTS.md Gotcha + reproduced the gate locally. The AmbiguousForeignKeysError (SW1, `configure_mappers()`) + attribution-None (SW7, live verify) were within-SW SAME-mechanism fixes per W138 L#1, not (z). **0 NEW anti-patterns** (14-pattern register stable post-W159 #15 archival). **W141 compliance:** #1 (each SW 1-iter; the attribution fix + the tsc/test/listbox-dupe sub-fixes are within-SW SAME-mechanism, not pivots) + #3 (verify-before-write caught the second-chats-FK ambiguity, the profile-not-on-User attribution path, the `useMemo<Contact[]>` prop-inference, the `getByLabelText` listbox-dupe, the MessengerFeature QueryClient coupling — all before/at commit) + #4 ("GREEN" attributed only after captured gate output — FULL pytest 3000, test:ci 70.28%, Build × 3 sha; F live-verified, FE-UI smoke honestly deferred) + #15 (every commit clean husky). **6 NEW Gotchas** (## Gotchas section): JWT `extra_claims` carry NOT needed here (no auth change); snapshot-copy forwarding privacy one-way-door (self-FK = cross-chat BOLA leak); `forwarded_from_name` resolves from `UserProfile.full_name` via batched `get_user_display_names` not `MessageDTO.sender` (W207 SW5); a second `Message→chats.id` FK breaks the inferred `Chat.messages` join → explicit `foreign_keys=`; `chatDisplayInfo` single-source group/DM branch + GroupAvatar theme-independent constant-white glyph; NewChatModal group-mode `onCreateGroup`-gated toggle keeps it DM-only/backward-compatible. **Messenger arc:** W203 read receipts → W204 live bridge → W205 new_message+edit/delete → W206 reactions → W207 reply/quote+reactor-list+typing → W208 reply notifications+cleanup+polish → W209 group-chat backend foundation (G1) → W210 group-message backend completion (G2+G3) → **W211 forwarding (F) + group UI (G4 display/create/manage)**; W212 = G4 SW11 seen-by-N read marker + combined FE-UI live smoke (forward UI + group create/manage + seen-by-N), then Track A (attachment perfection) / S (pgvector message search) / F-extras (multi-select forward UI). Prod ws-hub + NATS deploy (closes `live-in-DEV-only` across W203-W211) remains user-deferred. Full detail in [AUDIT_WAVE211.md](docs/audits/AUDIT_WAVE211.md). Memory references (`.Codex` profile only): `memory/wave211_backlog.md`, `memory/wave212_opening_prompt.md`.
- Wave 210 (Group-message BACKEND completion — Track G: **G2** per-recipient read receipts (the live group unread-count bug fix) + **G3** group notification re-tiering + **B** reply-notification live e2e verify (closes W208 §Honesty #4); **all THREE PROVEN LIVE end-to-end** through the real backend chain; user Q0=G2+G3 combined + the B carry-over; **G2 = backend-complete + FE-api-surface only** (the "Seen by N" group marker UI defers to G4; DMs 100% unchanged), **G3 = tests + group-name re-tiering**; **70th consecutive wave** with brainstorming + Phase 1 Explore + Plan-agent design + Phase 3 verify-before-write + W141 anti-pattern discipline; 2026-06-01): **6 code SW + SW8 live verify + SW9 close.** **Two pivotal Phase-1/Plan findings (W141 #3):** (a) **G3 was already working** — the handoff's "group push won't fire today" was _stale_ (pre-W205): `get_by_id` selectinloads participants, `notify_new_message`'s `[p.id for p in chat_participants if p.id != sender.id]` fans out to any N, the outbox is live since W205 SW-A → building "wire fan-out from scratch" would have been dead code; G3 re-aimed at the genuine gap (a group push titled "Alice" with no group context); (b) the **DM-byte-identical landmine has a clean escape** — the outer `get_chats_for_user` query ALREADY joins `Chat`, so leave `msg_stats_cte` byte-identical + add an _additive_ `group_unread_cte` + a `CASE WHEN Chat.chat_type='group'` (DMs run the same SQL). **Plan-agent catch:** `mark_messages_read` has TWO callers (the WS dispatcher AND the REST `ChatMaintenanceService.mark_read`). **Design (Option A):** groups use a NEW `ChatReadReceipt(chat_id,user_id,last_read_at,UNIQUE)` **timestamp** high-water-mark (NOT a message-id UUID compare — dialect-safe; proven SQLite + PG); DMs keep `Message.read_status` byte-identical; the upsert is the W209 dialect-agnostic check-then-(INSERT|UPDATE) (NOT `pg_insert`); `read_receipts` a _defaulted_ `ChatResponse` field populated only by `get_chat_details` (5-site fan-out untouched; service-computed, not a `ChatDTO` field). **SW1 `dc182b3c7`** `ChatReadReceipt` model + alembic `202605300006` (mirrors `202605300003`; up→down→up idempotent LIVE on real PG; `UUID7PrimaryKeyMixin.id` column-default → the Core insert populates the PK). **SW2+SW3 `c538e15c1`** repo read+write — additive `group_unread_cte` + `CASE` in `_get_chats_for_user_impl` (msg_stats_cte + ORDER BY untouched), `get_unread_count` `chat_type` branch, NEW `get_read_receipts`/`get_chat_type`, `mark_messages_read` group upsert + affected-gate (mypy ✓). **SW4+SW5-schema `d3ef5e856`** `ReadReceiptInfo` + `ChatResponse.read_receipts` + thread `chat_type` through `mark_read`/the dispatcher (which fetches `get_chat_type`)/`get_chat_details` (+ populates `read_receipts`) (mypy ✓). **SW5-FE `f2175c101`** `Chat.read_receipts?` type field (api-surface only — no marker UI, no `applyReadFrame` change; DMs unchanged). **SW7 `452e3bdee`** G3 group-name `title`/`body` in `notify_new_message` (generic + reply paths) + `handle_message_sent` threads `chat.chat_type`/`chat.name`. **Tests `557139245`** NEW `tests/test_chat_read_receipts.py` (8 real-DB, driven via `get_chats_for_user` NOT the `SET LOCAL` `get_unread_count`: per-user-not-global headline, DM-byte-identical guard, HWM-advance, upsert idempotency, affected-gate, mixed-CASE) + command/dispatcher/query-service updates (3-arg `mark_messages_read` + `get_chat_type` mock + read_receipts) + 3 G3 notification tests. **LIVE PROOF (rebuilt backend, real Caddy→backend chain, CSRF dance, 3 seeded accounts):** **B** — anna→test@ reply → within ~2s anna's `GET /notifications` shows **chat.reply=1, chat.message=0** (closes W208 §H#4); **G2** — group BEFORE anna=1/ivan=1; anna marks read → **anna=0, ivan=1 UNCHANGED** (the headline first-reader-doesn't-zero-everyone fix; sender sees 0); **G3** — anna's group notification = **title='W210 Test Group' body='User: Group hello from test'**; temp cookie jars deleted. **Gates:** ruff clean; **FULL `uv run pytest --ignore=tests/contracts/test_ws_hub_contract` 2988 passed / 25 skipped / 0 failed** (W209 2975 + 13 new = exact, no-cascade — W203 §H#5); **OpenAPI contract passed** (superset, no regen); tsc 0; `npm run test:ci` EXIT=0 functions ≥70%; **Build × 3 BYTE-IDENTICAL — main `index-BNy-Fnph.js` 180,268 b sha `c4eabf25fc0b90f77ffdec1b9e8094e5542df92ac0d1a3b9ab1d84c7b146f4a6` + server.js `d4911fbebcd46ddce101eeb20025e1181cbb7f1278f12be6f13a9ebb92a8e65f` = BYTE-IDENTICAL to W209** (the only FE change is a TypeScript interface field → erases at compile time → ZERO bundle delta, stronger than the plan anticipated; tree-shake + SW IIFE preserved by construction); husky clean every commit (the SW1/SW2 ruff-format re-stages are the documented flow), NO `--no-verify`. **§Honesty 0-2 OPEN:** CLOSED W208 §H#4 (B-verify live); carry-forward `live-in-DEV-only` (prod ws-hub/NATS user-deferred) + W134 §H#2 bundle-delta (moot — byte-identical to W209) + W134 §H#10 /messenger Phase 5 SSR by-design; NEW G2 by-design deferral (the "Seen by N" group marker UI is G4 — no group chat view polish exists yet; the backend + the `read_receipts` api-surface ship now so G4 is pure-FE; DMs unchanged → no FE regression) + NEW CI-infra finding (the "Verify OpenAPI Types" gate diffs a nonexistent `schema.ts` → a no-op; chat uses hand-written types; W211+ housekeeping). **0 NEW (z)** — Phase 1 + Phase 3 + the Plan agent resolved the stale-G3 premise, the additive-CTE escape, the two `mark_messages_read` callers, the timestamp-vs-UUID HWM, the `_set_rls_user`-on-SQLite constraint, the `read_receipts`-defaulted-field safety, the `UUID7PrimaryKeyMixin` column-default before any edit; within-iter sub-fixes (the `get_chat_type` dispatcher mock, the 2 handler stand-ins, the unused-`Chat`-import removal, the ruff-format re-stages) SAME-mechanism per W138 L#1. **0 NEW anti-patterns** (14-pattern register stable post-W159 #15 archival). **W141 compliance:** #1 (each SW 1-iter; no mechanism pivots) + #3 (verify-before-write caught all the landmines) + #4 ("GREEN" only after captured gate output — live migration cycle, 2988 pytest, test:ci EXIT=0, Build × 3 sha; B/G2/G3 attributed only after captured live network + DB evidence) + #15 (all 6 code commits clean husky). **5 NEW Gotchas** (## Gotchas section): additive `group_unread_cte` + `CASE` keeps the DM unread path byte-identical; per-recipient read = timestamp HWM not message-id UUID; `mark_messages_read` has two callers; G3-already-works was a stale-handoff premise; the no-op "Verify OpenAPI Types" CI gate. **Messenger arc:** W203 read receipts → W204 live bridge → W205 new_message + edit/delete → W206 reactions → W207 reply/quote + reactor-list + typing → W208 reply notifications + cleanup + polish → W209 group-chat backend foundation (G1) → **W210 group-message backend completion (G2 + G3) + B live verify**; W211+ = G4 group UI (create-group modal + member panel + the `read_receipts`-consuming "Seen by N" marker + group name/avatar rendering), then Track A (attachment perfection) / S (pgvector message search) / F (forwarding); housekeeping = fix the no-op "Verify OpenAPI Types" gate. Prod ws-hub + NATS deploy (closes `live-in-DEV-only` across W203-W210) remains user-deferred. **CI close-out (post-SW9, 3 follow-up commits):** the SW9 close docs (`f767c0c3f`) committed before CI ran; the run surfaced **2 PRE-EXISTING CI-infra blockers** (fresh upstream events in the W209→W210 window — NOT W210 code, zero deps changed): **(z)#1** the MOD-W5-03 `uv lock --check` gate failed on a 1-line `requires-dist[redis]` mismatch — **NOT "CDN-edge skew" (initial misdiagnosis, corrected per the «безупречно?» self-audit when resolving the PR conflict)**, but **`main` ahead with an unmerged Dependabot redis `<8→<9` bump** (PR #1127, `a2161d8c1` — it edited pyproject but left main's own `uv.lock` stale at `<8`): the `pull_request` event runs against `refs/pull/1126/merge`, so main's newer pyproject `<9` combined with the stale lock `<8` → mismatch, **irreproducible from egorribun alone** (internally consistent `<8`/`<8`; ~14 local rounds — uv-upgrade/`--refresh`/`--offline`/`--upgrade`/Rust-Linux-container — burned before checking `git log origin/main ^HEAD`, which is the FIRST diagnostic that should have been run). Diagnosed decisively via a temporary upload-artifact step (`41201964a`, reverted) → `gh run download` + `diff` = exactly 1 line; fixed by `5800cffab` aligning egorribun pyproject `redis<8→<9` + regen lock (resolved redis stays **7.4.0**, metadata-only; `--upgrade`'s 1921-line 30-package wave REJECTED) and conclusively by the **`6c3c5ff8c` merge of `origin/main`** (resolving the PR conflict — the post-fix `refs/pull/1126/merge` had become a textual conflict on the redis line, which is what flipped the PR to CONFLICTING/DIRTY and why only `workflow_dispatch` runs went green); **(z)#2** the Node.js Dependency Audit failed on a fresh **critical** vitest UI-server advisory (GHSA-5xrq-8626-4rwp / id `1120011`, dev-only — `npm audit --omit=dev` = 0), allowlisted by `b0dc0b116` (`security/audit-allowlist.yaml`, expires 2026-08-31, W191 dev-only-cascade pattern; tmp/inquirer/external-editor `1119610` cascade already covered). **CI - Matrix Expansion: completed/success — 0 failures, Lighthouse + CI Success green on `b0dc0b116`** (full Matrix incl. the 13 new G2/G3 tests + Backend Unit/Integration + FE Unit + E2E); merge HEAD `6c3c5ff8c` re-validated (Pre-commit + Security Audit + Backend/FE/E2E green). The byte-identical FE-bundle claim HOLDS (all fixes are pyproject/uv.lock/allowlist/merge config — no FE-bundle change). **PR #1126 → MERGEABLE** post-merge. §Honesty: both fresh-disclosure CI-infra blockers RESOLVED in-wave (not deferred), per W138 L#1 (closing the wave's CI is the same close-the-wave mechanism); the «безупречно?» self-audit corrected the (z)#1 mechanism — a real diagnostic-discipline lesson (check branch divergence FIRST when a dep/lock gate fails on a PR but not locally). Full detail in [AUDIT_WAVE210.md](docs/audits/AUDIT_WAVE210.md). Memory references (`.Codex` profile only): `memory/wave210_backlog.md`, `memory/wave211_opening_prompt.md`.
- Wave 209 (Group-chat BACKEND foundation — Track G slice G1, the FIRST wave of the corporate-messenger backend-first program; user Q0=1+3 reframed as a backend-first program → AskUserQuestion round 2 chose **"Group chats G1 (Recommended)"**; backend + FE-api-surface only, NO group UI = G4; **69th consecutive wave** with brainstorming + Phase 1 Explore + Plan-agent design + Phase 3 verify-before-write + W141 anti-pattern discipline; 2026-06-01): **7 code SW + SW8 verification + SW9 close.** **Key discovery:** the chat model was already ~70% group-ready — `chat_participants` is a plain N-participant M2M `Table` (no two-party columns; `broadcast_to_chat` / `check_participant` / reactions / typing already iterate N participants generically) — so G1 adds _identity_ (`chat_type`/`name`/`created_by`) + a create/membership flow + the FE api surface, deferring per-recipient read receipts (G2), group notification re-tiering (G3) + the group UI (G4) to their own waves. **SW1 `f9dbdd846`** model + alembic `202605300005`: `Chat` += `chat_type String(20)` + `CheckConstraint("chat_type IN ('dm','group')")` (NOT a StrEnum — mirrors `Attachment.file_type`, a closed display discriminator) + `name String(128) nullable` + `created_by` FK `ondelete=SET NULL` (an owner-account delete must not cascade-drop the group); idempotent up→down→up verified LIVE against the real dev PG via `docker compose run --build --rm --no-deps migrations` (the `--build` is load-bearing — the runtime image must carry the new revision; `alembic` from the host fails getaddrinfo on the `postgres` service name). **SW2 `d1fda7036`** `ChatDTO` += the 3 fields (the silent gatekeeper — `model_validate` drops undeclared columns) + repo `create_group`/`add_participant`/`remove_participant`/`rename_chat`; **`add_participant` is a dialect-agnostic check-then-insert** (`if await self.check_participant(...): return False` then a plain `insert(chat_participants)`), NOT `pg_insert.on_conflict_do_nothing` (PostgreSQL-only — it won't compile on the SQLite test DB, which would force a W206-style mock-only test; the PK is the uniqueness backstop, so the full path becomes real-DB-testable) + 5 real-`db_session` tests. **DM-regression landmine fix:** a `server_default="dm"`-only column is _expired_ post-INSERT → the untouched DM `create_chat → _to_dto` sync pydantic read in the async session = `MissingGreenlet` → so `chat_type` carries BOTH `server_default="dm"` AND a Python `default="dm"`. **SW3 `281e3f213`** `ChatResponse` += the 3 fields + 3 input schemas (`GroupChatCreate`/`AddParticipant`/`RenameChat`) + the **W203-SW8 generalized to a 5-site `ChatResponse` fan-out** — 4 explicit builds (`creation_service.py:112,144` + `query_service.py:117,203`) pass the 3 kwargs; the spread at `query_service.py:168` (`**model_dump(exclude=...)`) auto-carries (re-passing = duplicate-kwarg `TypeError`); **a missed explicit site renders a group as a nameless DM with NO error** → the `_mock_chat` MagicMock + `extra="forbid"` trap (set `chat_type`/`name`/`created_by` or the build feeds a MagicMock into a `str`/`UUID` field + 500s in-test). **SW4 `d89dba6a9`** `ChatCreationService.create_group` (strip+validate name → dedupe ids + drop the creator → `total = members + 1` bounded 3..100 → `repo.create_group` → commit → the exact `create_chat:132-149` presence-hydration block with the 3 new fields; **NO Redis lock** — no uniqueness invariant) + `chat_group_{min,max}_members` config (min-3 is load-bearing: it avoids colliding with `find_existing_dm`'s `==2` participant check) + 5 i18n keys (ru+en) + 3 mocked tests. **SW5 `40559045f`** `ChatMaintenanceService` `add_participant`/`remove_participant`/`rename_chat` + private `_require_group_participant` (**authz-first: 403 `not_participant` BEFORE 400 `not_a_group`**; remove = `created_by` owner-kick OR self-leave else 403 `remove_forbidden`); **cache invalidation after every membership commit** (`chat:{id}:participants` is the SECURITY invariant — both `broadcast_to_chat` and the ws-hub join-gate read it) gated on added/affected; 7 tests, 32 passed. **SW6 `b540854a1`** routes `POST /chats/groups` (static-before-dynamic — placed before the `/chats/{chat_id}` templates), `POST /chats/{chat_id}/participants`, `DELETE .../participants/{user_id}`, `PATCH /chats/{chat_id}` (JSON-body Pydantic, `{"status":"ok"}` returns, `sensitive_route_limit`); 7 integration tests scoped to endpoint contracts (status/routing/authz) — the trailing `GET /chats/{id}` verifications were DROPPED because `get_unread_count → _set_rls_user` issues `SET LOCAL` (PostgreSQL-only; SQLite rejects); the writes returned 200, persistence is covered by the SW2 repo tests. **SW7 `e0968831c`** FE `chatApi.createGroup`/`addParticipant`/`removeParticipant`/`renameChat` + `Chat` type += optional `chat_type?`/`name?`/`created_by?` (DM consumers compile unchanged; the group UI is G4) + 4 tests. **Gates (SW8, W203 §H#5 — group create touches the chat-creation/broadcast hot paths → SINGLE FULL pytest, not a slice):** OpenAPI contract 8 passed (additions hold the superset — no regen); **FULL `uv run pytest --ignore=tests/contracts/test_ws_hub_contract` 2975 passed / 25 skipped / 0 failed** (W208 baseline 2952 + 23 new = 2975 exact, the matching arithmetic is a no-cascade signal); FE lint 0; `npm run test:ci` EXIT=0 **functions 70.45% ≥ 70%** (the new `chatApi` methods are in coverage-INCLUDED `src/api/` — W207 lesson); **Build × 3 BYTE-IDENTICAL** main `index-BNy-Fnph.js` 180,268 b + server.js 24,024 b (size identical to W208, content hash-shifted — `chat.ts` rides the messenger route-lazy chunk per W193 SW5/W202; NOT byte-identical to W208, expected, not a regression); tsc 0; tree-shake ✓; SW IIFE ✓. **§Honesty 0-3 OPEN:** carry-forward `live-in-DEV-only` (prod has no ws-hub/NATS — user-deferred) + W134 §H#2 bundle-delta + W134 §H#10 /messenger Phase 5 SSR by-design; NEW G1 by-design deferrals (per-recipient read receipts G2 — groups inherit the per-message global `read_status`/`read_at`, so the `get_chats` unread CTE under-counts for N>2; group notification re-tiering G3 — `notify_new_message` assumes 2 parties + the synchronous notify is already commented out so group push simply won't fire; group UI G4) + GET /chats/{id} PostgreSQL-RLS-only test-infra note + group-UI live smoke honestly NOT performed (nothing user-facing to drive — that's G4; the `async_client` integration tests ARE the primary verification per the W208 B precedent). **0 NEW (z)** — Phase 1 + Phase 3 + the Plan agent resolved every landmine (M2M-already-exists, the 5-site fan-out, the `ChatDTO` gatekeeper, the `server_default`-expiry/`MissingGreenlet` trap, `pg_insert`/RLS-on-SQLite, `raise_forbidden(locale,key)` vs `raise_validation_error(key,locale)` opposite-arg-order, the `assert_not_awaited`-on-MagicMock fix) BEFORE any edit; the within-iter sub-fixes are SAME-mechanism per W138 L#1. **0 NEW anti-patterns** (14-pattern register stable post-W159 #15 archival). **W141 anti-pattern compliance:** #1 (each SW1-SW7 landed 1-iter; the SW4 `assert_not_awaited`→`assert_not_called` + the SW6 GET-verification drop + the ruff unused-`creator`→`_creator` are within-iter SAME-mechanism corrections per W138 L#1, NOT pivots); #3 (read the chat model + repo + DTO + the 5 ChatResponse sites + the localization helper signatures + the SQLite test-harness facts from source before depending on them; caught the M2M-already-exists fact + the 5-site fan-out + the `pg_insert`/RLS SQLite incompatibility before writing); #4 ("GREEN" attributed only after captured gate output — full pytest 2975, test:ci 70.45%, Build × 3 sha; group-UI live smoke honestly NOT claimed, deferred to G4; "complete" waits for CI green post-push); #15 (every commit fired the husky pre-commit chain cleanly, NO `--no-verify`; the SW5 ruff-format re-stage is the standard documented flow). **5 NEW Gotchas** (## Gotchas section): `chat_type` String-not-StrEnum + the dual `default`+`server_default` (MissingGreenlet) landmine; `ChatResponse` 5-site fan-out + the `ChatDTO` silent gatekeeper; `add_participant` dialect-agnostic check-then-insert (real-DB-testable on SQLite, unlike `pg_insert`); member-change `chat:{id}:participants` cache-invalidation security invariant; GET /chats/{id} is PostgreSQL-RLS-only (`_set_rls_user` SET LOCAL) — DB-effect assertions live in the repo tests, not the API integration tests. **Messenger arc:** W203 read receipts → W204 live bridge → W205 new_message + edit/delete → W206 reactions → W207 reply/quote + reactor-list + live typing → W208 reply notifications + cleanup + polish → **W209 group-chat backend foundation (G1)**; W210+ = G2 per-recipient read receipts + G3 notification re-tiering + G4 group UI, then Track A (attachment perfection) / S (pgvector message search) / F (forwarding). Full detail in [AUDIT_WAVE209.md](docs/audits/AUDIT_WAVE209.md). Memory references (`.Codex` profile only): `memory/wave209_backlog.md`, `memory/wave210_opening_prompt.md`.
