# ADR-022: Go Integration Testing with Testcontainers

## Status

Accepted and fully operational (updated 2026-08-17)

## Context

Unit tests and wire-format contracts do not reproduce broker delivery,
container lifecycle, object storage, or Redis behavior. The gateway,
file-processor, and ws-hub therefore need a small integration tier against the
same classes of infrastructure used in production.

## Decision

Each Go service keeps fast unit tests as its default and exposes Docker-backed
integration tests behind the `integration` build tag:

- `make test` runs unit tests.
- `make test-integration` runs `go test -tags integration -race -timeout 5m ./...`.
- `make test-all` runs both tiers.

The integration tier uses `testcontainers-go` v0.44.0 and is required by the
aggregate CI gate. Each service runs in an independent reusable-workflow job so
a failure identifies its owning service without masking the others.

## Implemented Coverage

The repository currently contains 16 `TestIntegration_*` tests:

- **ws-hub (7):** core NATS delivery and malformed-message handling,
  oversized-message rejection, client-capacity enforcement, cache
  invalidation, JetStream consumer setup, and offline replay.
- **file-processor (2):** MinIO image-processing lifecycle and NATS-triggered
  workflow execution.
- **gateway (7):** Redis rate-limit fallback, L1-cache refresh and warmup,
  session revocation, WebSocket ticket routing, gRPC default timeout, and OTEL
  propagation.

The required workflow is
`.github/workflows/reusable-go-integration-tests.yml`; the three callers are
declared in `.github/workflows/ci.yml` and their results are included in
`ci-success`.

## Boundaries

- ClamAV is not claimed by this tier because the production file workflow does
  not yet contain a ClamAV activity.
- The Python `RedisCircuitBreaker` is not represented as a Go gateway
  component; gateway tests cover the fallback implementation that actually
  exists.
- Full load and chaos scenarios remain in the longer nightly workflow. This ADR
  governs deterministic service integration tests, not load certification.
- Contract tests remain responsible for cross-language wire formats; these
  tests verify runtime semantics.

## Consequences

- Docker is required only for the integration target.
- CI failures are merge-blocking and service-specific.
- Testcontainers clean up their resources at process exit; GitHub-hosted
  runners are also ephemeral.
- New infrastructure-dependent behavior must add an integration test in the
  owning service and remain within the five-minute service timeout.

## Verification

Run from each of `services/gateway`, `services/file-processor`, and
`services/ws-hub`:

```sh
make test
make test-integration
```

## References

- ADR-015: Go services testing strategy
- ADR-016: FakeRedis versus Testcontainers for Python
- `.github/workflows/reusable-go-integration-tests.yml`
