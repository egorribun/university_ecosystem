# Maximum Credible Test Coverage Roadmap

**Status:** active programme

**Baseline audited:** 2026-07-16
**Scope:** Python API and workers, React frontend, Go services, Rust/WASM modules, contracts, browsers, data migrations, deployment manifests, CI/CD and operational quality gates.

## Definition of “maximum”

This programme does not treat a large coverage number as proof of correctness. The end state requires all of the following:

- Every handwritten production component has at least 99% line/statement coverage and at least 98% branch/function coverage where the language tool can measure those dimensions.
- Every Tier 0 security, money-like, identity, authorization, integrity, persistence, migration, distributed-message and data-loss path has 100% line, branch and function coverage, explicit negative-path tests, and a contract or end-to-end proof where it crosses a process boundary.
- Changed production lines have 100% diff/patch coverage. New untestable code is rejected instead of hidden behind a global threshold.
- Mutation testing kills 100% of viable mutants. Equivalent mutants must be recorded with a proof and an expiry; they do not silently reduce the denominator.
- Every exclusion, skip and quarantine item has a narrowly scoped path/test id, owner, issue reference, evidence, expiry date and a CI-enforced removal date. The initial contract contains no exclusions or quarantines.
- CI executes the relevant test types, not merely reports them. A green required check means that its evidence was generated in the same workflow run.
- Coverage reports are machine-readable, retained as artifacts, uploaded to Codecov and Sonar, and cross-checked against their manifests.

The programme explicitly rejects coverage-only tests, blanket mocks, arbitrary sleeps, disabled test files, dynamic skips without an owner, generated-report hand editing and “pass on retry” as quality signals.

## Measured starting point

The audited repository already has substantial test investment, but enforcement and measurement disagree:

| Surface | Evidence at baseline | Main gap |
| --- | --- | --- |
| Python/FastAPI | 5,311 collected tests in the isolated Windows worktree; prior CI reported about 95.41% lines and 85.74% branches | contradictory 93/91/98 floors, omissions and no per-file/patch policy |
| React/Vite | 352 Vitest test files discovered; prior CI reported about 92.34% statements/lines, 82.63% branches, 84.21% functions | broad runtime exclusions, no LCOV reporter despite Sonar expecting it, weak browser matrix |
| Go | Gateway, ws-hub and file-processor have race/coverage jobs and roughly 90–92% historic line coverage | branch semantics, mutation/fuzz/property evidence and per-package ratchets are incomplete |
| Rust/WASM | native extension historic line coverage about 76%; PyO3 sanitizer about 92%; browser WASM sanitizer KATs exist | no uniform llvm-cov thresholds; native crypto coverage is not independently enforced |
| Contracts/E2E/ops | API, gRPC, NATS, OpenAPI, Playwright, migrations, Helm/Kubernetes and chaos suites exist | artifacts and release-quality gates do not yet form one truthful contract |

The starting values are baselines, not a claim of the target. Each wave replaces them with repeatable reports generated in CI.

## Quality architecture

~~~text
source/test inventory
        |
        +-- deterministic unit, property and mutation tests
        +-- component/integration tests with disposable dependencies
        +-- consumer/provider contracts and schema compatibility checks
        +-- browser, visual, accessibility and mobile-browser journeys
        +-- migration, IaC, deployment and resilience verification
        +-- security, performance and supply-chain checks
        |
        v
versioned quality contract --> report normalizers --> CI policy gate
        |                            |                    |
        +-- exclusions/quarantine    +-- Codecov/Sonar     +-- required PR checks
~~~

The quality contract is the source of truth for thresholds, Tier 0 scope, report expectations, exclusions, quarantines and required matrix cells. Native tool configuration remains in each ecosystem; CI validates that it agrees with the contract.

## Coverage policy and evidence taxonomy

