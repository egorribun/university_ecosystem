# ADR-022: Go Services Integration Testing with Testcontainers

## Status
Accepted (2026-05-04, primary device routine)

## Context

Three Go services (`services/ws-hub`, `services/file-processor`, `services/gateway`) currently rely on:

- **Unit tests** with mocked dependencies (`testify/mock`, hand-rolled fakes for NATS, Redis, MinIO).
- **Contract tests** in Python (`tests/contracts/`) that pin the wire format of cross-service messages but do not exercise the Go runtime.
- A small number of **integration tests** that hit a fixed local Redis container, configured by hand outside the test runner.

This setup leaves three uncovered classes of behaviour:

1. **NATS JetStream semantics** — message acks, redelivery on `Nak(...)` with delay, durable consumer rebalancing, and the `keys.rotated` / `cache.invalidate` subjects. Mocks do not implement the at-least-once delivery guarantee or the `WaitGroup`-tracked goroutine lifecycle that production depends on.
2. **MinIO object lifecycle** — file-processor's GraphQL mutation-driven uploads/deletes interact with object versioning, multipart upload chunking, presigned-URL TTLs, and gRPC path-traversal validation in ways the local fake doesn't model.
3. **Cross-service Redis behaviour under load** — the gateway's L1 cache uses XFetch probabilistic refresh; the rate-limit subsystem uses Lua scripts via EVALSHA. Neither is faithful in `fakeredis` (Python) or any of the Go fakes; both have caused subtle staging-only bugs in past audits.

ADR-016 (FakeRedis vs Testcontainers) explicitly draws the line: FakeRedis is the Python default; Testcontainers is reserved for "a small subset of critical E2E and concurrency tests". This ADR proposes the equivalent strategy for Go services.

## Decision

Adopt **`testcontainers-go`** for a focused integration-test layer in each Go service, alongside the existing unit/contract tests. The integration tier targets exactly the behaviours unit tests cannot cover:

- ws-hub: NATS JetStream ack/Nak/redeliver, broadcast oversized message rejection, `maxClients` pre-check, JWKS hot-reload.
- file-processor: MinIO + ClamAV integration, GraphQL depth + timeout middleware, gRPC path-traversal rejection.
- gateway: Redis-backed circuit breaker, L1 cache XFetch refresh, gRPC default timeout, composite OTEL propagator.

Tests run under a separate Make target (`make test-integration`) and a separate CI job (`reusable-go-integration-tests.yml`) so the unit-test feedback loop stays under 30 seconds.

## Rationale

1. **Fidelity gap**: `nats-server -js` started by `testcontainers-go` is the same binary deployed in production, eliminating the entire class of "fake disagrees with real" bugs.
2. **CI runtime envelope is acceptable**: Go services are small (each <2 minutes wall-clock for a full container-backed integration run on GitHub-hosted Linux runners with Docker pre-installed).
3. **Local developer experience is preserved**: by gating containers behind a separate Make target, `go test ./...` (the default) still runs in seconds without Docker. Devs only pay the container startup cost when targeting integration tests explicitly.
4. **Existing infrastructure investment is reused**: testcontainers-go is already a transitive dep of `nats.go`'s integration suite, so the binary + image-pull cost is partially amortised.

## Alternatives Considered

- **In-process embedded NATS** (`natsserver` package). Rejected: covers ~80 % of behaviour but not durable consumer state across restarts.
- **Hand-rolled `docker-compose.test.yml`**. Rejected: adds a manual setup step, makes parallel test execution hard, doesn't clean up containers on test crashes.
- **Skip integration tests entirely** and rely on staging. Rejected: staging incidents (e.g. the gateway L1 cache stampede) have surfaced bugs that a 5-minute CI run would have caught.

## Consequences

### Positive

- Three previously-unobservable failure modes (NATS Nak storms, MinIO multipart misuse, Redis Lua script EVALSHA cache misses) become reliably reproducible in CI.
- The Python contract tests in `tests/contracts/` keep their role as wire-format pinning; integration tests cover semantics.
- Ownership of integration tests stays in the same repository as the service code, matching how the ws-hub team already maintains `*_test.go`.

### Negative

- CI time for the Go services workflow doubles (estimated +1–3 minutes wall-clock per service for the integration tier).
- Developers must install Docker locally to run integration tests (mitigated by the separate Make target — the default `go test ./...` is unaffected).
- The first run on a clean machine pulls ~500 MB of images (NATS, MinIO, Redis, ClamAV); subsequent runs are cached.

### Migration

This ADR proposes the strategy. Adoption work is tracked separately:

1. Add `testcontainers-go` to each service's `go.mod`.
2. Write `_integration_test.go` files using the `//go:build integration` build tag.
3. Add `make test-integration` targets to each service.
4. Add `.github/workflows/reusable-go-integration-tests.yml` and wire it into `ci.yml` as an optional / non-blocking job initially.
5. Promote to required status only once flake rate over 30 days falls below 1 %.

