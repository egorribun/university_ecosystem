# AGENTS.md — Go Microservices & Edge Domain Standards (`services/`)

This document defines the architectural invariants, concurrency models, error handling strategies, and code conventions for Go microservices (`services/gateway`, `services/ws-hub`, `services/file-processor`) and the Caddy edge proxy (`services/caddy`). All agents modifying service code must adhere strictly to these rules.

---

## 1. Go Runtime & Tooling Standards

- **Go Version**: Standardized on **Go 1.22+**.
- **Static Analysis & Linting**: `.golangci.yml` must enable:
  - `exhaustive` (with `default-signifies-exhaustive: true` to catch unhandled enum switch cases).
  - `govet`, `errcheck`, `staticcheck`, and `gosec` (SAST vulnerability scanner).
- **Zero-Warning Policy**: All packages must build with zero lint warnings and pass race detection (`go test -race ./...`).
- **Telemetry**: All Go services must register the OpenTelemetry composite propagator combining `TraceContext` and `Baggage` (MOD-31-02).
- **Coverage Baseline**: 100% statement coverage required per `quality/quality-contract.json`.

---

## 2. Microservice Lifecycle & Concurrency Invariants

### 2.1. Channel-Based Error Propagation (No `os.Exit`)
- **Invariant**: Service initialization and startup errors must propagate through error channels back to `main()`. Direct calls to `os.Exit` inside helper routines are strictly forbidden (RZ-31-01).
- **Rationale**: `os.Exit` bypasses deferred cleanup handlers (`defer`), causing leaked sockets, corrupted database connections, and unclosed telemetry spans.

### 2.2. Goroutine Lifecycle Tracking
- Every background goroutine must be tracked via `sync.WaitGroup` or context cancellation.
- The real-time active goroutine count must be registered and reported using the `ws_hub_active_goroutines` Prometheus gauge.
- Loop workers (such as WebSocket pumps) must listen on `ctx.Done()` or `c.ctx.Done()` for graceful termination.

---

## 3. Real-Time Hub (`services/ws-hub`)

### 3.1. Strict Mutex Ordering (`Hub.mu` -> `Client.mu`)
- **CRITICAL INVARIANT**: Always acquire `Hub.mu` **BEFORE** acquiring `Client.mu`.
- **Never Invert Lock Order**: Acquiring `Client.mu` followed by `Hub.mu` will cause deadlocks under high concurrent broadcast loads.

```go
// CORRECT LOCK ORDER
h.mu.RLock()
client, exists := h.clients[clientID]
h.mu.RUnlock()

if exists {
    client.mu.Lock()
    client.send(msg)
    client.mu.Unlock()
}
```

### 3.2. Oversized Message Guard (>60 KB)
- Messages exceeding 60 KB (61,440 bytes) must be rejected immediately.
- The hub sends a `message_too_large` error frame to the sender client and terminates the frame processing pipeline (RZ-31-02).

### 3.3. Client Limits & Connection Pre-Check
- `maxClients` limit must be validated in `HandleWebSocket` **before** executing the HTTP-to-WebSocket connection upgrade (TD-31-05).

### 3.4. NATS JetStream Consumer Backoff
- When processing NATS JetStream events, transient delivery failures must trigger `NakWithDelay(5 * time.Second)` to prevent cascading message redelivery storms.

### 3.5. WebSocket Routing & One-Time Tokens (OTT)
- **Path**: Frontend clients connect to `/ws/chat`; Caddy rewrites the request path to `/ws`.
- **Ticket Validation**: WebSocket connections require a one-time ticket (`ott:ws:<ticket>`) issued by the backend and validated against Redis using `REDIS_PASSWORD`.
- **Allowed Origins**: `ALLOWED_ORIGINS` must include `http://localhost` (port 80 Caddy) in development and local compose configurations.
- **Message Types**: All incoming payload types must be validated against the whitelist map `allowedMessageTypes`.

---

## 4. API Gateway (`services/gateway`)

### 4.1. gRPC Default RPC Timeout
- All gRPC client connections must configure a 30-second default per-RPC timeout via service config (`WithDefaultServiceConfig`) (RZ-31-05).

### 4.2. Identity Assertion & HMAC Headers
- The Gateway intercepts and verifies JWTs at the edge on `/api/v1/*`.
- Once verified, the gateway signs the caller's identity claims into `X-Internal-Signature` via HMAC-SHA256 before proxying upstream to backend microservices.