| Test class | Required evidence |
| --- | --- |
| Pure logic | Unit tests, boundary matrix, property tests where the input space is non-trivial, mutation score |
| HTTP/GraphQL/gRPC | Schema validation, authentication/authorization matrix, malformed input, idempotency, error envelope and consumer/provider contract |
| Database/repository | Disposable real database, transaction/rollback, concurrency and migration round-trip |
| Queue/cache/WebSocket | Real protocol or faithful test container, reconnection, ordering, back-pressure, duplicate and poison-message behaviour |
| UI component/hook | Accessible user interaction, keyboard/focus, loading/error/empty states, SSR/hydration where applicable, state-machine transitions |
| Browser journey | Chromium, Firefox, WebKit and mobile-WebKit paths; visual/a11y assertions on critical flows |
| Native/Rust | Unit, proptest, fuzz corpus replay, FFI error mapping, memory safety/sanitizer run and cross-language integration |
| Go | Unit, table/property/fuzz, race detector, leak/cancellation tests, gRPC/NATS integration and per-package coverage |
| IaC/data/operations | Schema lint, template render, policy test, upgrade/downgrade, rollback, chaos/failure injection and observability assertion |

## Tiering

- **Tier 0:** authentication, session/JWT/MFA/WebAuthn, authorization/SpiceDB, CSRF, PII, payments-like state transitions, file malware/sanitization, tenant/data isolation, migrations, destructive actions, cache consistency, distributed idempotency, WebSocket ticketing and native cryptography. Full coverage and negative tests are mandatory on every relevant PR.
- **Tier 1:** public API, repositories, event/calendar/news/chat workflows, notification delivery, rate limiting, search and user-facing error handling. Target metrics apply; contracts/integration tests are mandatory when a boundary changes.
- **Tier 2:** UI presentation, helpers, telemetry adapters, import/export and operational tooling. Target metrics apply; a documented testability decision is required for code that cannot be instrumented.
- **Generated/vendor/bootstrap:** excluded only by a reviewed, expiring contract entry. Bootstrap code is not automatically excluded; a smoke/integration test must prove it.

## Programme waves

### Wave 0 — truthful measurement and policy foundation

- [x] 1. Add the versioned quality contract, validator and empty exclusion/quarantine registers.
- [x] 2. Produce a normalized manifest for Python XML, Vitest LCOV/JSON, Go profiles and Rust llvm-cov output; reject stale, absent or mismatched artifacts.
- [x] 3. Align local commands, native configuration, Sonar and CI so every declared report is actually emitted.
- [x] 4. Make a required policy job validate report freshness, thresholds, Tier 0 entries, diff coverage and expiry dates before uploads are accepted.

Exit gate: the same revision produces deterministic, schema-valid evidence locally and in CI; no report path, threshold or exclusion is aspirational.

### Wave 1 — test-harness reliability and inventory

1. Build a generated inventory of handwritten source, generated code, tests, owners and Tier 0 classification for Python, TypeScript, Go, Rust, Bash/PowerShell and infrastructure.
2. Detect orphan source, orphan tests, duplicate test IDs, unbounded retries/sleeps, dynamic skips and focused test markers.
3. Make all fixtures hermetic: frozen time, seeded random generators, ports/temp roots, disposable databases/buckets/topics and failure diagnostics.
4. Add test-sharding by historical duration without weakening ordering-sensitive or integration suites.

Exit gate: all executable handwritten paths have a classification and at least one named verification owner.

### Wave 2 — Python backend and workers

1. Close coverage by module and branch map, beginning with Tier 0: auth/MFA/WebAuthn/JWT, authorization, CSRF, uploads/sanitization, storage, rate limit/circuit breaker, cache invalidation and migrations.
2. Replace coverage boosters that only call internals with behavioural tests through public service/API contracts; retain narrow unit tests for pure branches.
3. Add Hypothesis/Schemathesis stateful/property tests for schemas, pagination, serialization, security parsing and API invariants.
4. Run disposable PostgreSQL, Valkey, NATS, MinIO and SpiceDB integration cells; assert transactions, retries, timeout/cancellation and observability.
5. Add mutation batches by owned package until 100% viable-mutant score and remove equivalent-mutant records as code becomes testable.

