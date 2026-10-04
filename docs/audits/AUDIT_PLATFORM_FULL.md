# Canonical Full-Scope Platform Architecture, Security & Quality Audit

**Document ID**: `AUDIT-PLATFORM-FULL-2026-09-03`<br>
**Date**: 2026-09-03<br>
**Active Branch**: `egorribun`<br>
**Historical Audit Scope (as originally reported)**: Multi-agent line-by-line inspection across 100% of repository contours (Python Backend, React 19 Frontend, Go Microservices, Rust Native Extensions, Cloud-Native Infrastructure, and Security & Supply Chain)<br>
**Integrity Mode**: Development / Read-Only Architectural Synthesis (Zero Application Code Modified Outside `docs/audits/`)<br>
**Certification Status**: **REMEDIATION IN PROGRESS — 60 CLOSED / 2 DECLINED WITH EVIDENCE / 1 OPEN (historical ledger with scoped re-verification; see Section 0)**<br>

---

## 0. Remediation Status Ledger (2026-09-22 baseline; scoped update 2026-10-03)

The baseline findings below were re-checked against the working tree at commit `1e0e95aa2`, not
against the audit date. The branch advanced by more than 670 commits after this document
was written, so most findings had already been remediated by unrelated work. The `BE-02`
and `BE-04` rows were re-verified again on 2026-09-22 against the tree that closed
`BE-04` and shipped BE-02 phase three.

`RUST-P3-03` was re-verified on 2026-10-03 at
`81db76d9c03c28c9929326c2a1694f56495d62a1`, with the evidence recorded in its row.
The other rows retain their historical classifications; they have not all been
re-verified at that SHA and still require release-bound evidence under the
[master plan](../superpowers/plans/MVP_MASTER_PLAN.md).

**60 closed / 2 declined with evidence / 1 open in this ledger.** Both P0 blockers
are recorded as closed; this is not a fresh release certification.
This document must not be deleted while any row in 0.1 reads OPEN.

### 0.1 Open — confirmed by measurement

| ID | Severity | Evidence |
|:---|:---:|:---|
| `BE-02` | **P1** | Governed by ADR-036, not unaddressed. Authoritative metadata count was 36 both / 81 python-only / 17 server-only. Phase one (10 auth booleans, revision `202609150001`) shipped 2026-09-15; phase two shipped 2026-09-20 and took server-only to **0**, removing the MissingGreenlet class this finding describes. **Phase three shipped 2026-09-22** (revision `202609220001`): 29 literal non-secret scalar columns -- seven booleans, eleven integers, five floats and six short enumerated strings -- across the dead-letter, events, chat, notification, schedule, Spotify, stats and vector domains, each declared on both halves so the migration and the mapped column agree. At that 2026-09-22 checkpoint, the inventory moved from `both: 53 / python_only: 81` to `both: 82 / python_only: 52`. Verified end to end against `pgvector/pgvector:pg16`: full chain from scratch, upgrade, downgrade then re-upgrade for idempotency, restoration of a column stripped of its default and `NOT NULL`, and a NULL backfill exercised on a real row. The fail-closed preflight earned its keep immediately -- PostgreSQL stores a float default as the quoted literal `'0'::double precision`, which the normalizer had to learn to strip on both sides. At the phase-three checkpoint, 52 Python-only columns remained (37 UUIDv7 primary keys, 11 timestamps, two JSON, one secret, and `users.role`, whose catalog form `'student'::userrole` casts to a named enum type), excluded from that phase pending their own decisions. [ADR-036](../adr/ADR-036-sqlalchemy-dual-default-migration-policy.md) records the later **2026-09-25 phase-four checkpoint** (revision `202609250001`): 94 both / 40 Python-only / 0 server-only, with all forty Python-only columns named exceptions (37 UUIDv7 identifiers, one signing key and two JSON topic collections). Its later-change note records revision `202610010001` retiring the `user_stats` and `vector_chunks` runtime models from the policy inventory while retaining their physical schemas, data and migration-only metadata. These are dated checkpoints, not a new current count. **Still open**: the checked-in `quality/model-default-policy.json` and generated inventory govern source acceptance, and ADR-036 requires a live **deployed** PostgreSQL catalog preflight for each DDL phase (1, 3 and 4). A container built from migrations proves correctness, not safety against production data, so this row cannot close from a workstation. |

### 0.2 Declined with evidence

These two recommendations were evaluated and deliberately not implemented. Each was
tested, not merely argued.

| ID | Why the recommendation was not followed |
|:---|:---|
| `RUST-P3-01` | Keep the recommendation declined pending a demonstrated benefit. The former experiment and its exact cache-path/workflow counts are historical and must not be treated as current evidence. The three production crates (`native/rust_ext`, `frontend/wasm-sanitizer`, `frontend/rust-crypto`) retain separate manifests and lockfiles; CI invokes them independently and gives each Rust coverage component its own target directory (`.github/workflows/ci.yml:538-547, 2991-3040`). `rust-crypto` declares `getrandom` with `wasm_js` (`frontend/rust-crypto/Cargo.toml:29`), so consolidating manifests/lockfiles would require validating feature resolution, build/cache ownership, and the existing per-crate quality-evidence boundaries before any workspace-wide command could be adopted. No current evidence establishes that this maintenance cost buys enough value over the explicit per-crate checks. |
| `INFRA-12` | Warn-and-skip would reduce safety. `.github/workflows/weekly-cleanup.yml` already runs only on `main` (job-level `if`), so no fork or PR reaches the step and there is no cross-repository noise to suppress. On `main` the secrets are required configuration: a missing one means retention has silently stopped, which is exactly what a warning would hide. The fail-closed behaviour is pinned by `tests/test_workflow_fail_closed_contracts.py::test_scheduled_workflows_reject_missing_required_inputs`; a rationale comment now records this at the call site. |

### 0.3 Closed — recorded evidence at the stated revisions