### 4.3. L1 Cache Stampede Prevention (XFetch)
- In-memory L1 cache entries utilize XFetch probabilistic early refresh via `shouldRefreshProbabilistic()` (PERF-31-02).
- Prevents cache stampedes and dog-piling when hot keys near expiration.

### 4.4. JWKS Background Refresher
- `StartJWKSRefresher(ctx, endpoint, interval, logger)` executes background polling against the backend RSA JWKS endpoint (`/.well-known/jwks.json`) and performs an atomic key swap in memory (MOD-W17-03).
- **Configuration**:
  - `JWKS_ENDPOINT`: URL of backend RSA JWKS.
  - `JWKS_REFRESH_INTERVAL`: Default `300s` (5 minutes).
  - Also listens for `keys.rotated` NATS subjects for instant key invalidation.

### 4.5. Health Probe Auth Exemption
- Selective auth interceptors (`selectiveUnaryAuth` and `selectiveStreamAuth`) must explicitly exempt `/grpc.health.v1.Health/` so that Kubernetes `grpc_health_probe` succeeds without receiving HTTP/gRPC 401 Unauthenticated.

### 4.6. Handler Dispatching
- `/api/v1/*` routes undergo JWT validation and request dispatch.
- `ProxyOrFileHandler` intercepts `/files/process/sync` and forwards to gRPC file processor, while proxying general requests to backend.
- Empty `room_id` NATS messages trigger `cache.invalidate` cache eviction.

---

## 5. File Processor (`services/file-processor`)

### 5.1. Environment Variable Prefix (`FP_`)
- All environment variables must use the `FP_` prefix (`FP_GRPC_PORT`, `FP_STORAGE_BACKEND`, `FP_MAX_FILE_SIZE_MB`) per `viper.SetEnvPrefix("FP")`.

### 5.2. File Path Traversal Defense
- `sourceKey` and `destKey` RPC arguments must be validated against path traversal (`..`, absolute prefixes).
- Keys are restricted to a maximum length of 1024 bytes; metadata options maps must contain $\le$ 10 entries.

### 5.3. GraphQL Engine Safeguards
- The embedded GraphQL engine enforces a maximum query depth limit of **10** and a hard **30s** request timeout middleware.
- Strict `gql.ID` scalar usage with `graph-gophers/graphql-go v1.9.0+`.
- Escaped quotes must be handled correctly in `estimateQueryDepth`.

---

## 6. Caddy Edge Proxy (`services/caddy`)

### 6.1. Edge Routing Table
- Edge liveness: `/healthz` responded locally by Caddy.
- Dynamic APIs: `/api/*` and `/graphql*` -> `gateway:8080`.
- WS Ticket Issuance: `/ws/ticket` -> `gateway:8080`.
- WebSocket Tunnel: `/ws/chat*` -> `ws-hub:8081` (rewriting path to `/ws`).
- Static Assets & JWKS: `/static/*` and `/.well-known/*` -> `backend:8000`.
- SSR & Web App: `/sw.js` and default route `/` -> `frontend:3000`.

### 6.2. Rate Limiting
- WebSocket upgrades on `/ws/*` are rate-limited to 10 requests per minute per client IP.

---

## 7. Services Anti-Patterns Summary

| Anti-Pattern | Why It Is Forbidden | Correct Pattern |
|---|---|---|
| Calling `os.Exit` inside worker goroutines | Bypasses `defer` handlers; leaks connections and spans | Propagate errors via channel to `main()` |
| Acquiring `Client.mu` before `Hub.mu` | Causes deadlocks under concurrent broadcast | Always acquire `Hub.mu` before `Client.mu` |
| Accepting WebSocket frames >60 KB | High memory pressure and DoS vulnerability | Send `message_too_large` error frame and reject |
| Missing `FP_` prefix on file processor env vars | Ignored by Viper configuration parser | Always use `FP_` prefix (e.g. `FP_GRPC_PORT`) |
| Unhandled enum switch cases in Go | Leads to silent runtime bugs | Configure `exhaustive` linter in `.golangci.yml` |
| Monolithic un-timeouted gRPC client | Thread pool exhaustion on hanging upstream RPCs | Configure 30s timeout via `WithDefaultServiceConfig` |
| Authenticating `/grpc.health.v1.Health/` | Breaks Kubernetes readiness probes (401 error) | Exempt health checks in selective auth interceptor |