Exit gate: Python targets and Tier 0 requirements pass on Linux/Windows, CPython 3.13/3.14 and the supported free-threaded cell.

### Wave 3 — frontend unit, component and SSR coverage

1. Remove broad runtime exclusions one accountable module at a time; add LCOV and per-file thresholds from the contract.
2. Cover routes, pages, providers, state stores, hooks, query retries/cancellation, WebSocket reconnection, PWA/service worker, SSR, hydration, offline and i18n fallbacks.
3. Use user-facing Testing Library interactions and MSW boundary tests; test error/loading/empty/permission/keyboard/focus/reduced-motion branches.
4. Add mutation testing for pure utilities, validation schemas, reducers and hook state machines; use property tests for parsers and URL state.
5. Keep generated route/API files classified but test the generation/check commands and public behavior.

Exit gate: frontend target metrics, LCOV/Sonar parity, no unowned exclusions and type/lint/build/SSR tests all pass under Node 22 and current LTS.

### Wave 4 — Go services

1. Emit atomic per-package profiles and normalized reports for gateway, ws-hub, file-processor and Caddy helpers.
2. Expand table-driven, fuzz and property tests for parser, auth/JWKS, cache, back-pressure, cancellation, limits and error propagation.
3. Require race detector, goleak/cancellation proofs, deterministic clock/transport injection and real gRPC/NATS/Temporal-compatible integration where relevant.
4. Add contract conformance against Python/OpenAPI/proto/message schemas and mutation testing where the toolchain supports it.

Exit gate: all Go packages meet their quality contract and race/integration cells pass on Linux and Windows where supported.

### Wave 5 — Rust, PyO3 and browser WASM

1. Gate cargo llvm-cov line/region/function metrics for native rust_ext, pyo3-sanitizer, wasm-sanitizer and rust-crypto.
2. Add proptest, fuzz/corpus replay and known-answer tests for scheduling, partitioning, HMAC/crypto, sanitization and FFI error paths.
3. Exercise Python PyO3 and browser WASM bindings end-to-end, including malformed bytes, boundary sizes, panic/error translation and deterministic feature flags.
4. Run clippy, fmt, cargo-deny/audit, Miri or sanitizer cells where platform support permits.

Exit gate: native and binding-level reports agree; every exported FFI/WASM API has success, malformed-input and failure semantics tested.

### Wave 6 — contracts, schemas and compatibility

1. Make OpenAPI, GraphQL, protobuf, NATS and WebSocket schemas versioned artifacts with compatibility tests.
2. Add consumer-driven provider verification and contract replay in both producer and consumer jobs.
3. Test backward/forward migration of persisted payloads, enum evolution, optional fields, retries and idempotency.
4. Reject breaking changes unless an explicit version/migration plan is validated.

Exit gate: boundary changes cannot merge without consumer/provider evidence.

### Wave 7 — browser, accessibility, visual and end-to-end evidence

1. Encode critical user journeys as Playwright state machines for Chromium, Firefox, WebKit and mobile WebKit: sign-in/MFA, authorization, schedule, events RSVP, messaging, uploads, offline/reconnect and admin actions.
2. Add deterministic network, clock and seeded-data setup; trace/video/screenshot artifacts on failure only.
3. Run axe checks, keyboard-only navigation, focus restoration, reduced motion, locale/RTL where supported and visual baseline review for key surfaces.
4. Test SSR/streaming/cache headers and production static server behavior, not only Vite dev mode.

Exit gate: cross-browser Tier 0 journeys, accessibility and visual baselines are required PR checks.

### Wave 8 — data, deployment and infrastructure

