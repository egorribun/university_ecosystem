# ADR-022: Go Services Integration Testing with Testcontainers

## Status
Proposed

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

## References

- ADR-015: Go services testing strategy (unit-test boundary)
- ADR-016: FakeRedis vs Testcontainers (Python equivalent decision)
- ADR-021: Go circuit breaker (the gateway component that motivated this ADR)
- testcontainers-go: <https://golang.testcontainers.org/>
