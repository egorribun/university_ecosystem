# Phase 2: Maximum Coverage Testing Roadmap

> **Historical planning snapshot (2026-07-04):** its thresholds and status
> statements are archival. The live enforceable policy is
> `quality/quality-contract.json`, including a 100% viable mutation score.

This document outlines the comprehensive roadmap to achieve maximum test coverage and testing robustness across all components of the University Ecosystem project.

---

## 1. Executive Summary & Current Status

Following the completion of the Phase 1 testing milestones (establishing basic 90% floors for Python/Go, and 92% for Frontend), the codebase has expanded through Wave 211 (adding group chats, NATS integration, message forwarding, and reply quoting).

While the overall numbers satisfy the minimal floors, new feature branches and core lifecycle layers remain uncovered. This roadmap defines a structured, multi-wave plan to push coverage to absolute maximums:

| Stack / Service | Current Statement Coverage | Target Goal | Primary Coverage Tool |
|---|---|---|---|
| **Python Backend** | **91%** | **98%+** | `coverage.py` |
| └ *app/api/* | 87% | 98%+ | `coverage.py` |
| └ *app/core/* | 87% | 98%+ | `coverage.py` |
| └ *app/services/* | 95% | 99%+ | `coverage.py` |
| └ *app/graphql/* | 93% | 98%+ | `coverage.py` |
| **Go Gateway** | **90.0%** | **95%+** | `go tool cover` |
| **Go WS-Hub** | **90.1%** | **95%+** | `go tool cover` |
| **Go File-Processor** | **92.0%** | **95%+** | `go tool cover` |
| **Go Uni-CLI** | **92.4%** | **95%+** | `go tool cover` |
| **Rust Crates** | **Unknown** (Smoke-only) | **98%+** | `cargo-llvm-cov` |
| **Frontend Unit** | **92.48%** | **98%+** | `vitest (v8)` |
| └ *FE Branches* | 81.23% (branches) | 92%+ | `vitest (v8)` |
| └ *FE Functions* | 84.54% (functions) | 95%+ | `vitest (v8)` |
| **E2E Tests** | 18 Playwright specs | Full path coverage | `playwright` |

---

## 2. Multi-Wave Roadmap

### Wave 0: Infrastructure, Configuration, & Scripts Setup
**Goal:** Align configurations, resolve typos in scripts, and establish uniform local coverage gathering.

1. **Makefile Alignment**:
   - Fix the `go-coverage` target to call `scripts/go-coverage-report.ps1` instead of `scripts/go-coverage.ps1`.
   - Update `--cov-fail-under` thresholds across Makefile targets to ensure unified baselines.
2. **Pytest Config Consolidation**:
   - Clean up pytest configurations inside `pyproject.toml` to prevent warnings from missing/conflicting `pytest.ini` parameters.
3. **Rust Coverage Automation**:
   - Compiling and calculating Rust coverage is configured to run exclusively in Linux-based CI environments (e.g., GitHub Actions using standard `cargo-llvm-cov` steps). Creation of a local Windows PowerShell script is omitted based on design review.
4. **CI Gate Baseline Synchronization**:
   - Align all CI workflow files to run tests with explicit coverage reporting and store coverage reports as artifacts.

---

### Wave 1: Python Backend Core & API Gaps (Target: 98%+)
**Goal:** Eliminate statement and branch gaps in `app/api` (87% coverage) and `app/core` (87% coverage), focusing on critical business path flows.

1. **Lifespan Lifecycle (`app/core/lifespan.py` - 53%)**:
   - Add tests simulating startup failure modes: DB connections timing out, OTEL/Sentry registry initialization blocks failing, NATS brokers being unreachable.
   - Assert correct graceful shutdown and connection termination on SIGTERM.
2. **WebSocket Presence & Auth (`app/api/ws/presence.py` - 74%, `app/api/ws/auth.py` - 80%)**:
   - Mock client connections and verify client join/leave NATS broadcast channels.
   - Target ticket parsing edge cases: expired tickets, duplicate tickets, and malformed auth headers.
3. **Schedule Optimization (`app/services/schedule_optimizer.py` - 76%)**:
   - Expand unit tests to verify branch paths for complex schedule conflict detection.
   - Cover maximum bounds, invalid input parameters, and overlap handling.
4. **Resizing & Sanitization (`app/utils/images.py` - 68%, `app/utils/sanitization.py` - 90%)**:
   - Verify fallback mechanism when libvips-based resizing fails (graceful downgrade to basic PIL).
   - Expand input sanitization test suite to verify a comprehensive list of XSS payloads.
5. **GraphQL Schema (`app/graphql/schema.py` - 67%)**:
   - Add unit tests for resolver validations, custom directive filters, and type parsing constraints.
6. **Property-Based Testing (Hypothesis)**:
   - Add property tests to `tests/test_property_based.py` for:
     - `PaginationParams`: Ensure offset/limit validations never raise 500 under any inputs.
     - `UUID7`: Verify monotonicity, ordering, and date extraction invariants.
7. **Mutation Testing (mutmut)**:
    - Historical target: run `mutmut run` on the entire backend codebase as a
      blocking CI gate with an 85% mutation-score floor. This archival target
      is superseded by the live 100% viable-score policy above.

---

### Wave 2: Go Services Reliability & Integration (Target: 95%+)
**Goal:** Harden the boundaries of Go microservices, expand File-Processor coverage, and verify race-safety.

1. **File-Processor Service (`services/file-processor` - 92%)**:
   - Expand tests from 3 to 20+.
   - Add unit tests for `internal/service/scan_service.go` using a mocked ClamAV daemon: simulate infected files, scanning timeouts, and permission failures.
   - Test MinIO write failure rollbacks to verify transactions are deleted from storage upon failure.
2. **Gateway Middleware & Caching (`services/gateway` - 90.0%)**:
   - Test probabilistic L1 cache refresh (XFetch) to verify stampede prevention.
   - Add concurrent JWKS token verification checks and token rotation window races under load.
   - Validate circuit breaker transitions under simulated upstream service outages.
3. **WS-Hub Concurrency (`services/ws-hub` - 90.1%)**:
   - Add presence subscription boundary checks.
   - Test hub graceful shutdown while clients are still actively sending packets.
4. **Enforce Race-Detector**:
   - Integrate `go test -race` into all local testing and CI pipeline stages.

---

### Wave 3: Rust Core & WASM Sanitizer Isolation (Target: 98%+)
**Goal:** Complete boundary verification on PyO3 extensions and compile/test WASM bindings isolated in Node.js.

1. **PyO3 FFI Integrity (`native/rust_ext`)**:
   - Write comprehensive python-side tests checking FFI bindings: verify that passing incorrect types or `None` triggers a clean python `TypeError` instead of a cargo panic or segfault.
   - Validate GIL release safety using multiple threads calling optimized rust helpers simultaneously.
2. **Sanitizer Edge Cases (`crates/pyo3-sanitizer`)**:
   - Test deep nested tags (>100 levels) to verify stack overflow safety.
   - Validate non-ASCII unicode and emoji preservation under strict stripping filters.
3. **WASM Testing (`frontend/wasm-sanitizer`)**:
   - Set up and run `wasm-pack test --node` inside Node.js.
   - Enforce a strict identical output verification assertion (iso-functional testing) between the WebAssembly sanitizer (`wasm-sanitizer`) and the Python binder (`pyo3-sanitizer`) for identical HTML input strings to guarantee complete client-server parity.
4. **Fuzz Testing Expansion**:
   - Add cargo-fuzz targets for HMAC verification and UUIDv7 parsing. Run weekly fuzzing jobs with a 90-minute timeout limit.

---

### Wave 4: Frontend Hook & playwrite E2E Resiliency (Target: 98%+ Statements, 92%+ Branches)
**Goal:** Expand Vitest coverage on async hooks, add critical Playwright E2E sad paths, and integrate accessibility testing.

1. **Async Hooks Gaps (Vitest)**:
   - Target `useChatWebSocket`: test exponential reconnect backoffs, offline message queueing, and ticket exchange failures.
   - Target `api/client.ts`: mock API rate limits (429) and verify client automatic retry schedules.
2. **Playwright E2E Sad Paths**:
   - Add `mfa_recovery.spec.ts`: complete lost MFA flow using backup recovery codes.
   - Add `upload_rejection.spec.ts`: confirm UI warning displays when file scanner flags a uploaded asset as malicious.
   - Add `offline_behavior.spec.ts`: verify offline banner alerts display correctly and form submissions queue when service worker is disconnected.
3. **Accessibility Gates (axe-core)**:
   - Integrate `@axe-core/playwright` audits directly in E2E tests, verifying that critical pages (login, dashboard, profile, chat) maintain **0 critical/serious accessibility violations**.
4. **Lighthouse CI (LHCI)**:
   - Enforce strict LHCI budgets inside `.lighthouserc.js` (Performance >= 90, Accessibility >= 95, Best Practices = 100).

---

## 3. Implementation Guidelines & Best Practices

1. **Testing Pyramid**: Follow the 70% Unit, 20% Integration, 10% E2E distribution.
2. **No Coverage Cheats**: The use of `# pragma: no cover` or `/* istanbul ignore next */` is strictly prohibited except for genuine platform-specific imports.
3. **Defensive Assertions**: Check both positive (happy path) and negative (error boundary) cases in every unit test. Avoid assertions without check payloads (e.g., check content, not just `assert mock.called`).
4. **Isolate State**: Clear database states and Redis/Valkey caches before and after every single test run to prevent cross-test contamination.