1. Test every Alembic migration forward, backward where supported, fresh install, upgrade from supported historical states, data invariants and rollback.
2. Render/lint Helm/Kustomize/Kubernetes/Docker/Caddy/Compose for all supported environments; run policy-as-code, admission and NetworkPolicy assertions.
3. Exercise secret/feature-flag/observability configuration, startup/readiness/liveness, graceful shutdown and deployment rollback.
4. Verify container image smoke tests, SBOM, provenance and reproducibility.

Exit gate: an environment is deployable only when its exact rendered manifests and migration route are tested.

### Wave 9 — non-functional, security and resilience

1. Establish performance SLO tests for API, WebSocket and native optimizer with statistically stable thresholds and regression baselines.
2. Run load/soak, concurrency/race, chaos and network-partition tests against disposable stacks; assert recovery and telemetry rather than only availability.
3. Run SAST, dependency/SBOM, secret, container and IaC scans; add DAST/fuzz for APIs/parsers/upload flows.
4. Test abuse and negative security cases: privilege escalation, tenant crossover, replay, timing, deserialization, SSRF, traversal, cache poisoning and resource exhaustion.

Exit gate: security/resilience evidence is connected to prioritized threats and all blocking findings are resolved or expiring exceptions.

### Wave 10 — ratchet, certification and maintenance

1. Enable strict global/per-file/component/Tier 0/diff/mutation gates in the required PR matrix.
2. Maintain an automatically generated dashboard from quality manifests; trends may improve, never silently loosen.
3. Run periodic independent test-gap review, flaky-test audit, mutation rotation and disaster-recovery exercise.
4. Publish the certification record: exact commit, matrix, reports, exclusions, quarantines, known limitations and verification hashes.

Exit gate: the final certification pipeline is reproducible from a clean checkout and contains no expired waiver, stale artifact or optional critical check.

## Required PR matrix

Every PR runs the maximum applicable workload, using a hybrid of GitHub-hosted and self-hosted runners:

- Python: CPython 3.13 and 3.14 on Linux and Windows; a supported free-threaded cell; lint/type/SAST, unit/property, integration, coverage/diff and mutation rotation.
- Frontend: Node 22 and current LTS; type/lint/build/SSR/Vitest coverage; Playwright Chromium, Firefox, WebKit and mobile WebKit; a11y and visual checks.
- Go: Linux and Windows unit/atomic coverage/race detector; Linux integration, fuzz and mutation cells.
- Rust: Linux/Windows native coverage, proptest/fuzz/cargo test; browser WASM test cell; sanitizer/Miri only where supported.
- Boundary/data/ops: contracts, migrations, rendered manifests/policies, image smoke, security/SBOM and selected resilience/load proof.

Long-running workload is sharded and cached, never demoted to advisory. Any platform that cannot run a tool must have an equivalent supported runner documented in the contract.

## Governance and anti-gaming controls

- A PR may not lower a threshold, add an omission, add a skip/quarantine, relax a timeout or change a test command without an explicit reviewed contract diff.
- The policy validator rejects wildcard exemptions, past expiries, missing owners/issues, duplicate paths and thresholds below the programme minimum.
- Report normalizers verify commit SHA, timestamp, source roots, hash and expected artifact dimensions before aggregation.
- Code review requires a behavior-oriented test for every changed externally observable behavior and a testability-refactor rationale for difficult code.
- Flake retries are diagnostic only; a retry cannot turn a required test green. Quarantine requires owner, expiry and a removal test.
- Coverage, mutation, property, contract, browser and operational evidence are separately reported; one category cannot compensate for another.

## Completion record

The programme is complete only when the final generated manifest lists every handwritten source file, its coverage dimensions, tier, test evidence, mutation status, owning suite and report hash; all gates in this roadmap pass on the designated PR matrix; and the exclusion/quarantine registers are empty or contain only valid, unexpired, independently approved entries.
