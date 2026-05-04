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

Implemented across routine commits `b65ba02a1` (2 foundational ws-hub NATS
tests, beyond §Decision scope — sanity checks for the testcontainers-go ↔
Hub.Broadcast pipeline + parse-boundary defense) and the follow-up routine-e5
commit set (10 more integration tests + 1 companion unit test across all 3
services). Of the 11 §Decision items, **7 are shipped** (one with the ClamAV
portion of fp.1 deferred — see §Deferred); the remaining **4 are deferred**
fully. Total: **12 integration tests + 1 companion unit test landed**.

Versions used (test-side pins match prod docker-compose exactly):

- testcontainers-go: v0.42.0 (modules/nats, modules/redis, modules/minio) — latest as of 2026-04-09
- nats:2.12.6-alpine (exact pin matching `docker-compose.yml`)
- redis:7.4.2-alpine (exact pin matching `docker-compose.yml`)
- minio/minio:RELEASE.2025-09-07T16-13-09Z (exact pin matching `docker-compose.full.yml`)

Each service's `make test-integration` target runs its tier in 1.5-7 seconds
on warm Docker (1.5s file-processor, 2.9s gateway, 6.3s ws-hub at -count=1).
Cold first-run pulls ~360 MB of images (NATS ~40 MB, Redis ~61 MB, MinIO
~241 MB, Ryuk reaper ~14 MB) — measured on dev machine 2026-05-04 via
`docker image ls`.

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

**gateway (4 integration + 1 unit)** — `services/gateway/{middleware,cmd/gateway}/*_integration_test.go` + `auth_test.go`:
- TestIntegration_RateLimiterRedisInMemoryFallback (replaces RedisCircuitBreaker — see §Deferred)
- TestIntegration_L1CacheXFetchProbabilisticRefresh (PERF-31-02 — wiring; bounds 30 < delta ≤ 100 over 100 sessions, TTL 500 ms + sleep 400 ms = 100 ms remaining → e^-0.2 ≈ 81.9% expected refresh rate; verified flake-free across 10 consecutive runs)
- TestShouldRefreshProbabilistic_BoundaryAndStatistical (companion unit test — derives e^(-remaining/ttl) refresh rate via 1000-trial Wald sampling on synthetic timestamps; verified flake-free across 10 consecutive runs)
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

### Quality gates

All 12 integration tests + the companion unit test pass each of the following
gates as of close-out:

- `go test -tags integration -count=1 -timeout 5m ./...` per service: 0 failures
- `go vet -tags integration ./...` per service: 0 issues
- `gofmt -l` on all 9 new/modified Go files: clean
- `golangci-lint run --build-tags=integration` per service (config:
  `.golangci.yml` with `exhaustive` linter per MOD-31-01): 0 issues
- Probabilistic tests (`TestShouldRefreshProbabilistic_BoundaryAndStatistical`
  + `TestIntegration_L1CacheXFetchProbabilisticRefresh`): 10 consecutive runs
  each, 0 flakes (after relaxing the latter's bounds from 10–95 to 30–100
  with TTL widened from 200 ms to 500 ms in the polish pass — Windows Docker
  jitter pushed remaining time to ~8 ms in one run, e^-0.04 ≈ 96% > original
  95% upper bound)

Local `-race` flag is blocked on this Windows machine (no `gcc` in PATH;
chocolatey `mingw` not installed); the production `Makefile` invocation
`go test -tags integration -race -timeout 5m ./...` runs `-race` on CI Linux
(GitHub-hosted Ubuntu runner has `gcc` pre-installed). The CI workflow
`reusable-go-integration-tests.yml` calls `make test-integration`, so race
detection is exercised on every PR + push to `main` / `develop` / `release/**`.

## References

- ADR-015: Go services testing strategy (unit-test boundary)
- ADR-016: FakeRedis vs Testcontainers (Python equivalent decision)
- ADR-021: Go circuit breaker (the gateway component that motivated this ADR)
- testcontainers-go: <https://golang.testcontainers.org/>