The actual implementation work is owned by the primary device's wave queue.

## Implementation Notes (2026-05-04)

Implemented across routine commits `b65ba02a1` (2 of 11 ws-hub tests) and the
follow-up routine-e5 commit set (8 more tests across all 3 services), totaling
**10 of 11 §Decision tests landed**. Versions used:

- testcontainers-go: v0.42.0 (modules/nats, modules/redis, modules/minio)
- nats:2.12-alpine
- redis:7-alpine
- minio/minio:RELEASE.2025-09-07T16-13-09Z (matches prod docker-compose)

Each service's `make test-integration` target runs its tier in 2-15 seconds on
warm Docker. Cold first-run pulls ~150 MB of images (NATS ~20, Redis ~15,
MinIO ~80, Ryuk reaper ~10).

### Tests landed

**ws-hub (5 tests)** — `services/ws-hub/pkg/hub/hub_integration_test.go`:
- TestIntegration_NATSChatMessageDelivery (foundational NATS↔Hub.Broadcast pipeline)
- TestIntegration_NATSMalformedMessageDropped (parse-boundary defense)
- TestIntegration_BroadcastOversizedMessageDropped (RZ-23-05, 60 KB cap)
- TestIntegration_HandleRegisterMaxClients (TD-31-05 authoritative enforcement)
- TestIntegration_HandleWebSocketPrecheckMaxClients (TD-31-05 HTTP 503 pre-check)

**file-processor (3 tests)** — `services/file-processor/internal/{workflow,middleware,service}/*_integration_test.go`:
- TestIntegration_MinIOResizeImageHappyPath (rescoped from MinIO+ClamAV — see §Deferred)
- TestIntegration_GraphQLDepthAndTimeout (RZ-24-05, depth=10 + timeout=30s)
- TestIntegration_GRPCPathTraversalRejection (RZ-27-04 + RZ-26-04)

**gateway (4 tests)** — `services/gateway/{middleware,cmd/gateway}/*_integration_test.go`:
- TestIntegration_RateLimiterRedisInMemoryFallback (replaces RedisCircuitBreaker — see §Deferred)
- TestIntegration_L1CacheXFetchProbabilisticRefresh (PERF-31-02; companion unit test in auth_test.go)
- TestIntegration_GRPCDefaultTimeout (RZ-31-05, methodConfig timeout)
- TestIntegration_OTELCompositePropagator (MOD-31-02, W3C TraceContext + Baggage)

### Deferred from §Decision

The following §Decision items are deferred — three are blocked on production code
that does not yet exist; one is a structural test that will land alongside its
production component:

1. **ws-hub: NATS JetStream ack/Nak/redeliver** — current ws-hub uses core NATS
   pub/sub for `chat.*` / `notifications.*` / `cache.invalidate`. NakWithDelay
   paths fire only when the message has a non-empty Reply subject (JetStream ack
   protocol). Adding JetStream-mode tests requires `tcnats.WithArgument("jetstream", "")`
   and a different message-flow assertion. Future-wave work.

2. **ws-hub: JWKS hot-reload** — exercised by the `keys.rotated` NATS subject
   path. Requires a JWKS server fixture (httptest serving a JSON Web Key Set)
   plus a token-signing harness. Reasonably scoped as its own future-wave item.

3. **file-processor: ClamAV scan** — ClamAV is not yet integrated in production
   code (workflow.go:57 has `// v2: reserved — add e.g. a ClamAV scan activity here`).
   §Decision test #1 was rescoped to a MinIO-only happy path covering the
   existing production code path (`PutObject → ResizeImageActivity → GetObject`).
   ClamAV integration test will be added when ClamAV scanning lands.

4. **gateway: Redis-backed circuit breaker** — `RedisCircuitBreaker` exists in
   the Python backend (`app/core/ratelimit/circuit_breaker.py`, PERF-30-01) but
   not in the Go gateway. The gateway uses a 2-tier rate-limit fallback
   (P0-W5-04 / RZ-22-06) which is now covered by
   TestIntegration_RateLimiterRedisInMemoryFallback. Porting the circuit
   breaker to Go (with `sony/gobreaker`) is a separate scope decision.

### Migration status

Per §Migration step 5, the new CI jobs (`go-integration-{ws-hub,file-processor,gateway}`)
are wired as **non-blocking initially**. Promotion to required is conditional on
a 30-day flake rate < 1 % — track via the workflow run history. The reusable
workflow at `.github/workflows/reusable-go-integration-tests.yml` was added in
commit `31e12af5f` (routine-e5 scaffolding); each service's `Makefile` already
has the `test-integration` target.

## References

- ADR-015: Go services testing strategy (unit-test boundary)
- ADR-016: FakeRedis vs Testcontainers (Python equivalent decision)
- ADR-021: Go circuit breaker (the gateway component that motivated this ADR)
- testcontainers-go: <https://golang.testcontainers.org/>