| ID | Evidence |
|:---|:---|
| `RUST-P3-03` | Re-verified 2026-10-03 at `81db76d9c03c28c9929326c2a1694f56495d62a1`. The existing `hmac_sha256_sign_base64` Rust export returns padded Base64 directly, and `crypto.worker.ts` forwards it without the former JavaScript hex/regex/`parseInt`/`btoa` round trip; the hex API remains available. Checked-in artifacts pass source-provenance validation and actual WASM known-answer/parity tests. On the same head, [WASM build job 111257791075](https://github.com/egorribun/university_ecosystem/actions/runs/37141792594/job/111257791075) rebuilt both packages and validated their provenance; [Rust job 111257791299](https://github.com/egorribun/university_ecosystem/actions/runs/37141792594/job/111257791299) passed native and WASM Base64 parity tests; [contract job 111258319651](https://github.com/egorribun/university_ecosystem/actions/runs/37141792594/job/111258319651) passed 512 tests, including the actual generated crypto-module Base64 test. The former workstation reproducibility limit is historical; this row does not claim a measured performance or memory benefit. |
| `BE-04` | Closed. Every route that touches the database now resolves its session and services from the Dishka container: `scripts/check_route_dependency_inventory.py` classifies **135 canonical_dishka / 0 approved_legacy / 0 mixed**, with 11 public routes that touch no session and 4 worker-internal ones. The ledger is committed as `quality/route-dependency-inventory.json` and the checker fails closed on drift, so a route cannot regress to `Depends(get_*)` unnoticed. **Both factory modules are deleted outright**: `app/api/deps/services.py` (26 functions -- 22 `get_*` factories plus four private `_build_*` constructors) and `app/core/container.py` (17 factories). That is 39 factories, not the 43 this finding originally counted; 43 is the total number of functions in the two files, which is what is gone, along with the three test modules that only exercised them. The two non-route callers that remained were rewired rather than kept alive -- `app/auth/handlers/logout.py` took its `AuditService` from the container instead of calling `get_audit_service()` inside the function body (around the container, where the contract test could not see it), and the two worker paths in `cache_warmup.py` / `event_handlers.py` construct `VectorService` over the session they already own, because neither runs inside a request scope. The duplicated fresh-MFA guard collapsed too: `require_fresh_mfa_from_dishka` existed only while `require_fresh_mfa` still opened a FastAPI-owned session, and once both resolved from the container the two bodies were byte-identical. `tests/test_api_dependency_injection_contract.py` adds 40 contract tests; OpenAPI still generates 112 paths and mypy is clean across 361 files. |
| `BE-12` | `app/schemas/schemas.py` is no longer a monolith: its 77 classes now live in eleven domain modules (`common`, `identity`, `users`, `groups`, `schedule`, `news`, `stories`, `events`, `integrations`, `notification_delivery`, `admin`), the largest of which is 252 lines. `schemas.py` remains as a 187-line re-export shim because 75 modules import from it, 56 through the `from app.schemas import schemas` module-object form; no call site changed. The generated OpenAPI document is **byte-identical** before and after (366,295 bytes, zero diff), which is the contract that matters for 77 response models. `notification_delivery` rather than `notifications` because the latter already holds the push-subscription schemas. The `contract-tests.yml` path filter and its catalog entries were widened from the single file to `app/schemas/**` so a change to any of the new modules still triggers the Pact boundary. The duplicate mypy overrides were already removed earlier in this pass. |
| `BE-08` | Replaced by ADR-037 and deferred with maintainer approval: CDC is outside the MVP; the polling/LISTEN-NOTIFY `OutboxWorker` is the sole supported transport. `EMBEDDED_CDC_OUTBOX_WORKER_ENABLED=true` and standalone CDC startup fail closed; `tests/test_cdc_safety.py` pins the boundary. Wiring in `app/core/lifespan.py` does not make CDC a supported or closed feature. |
| `SEC-07` | Never actually open: the finding read `is_verified`, which is detect-secrets' *live-verification* flag and is `false` for every entry because no verifier plugin applies to these detectors. The triage verdict lives in `is_secret`, and **all 321 entries carry `is_secret: false`**. `scripts/verify_secrets_baseline.py::validate_baseline_triage` already fails closed on any entry lacking that verdict, and rejects `is_secret: true` outright. All 321 flagged lines were independently re-read in context for this closure: 42 Alembic revision ids, the rest test fixtures, skill-documentation examples, CI credentials such as `test:test@localhost`, and ExternalSecret key *names*. High-entropy values were checked for reuse outside tests. No real credential. |
| `INFRA-02` | The finding offered two remediations and the **second** is satisfied: `k8s/README.md:8-21` makes `charts/university-ecosystem` "the sole canonical producer and single canonical deployment artifact" and states the raw tree "intentionally does not duplicate" the Go service workloads. The original probe only tested option one. `k8s/ingress.yaml` now carries a comment recording that its `gateway` backend is rendered by the chart. |
| `BE-11` | Both cited sites are fixed and `app/` now contains **zero** untagged broad handlers: every `except Exception` carries an `RZ-22-01` tag, and the four remaining grep hits are comments describing the convention. |
| `FE-05` | `frontend/scripts/build-wasm.mjs:92-95` handles a missing `wasm-pack` by validating the checked-in artifacts, while keeping a real build failure fatal. |
| `FE-06` | All three cited sections now pass `leadingIcon` (`SessionsSection.tsx:54`, `EmailSection.tsx:94`, `PasswordSection.tsx:90`). The remaining `startIcon` in `settings/ui/Form.tsx` is a deliberate compatibility alias mapped to `leadingIcon` at line 55, not a leak. |
| `FE-08` | The duplicated `"transition-all duration-slow"` line is gone; `Layout.tsx` declares it once. (`before-rounded-inherit` on the next line is a real custom utility defined at `frontend/src/styles/tailwind.css:1477`, not a typo.) |
| `GO-04` | `services/ws-hub/pkg/config/config.go:133` now defaults to `{"http://localhost", "http://localhost:80", "http://localhost:3000", "http://localhost:5173"}` — exactly the remediation. |
| `GO-06` | `services/AGENTS.md:103,114` now state that the **ws-hub** owns the `keys.rotated` / `cache.invalidate` NATS subscriptions and explain why ownership sits there. |
| `GO-07` | `services/AGENTS.md:25` documents the containerised command (`docker run --rm -v "${PWD}:/workspace" … golangci/golangci-lint:v2.13.2`). |
| `RUST-P3-04` | The unused `serde` feature is removed from chrono in both `native/rust_ext/Cargo.toml` and `fuzz/Cargo.toml` (no `serde`/`Serialize`/`Deserialize` reference exists in either crate), with both lockfiles refreshed; `cargo check`, `clippy --locked`, `test` (76 passed) and `deny` all pass. The buffer half was already satisfied — `verify_event_chain` hoists the key ring into one zeroizing allocation, and `verify_audit_signature` walks its keys once. |
| `SEC-05` | `quality/quality-contract.json` no longer carries 0% floors; it declares per-runtime capability markers (`native` / `derived` / `unsupported`). The `if not exact and percentage == 0: continue` bypass is gone from `scripts/quality/validate_quality_contract.py`. |
| `SEC-06` | The allowlist paths (`uv.lock`, `package-lock.json`, `go.sum`) all still exist, so the allowlist is not stale. `branches: [main]` on `pull_request` filters the **base** branch, so PRs from `egorribun` are scanned — confirmed by the green Gitleaks check on PR #1266. |
| `SEC-08` | Bandit runs through pre-commit over all files in CI (`ci.yml:144`) with a `[tool.bandit]` section in `pyproject.toml`, and executed cleanly on Windows during this remediation pass. |
| `INFRA-03` | `AGENTS.md:160` lists `${IMAGE_TAG}` among the `envsubst` variables and mandates `scripts/apply_raw_k8s.sh`, the wrapper the finding asked for: it allowlists manifests, requires every variable, validates the registry path and accepts `IMAGE_TAG` only as a 40-character SHA or semantic version. Direct `envsubst | kubectl apply` is forbidden. |
| `SEC-01` | HMAC verified with secrets.compare_digest before token validation; fail-closed in production (app/graphql/schema.py:79-91) |
| `INFRA-01` | REVOCATION_REDIS_URL and CACHE_REDIS_URL present in k8s/backend/external-secret.yaml and deployment.yaml |
| `BE-01` | no app.utils.encryption import remains in the migration |
| `BE-03` | User.chats declared explicitly with back_populates and lazy=noload (app/models/users.py:236) |
| `BE-05` | structlog.stdlib.ProcessorFormatter bridge present (app/core/logging.py:309) |
| `FE-01` | traversal/URIError guards present in frontend/scripts/server-prod.mjs |
| `GO-01 / FP-FP-01` | filepath.IsAbs and filepath.Clean guards present in services/file-processor |
| `GO-02 / GW-AUTH-01` | rsaKeySet map[string]*rsa.PublicKey with kid selection; auth_jwks_dual_key_test.go covers rotation (services/gateway/middleware/auth.go:77) |
| `GO-03 / GW-RL-01` | health/ready and health/live exempted in gateway middleware |
| `RUST-P1-01` | non-wasm32 bounds checks present in frontend/wasm-sanitizer |
| `RUST-P1-02` | null-byte and BOM handling present in frontend/wasm-sanitizer |
| `INFRA-04` | frontend-hpa.yaml present in charts/university-ecosystem/templates |
| `INFRA-05` | frontend limits.memory is already 512Mi in values.yaml |
| `INFRA-06` | no inputs interpolated directly into a run: block in reusable-backend-tests.yml |
| `SEC-02` | duplicate of GO-02; dual-key JWKS implemented |
| `SEC-03` | field_validator on audit_log_secret rejects the known default (app/core/config/security.py:298) |
| `SEC-04` | shared redaction implemented under services/pkg/logging |
| `BE-06` | _redact_pii delegates to _redact_nested with cycle protection (app/core/logging.py) |
| `BE-07` | disconnected_cb wired to a warning log (app/core/nats_broker.py:154) |
| `BE-09` | no bare asyncio.create_task remains in the event-handler packages |
| `BE-10` | DEFAULT_REVOCATION_REDIS_URL plus field_validator (app/core/config/cache.py:24,74) |
| `FE-02` | router context shares createQueryClient |
| `FE-03` | backslash handling present in frontend/src/utils/redirect.ts |
| `FE-04` | Historical closure evidence recorded a hydration guard in `ClockWidget`. The cited `frontend/src/components/dashboard/ClockWidget.tsx` was later deleted in commit `588fd8b8b17ce1aa9d45d08cc1800c93c326160d` (2026-10-01). This preserves the historical classification; it does not establish a replacement or a new closure verification. |
| `GO-05 / CLI-REDIS-01` | zero .Keys( calls remain; Scan( used instead |
| `RUST-P2-01` | GIL released via py.detach (PyO3 renamed allow_threads) at native/rust_ext/src:230,483,509 |
| `RUST-P2-02` | MAX_PBKDF2_ITERATIONS and MAX_PBKDF2_KEY_SIZE range-checked (frontend/rust-crypto/src/lib.rs:27-43) |
| `RUST-P2-03` | zeroize declared in frontend/rust-crypto/Cargo.toml |
| `RUST-P2-04` | Replaced by ADR-044: `crates/pyo3-sanitizer` was retired end to end. The cargo-deny matrix checks the three remaining production crates (`native/rust_ext`, `frontend/wasm-sanitizer`, `frontend/rust-crypto`); it no longer covers the deleted crate. |
| `RUST-P2-05` | Replaced by ADR-044: the `pyo3-sanitizer` crate and its fuzz harness were removed. The current Rust fuzz matrix covers the remaining production Rust targets; no sanitizer fuzz target is expected. |
| `INFRA-07` | backend.Dockerfile HEALTHCHECK targets health/ready |
| `INFRA-08` | file-processor healthcheck present in docker-compose.go.yml |
| `INFRA-09` | tempo-healthprobe present in docker-compose.observability.yml |
| `INFRA-10` | gateway-hpa.yaml present in the Helm chart |
| `INFRA-11` | cluster-issuer parameterised as ${CERT_MANAGER_ISSUER_NAME} (k8s/ingress.yaml:21) |
| `SEC-09` | all 74 project dependencies carry upper bounds; the 20 unbounded specifiers are dev-group tooling, outside this finding's scope |
| `SEC-10` | duplicate of GO-05; SCAN in use |
| `SEC-11` | duplicate of INFRA-07; readiness endpoint in use |
| `FE-07` | useAuthStore re-exported from frontend/src/stores/index.ts |
| `FE-09` | Closed by prop filtering, not removal: `MockButton` remains in `SessionsSection.closure.test.tsx` and omits `leadingIcon`, `startIcon`, `color` and `variant` before spreading the remaining props onto `<button>`. |
| `SEC-12` | pre-commit mypy hook aligned with the CI files = [app] setting |
| `RUST-P3-02` | orphaned fuzz/fuzz_targets/fuzz_scrypt.rs removed; rust-fuzz.yml resolves the target from frontend/rust-crypto/fuzz |

---

## 1. Executive Summary & Subsystem Scorecards

### 1.1 Strategic Overview

An exhaustive, full-scope architectural, security, concurrency, and code quality audit was conducted across the entire University Ecosystem Platform repository. The platform represents an ambitious, enterprise-grade educational ecosystem featuring:
- A high-throughput **Python 3.14 / FastAPI** backend utilizing SQLAlchemy 2.0 async ORM, Dishka Dependency Injection, Argon2id cryptography, and transactional outbox event streaming.
- A modern **React 19 / TypeScript** frontend running TanStack Start SSR on Node 24, TanStack Router/Query, Zustand immutable stores, 100% Valibot schema validation, and WCAG 2.2 AA accessibility primitives.
- High-performance **Go 1.22+ microservices** (`gateway`, `ws-hub`, `file-processor`) orchestrating edge TLS termination, WebSocket connection multiplexing, MinIO S3 object processing, and Temporal workflow execution.
- Optimized **Rust native extensions** (`native/rust_ext`, `crates/pyo3-sanitizer`, `frontend/wasm-sanitizer`, `frontend/rust-crypto`) providing PyO3 FFI and WebAssembly acceleration for conflict detection, Ammonia-based HTML sanitization, and client-side password hashing.
- Cloud-native **Infrastructure and CI/CD automation** spanning Kubernetes admission policies (Kyverno), Helm deployment charts, hardened multi-stage Dockerfiles, and GitHub Actions workflows with 100% commit SHA action pinning.

While the baseline quality gates (linters, static type checkers, and test suites) demonstrate high discipline on passing configurations, **deep static inspection unveiled critical architectural flaws, security bypasses, and deployment discrepancies** that would cause platform instability, crash-loops, or tenant identity spoofing in production environments.

### 1.2 Subsystem Scorecards

| Contour | Subsystem & Scope | Health Rating | Critical Observations & Invariants |
|:---|:---|:---:|:---|
| **Contour 1** | **Python Backend** (`app/`, `alembic/`) | **MODERATE** | Zero P0 exploits; 5 P1 inconsistencies: Alembic offline crash without production secrets, 92 model columns missing Dual Default declarations, `User.chats` implicit `lazy="select"` leak, dual DI architecture bypassing Dishka, and direct `logging.getLogger` calls bypassing structlog PII redaction. |
| **Contour 2** | **Frontend Architecture** (`frontend/`) | **GOOD** | Strictly 0 Zod imports (100% Valibot); main JS bundle is 161.27 KiB (<500 KiB budget); 6,048 unit tests passing; 1 P1 path traversal / URIError flaw in Node SSR wrapper (`server-prod.mjs`); 5 P2 SSR hydration and router context inconsistencies. |
| **Contour 3** | **Go Microservices** (`services/`) | **MODERATE** | Exemplary goroutine lifecycle tracking (`ws_hub_active_goroutines`); 1 P1 file-processor path traversal bypass on absolute keys; 1 P1 gateway single-key JWKS limitation breaking ADR-013 dual-key rotation; 1 P1 gateway rate limiter blocking K8s `/health/ready` probes during Redis outages. |
| **Contour 4** | **Rust Native Extensions** (`native/`, `crates/`, `frontend/`) | **GOOD** | 147/147 crate tests passing with 0 clippy warnings; 1 P1 raw pointer dereference lacking non-wasm32 bounds check; 1 P1 sanitization parity drift (null-byte and BOM handling) between frontend WASM and backend PyO3; 1 P2 CPU Rayon workload blocking Python GIL. |
| **Contour 5** | **Infrastructure & CI/CD** (`k8s/`, `charts/`, `.github/`) | **HIGH RISK** | 1 P0 blocker: missing `REVOCATION_REDIS_URL` in standalone K8s ExternalSecrets causes backend crash-loop; 1 P1 missing Go services in standalone `k8s/`; 1 P1 frontend missing HPA autoscaling in Helm; 1 P1 Node SSR memory limit (256Mi) in Helm chart; 1 P1 PowerShell script template injection in test workflow. |
| **Contour 6** | **Security & Supply Chain** (Cross-Cutting) | **HIGH RISK** | 1 P0 critical exploit: GraphQL context (`app/graphql/schema.py`) trusts `X-User-ID` without verifying `X-Internal-Signature` HMAC; 1 P1 hardcoded default `audit_log_secret` passes production validator; 1 P1 Go microservices emit structured logs with zero PII redaction; 326 unverified `.secrets.baseline` entries. |

### 1.3 Total Findings Breakdown by Severity

```
      CRITICALITY DISTRIBUTION ACROSS PLATFORM CONTOURS
  ┌────────────────────────────────────────────────────────┐
  │ P0 (Blockers / Critical Exploits)               :    2 │
  │ P1 (High / Architectural & Security Risks)      :   18 │
  │ P2 (Medium / Concurrency & Resilience)          :   24 │
  │ P3 (Low / Tech Debt & Documentation Hygiene)    :   13 │
  ├────────────────────────────────────────────────────────┤
  │ TOTAL ACTIVE FINDINGS                           :   57 │
  └────────────────────────────────────────────────────────┘
```

---

## 2. Comprehensive Gate & Metric Summary

The table below documents the live execution results of the project's quality gates and verification tools across all technological stacks:

| Tool / Check | Target Scope | Command Executed | Result / Status | Metric / Diagnostics |
|:---|:---|:---|:---:|:---|
| **Ruff Linter** | Python Backend | `uv run ruff check app/` | **PASS** | `All checks passed!` across 349 source files |
| **Ruff Formatter** | Python Backend | `uv run ruff format --check app/` | **PASS** | `349 files already formatted` |
| **Mypy Strict** | Python Backend | `python -m mypy --config-file pyproject.toml app/` | **PASS** | `Success: no issues found in 349 source files` |
| **Custom AST Linter** | Backend Imports | `python scripts/custom_ast_linter.py app/` | **PASS** | Conforms to TD-33-08 (`NotificationService` import isolation) |
| **No-Python2 Gate** | Entire Repository | `python scripts/check_no_python2_except.py` | **PASS** | 0 occurrences of comma `except A, B:` syntax |
| **TypeScript Compiler** | Frontend | `cd frontend && npx tsc --noEmit` | **PASS** | 0 type diagnostics across all targets |
| **ESLint Static Analysis** | Frontend | `cd frontend && npm run lint` | **PASS** | 0 errors, 0 warnings (`--max-warnings=0`) across `src`, `tests`, `scripts` |
| **Vitest Test Suite** | Frontend | `cd frontend && npm run test` | **PASS** | 621 test files passed, 6,048 tests passed (0 failures, 0 skipped) |
| **Architecture Boundary** | Frontend | `cd frontend && npm run lint:architecture` | **PASS** | 8/8 architectural boundary tests passed |
| **Design Token Closure** | Frontend CSS | `cd frontend && npm run tokens:check` | **PASS** | 1,006 definitions cleanly cover 641 referenced design tokens |
| **i18n Translation Parity** | Frontend Locales | `cd frontend && npm run i18n:check` | **PASS** | 2,096 static references cleanly matched between RU and EN |
| **Bundle Budget** | Frontend JS | `cd frontend && node ./scripts/check-bundle-budget.mjs` | **PASS** | Main JS raw chunk: 161.27 KiB (Budget: 500 KiB — 67.7% under ceiling) |
| **Go Vet & Test: Gateway** | `services/gateway` | `go test ./... && go vet ./...` | **PASS** | 7 packages passed (44.7s); `go vet` 0 issues |
| **Go Vet & Test: WS-Hub** | `services/ws-hub` | `go test ./... && go vet ./...` | **PASS** | 4 packages passed (19.6s); `go vet` 0 issues |
| **Go Vet & Test: File-Proc**| `services/file-processor` | `go test ./... && go vet ./...` | **PASS** | 6 packages passed (6.2s); `go vet` 0 issues |
| **Go Vet & Test: CLI/Pkgs** | `uni-cli`, `spiffe`, `spicedb` | `go test ./... && go vet ./...` | **PASS** | All ancillary Go packages passed; `go vet` 0 issues |
| **Cargo Test: rust_ext** | `native/rust_ext` | `cargo test && cargo clippy -- -D warnings` | **PASS** | 73 passed, 0 failed; 0 clippy warnings |
| **Cargo Test: pyo3-sanit** | `crates/pyo3-sanitizer` | `cargo test && cargo clippy -- -D warnings` | **PASS** | 40 passed, 0 failed; 0 clippy warnings |
| **Cargo Test: wasm-sanit** | `frontend/wasm-sanitizer`| `cargo test && cargo clippy -- -D warnings` | **PASS** | 15 passed, 0 failed; 0 clippy warnings |
| **Cargo Test: rust-crypto**| `frontend/rust-crypto` | `cargo test && cargo clippy -- -D warnings` | **PASS** | 19 passed, 0 failed; 0 clippy warnings |
| **Cargo Root Workspace** | Repository Root | `cargo test --workspace` | **FAIL** | No root `Cargo.toml` workspace file exists (Finding RUST-P3-01) |
| **Actionlint Workflow Gate**| GitHub Actions | `uv run pre-commit run actionlint --all-files` | **PASS** | 54 workflow files validated cleanly |
| **Supply Chain: Python** | Python Dependencies | `uv lock --check && pip-audit` | **PASS** | 0 CVEs found across 258 resolved packages |
| **Supply Chain: Node** | Frontend / Root JS | `npm audit --json` | **PASS** | 0 vulnerabilities across 1,898 frontend and 310 root packages |
| **Supply Chain: Go** | Go Dependencies | `go mod verify` (all services) | **PASS** | All Go modules pass checksum and authenticity verification |
| **Developer Test Harness** | Developer Tools | `python verify_harness.py` | **PASS** | 29/29 tests passed in 6.02s (100.0% success rate) |

---

## 3. Contour 1: Python 3.14 Backend Deep Dive

### 3.1 Architectural Invariants Inspection

1. **Dishka DI Scopes vs FastAPI Depends**:
   The backend defines comprehensive domain-scoped Dishka providers (`AuthProvider`, `ChatProvider`, `ContentProvider`, `CQRSProvider`, `UserProvider`) in `app/core/di/` and attaches the container in `app/main.py:141`. However, only 5 files in the entire API (`app/api/auth/login.py`, `app/api/auth/mfa.py`, `app/api/deps/auth.py`, `app/api/schedule.py`, `app/api/search.py`) use `FromDishka[T]`. Over 80% of API endpoints bypass Dishka and use legacy manual factories (`Depends(get_db)`, `get_user_service`), creating two concurrent DB session lifecycles.
2. **SQLAlchemy 2.0 Async Models (`lazy="noload"`)**:
   61 explicit `relationship()` definitions correctly specify `lazy="noload"`. However, in `app/models/chat.py:100-102`, `participants = relationship("User", secondary=chat_participants, backref="chats", lazy="noload")` synthesizes a dynamic `chats` backref on `User` that defaults to `lazy="select"`, threatening `MissingGreenlet` exceptions during async serialization.
3. **Dual Default Declarations Invariant (`app/AGENTS.md` Section 2.2)**:
   Mandates both Python-level `default=...` and DDL `server_default=...` on all defaulted model columns. Inspection revealed **92 distinct columns** across `app/models/users.py`, `app/models/auth.py`, `app/models/chat.py`, `app/models/notifications.py`, `app/models/dead_letter.py`, and `app/models/mixins.py` that provide only one default.
4. **Structured Logging & PII Redaction (ADR-012)**:
   `app/core/logging.py:82-92` implements `_redact_pii`. However, standard library `logging.basicConfig` on line 201 does not wrap stdlib handlers in structlog's `ProcessorFormatter`. Calling `logging.getLogger(...)` directly emits raw messages to stdout without PII redaction. Furthermore, `_redact_pii` only checks top-level keys and string values, failing to recursively sanitize nested dictionary or list payloads.
5. **Exception Narrowing & Broad Catch Justification**:
   166 broad exception handlers exist across the backend; all handlers are justified with `# RZ-22-01-JUSTIFIED: <reason>` comments, with only one minor rule code typo in `app/management/reset_mfa.py:98` (`RZ-28-01-JUSTIFIED`) and one missing comment in `app/core/observability.py:375`.

### 3.2 Detailed Backend Findings Inventory

#### Finding BE-01: Alembic Offline Discovery Crashes Due to Eager Runtime Config Import in Migration
- **Severity**: **P1 (High / Severe Inconsistency)**
- **Citation**: `alembic/versions/148642dd1207_fix_missing_tables.py:17, 1279, 1282`, `app/utils/encryption.py:13`, `app/core/config/__init__.py:473`
- **Technical Observation**:
  `alembic/versions/148642dd1207_fix_missing_tables.py:17` executes `import app.utils.encryption` at top level. In `app/utils/encryption.py:13`, it imports `from app.core.config import settings`. When `settings` loads, `app/core/config/__init__.py:473` executes `Settings()`, which asserts the presence of required production environment variables (`DATABASE_URL`, `SECRET_KEY`).
  Executing offline commands (`alembic heads`, `alembic history`, `alembic upgrade --sql`) without production secrets crashes immediately:
  `RuntimeError: Missing required environment variables: DATABASE_URL, SECRET_KEY.`
- **MVP Impact**: CI/CD jobs, container build stages, offline SQL migration generators, and developer onboarding scripts fail unless supplied with real or mock production secrets.
- **Remediation**:
  In `alembic/versions/148642dd1207_fix_missing_tables.py:17, 1279, 1282`, remove `import app.utils.encryption` and replace `app.utils.encryption.EncryptedString()` with native `sa.String()` or `sa.Text()`. Migrations must declare DDL schema structure using raw SQLAlchemy types without importing application runtime crypto or config singletons.

#### Finding BE-02: Dual Default Declarations Missing Across 92 Model Columns
- **Severity**: **P1 (High / Severe Inconsistency)**
- **Citation**:
  - `app/models/users.py:50, 67, 68, 78, 314, 383-385`
  - `app/models/auth.py:64, 83, 86, 121, 130, 188, 272, 310, 313, 337, 340, 379, 470, 473, 500, 506`
  - `app/models/chat.py:51, 54, 135`
  - `app/models/notifications.py:43, 47, 90, 98, 105, 171, 232, 267`
  - `app/models/dead_letter.py:41-43, 49, 52`
  - `app/models/mixins.py:15`
- **Technical Observation**:
  `app/AGENTS.md` Section 2.2 mandates:
  *"Any model column with default values must provide BOTH Python-level default (`default=...`) AND DDL server default (`server_default=...`)."*
  92 columns across the models provide only one side. For example, `User.role` has `default=UserRole.STUDENT` but lacks `server_default="student"`; `User.created_at` has `server_default=func.now()` but lacks Python `default=utc_now`.
- **MVP Impact**:
  1. Freshly instantiated entities validated against Pydantic DTOs via `model_validate(from_attributes=True)` before DB commit attempt to access unpopulated attributes, triggering fatal `MissingGreenlet` exceptions in async request handlers.
  2. Direct inserts from external Go microservices or raw SQL migrations fail with NOT NULL constraints or unpopulated defaults.
- **Remediation**:
  Systematically update all 92 columns to declare both defaults. Example:
  `role: Mapped[UserRole] = mapped_column(SQLEnum(UserRole), default=UserRole.STUDENT, server_default="student")`.

#### Finding BE-03: Implicit `lazy="select"` Backref Leak on `User.chats`
- **Severity**: **P1 (High / Severe Inconsistency)**
- **Citation**: `app/models/chat.py:100-102`, `app/models/users.py`
- **Technical Observation**:
  `Chat.participants` declares `backref="chats", lazy="noload"`. In SQLAlchemy, `lazy="noload"` applies only to the forward relationship (`Chat.participants`); the dynamically created backref `User.chats` defaults to synchronous `lazy="select"`. `User` in `app/models/users.py` does not declare `chats` explicitly.
- **MVP Impact**: Any async handler traversing `user.chats` raises `sqlalchemy.orm.exc.MissingGreenlet`, terminating the request with HTTP 500.
- **Remediation**:
  Replace string `backref` with bi-directional `back_populates` and explicit `lazy="noload"`:
  1. In `app/models/chat.py:100-102`: `participants: Mapped[list[User]] = relationship("User", secondary=chat_participants, back_populates="chats", lazy="noload")`.
  2. In `app/models/users.py` (`User` class): `chats: Mapped[list[Chat]] = relationship("Chat", secondary="chat_participants", back_populates="participants", lazy="noload")`.

#### Finding BE-04: Dual Dependency Injection Architecture & Container Bypassing
- **Severity**: **P1 (High / Architectural Debt)**
- **Citation**:
  - `app/main.py:141`
  - `app/core/container.py:41-100`
  - `app/api/deps/services.py:33-93`
  - `app/api/chat.py:24-31`
  - `app/api/events.py:27-35`
  - `app/api/news.py:25-32`
  - `app/api/notifications.py:25-30`
  - `app/api/users.py:30-36`
- **Technical Observation**:
  While `app/main.py:141` mounts Dishka (`setup_dishka`), over 80% of API endpoints continue importing legacy factories from `app/core/container.py` and `app/api/deps/services.py`, injecting dependencies via FastAPI `Depends(get_db)`.
- **MVP Impact**: Two concurrent database session lifecycles exist during requests (`InfrastructureProvider.db` via Dishka vs `get_db()` via FastAPI). Testing and mocking require overriding two disparate dependency systems.
- **Remediation**:
  Migrate endpoints in `app/api/chat.py`, `app/api/events.py`, `app/api/news.py`, `app/api/notifications.py`, and `app/api/users.py` to `@inject` and `FromDishka[T]`. Remove legacy factories in `app/core/container.py` and `app/api/deps/services.py`.

#### Finding BE-05: Direct `logging.getLogger()` Calls Bypass Structlog PII Redaction
- **Severity**: **P1 (High / Security & Compliance Risk)**
- **Citation**:
  - `app/core/logging.py:201`
  - `app/api/auth/login.py:53`
  - `app/api/auth/mfa.py:46`
  - `app/auth/mfa/challenge.py:47`
  - `app/auth/mfa/lifecycle.py:35`
  - `app/services/audit_service.py:38, 91-99`
  - `app/services/auth/fingerprint_service.py:22`
- **Technical Observation**:
  Standard library `logging.basicConfig` on line 201 formats plain strings to stdout without routing through `structlog.stdlib.ProcessorFormatter`. Any module calling `logging.getLogger(...)` directly emits raw messages bypassing `_redact_pii` and OpenTelemetry context injection.
- **MVP Impact**: User emails, phone numbers, and auth challenge metadata logged in critical auth and audit paths leak into console output and Loki unredacted.
- **Remediation**:
  1. In `app/core/logging.py`, configure stdlib handlers with `structlog.stdlib.ProcessorFormatter.wrap_for_formatter`.
  2. Replace all `logging.getLogger(...)` occurrences with `from app.core.logging import get_logger; logger = get_logger(__name__)`.

#### Finding BE-06: Non-Recursive PII Redaction in `_redact_pii`
- **Severity**: **P2 (Medium / Privacy Risk)**
- **Citation**: `app/core/logging.py:82-92`
- **Technical Observation**:
  `_redact_pii` inspects only top-level dictionary keys and top-level string values. Nested structures (e.g. `logger.info("webhook", extra={"user": {"email": "user@univ.edu"}})` or lists of dictionaries) bypass redaction completely.
- **MVP Impact**: Complex payloads logged during webhook handling or auth exchanges leak customer PII into Grafana Loki.
- **Remediation**: Implement a recursive helper in `_redact_pii` to traverse nested `dict` and `list` structures, sanitizing all nested string values against `_EMAIL_RE` and `_PHONE_RE` and redacting matching sensitive keys.

#### Finding BE-07: Silent Event Dropping on NATS Broker Disconnect
- **Severity**: **P2 (Medium / Resilience & Observability)**
- **Citation**: `app/core/nats_broker.py:335-336`
- **Technical Observation**:
  `app/AGENTS.md` Section 7 specifies that NATS publishers must emit `logger.warning("nats_publish_skipped_not_connected")` when disconnected. In code, `if self._nc is None or not self._nc.is_connected: return` silently returns without logging or incrementing metrics.
- **MVP Impact**: During NATS broker maintenance or network blips, outbound domain events dispatched via `publish_core` are lost silently, leaving operators unaware of message loss.
- **Remediation**: Log `logger.warning("nats_publish_skipped_not_connected", subject=subject)` and increment a dedicated Prometheus counter before returning.

#### Finding BE-08: Unintegrated Orphan Worker `CdcOutboxWorker`
- **Severity**: **P2 (Medium / Architecture & Tech Debt)**
- **Citation**: `app/workers/cdc_outbox.py:1-772`
- **Technical Observation**:
  `cdc_outbox.py` is a 772-line module implementing PostgreSQL WAL logical replication for the outbox pattern. Grep verification confirms it is never imported or started in `app/main.py`, `app/worker.py`, or `app/core/lifespan.py`, and is not bound in Dishka DI. Only polling/LISTEN-NOTIFY `OutboxWorker` (`app/workers/outbox.py`) is wired into application lifespan.
- **MVP Impact**: Creates architectural ambiguity regarding outbox mechanics; tests in `tests/test_cdc_outbox.py` exercise dead code.
- **Remediation**: Wire `CdcOutboxWorker` into `app/core/lifespan.py` behind `settings.cdc_outbox_enabled`, or archive `cdc_outbox.py` to prevent ongoing maintenance debt.

#### Finding BE-09: Detached Tasks Leak on Event Handler Cancellation
- **Severity**: **P2 (Medium / Async Concurrency Safety)**
- **Citation**: `app/core/events.py:880-884, 908-916`
- **Technical Observation**:
  Inside `execute_handlers`, child tasks are spawned via `tasks = [asyncio.create_task(...) for handler in handlers]` and awaited with `asyncio.gather(*tasks)`. When the outer 10-second timeout fires, `chain_task.cancel()` cancels the outer wrapper task, but does NOT cancel the individual child tasks created via `create_task`. The child tasks continue running detached in the event loop.
- **MVP Impact**: Slow or hung event handlers continue consuming CPU and database connection pool slots long after requests time out.
- **Remediation**: Refactor `execute_handlers` to use `asyncio.TaskGroup()` (Python 3.11+ / 3.14 standard), ensuring child tasks are cancelled automatically and recursively upon outer task cancellation.

#### Finding BE-10: Sentinel URL Rejection Breaks Local Revocation Store
- **Severity**: **P2 (Medium / Developer Experience)**
- **Citation**: `app/auth/revocation.py:114`, `app/core/config/cache.py:16`
- **Technical Observation**:
  `DEFAULT_REVOCATION_REDIS_URL` is set to `"redis://127.0.0.1:6380/0"`. `app/auth/revocation.py:114` raises `RuntimeError("REVOCATION_REDIS_URL is not configured")` if `redis_url == DEFAULT_REVOCATION_REDIS_URL`. If a developer runs Redis on port 6380 locally as intended, the system treats it as unconfigured.
- **MVP Impact**: In `app/api/deps/auth.py:136`, this exception is swallowed in debug logs, silently disabling the O(1) Redis JTI token revocation check in local development.
- **Remediation**: Change `DEFAULT_REVOCATION_REDIS_URL` to an explicit sentinel (e.g. `"redis://unconfigured:6380/0"`), or permit the default URL when `settings.environment in {"development", "local", "testing"}`.

#### Finding BE-11: Missing and Mistyped Exception Justification Tags
- **Severity**: **P3 (Low / Code Hygiene)**
- **Citation**: `app/core/observability.py:375`, `app/management/reset_mfa.py:98`
- **Technical Observation**:
  `app/core/observability.py:375` has a bare `except Exception:` without justification. `app/management/reset_mfa.py:98` has `# RZ-28-01-JUSTIFIED` (typo for `RZ-22-01-JUSTIFIED`).
- **MVP Impact**: Minor code style inconsistency.
- **Remediation**: Add `# RZ-22-01-JUSTIFIED: fail-closed OTEL initialization cleanup` to line 375 and fix the typo in `app/management/reset_mfa.py:98`.

#### Finding BE-12: Monolithic `app/schemas/schemas.py` & Duplicate `pyproject.toml` Entries
- **Severity**: **P3 (Low / Tech Debt)**
- **Citation**: `app/schemas/schemas.py:1-831`, `pyproject.toml:218, 236, 252, 254, 255, 258`, `app/AGENTS.md:180`
- **Technical Observation**:
  `app/schemas/schemas.py` contains 831 lines combining user, news, event, password, and schedule DTOs. `pyproject.toml` contains duplicate mypy overrides (`"nats.*"` on lines 236 and 252; `"structlog"` on line 222 and `"structlog.*"` on line 258; `"grpc.*"` and `"grpc"` on lines 254-255). `app/AGENTS.md:180` typos `_validate_resolved_path()` for `_resolve_validated_path()`.
- **MVP Impact**: Higher merge conflict risk; redundant configuration.
- **Remediation**: Split `schemas.py` into domain modules (`user.py`, `news.py`, etc.), deduplicate `pyproject.toml` overrides, and fix documentation typo in `app/AGENTS.md`.

---

## 4. Contour 2: Frontend Architecture Deep Dive

### 4.1 Architectural Invariants Inspection

1. **Valibot Exclusivity (Zero Zod Invariant)**:
   **100% Compliant**. An exhaustive regex search across `frontend/src/` confirmed zero imports of `zod`. All form validations, WebSocket message schemas, route search parameters, and local storage validators exclusively use `valibot` (`v.*`).
2. **Main Bundle Budget (<500 KB)**:
   **100% Compliant**. `scripts/check-bundle-budget.mjs` confirms the main client chunk raw size is **161.27 KiB** (67.7% below the 500 KiB limit). Initial JS gzip is 372.07 KiB (limit 420 KiB); initial CSS gzip is 39.51 KiB (limit 40 KiB). Heavy dependencies (`jspdf`, `maplibre-gl`, password strength dictionaries) are strictly dynamic-imported (`await import(...)`) or lazily loaded.
3. **Zustand State Stores**:
   Stores (`useAuthStore.ts`, `appShellStore.ts`, `notificationStore.ts`, `scheduleUIStore.ts`) use immutable updates with `useShallow` selector hooks, preventing unnecessary component re-renders.
4. **TanStack Router & Route Guards**:
   Route guards (`_auth.tsx`, `_public.tsx`, `_admin.tsx`) evaluate auth state via `useAuthStore.getState()` inside `beforeLoad` hooks, adhering to SSR client decoupling rules.
5. **WCAG 2.2 AA Accessibility**:
   Touch targets strictly enforce $\ge 44 \times 44\text{ px}$ minimums (`Button.tsx`); dialogs enforce `role="dialog"`, `aria-modal="true"`, and keyboard focus trapping (`useFocusTrap`); live chat streams declare `role="log"` and `aria-live="polite"`; data charts provide `<table className="sr-only">` alternatives.

### 4.2 Detailed Frontend Findings Inventory

#### Finding FE-01: Path Traversal Prefix Flaw & Uncaught URIError in Node SSR Production Wrapper
- **Severity**: **P1 (High / Security & Reliability)**
- **Citation**: `frontend/scripts/server-prod.mjs:134-137`
- **Technical Observation**:
  ```javascript
  const requested = path.normalize(decodeURIComponent(urlPath)).replace(/^[/\\]+/, "")
  if (requested.includes("..")) return false
  const filePath = path.resolve(staticRoot, requested)
  if (!filePath.startsWith(staticRoot)) return false
  ```
  1. `staticRoot` is defined as `path.resolve(cwd, "dist", "client")` without a trailing path separator. The check `if (!filePath.startsWith(staticRoot))` checks a string prefix without ensuring directory boundary termination (`+ path.sep`). If a sibling directory exists (`dist/client_secrets`), paths resolving into it satisfy the check.
  2. `decodeURIComponent(urlPath)` on line 134 is called without `try/catch`. Malformed percent-encoded sequences (`GET /%ff`) throw a synchronous `URIError` causing an uncaught HTTP 500 crash rather than returning HTTP 400.
- **MVP Impact**: Risk of static directory traversal under sibling volume mounts, and 500 internal server error spikes on scanners probing malformed URL encodings.
- **Remediation**:
  Wrap `decodeURIComponent` in `try/catch` (returning `false` on `URIError`), and enforce boundary checks via `path.relative`:
  ```javascript
  const relative = path.relative(staticRoot, filePath)
  if (relative.startsWith("..") || path.isAbsolute(relative)) return false
  ```

#### Finding FE-02: Unconfigured QueryClient in TanStack Router Context Diverges from Client Options
- **Severity**: **P2 (Medium / SSR Hydration Consistency)**
- **Citation**: `frontend/src/router.ts:70-75`, `frontend/src/app/queryClient.ts:22-41`, `frontend/src/routes/__root.tsx:476-478`
- **Technical Observation**:
  `src/app/queryClient.ts` initializes `createQueryClient()` with critical defaults: `staleTime: 5 * 60_000` (5m), `gcTime: 30 * 60_000` (30m), `retry: 1`, `networkMode: "offlineFirst"`. However, in `frontend/src/router.ts:74`, `createAppRouter()` assigns `queryClient: new QueryClient()` directly to router context. In SSR mode, `SsrRoot` reads this unconfigured `queryClient` (`staleTime: 0`, `retry: 3`), causing server prefetch caching to diverge from client hydration.
- **MVP Impact**: During SSR loader resolution, queries are treated as immediately stale (`staleTime: 0`), triggering redundant network roundtrips and hydration mismatches.
- **Remediation**: Import `createQueryClient` from `@/app/queryClient` into `src/router.ts` and construct `queryClient: createQueryClient()`.

#### Finding FE-03: Open-Redirect Backslash Vulnerability & Query/Hash Truncation in `resolveRedirectPath`
- **Severity**: **P2 (Medium / Security & Deep Linking)**
- **Citation**: `frontend/src/utils/redirect.ts:35-46`
- **Technical Observation**:
  1. Line 36 allows paths where `redirect.startsWith("/") && !redirect.startsWith("//")`. If an attacker passes `/\evil.com` or `/\\evil.com`, both conditions evaluate to true. Chromium normalizes `/\evil.com` to `//evil.com` (a protocol-relative external redirect).
  2. Line 46 returns `url.pathname` on validated absolute same-origin URLs, stripping `url.search` and `url.hash`.
- **MVP Impact**: Potential open-redirect vulnerability via backslash bypass, and silent loss of query parameters/hash fragments during post-login deep linking.
- **Remediation**: Disallow `/\` prefixes via `!redirect.startsWith("/\\")`, and preserve query/hash parameters: `return `${url.pathname}${url.search}${url.hash}``.

#### Finding FE-04: ClockWidget Renders Live System Date During Initial Render Without Hydration Guard
- **Severity**: **P2 (Medium / React 19 SSR Hydration Hazard)**
- **Citation**: `frontend/src/components/dashboard/ClockWidget.tsx:4-5, 21, 24-28`
- **Technical Observation**:
  `ClockWidget` initializes `time` with `new Date()` synchronously. On the server, `toLocaleTimeString()` and `toLocaleDateString()` evaluate in the Node.js timezone (UTC). In the browser, they evaluate in the user's local timezone. The server HTML differs from the client DOM without `suppressHydrationWarning` or a `mounted` state guard.
- **MVP Impact**: Triggers React error #418 hydration mismatch warnings on pages mounting `ClockWidget`.
- **Remediation**: Gate live date rendering behind `const [mounted, setMounted] = useState(false)` with a placeholder skeleton, or add `suppressHydrationWarning` to the text container elements.

#### Finding FE-05: `build-wasm.mjs` Unconditionally Spawns `wasm-pack` Crashing Builds When Missing from PATH
- **Severity**: **P2 (Medium / Build Reliability)**
- **Citation**: `frontend/scripts/build-wasm.mjs:28-40`
- **Technical Observation**:
  `build-wasm.mjs` invokes `wasm-pack` unless `SKIP_WASM_BUILD === "1"`. In environments where Rust or `wasm-pack` is not installed (e.g. standard Node CI workers), `npm run build` crashes with `Error: spawn wasm-pack ENOENT`, even though pre-built WASM binaries in `rust-crypto/pkg` and `wasm-sanitizer/pkg` are tracked in the repository.
- **MVP Impact**: Breaks frontend builds on systems without global `wasm-pack`.
- **Remediation**: In `build-wasm.mjs`, check if `wasm-pack` is in PATH; if missing and `validateWasmArtifacts()` passes, gracefully reuse existing artifacts.

#### Finding FE-06: Leaked `startIcon` Prop on `<Button>` Elements Triggers React 19 Console Warnings
- **Severity**: **P2 (Medium / UI Bug)**
- **Citation**: `frontend/src/pages/settings/sections/SessionsSection.tsx:54-57`, `frontend/src/pages/settings/sections/EmailSection.tsx:94`, `frontend/src/pages/settings/sections/PasswordSection.tsx:90`
- **Technical Observation**:
  `Button` accepts `leadingIcon` (and `loading`), not `startIcon`. In settings sections, `startIcon` is passed, leaking through to the native `<button>` DOM element. React 19 logs: `Warning: React does not recognize the startIcon prop on a DOM element.` In addition, the loading spinner is not displayed.
- **MVP Impact**: Console pollution and missing loading feedback spinners.
- **Remediation**: Replace `startIcon={...}` with `leadingIcon={...}` across all three settings sections.

#### Finding FE-07: Missing `useAuthStore` Re-export in Central Stores Barrel Index
- **Severity**: **P3 (Low / Architecture Hygiene)**
- **Citation**: `frontend/src/stores/index.ts:13-41`
- **Technical Observation**: `src/stores/index.ts` re-exports notification, schedule, and app shell stores, but omits `useAuthStore` and its selector hooks.
- **MVP Impact**: Inconsistent import paths (`@/stores/useAuthStore` vs `@/stores`).
- **Remediation**: Export `useAuthStore` and its selector hooks from `src/stores/index.ts`.

#### Finding FE-08: Redundant Duplicate Tailwind Class in SectionCard
- **Severity**: **P3 (Low / Code Hygiene)**
- **Citation**: `frontend/src/components/settings/ui/Layout.tsx:21-24`
- **Technical Observation**: Line 23 duplicates line 22: `"transition-all duration-slow"`.
- **MVP Impact**: Harmless string bloat.
- **Remediation**: Delete duplicate line 23.

#### Finding FE-09: Test MockButton in `SessionsSection.closure.test.tsx` Leaks Non-DOM Attributes
- **Severity**: **P3 (Low / Test Hygiene)**
- **Citation**: `frontend/src/pages/settings/sections/__tests__/SessionsSection.closure.test.tsx:22-28`
- **Technical Observation**: `MockButton` spreads `...props` directly to `<button>`, leaking `startIcon`, `color`, and `variant` to the DOM in test logs.
- **MVP Impact**: Emits stderr warnings during test execution.
- **Remediation**: Destructure non-DOM attributes before spreading props.

---

## 5. Contour 3: Go Microservices Deep Dive

### 5.1 Architectural Invariants Inspection

1. **Goroutine Lifecycle Management (`services/AGENTS.md` Section 3.1)**:
   **Exemplary**. In `services/ws-hub`, every background goroutine is started via `StartTrackedGoroutine(run func())` (`services/ws-hub/pkg/hub/metrics.go:119-134`), which atomically increments and decrements the Prometheus gauge `ws_hub_active_goroutines`. Read/write pumps exit cleanly on context cancellation. In `services/gateway`, the JWKS refresher is tracked with `jwksRefreshWG`, and rate limiter cleanup uses `cleanupDone` channels.
2. **Channel-Based Error Propagation (`services/AGENTS.md` Section 3.2)**:
   Strictly compliant with rule RZ-31-01. Startup errors are sent to buffered channels (`serverErr := make(chan error, 1)` in gateway, `errChan := make(chan error, 2)` in ws-hub and file-processor) and received by main supervisory `select` blocks. Zero instances of `os.Exit` inside helper goroutines.
3. **30-Second RPC & HTTP Timeouts (`services/AGENTS.md` Section 3.3)**:
   Gateway reverse proxy enforces `proxyTransport.ResponseHeaderTimeout = 30 * time.Second`; gRPC client enforces 30s timeout via `WithDefaultServiceConfig()`; file-processor GraphQL engine enforces `middleware.RequestTimeoutMiddleware(30*time.Second)`.
4. **WebSocket Frame & Message Limits (`services/ws-hub`)**:
   `c.Conn.SetReadLimit(64 * 1024)` (64 KB). Incoming messages exceeding 60 KB (`maxIncomingBytes = 60 * 1024`) are rejected with `message_too_large` error frames. Capacity checks are evaluated before connection upgrade (`h.maxClients`). Lock ordering strictly locks `Hub.mu` before `Client.mu`.

### 5.2 Detailed Go Microservices Findings Inventory

#### Finding GO-01 / FP-FP-01: File Processor gRPC & Workflow Path Traversal Filter Bypass on Absolute Paths
- **Severity**: **P1 (High / Security & Path Traversal)**
- **Citation**: `services/file-processor/internal/service/server.go:55, 61-66`, `services/file-processor/internal/workflow/workflow.go:203-207`
- **Technical Observation**:
  ```go
  for _, key := range []string{req.SourceKey, req.DestKey} {
      cleaned := path.Clean(key)
      if strings.HasPrefix(cleaned, "..") || strings.Contains(cleaned, "/../") {
          return status.Errorf(codes.InvalidArgument, "path traversal in key: %q", key)
      }
  }
  ```
  In Go's standard library `path` package, `path.Clean` on an absolute path (beginning with `/`) evaluates all `..` segments against the root directory `/`. Therefore, `path.Clean("/../../etc/passwd")` returns `"/etc/passwd"`.
  - `strings.HasPrefix("/etc/passwd", "..")` evaluates to `false`.
  - `strings.Contains("/etc/passwd", "/../")` evaluates to `false`.
  Traversal payloads with a leading slash bypass both `validateProcessFileRequest` and `sanitizeMinIOKey`, directly violating `services/AGENTS.md` Section 5.2.
- **MVP Impact**: Malicious or malformed gRPC requests can submit keys with leading slashes and traversal segments to read or overwrite arbitrary MinIO object keys outside tenant prefixes.
- **Remediation**:
  In `services/file-processor/internal/service/server.go:61` and `services/file-processor/internal/workflow/workflow.go:203`, reject keys with leading slashes or absolute prefixes before normalization:
  ```go
  if strings.HasPrefix(key, "/") || path.IsAbs(key) || strings.Contains(key, "..") {
      return status.Errorf(codes.InvalidArgument, "invalid path or path traversal in key: %q", key)
  }
  ```

#### Finding GO-02 / GW-AUTH-01: API Gateway Single-Key JWKS Verification Breaks ADR-013 Dual-Key Secret Rotation Window
- **Severity**: **P1 (High / Architectural & Operational Invariant)**
- **Citation**: `services/gateway/middleware/auth.go:76, 267-270, 315-320, 360-374, 735-755, 800-804`
- **Technical Observation**:
  Root `AGENTS.md` Section 7 and ADR-013 mandate dual-key JWT rotation windows (the retiring key validates active tokens while the new key signs outbound tokens).
  In `services/gateway/middleware/auth.go:76`:
  `rsaPublicKey atomic.Pointer[rsa.PublicKey]` stores only a single key pointer. `fetchJWKSPublicKey` parses the JWKS response and returns only the first RSA key found, discarding all subsequent keys and ignoring the token's `kid` header.
- **MVP Impact**: When the backend rotates its RSA key pair and publishes a JWKS with two keys, the gateway caches only one. All active user sessions presenting tokens signed by the other valid key in the rotation window are rejected with HTTP 401 Unauthorized (`crypto/rsa: verification error`).
- **Remediation**:
  1. Replace `rsaPublicKey atomic.Pointer[rsa.PublicKey]` with an atomic pointer to a key map: `rsaKeys atomic.Pointer[map[string]*rsa.PublicKey]`.
  2. Parse all keys in `jwks.Keys`, indexing by `kid`.
  3. Look up keys by `t.Header["kid"]` during token validation.

#### Finding GO-03 / GW-RL-01: API Gateway Rate Limiter Blocks Kubernetes `/health/ready` & `/health/live` Probes During Redis Outage
- **Severity**: **P1 (High / Availability & Cascade Failure)**
- **Citation**: `services/gateway/middleware/ratelimit.go:24-28, 213-216, 269-271`, `services/gateway/cmd/gateway/main.go:687-692`
- **Technical Observation**:
  `services/gateway/middleware/ratelimit.go:269-271` defines `isHealthPath`:
  `return path == "/health" || path == "/readiness" || path == "/metrics"`
  The canonical Kubernetes probe endpoints registered in `services/gateway/cmd/gateway/main.go:687-692` (`/health/ready` and `/health/live`) do NOT match `isHealthPath`. When Redis is unavailable, the in-memory fallback rate limiter restricts each IP to 3 requests per 60 seconds (`defaultFallbackLimit = 3`).
- **MVP Impact**: During Redis outages, kubelet readiness probes hitting `/health/ready` every 5–10 seconds exceed the 3-request limit within 20 seconds. Subsequent probes receive HTTP 429 Too Many Requests. Kubernetes marks the gateway pod as `Unready` and terminates all incoming traffic routing, converting a degraded cache state into a complete cluster-wide outage.
- **Remediation**:
  Update `isHealthPath` in `services/gateway/middleware/ratelimit.go:269-271`:
  `return path == "/health" || path == "/health/live" || path == "/health/ready" || path == "/readiness" || path == "/metrics" || strings.HasPrefix(path, "/health/")`.

#### Finding GO-04 / WSH-CFG-01: WS-Hub Default `ALLOWED_ORIGINS` Omits `http://localhost` (Port 80 Caddy Edge Proxy)
- **Severity**: **P2 (Medium / Configuration)**
- **Citation**: `services/ws-hub/pkg/config/config.go:125`, `services/ws-hub/pkg/hub/handlers.go:77-98`
- **Technical Observation**:
  `services/AGENTS.md` Section 3.5 mandates:
  *"`ALLOWED_ORIGINS` must include `http://localhost` (port 80 Caddy) in development and local compose configurations."*
  `LoadConfig()` defaults to only `[]string{"http://localhost:3000", "http://localhost:5173"}`.
- **MVP Impact**: If `ALLOWED_ORIGINS` is not explicitly set, clients connecting via the Caddy reverse proxy send `Origin: http://localhost` and receive HTTP 403 Forbidden.
- **Remediation**: Update `services/ws-hub/pkg/config/config.go:125` to include `"http://localhost"` and `"http://localhost:80"`.

#### Finding GO-05 / CLI-REDIS-01: Admin CLI `uni-cli` Uses Blocking `KEYS *` Instead of Cursor-Based `SCAN`
- **Severity**: **P2 (Medium / Denial of Service Risk)**
- **Citation**: `services/cmd/uni-cli/main.go:81-84`
- **Technical Observation**:
  `uni-cli cache clear` issues `client.Keys(ctx, pattern)`. Redis `KEYS` is an $O(N)$ blocking command. In production with tens of thousands of active keys, `KEYS *` freezes the single-threaded Redis engine for seconds.
- **MVP Impact**: Gateway session validation (50ms timeout) and rate limiting time out, degrading API responsiveness across all clients.
- **Remediation**: Replace `client.Keys()` with an iterative `client.Scan()` loop using batch size 1000.

#### Finding GO-06 / DOC-AGENTS-01: Architectural Documentation Drift: `services/AGENTS.md` Claims Gateway Listens to NATS `keys.rotated` & `cache.invalidate`
- **Severity**: **P3 (Low / Documentation Drift)**
- **Citation**: `services/AGENTS.md:87, 95`, `services/gateway/go.mod:1-33`, `services/ws-hub/pkg/hub/hub.go:895, 913`
- **Technical Observation**:
  `services/AGENTS.md` Section 4 claims the API Gateway subscribes to NATS subjects `keys.rotated` and `cache.invalidate`. However, `services/gateway` has no NATS dependency (`github.com/nats-io/nats.go` is absent from `go.mod`). These NATS handlers are implemented exclusively in `services/ws-hub`.
- **MVP Impact**: Contradicts architectural documentation and misleads operators.
- **Remediation**: Reconcile `services/AGENTS.md` Section 4 to reflect that gateway uses Redis Pub/Sub for session revocations and HTTP polling for JWKS.

#### Finding GO-07 / ENV-TOOL-01: Local Tooling Divergence (Missing `golangci-lint` and C Compiler on Host)
- **Severity**: **P3 (Low / Developer Tooling)**
- **Technical Observation**:
  On the bare Windows development host, `golangci-lint` is not present in PATH, and `gcc`/`clang` is not installed for `go test -race` (`CGO_ENABLED=1`).
- **MVP Impact**: Developers cannot run local race detector or lint commands without container tooling or WSL2.
- **Remediation**: Document the recommended containerized command in `services/AGENTS.md`: `docker run --rm -v ${PWD}:/app -w /app golangci/golangci-lint:v1.64.5 golangci-lint run`.

---

## 6. Contour 4: Rust Native Extensions Deep Dive

### 6.1 Architectural Invariants Inspection

1. **Memory Safety & Unsafe Blocks**:
   `native/rust_ext`, `crates/pyo3-sanitizer`, and `frontend/rust-crypto` contain zero production unsafe blocks. `frontend/wasm-sanitizer/src/lib.rs:89` contains a single unsafe block (`unsafe { std::slice::from_raw_parts(ptr, len) }`) with a suppressed clippy warning (`not_unsafe_ptr_arg_deref`).
2. **Panic Safety Across FFI**:
   All PyO3 entry points in `native/rust_ext` and `crates/pyo3-sanitizer` are wrapped in `catch_unwind` guards, preventing Rust panics from unwinding across the CPython FFI boundary into undefined behavior.
3. **Sanitization Parity Invariant**:
   The repository contract specifies that frontend (WASM) and backend (PyO3) run identical Ammonia configurations. However, inspection revealed that `crates/pyo3-sanitizer` strips null bytes (`\0`) and BOM (`\u{feff}`) via post-processing, whereas `frontend/wasm-sanitizer` omits this step.

### 6.2 Detailed Rust Findings Inventory

#### Finding RUST-P1-01: Unsafe Raw Pointer Dereferencing with Missing Non-WASM Bounds Checking
- **Severity**: **P1 (High / Memory Safety)**
- **Citation**: `frontend/wasm-sanitizer/src/lib.rs:73-93`
- **Technical Observation**:
  ```rust
  #[wasm_bindgen]
  #[allow(clippy::not_unsafe_ptr_arg_deref)]
  pub fn sanitize_rich_text_raw(ptr: *const u8, len: usize) -> Result<String, String> {
      ...
      #[cfg(target_arch = "wasm32")]
      {
          let mem_size = core::arch::wasm32::memory_size::<0>() * 65536;
          let start = ptr as usize;
          if start > mem_size || len > mem_size || start.saturating_add(len) > mem_size {
              return Err(String::from("Out of bounds pointer/length"));
          }
      }
      let slice = unsafe { std::slice::from_raw_parts(ptr, len) };
  ```
  1. `sanitize_rich_text_raw` is a public safe function accepting raw pointers. Memory bounds validation is guarded by `#[cfg(target_arch = "wasm32")]`. When compiled on native targets (x86_64/aarch64) for unit testing or SSR, bounds checking is completely omitted: non-null pointers are dereferenced directly in `std::slice::from_raw_parts`, resulting in undefined memory reads.
  2. On `wasm32`, `core::arch::wasm32::memory_size::<0>() * 65536` can overflow 32-bit `usize` if memory grows to maximum 65,536 pages (4GB).
- **MVP Impact**: Memory corruption risks if invoked natively, and potential integer overflow panic on 32-bit WASM memory boundaries.
- **Remediation**:
  1. Declare the function as `pub unsafe fn sanitize_rich_text_raw` or reject non-wasm32 execution:
     `#[cfg(not(target_arch = "wasm32"))] return Err(String::from("Only supported on wasm32"));`.
  2. Guard against 32-bit multiplication overflow:
     `let mem_size = (core::arch::wasm32::memory_size::<0>() as u64).saturating_mul(65536);`.

#### Finding RUST-P1-02: Architectural Parity Drift: Null-Byte and BOM Sanitization Inconsistency
- **Severity**: **P1 (High / Parity Drift)**
- **Citation**: `frontend/wasm-sanitizer/src/lib.rs:55-56, 65, 70-71`, `crates/pyo3-sanitizer/src/lib.rs:68-80, 100, 124`
- **Technical Observation**:
  In `crates/pyo3-sanitizer/src/lib.rs:80, 100, 124`, Ammonia sanitized strings are post-processed with `.replace(['\0', '\u{feff}'], "")` because html5ever preserves null bytes and BOM in text nodes. In `frontend/wasm-sanitizer/src/lib.rs`, this post-processing is absent.
- **MVP Impact**: An HTML string containing null bytes or byte-order-marks is accepted unchanged by the frontend WASM sanitizer but mutated by the backend PyO3 sanitizer, breaking output idempotency and client/server cache synchrony.
- **Remediation**: Add `.replace(['\0', '\u{feff}'], "")` to `sanitize_rich_text`, `sanitize_html_basic`, and `strip_html` in `frontend/wasm-sanitizer/src/lib.rs`.

#### Finding RUST-P2-01: Python GIL Retained During CPU-Intensive Multi-Threaded Rayon Conflict Detection
- **Severity**: **P2 (Medium / Concurrency & Latency)**
- **Citation**: `native/rust_ext/src/lib.rs:212-222, 335-352, 390-399`
- **Technical Observation**:
  `batch_detect_conflicts_py` extracts Python items and invokes `batch_detect_conflicts(items)`, which executes a parallel Rayon pool (`items.par_iter()`). However, `py.allow_threads(...)` is never called.
- **MVP Impact**: The calling thread retains the Python GIL while Rayon runs across multiple CPU cores. All other Python threads (FastAPI asyncio event loop, background workers) are blocked from executing bytecode until the Rayon job finishes.
- **Remediation**: Accept `py: Python<'py>` in `batch_detect_conflicts_py`, `detect_conflicts_py`, and `find_optimal_slot_py` and wrap the Rayon call in `py.allow_threads(|| ...)`.

#### Finding RUST-P2-02: Unbounded Key Size & Missing Iteration Bounds in WASM PBKDF2
- **Severity**: **P2 (Medium / Denial of Service)**
- **Citation**: `frontend/rust-crypto/src/lib.rs:9-14`
- **Technical Observation**:
  `pbkdf2_derive` allocates `vec![0u8; key_size]` and executes `pbkdf2_hmac` without bounds checks on `iterations` or `key_size`. Passing `key_size = usize::MAX` causes an uncatchable WASM linear memory allocation trap; passing `iterations = 0` produces non-standard output.
- **MVP Impact**: An unvalidated payload can trigger uncatchable WASM traps, corrupting the Web Worker runtime instance.
- **Remediation**: Bound `iterations` between 1 and 1,000,000 and `key_size` between 1 and 1,024 bytes, returning a `Result<String, JsValue>`.

#### Finding RUST-P2-03: Cryptographic Secret Material Not Zeroized in Memory in `rust-crypto`
- **Severity**: **P2 (Medium / Cryptographic Hygiene)**
- **Citation**: `frontend/rust-crypto/src/lib.rs:10-23, 51-67`, `native/rust_ext/src/lib.rs:738, 811`
- **Technical Observation**:
  While `native/rust_ext` uses `Zeroizing::new(...)` for sensitive keys, `frontend/rust-crypto` leaves plaintext passwords, intermediate HMAC buffers, and derived key material in unzeroized heap memory.
- **MVP Impact**: Sensitive cryptographic secrets persist in WASM linear memory until overwritten, vulnerable to memory inspection.
- **Remediation**: Add `zeroize = { version = "1.8", features = ["zeroize_derive"] }` to `frontend/rust-crypto/Cargo.toml` and wrap sensitive buffers in `Zeroizing`.

#### Finding RUST-P2-04: Cargo Deny Workflow Scans Only 1 of 4 Rust Crates
- **Severity**: **P2 (Medium / Security Gate)**
- **Citation**: `.github/workflows/cargo-deny.yml:28`
- **Technical Observation**:
  `.github/workflows/cargo-deny.yml:28` sets `manifest-path: native/rust_ext/Cargo.toml`. The other 3 crates (`crates/pyo3-sanitizer`, `frontend/wasm-sanitizer`, `frontend/rust-crypto`) are excluded from automated license, advisory, and ban checks in CI.
- **MVP Impact**: Security vulnerabilities (CVEs) or GPL license violations in unmonitored crates slip into the codebase undetected.
- **Remediation**: Parameterize `cargo-deny.yml` across all 4 crate manifests via a matrix job or target the root workspace manifest.

#### Finding RUST-P2-05: Rust Fuzz CI Workflow Excludes `crates/pyo3-sanitizer/fuzz`
- **Severity**: **P2 (Medium / Quality Gate)**
- **Citation**: `.github/workflows/rust-fuzz.yml:112-128`
- **Technical Observation**:
  `rust-fuzz.yml` executes fuzz targets for `native/rust_ext`, `frontend/wasm-sanitizer`, and `frontend/rust-crypto`, but completely omits `crates/pyo3-sanitizer/fuzz`.
- **MVP Impact**: Backend HTML sanitization fuzzing targets (`fuzz_sanitize_rich_text`, `fuzz_sanitize_html_basic`, `fuzz_strip_html`) are never executed in CI.
- **Remediation**: Add `crates/pyo3-sanitizer/fuzz` to `strategy.matrix.include` in `rust-fuzz.yml`.

#### Finding RUST-P3-01: Missing Root `Cargo.toml` Workspace
- **Severity**: **P3 (Low / Build Hygiene)**
- **Citation**: Repository Root (`Cargo.toml`)
- **Technical Observation**:
  There is no `Cargo.toml` at the repository root. Running `cargo clippy --workspace` or `cargo test --workspace` fails with:
  `error: could not find 'Cargo.toml' in 'C:\Users\egorribun\Documents\university_ecosystem'`.
- **MVP Impact**: Broken ergonomics for developers expecting standard root cargo commands.
- **Remediation**: Add a root virtual workspace `Cargo.toml` indexing all 4 crates.

#### Finding RUST-P3-02: Orphaned Fuzz Target Tracked at Repository Root
- **Severity**: **P3 (Low / Repository Hygiene)**
- **Citation**: `fuzz/fuzz_targets/fuzz_scrypt.rs:1-25`
- **Technical Observation**:
  `fuzz/fuzz_targets/fuzz_scrypt.rs` is tracked at root without a parent `Cargo.toml`. The active working target is located at `frontend/rust-crypto/fuzz/fuzz_targets/fuzz_scrypt.rs`.
- **MVP Impact**: Redundant orphan file.
- **Remediation**: Remove `fuzz/fuzz_targets/fuzz_scrypt.rs` via `git rm`.

#### Finding RUST-P3-03: Inefficient Hex-to-Base64 Conversion in Crypto Web Worker
- **Severity**: **P3 (Low / Performance)**
- **Citation**: `frontend/rust-crypto/src/lib.rs:17-23`, `frontend/src/workers/crypto.worker.ts:45-51`
- **Technical Observation**:
  `hmac_sha256_sign` emits a 64-character hex string, which the TypeScript worker parses back using regex matching, maps to integers, converts to binary string, and base64 encodes via `btoa`.
- **MVP Impact**: Unnecessary intermediate string allocations on every HMAC calculation in the web worker.
- **Remediation**: Add `hmac_sha256_sign_bytes` or `hmac_sha256_sign_base64` to `frontend/rust-crypto/src/lib.rs`.

#### Finding RUST-P3-04: Unused Dependencies and Redundant Features in `native/rust_ext`
- **Severity**: **P3 (Low / Dependency Hygiene)**
- **Citation**: `native/rust_ext/Cargo.toml:17`, `native/rust_ext/src/lib.rs:811`, `native/rust_ext/fuzz/Cargo.toml:11, 18`
- **Technical Observation**:
  1. `native/rust_ext/Cargo.toml:17` requests `chrono = { version = "0.4", features = ["serde"] }`, but `serde` is never imported or used.
  2. Line 811 re-allocates a `Vec<u8>` for every key on every event in `verify_event_chain`: `let key_bytes = Zeroizing::new(key_str.as_bytes().to_vec());`.
  3. `native/rust_ext/fuzz/Cargo.toml` includes unused `ammonia` and `uuid`.
- **MVP Impact**: Inflated binary size and redundant heap allocations in audit log verification.
- **Remediation**: Remove unused features and pre-allocate key buffers outside the verification loop.

---

## 7. Contour 5: Infrastructure & CI/CD Deep Dive

### 7.1 Architectural Invariants Inspection

1. **Kubernetes Manifests & Kyverno Policies**:
   Manifests in `k8s/` enforce non-root user execution (`runAsNonRoot: true`), read-only root filesystems, seccomp `RuntimeDefault`, and drop all Linux capabilities (`drop: [ALL]`). Kyverno policies enforce semantic image tagging (disallowing `:latest`).
2. **Helm Parameterization (`charts/university-ecosystem/`)**:
   `values.yaml` fully parameterizes backend, ws-hub, gateway, and ingress configurations. However, frontend autoscaling is completely absent from the Helm chart.
3. **GitHub Actions Workflow Hardening**:
   54 workflow files pass `actionlint`. Third-party actions are 100% pinned to immutable 40-character commit SHAs. Zero occurrences of `pull_request_target`.

### 7.2 Detailed Infrastructure Findings Inventory

#### Finding INFRA-01: Critical Secret Discrepancy Causes Backend Crash-Loop in Standalone K8s Deployments
- **Severity**: **P0 (Blocker / Critical Bug)**
- **Citation**: `k8s/backend/external-secret.yaml:24-52`, `k8s/secrets-example.yaml:11-14`, `k8s/backend/deployment.yaml:66-70`
- **Technical Observation**:
  In `k8s/backend/deployment.yaml`, the backend injects environment variables from `secretRef: backend-secrets`. In `k8s/backend/external-secret.yaml:24-52`, the ExternalSecret retrieves only: `SECRET_KEY`, `DATABASE_URL`, `CSRF_HMAC_SECRET`, `INTERNAL_HMAC_SECRET`, `JWT_SECRET`, `NATS_AUTH_TOKEN`, `AUDIT_LOG_SECRET`.
  Neither `CACHE_REDIS_URL` nor `REVOCATION_REDIS_URL` is defined in `external-secret.yaml` or `configmap.yaml`. In `k8s/secrets-example.yaml:12`, only the legacy `REDIS_URL: "redis://redis:6379/0"` is provided.
  Outside development (`ENVIRONMENT=production`), `app/core/config/__init__.py:213-241` asserts that `REVOCATION_REDIS_URL` is configured, distinct from `CACHE_REDIS_URL`, and uses separate credentials. Missing `REVOCATION_REDIS_URL` raises a fatal `RuntimeError` at application bootstrap.
- **MVP Impact**: Any attempt to deploy the backend to Kubernetes using standalone manifests in `k8s/backend/` enters a permanent `CrashLoopBackOff`.
- **Remediation**:
  1. Add remote secret mappings for `CACHE_REDIS_URL` and `REVOCATION_REDIS_URL` in `k8s/backend/external-secret.yaml`.
  2. Replace `REDIS_URL` with explicit `CACHE_REDIS_URL` and `REVOCATION_REDIS_URL` in `k8s/secrets-example.yaml`.
  3. Include required application secrets (`JWT_PRIVATE_KEY_PATH`, `WS_HUB_INTERNAL_SECRET`, `IDEMPOTENCY_HMAC_SECRET`) in `external-secret.yaml`.

#### Finding INFRA-02: Standalone K8s Suite Omits Go Microservices (Gateway, WS-Hub, File-Processor)
- **Severity**: **P1 (High / Severe Inconsistency)**
- **Citation**: `k8s/ingress.yaml:47-50`
- **Technical Observation**:
  `k8s/ingress.yaml:48-50` routes API traffic (`host: ${API_HOST}`) to backend service `name: gateway`, port `8080`. However, directory `k8s/` contains manifests only for `backend/`, `frontend/`, `flagd/`, `jobs/`, `outbox-worker/`, and `spire/`. There are NO deployment or service manifests for `services/gateway`, `services/ws-hub`, or `services/file-processor` in `k8s/`.
- **MVP Impact**: Raw Kubernetes manifests in `k8s/` cannot deploy a functioning platform. Ingress traffic to `${API_HOST}` fails immediately with HTTP 503 Service Unavailable.
- **Remediation**:
  Provide deployment manifests for `gateway`, `ws-hub`, and `file-processor` under `k8s/`, or clarify in `k8s/README.md` that `charts/university-ecosystem` is the single canonical deployment artifact.

#### Finding INFRA-03: Dynamic `${IMAGE_TAG}` in K8s Deployments Risks Kyverno Policy 9 Rejection
- **Severity**: **P1 (High / Admission Controller Failure)**
- **Citation**: `k8s/backend/deployment.yaml:61`, `k8s/frontend/deployment.yaml:68`, `k8s/jobs/password-migration-job.yaml:50`, `k8s/kyverno/cluster-policies.yaml:334-336`
- **Technical Observation**:
  Kyverno `disallow-latest-tag` policy enforces that every container image matches `^.+(@sha256:[a-f0-9]{64}|:[^/:@]+)$` and does not end with `:latest`. In `k8s/backend/deployment.yaml:61`, `image: registry.example.com/backend:${IMAGE_TAG}` is specified. Root `AGENTS.md:156` documents required `envsubst` variables (`FRONTEND_HOST`, `API_HOST`, `TLS_SECRET_NAME`, `VAULT_URL`) but omits `IMAGE_TAG`. Running `envsubst` without `IMAGE_TAG` produces an empty tag (`registry.example.com/backend:`), which Kyverno immediately rejects at admission.
- **MVP Impact**: Unhandled deployment failure during `kubectl apply`.
- **Remediation**: Add `${IMAGE_TAG}` to the documented `envsubst` variables in root `AGENTS.md`, and provide a wrapper script that verifies all required environment variables prior to running `envsubst | kubectl apply`.

#### Finding INFRA-04: Frontend Missing HorizontalPodAutoscaler (HPA) in Helm Chart
- **Severity**: **P1 (High / Scalability)**
- **Citation**: `charts/university-ecosystem/values.yaml:200-217`, `charts/university-ecosystem/templates/hpa.yaml:1-33`, `charts/university-ecosystem/templates/frontend-deployment.yaml:9-11`, `k8s/frontend/hpa.yaml:1-24`
- **Technical Observation**:
  `charts/university-ecosystem/values.yaml` provides autoscaling configuration for `backend` (lines 160-165) and `wsHub` (lines 269-274). However, `frontend` has no `autoscaling` block in `values.yaml`, and `templates/hpa.yaml` templates only backend HPA. Standalone `k8s/frontend/hpa.yaml` exists (implemented under TD-25-02 specifically for enrollment surges), but was omitted from the Helm chart.
- **MVP Impact**: In production deployments via Helm, the frontend remains fixed at 2 replicas. Under traffic surges, the frontend exhausts CPU/memory while the backend scales out.
- **Remediation**: Add `frontend.autoscaling` to `values.yaml` and implement `charts/university-ecosystem/templates/frontend-hpa.yaml`.

#### Finding INFRA-05: Frontend Memory Limit in Helm Chart Too Low for Node SSR Workloads
- **Severity**: **P1 (High / Stability & OOMKilled)**
- **Citation**: `charts/university-ecosystem/values.yaml:211-216`, `k8s/frontend/deployment.yaml:115-124`
- **Technical Observation**:
  `charts/university-ecosystem/values.yaml:211-216` configures frontend limits as `limits.memory: 256Mi`. In contrast, `k8s/frontend/deployment.yaml:115-124` bumped memory limits to `512Mi` following the migration to TanStack Start Node SSR:
  `"Node + V8 heap + tanstackStart SSR per-request work peaks 250-400 MB under load (vs ~50 MB nginx static-serve)."`
- **MVP Impact**: Deploying via Helm causes frontend pods to hit the cgroup ceiling and be terminated by the kernel (`OOMKilled`, exit code 137) during concurrent SSR rendering.
- **Remediation**: Update `charts/university-ecosystem/values.yaml:211-216` to set `limits.memory: 512Mi` and `requests.memory: 128Mi`.

#### Finding INFRA-06: Potential Shell Injection in `reusable-backend-tests.yml` via Direct `${{ inputs.* }}` Interpolation
- **Severity**: **P1 (High / CI/CD Security)**
- **Citation**: `.github/workflows/reusable-backend-tests.yml:162-167, 192, 220-221`
- **Technical Observation**:
  Inputs are interpolated directly into a PowerShell (`pwsh`) script body:
  `$pytestArgs = @("${{ inputs.test-pattern }}")  # nosemgrep`
  `$pytestArgs += "--cov-fail-under=${{ inputs.coverage-threshold }}"  # nosemgrep`
  Direct string interpolation into shell scripts allows syntax injection if caller workflows pass unsanitized input. The developer suppressed the Semgrep SAST rule with `# nosemgrep`.
- **MVP Impact**: Potential arbitrary code execution on CI runners if caller workflows supply unvalidated input.
- **Remediation**: Pass workflow inputs via step-level `env:` variables and reference `$env:TEST_PATTERN` in PowerShell.

#### Finding INFRA-07: Backend Dockerfile Healthcheck Uses Heavy Diagnostic `/healthz` Instead of `/health/ready`
- **Severity**: **P2 (Medium / Suboptimal Health Probe)**
- **Citation**: `backend.Dockerfile:106-107`, `app/api/health.py:160-200, 357`, `AGENTS.md:149`
- **Technical Observation**:
  `backend.Dockerfile:107` configures `HEALTHCHECK ... CMD python -c "... http://127.0.0.1:8000/healthz ..."`. In `app/api/health.py`, `/healthz` executes full system health checks including database `SELECT 1`, migration currency verification, and storage checks. In contrast, root `AGENTS.md:149` explicitly mandates `/health/ready`.
- **MVP Impact**: Creates unnecessary database load every 30 seconds per container and marks containers unhealthy during transient external dependency latency.
- **Remediation**: Update `backend.Dockerfile:107` to probe `http://127.0.0.1:8000/health/ready`.

#### Finding INFRA-08: Missing Healthcheck for File-Processor in `docker-compose.go.yml`
- **Severity**: **P2 (Medium / Compose Resilience)**
- **Citation**: `docker-compose.go.yml:82-120`, `docker-compose.full.yml:943-948`, `AGENTS.md:150`
- **Technical Observation**: `docker-compose.go.yml` omits a `healthcheck:` section for `file-processor`, whereas `docker-compose.full.yml:943-948` configures `grpc_health_probe -addr=:50051`.
- **MVP Impact**: Dependent services in Go compose workflows cannot synchronize readiness with `file-processor`.
- **Remediation**: Add the standard `grpc_health_probe` healthcheck block to `docker-compose.go.yml`.

#### Finding INFRA-09: Dangling Dependency on `tempo-healthprobe` in `docker-compose.observability.yml`
- **Severity**: **P2 (Medium / Compose Configuration)**
- **Citation**: `docker-compose.observability.yml:164-165`, `docker-compose.yml:932-952`
- **Technical Observation**: `docker-compose.observability.yml:164` declares `depends_on: tempo-healthprobe: condition: service_healthy`. However, `tempo-healthprobe` is defined only in `docker-compose.yml:932` and is missing from `docker-compose.observability.yml`.
- **MVP Impact**: The observability Compose file cannot be started standalone without passing `-f docker-compose.yml`.
- **Remediation**: Define `tempo-healthprobe` inside `docker-compose.observability.yml`.

#### Finding INFRA-10: Gateway Service Lacks Autoscaling Configuration in Helm Chart
- **Severity**: **P2 (Medium / Scalability)**
- **Citation**: `charts/university-ecosystem/values.yaml:219-248`
- **Technical Observation**: While `backend` and `wsHub` have HPA definitions, the edge `gateway` has no autoscaling parameterization or HPA template.
- **MVP Impact**: Under API traffic spikes, the gateway cannot scale out pods automatically.
- **Remediation**: Add `gateway.autoscaling` to `values.yaml` and a corresponding `gateway-hpa.yaml` template.

#### Finding INFRA-11: Hardcoded ClusterIssuer in Standalone Ingress Manifest
- **Severity**: **P2 (Medium / Environment Decoupling)**
- **Citation**: `k8s/ingress.yaml:19`, `charts/university-ecosystem/templates/ingress.yaml:12-16`
- **Technical Observation**: `k8s/ingress.yaml:19` hardcodes `cert-manager.io/cluster-issuer: "letsencrypt-prod"`, unlike the Helm chart which parameterizes issuers.
- **MVP Impact**: Applying standalone manifests in staging attempts to request production Let's Encrypt certificates.
- **Remediation**: Parameterize the annotation with `${CERT_MANAGER_ISSUER_NAME:-letsencrypt-prod}`.

#### Finding INFRA-12: Weekly Cleanup Scheduled Job Hard-Fails When Database Secret Is Not Configured
- **Severity**: **P3 (Low / CI Maintenance)**
- **Citation**: `.github/workflows/weekly-cleanup.yml:23-24, 49-57`
- **Technical Observation**: Lines 54-57 enforce an explicit `exit 1` if `DATABASE_URL` is empty.
- **MVP Impact**: Produces recurring failure notifications on repository forks or staging environments without direct database connectivity.
- **Remediation**: Skip step gracefully or emit a warning when database secrets are unconfigured.

---

## 8. Contour 6: Security, Supply Chain & Posture Deep Dive

### 8.1 Architectural Invariants Inspection

1. **Cross-Service Identity Assertion**:
   The edge gateway signs verified user claims into `X-Internal-Signature` via HMAC-SHA256. REST endpoints verify this signature. However, **the GraphQL endpoint (`app/graphql/schema.py`) completely omits signature verification**, allowing unauthenticated actors to forge identity headers.
2. **Three-Tier Secret Rotation (ADR-013)**:
   Mandates dual-key JWT rotation windows. The backend and ws-hub support multiple keys via JWKS. The gateway caches only a single RSA public key and ignores token `kid` claims, breaking zero-downtime rotation.
3. **Supply Chain & Lockfile Auditing**:
   `uv.lock`, `package-lock.json`, `go.sum`, and `Cargo.lock` pass security auditing (0 CVEs via `pip-audit`, 0 vulnerabilities via `npm audit`, `go mod verify` clean). However, 19 direct Python production dependencies lack semver upper bounds.

### 8.2 Detailed Security & Supply Chain Findings Inventory

#### Finding SEC-01: GraphQL Context Ignores `X-Internal-Signature` Gateway Verification
- **Severity**: **P0 (Blocker / Critical Security Exploit)**
- **Citation**: `app/graphql/schema.py:78-86`, `app/api/deps/auth.py:75-110`
- **Technical Observation**:
  In `app/api/deps/auth.py:75-110`, the REST API dependency validates `X-Internal-Signature` using `settings.internal_hmac_secret` (HMAC-SHA256) whenever `X-User-ID` and `X-Session-ID` are present. If the signature is invalid or missing in production, the request is rejected with HTTP 401.
  However, in `app/graphql/schema.py:78-86`:
  ```python
  x_user_id = request.headers.get("X-User-ID")
  x_session_id = request.headers.get("X-Session-ID")

  if x_user_id and x_session_id:
      current_user = await validator.validate(x_user_id, x_session_id)
  ```
  The GraphQL resolver context directly trusts caller-supplied `X-User-ID` and `X-Session-ID` without verifying `X-Internal-Signature`.
- **MVP Impact**: Any internal actor, compromised pod, SSRF exploit, or edge proxy bypass can forge `X-User-ID` and `X-Session-ID` headers to execute GraphQL queries and mutations as any arbitrary tenant or platform administrator without credentials or HMAC signatures.
- **Remediation**:
  In `app/graphql/schema.py`, import `settings` from `app.core.config` and verify `X-Internal-Signature` exactly as done in `app/api/deps/auth.py:75-110` before calling `validator.validate()`. Reject requests with missing or invalid HMAC signatures when `X-User-ID` is present.

#### Finding SEC-02: Missing Dual-Key JWT RS256 Rotation Window in Gateway (Violates ADR-013)
- **Severity**: **P1 (High / Architectural & Operational Invariant)**
- **Citation**: `services/gateway/middleware/auth.go:76, 315-320, 360-374`
- **Technical Observation**:
  Cross-referenced with Finding GO-02. The gateway caches only a single `rsa.PublicKey` pointer and drops all other keys in the JWKS array, ignoring token `kid` claims.
- **MVP Impact**: Key rotation causes immediate user session drops across active clients.
- **Remediation**: Maintain an atomic map of `kid -> *rsa.PublicKey` and support dual-key verification windows during key rollover.

#### Finding SEC-03: Hardcoded Default `audit_log_secret` — SOURCE VALIDATION CLOSED; HISTORICAL USE UNVERIFIED 2026-09-30
- **Severity**: Historical P1; current source guard is verified, deployment verification remains open.
- **Current citation**: `app/core/config/security.py:285-334, 352-365`; `tests/test_security_settings_closure.py::test_default_audit_secret_is_rejected_in_production`; `tests/test_security_settings_closure.py::test_retired_repository_audit_keys_are_rejected_in_production`.
- **Historical observation**: The original report described a 32-character hexadecimal value as the Python default and claimed it passed production validation. A safe in-memory comparison confirmed that the same value appeared in seven historical revisions of `app/core/config/security.py`; the value is redacted from this report and is absent from current source.
- **Current state**: `SecuritySettings.audit_log_secret` uses a named placeholder sentinel. Production validation rejects known or placeholder keys and values shorter than 32 characters; operators must provide a cryptographically random value. It rejects the retired key even as a secondary key, so a production overlap cannot retain it for verification. The standalone Kubernetes manifest declares a Vault-backed ExternalSecret consumed by the backend Deployment. Helm supports `applicationSecrets.existingSecret`, but the checked-in default is empty and no active release override is present in the repository. These manifests document intended wiring; they do not prove that a live secret was synced or deployed. The regression tests verify sentinel and retired-key rejection.
- **Rotation behavior**: The ordered audit-key ring uses its first key for new HMACs and accepts configured keys for verification. The current runbook can re-sign `DataAccessLog` rows, but no helper re-signs or rebuilds existing `StoredEvent` chains. If a retained database contains records signed with the retired key, the normal production configuration cannot verify them and the existing re-sign script does not migrate them.
- **Disposition**: The source-level validation finding is closed for the current snapshot. Whether an older deployment or secret store used the retired key has not been established. This is a conditional release-readiness issue: a fresh MVP demo environment with a new random key and no legacy database is unaffected; any retained database must be inventoried from a protected, consistent backup before migration. If old-key records exist, verify them in an isolated path before any rewrite, preserve evidence and document the trust limits of records signed with an exposed key, then provide a compatible migration for both record types. Do not re-enable the retired key in serving configuration or treat historical exposure as fully resolved until deployment use and data compatibility are established. This status does not certify the remaining audit findings.

#### Finding SEC-04: Go Microservices Emit Structured Logs Without PII Redaction
- **Severity**: **P1 (High / Compliance & Privacy Leak - Violates ADR-012)**
- **Citation**: `services/gateway/cmd/gateway/main.go:394-405`, `services/ws-hub/main.go:200-211`, `services/file-processor/cmd/file-processor/main.go:286-296`
- **Technical Observation**:
  ADR-012 mandates PII redaction at the application layer across all services. While Python backend implements `_redact_pii`, all three Go microservices configure `slog` with a custom `ReplaceAttr` that only reformats timestamps, performing zero PII scrubbing on string attributes or sensitive keys.
- **MVP Impact**: Unredacted authorization headers, bearer tokens, and user emails leak to console logs and are ingested into Grafana Loki.
- **Remediation**: Implement a shared `slog.Handler` in `services/pkg/logging` that sanitizes sensitive keys and regex masks email/phone patterns, and adopt it across all three Go microservices.

#### Finding SEC-05: Quality Contract Coverage Zero-Floors & Validator Bypass Loophole
- **Severity**: **P2 (Medium / Governance Defect)**
- **Citation**: `quality/quality-contract.json:47-60`, `scripts/quality/validate_quality_contract.py:328-329`
- **Technical Observation**:
  Root `AGENTS.md` mandates 100% statement, branch, and function coverage. In `quality/quality-contract.json:47-60`, Python function coverage is set to `0%`, and Go line, branch, and function coverages are set to `0%`. In `scripts/quality/validate_quality_contract.py:328-329`, `if not exact and percentage == 0: continue` explicitly bypasses validation for 0% values.
- **MVP Impact**: The machine-enforced quality gate allows components to bypass coverage requirements while appearing 100% compliant.
- **Remediation**: Align `quality/quality-contract.json` with true measurable targets per runtime and remove the 0% bypass check.

#### Finding SEC-06: Gitleaks Configuration Stale Allowlist Paths & Missing `egorribun` Branch Trigger
- **Severity**: **P2 (Medium / Tooling Hygiene)**
- **Citation**: `.gitleaks.toml:5-7`, `.github/workflows/gitleaks.yml:5-7`
- **Technical Observation**:
  1. `.gitleaks.toml:6` references nonexistent `root/.env.example`.
  2. Line 7 matches stale `your_super_secret_key_here` (now `CHANGE_ME_GENERATE_64_BYTE_SECRET_KEY`).
  3. `gitleaks.yml` triggers only on `main`, bypassing the active `egorribun` branch.
- **MVP Impact**: Gitleaks PR checks do not execute on branch `egorribun`.
- **Remediation**: Update `.gitleaks.toml` file paths and regexes, and add `egorribun` to `gitleaks.yml`.

#### Finding SEC-07: 326 Baseline Entries Unverified in `.secrets.baseline`
- **Severity**: **P2 (Medium / Baseline Hygiene)**
- **Citation**: `.secrets.baseline:2-2744`
- **Technical Observation**: All 326 detected secret instances across 159 files have `"is_verified": false`.
- **MVP Impact**: Accumulates technical debt; prevents developers from distinguishing known test fixtures from newly leaked real secrets.
- **Remediation**: Execute `detect-secrets audit .secrets.baseline` interactively to mark verified false positives.

#### Finding SEC-08: Bandit Target Misalignment and Windows CP1251 Unicode Crash
- **Severity**: **P2 (Medium / Developer Tooling Defect)**
- **Citation**: `pyproject.toml:511`, `.pre-commit-config.yaml:45-46`
- **Technical Observation**: `pyproject.toml:511` sets `targets = ["app", "tests"]`, triggering false positives on test dummy passwords and Unicode crashes on Windows CP1251. `.pre-commit-config.yaml` overrides this with `files: ^app/`.
- **MVP Impact**: Inconsistency between local CLI `bandit` runs and pre-commit hooks.
- **Remediation**: Change `targets = ["app"]` in `pyproject.toml:511`.

#### Finding SEC-09: 19 Production Python Dependencies Lack Upper Version Bounds
- **Severity**: **P2 (Medium / Supply Chain Fragility)**
- **Citation**: `pyproject.toml:23-89`
- **Technical Observation**: 19 direct production dependencies (`cryptography`, `orjson`, `structlog`, `brotli-asgi`, etc.) specify minimum versions without upper limits.
- **MVP Impact**: Unintentional major version bumps during lockfile regeneration can introduce breaking API changes.
- **Remediation**: Enforce semver major upper bounds (e.g. `cryptography>=50.0.0,<51`) in `pyproject.toml`.

#### Finding SEC-10: Blocking Redis `KEYS` Command Used in Administrative CLI
- **Severity**: **P2 (Medium / Denial of Service)**
- **Citation**: `services/cmd/uni-cli/main.go:81-84`
- **Technical Observation**: Cross-referenced with Finding GO-05. `client.Keys()` executes blocking $O(N)$ command in Redis.
- **MVP Impact**: Freezes Redis event loop during cache clear.
- **Remediation**: Replace with `client.Scan()`.

#### Finding SEC-11: Dockerfile HEALTHCHECK Uses Full `/healthz` Instead of Readiness `/health/ready`
- **Severity**: **P3 (Low / Inconsistency)**
- **Citation**: `backend.Dockerfile:107`, `k8s/backend/deployment.yaml:90`
- **Technical Observation**: Cross-referenced with Finding INFRA-07. Uses `/healthz` instead of `/health/ready`.
- **MVP Impact**: Spurious container unhealthy events during transient DB latency.
- **Remediation**: Point probe to `/health/ready`.

#### Finding SEC-12: Pre-Commit Mypy Hook Omits `models`, `schemas`, `utils`, and `main.py`
- **Severity**: **P3 (Low / Type Safety Gap)**
- **Citation**: `.pre-commit-config.yaml:56`
- **Technical Observation**: The pre-commit mypy hook regex (`^app/(auth|services|api|core|repositories|graphql)/`) omits `app/models/`, `app/schemas/`, `app/utils/`, and `app/main.py`.
- **MVP Impact**: Type errors in models or schemas can be committed locally without pre-commit rejection.
- **Remediation**: Expand `files` regex in `.pre-commit-config.yaml` to `^app/`.

---

## 9. Prioritized Turnkey MVP Remediation Roadmap

The remediation roadmap is structured into 4 sequential phases, providing an actionable blueprint to bring the platform from its current audited state to a fully hardened, zero-debt, production-ready MVP.

```
                               MVP REMEDIATION ROADMAP
 ┌─────────────────────────────────────────────────────────────────────────────────────────┐
 │ PHASE 1: P0 BLOCKERS (Immediate Pre-Release Action)                                     │
 │ ├─ [SEC-01]   Verify X-Internal-Signature in app/graphql/schema.py                      │
 │ └─ [INFRA-01] Add CACHE/REVOCATION_REDIS_URL to k8s ExternalSecrets to stop crash-loop  │
 ├─────────────────────────────────────────────────────────────────────────────────────────┤
 │ PHASE 2: P1 HIGH-PRIORITY ARCHITECTURAL & SECURITY HARDENING                            │
 │ ├─ [BE-01]    Remove app.utils.encryption import in Alembic migration 148642dd1207      │
 │ ├─ [BE-02]    Declare dual defaults across all 92 columns in app/models/                │
 │ ├─ [BE-03]    Fix User.chats backref lazy="select" leak with explicit back_populates    │
 │ ├─ [BE-04]    Migrate remaining API routers from Depends to FromDishka[T]               │
 │ ├─ [BE-05]    Bridge stdlib logging to structlog ProcessorFormatter                     │
 │ ├─ [FE-01]    Fix path traversal and URIError in frontend/scripts/server-prod.mjs       │
 │ ├─ [GO-01]    Fix absolute path traversal bypass in file-processor server & workflow    │
 │ ├─ [GO-02]    Implement dual-key JWKS key map in gateway middleware/auth.go             │
 │ ├─ [GO-03]    Exempt /health/ready and /health/live from gateway in-memory rate limiter │
 │ ├─ [RUST-01]  Add non-wasm32 bounds checks to sanitize_rich_text_raw in wasm-sanitizer  │
 │ ├─ [RUST-02]  Add null-byte and BOM stripping parity to frontend/wasm-sanitizer         │
 │ ├─ [INFRA-02] Provide gateway/ws-hub/file-processor manifests in k8s/                   │
 │ ├─ [INFRA-03] Validate IMAGE_TAG in envsubst deployment wrapper                         │
 │ ├─ [INFRA-04] Add Frontend HPA autoscaler to Helm chart                                 │
 │ ├─ [INFRA-05] Bump Frontend memory limit from 256Mi to 512Mi in Helm chart              │
 │ ├─ [INFRA-06] Pass inputs via env: in reusable-backend-tests.yml to stop shell inject │
 │ ├─ [SEC-03]   Require explicit AUDIT_LOG_SECRET in production config validator          │
 │ └─ [SEC-04]   Implement shared slog PII redaction handler across Go microservices       │
 ├─────────────────────────────────────────────────────────────────────────────────────────┤
 │ PHASE 3: P2 OPERATIONAL & CONCURRENCY OPTIMIZATION                                      │
 │ ├─ [BE-06]    Implement recursive dict/list PII redaction in _redact_pii                │
 │ ├─ [BE-07]    Log warning and increment metric on NATS broker disconnect                │
 │ ├─ [BE-08]    Wire CdcOutboxWorker into lifespan or archive dead code                   │
 │ ├─ [BE-09]    Refactor event handlers to asyncio.TaskGroup to stop task leaks           │
 │ ├─ [BE-10]    Allow default revocation Redis URL in development/testing environments    │
 │ ├─ [FE-02]    Synchronize Router context QueryClient with createQueryClient defaults    │
 │ ├─ [FE-03]    Harden open-redirect against /\ backslash bypass & preserve query params  │
 │ ├─ [FE-04]    Add mounted hydration guard to ClockWidget                                │
 │ ├─ [FE-05]    Gracefully reuse prebuilt WASM artifacts when wasm-pack is missing        │
 │ ├─ [FE-06]    Normalize Button startIcon to leadingIcon in settings sections            │
 │ ├─ [GO-04]    Add http://localhost (port 80 Caddy) to ws-hub ALLOWED_ORIGINS           │
 │ ├─ [GO-05]    Replace KEYS with SCAN loop in uni-cli cache clear                        │
 │ ├─ [RUST-03]  Release Python GIL during Rayon schedule conflict detection               │
 │ ├─ [RUST-04]  Add iteration and key size boundary checks to WASM PBKDF2                 │
 │ ├─ [RUST-05]  Add zeroize to frontend/rust-crypto for sensitive cryptographic buffers   │
 │ ├─ [RUST-06]  Expand cargo-deny CI scan across all 4 Rust crates                        │
 │ ├─ [RUST-07]  Add pyo3-sanitizer/fuzz to rust-fuzz CI workflow                          │
 │ ├─ [INFRA-07] Update Dockerfile HEALTHCHECK to target /health/ready                     │
 │ ├─ [INFRA-08] Add grpc_health_probe to file-processor in docker-compose.go.yml         │
 │ ├─ [INFRA-09] Add tempo-healthprobe to docker-compose.observability.yml                 │
 │ ├─ [INFRA-10] Add HPA template for gateway in Helm chart                                │
 │ ├─ [INFRA-11] Parameterize cert-manager cluster-issuer in k8s/ingress.yaml              │
 │ ├─ [SEC-05]   Align quality contract coverage floors with actual runtime capabilities   │
 │ ├─ [SEC-06]   Update Gitleaks allowlists and add egorribun branch trigger               │
 │ ├─ [SEC-07]   Audit and triage 326 entries in .secrets.baseline                         │
 │ ├─ [SEC-08]   Align pyproject.toml Bandit target to app/                                │
 │ └─ [SEC-09]   Add semver major upper bounds to 19 Python dependencies                   │
 ├─────────────────────────────────────────────────────────────────────────────────────────┤
 │ PHASE 4: P3 TECHNICAL DEBT & CODE HYGIENE                                               │
 │ ├─ [BE-11]    Add missing and fix mistyped RZ-22-01-JUSTIFIED exception tags            │
 │ ├─ [BE-12]    Decompose schemas.py, deduplicate pyproject.toml, fix AGENTS.md typo      │
 │ ├─ [FE-07]    Re-export useAuthStore from frontend/src/stores/index.ts                  │
 │ ├─ [FE-08]    Delete duplicate transition class in Layout.tsx                           │
 │ ├─ [FE-09]    Clean MockButton prop spreading in SessionsSection.closure.test.tsx       │
 │ ├─ [GO-06]    Reconcile services/AGENTS.md with gateway dependencies (remove NATS claim)│
 │ ├─ [GO-07]    Document containerized linting/race workflow in services/AGENTS.md        │
 │ ├─ [RUST-08]  Add root virtual workspace Cargo.toml                                     │
 │ ├─ [RUST-09]  Remove orphaned fuzz/fuzz_targets/fuzz_scrypt.rs at repository root       │
 │ ├─ [RUST-10]  Add zero-parse bytes/base64 HMAC export to rust-crypto                    │
 │ ├─ [RUST-11]  Remove unused serde feature and preallocate keys in rust_ext              │
 │ ├─ [INFRA-12] Gracefully handle missing database secret in weekly-cleanup.yml           │
 │ └─ [SEC-12]   Expand pre-commit mypy hook regex to cover entire app/ directory          │
 └─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 10. Programmatic Citation & Integrity Verification

The original audit recorded the following automated `file:line` citation check on 2026-09-03. Its 174/174 result and execution details are retained as historical filesystem and line-bound evidence for that audit snapshot; they do not establish current citation validity, implementation correctness or release certification:

```
Script: .agents/worker_synthesizer/verify_citations.py
Target Document: docs/audits/AUDIT_PLATFORM_FULL.md
Verification Engine: Python 3.14 AST & Filesystem Line-Bound Validator
Execution Timestamp: 2026-09-03T11:45:00Z
```

### Verification Execution Output

```
================================================================================
AUDIT CITATION VERIFICATION SUITE
================================================================================
Repository Root    : C:\Users\egorribun\Documents\university_ecosystem
Audited Document   : docs\audits\AUDIT_PLATFORM_FULL.md
Total Citations    : 174 file:line citations
Valid Citations    : 174
Failed Citations   : 0
Verification Status: 100.0% OF CITATIONS VERIFIED SUCCESSFULLY (174/174)
================================================================================
All cited files exist on the filesystem, and every specified line number
falls within the actual physical line count of the corresponding source file.
Zero application code outside docs/audits/ was modified during this audit.
================================================================================
```
