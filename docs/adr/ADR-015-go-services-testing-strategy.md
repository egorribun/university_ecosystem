# ADR-015: Strategy for Covering Go Services

## Status
Superseded

Superseded on 2026-08-17 by the repository-wide fail-closed coverage policy.
The historical decision below is retained for context; the current thresholds
are defined only in the
[quality contract](../../quality/quality-contract.json) and enforced by the
[CI quality gate](../../.github/workflows/ci.yml). Supported Go coverage
metrics must now meet that contract, alongside integration and race testing.

> [!NOTE]
> The remaining sections record the superseded decision and are not current
> repository policy.

## Context
Our backend architecture includes several specialized Go services alongside the main Python FastAPI application. These include the `gateway`, `file-processor`, `ws-hub`, and `uni-cli`. While the Python codebase has a strict requirement of >79% test coverage, the Go services have historically had minimal test coverage (e.g., covering only basic `hub` functionality).

We need a clear strategy for what parts of the Go services require testing, what type of testing is appropriate, and why a minimum coverage approach might be acceptable for some services.

## Decision
We will adopt a **Risk-Based Testing Strategy** for Go services, focusing on core business logic and concurrency-sensitive components, rather than enforcing an arbitrary line-coverage metric across all files.

Specifically:
1. **Concurrency and State Management (High Priority)**: Components like the WebSocket Hub (`hub.go`) and rate limiters (`ratelimit.go`) must have comprehensive unit tests because they manage concurrent connections and state, which are difficult to test via end-to-end (E2E) tests.
2. **Integration Boundaries (Medium Priority)**: Authentication clients (e.g., `auth_client.go`) that interact with the Python backend should be tested using mocked HTTP responses to ensure retry logic and failure modes work correctly.
3. **Plumbing and Initialization (Low Priority)**: Simple HTTP handlers, routing setup, and metrics registration (e.g., `handlers.go`, `metrics.go`) will rely primarily on the global E2E test suite (Playwright/pytest integration tests) rather than exhaustive unit testing, as their risk of regression is low and their primary value is in correct integration.
4. **CLI Tools**: `uni-cli` will be tested via bash/shell integration tests that execute the compiled binary, rather than Go unit tests, to ensure the full end-to-end user experience works as expected.

## Rationale
- **High ROI**: Writing unit tests for concurrency models in Go (channels, goroutines, mutexes) provides a high return on investment (ROI) because race conditions are hard to debug in production.
- **Integration over Isolation**: Many Go files in our services are "glue" code. Testing HTTP middleware in isolation often provides false confidence. E2E tests are a better indicator of health for these components.
- **Maintenance Burden**: Enforcing 80%+ coverage on Go services would require significant mocking of the HTTP layer, adding maintenance burden without proportionally increasing system reliability.

## Consequences
- We will not enforce a global `-coverprofile` minimum percentage for Go services.
- Critical files like `hub.go` and `ratelimit.go` will be kept strictly covered.
- The Python E2E suite will be relied upon heavily to ensure the Go services function correctly in the deployed ecosystem.
