# AGENTS.md — University Ecosystem Platform Root Standards

Welcome to the **University Ecosystem Platform** repository. This document defines workspace-wide architectural invariants, quality gates, CI/CD requirements, Git workflows, and cross-cutting security baselines.

Subsystem-specific rules are hierarchically partitioned into domain `AGENTS.md` files:
- **Backend Domain (`app/`)**: [`app/AGENTS.md`](app/AGENTS.md) — Python 3.14, FastAPI, SQLAlchemy 2.0 async (`lazy="noload"`), Dishka DI, Argon2id, Outbox pattern.
- **Frontend Domain (`frontend/`)**: [`frontend/AGENTS.md`](frontend/AGENTS.md) — React 19, TypeScript strict, TanStack Router/Query, Zustand, Valibot-only, SSR, ARIA standards.
- **Go Microservices (`services/`)**: [`services/AGENTS.md`](services/AGENTS.md) — Go 1.22+, `ws-hub`, `gateway`, `file-processor`, `caddy` edge proxy.

---

## 1. Workspace Architecture & Subsystem Layout

```
university_ecosystem/
├── app/                        # Python 3.14 backend (FastAPI + SQLAlchemy 2.0 + Dishka DI + Pydantic v2)
│   ├── api/                    # REST routers & endpoint handlers
│   ├── core/                   # Config (_NamespaceView composition), DI providers, security, events
│   ├── models/                 # SQLAlchemy 2.0 ORM models (mandatory lazy="noload")
│   ├── repositories/           # Async database repositories
│   ├── schemas/                # Pydantic v2 DTOs and validation schemas
│   ├── services/               # Narrow business logic services
│   └── AGENTS.md               # Backend domain invariants & guidelines
├── frontend/                   # React 19 frontend (Vite 8 / Rolldown + TanStack Router + Query + Zustand)
│   ├── src/                    # Application source code
│   │   ├── components/         # Reusable UI & design system primitives (ARIA compliant)
│   │   ├── features/           # Feature modules, routes, and Valibot schemas
│   │   ├── hooks/              # Custom hooks (useDebounced, useReducedMotion)
│   │   └── stores/             # Zustand state stores (useAuthStore)
│   └── AGENTS.md               # Frontend domain invariants & guidelines
├── services/                   # Go microservices & edge infrastructure
│   ├── gateway/                # Reverse proxy, JWT/JWKS validation, rate limiter, XFetch L1 cache
│   ├── ws-hub/                 # Real-time WebSocket hub (goroutine tracking, frame limits)
│   ├── file-processor/         # gRPC file processing & GraphQL engine
│   ├── caddy/                  # Caddy v2 reverse proxy & TLS termination
│   └── AGENTS.md               # Go microservices invariants & guidelines
├── native/rust_ext/            # Rust native optimizer (PyO3 FFI — schedule conflicts, HMAC, WASM sanitizer)
├── alembic/                    # Database migration history
├── charts/                     # Helm deployment charts (university-ecosystem)
├── k8s/                        # Kubernetes manifests (OpenFeature flagd, external secrets, Kyverno policies)
├── quality/                    # Quality contract & test manifests (quality-contract.json)
└── verify_harness.py           # Automated developer harness test suite
```

---

## 2. Workspace Commands

### Backend (Python 3.14)
```bash
# Linting & Formatting
python -m ruff check app/
python -m ruff format app/
python -m py_compile app/main.py

# Type Checking & Custom AST Checks
python -m mypy --config-file pyproject.toml app/
python scripts/custom_ast_linter.py app/
python scripts/check_no_python2_except.py

# Tests & Coverage
pytest --cov=app --cov-report=term-missing
```

### Frontend (React 19 / TypeScript)
```bash
# Type Checking & Linting
cd frontend && npx tsc --noEmit
cd frontend && npm run lint

# Tests & Build
cd frontend && npm run test -- --silent=true
cd frontend && npm run build
```

### Go Microservices
```bash
# Linting
cd services/gateway && golangci-lint run
cd services/ws-hub && golangci-lint run
cd services/file-processor && golangci-lint run

# Tests
cd services/gateway && go test -v -race ./...
cd services/ws-hub && go test -v -race ./...
cd services/file-processor && go test -v -race ./...
```

### Harness & Quality Verification
```bash
python verify_harness.py
```

---

## 3. Git & Commit Invariants

- **Active Branch**: `egorribun` (all feature and maintenance work branches off and targets `egorribun`).
- **Commit Message Format**:
  - `feat(waveXX): description`
  - `fix(waveXX): description`
  - `refactor(waveXX): description`
- **STRICT PROHIBITION**: **NEVER** include a `Co-Authored-By` trailer under any circumstances.
- **Testing & Waves Association**: Testing coverage and roadmaps do **NOT** belong to waves (waves are strictly reserved for main business features). Do not associate testing work with waves in commit messages, branch names, or logs.
- **Clean Git State**: After running `detect-secrets` or pre-commit hooks, always re-stage `.secrets.baseline` via `git add .secrets.baseline`.

---

## 4. Quality & Zero-Warning Contract

All contributions must strictly comply with `quality/quality-contract.json`:

1. **100% Coverage Mandate**:
   - 100% Line Coverage
   - 100% Statement Coverage
   - 100% Branch Coverage
   - 100% Function Coverage
   - Tier 0 core modules require 100% test coverage across all dimensions.
2. **Mutation Testing**:
   - 100% viable mutant score required (`mutmut` for Python backend, `Stryker` for TypeScript frontend).
3. **Pre-Commit Enforcement**:
   - `ruff` (v0.14.14 pinned — prevents syntax regressions).
   - `detect-secrets` (scans for credentials against `.secrets.baseline`).
   - `gitleaks` (repo secret scanning).
   - `bandit` (Python security static analysis).
   - `mypy` (strict type-checking for backend auth, services, api, core, repositories, graphql).
   - `no-python2-except` (rejects `except A, B:` comma syntax in favor of `except (A, B):`).
   - `actionlint` (validates GitHub Actions workflow syntax).
   - `semgrep-sast` (Static Application Security Testing).
   - `renovate-config-validator` (validates dependency update configurations).

---

## 5. Bypass Policy

GitHub admin bypass on the main-branch ruleset is intentionally left enabled for this single-maintainer repository. The accepted admin bypass risk is that a false-positive gate or third-party outage can be bypassed to avoid a deadlock.
- Any bypass merge **must** record an explicit bypass reason in the PR description or merge commit message.

---

## 6. Docker, Kubernetes & Infrastructure Standards

- **Base Images**:
  - Python backend: `python:3.14-slim-bookworm`
  - Frontend SSR: `node:24-alpine` (running on port 3000)
  - Go microservices: `golang:1.22-alpine` / scratch runtime with `grpc_health_probe`
- **Healthcheck Standards**:
  - Backend: `/health/ready` (FastAPI readiness probe)
  - File processor: `grpc_health_probe -addr=:50051`
  - Prometheus: `/-/healthy`
  - Grafana: `/api/health`
  - Imgproxy: `imgproxy health`
  - Tempo / Loki: HTTP health endpoints
  - Temporal dev server: binds `0.0.0.0` bridge network
- **Kubernetes Variable Interpolation**:
  - `${FRONTEND_HOST}`, `${API_HOST}`, `${TLS_SECRET_NAME}`, `${VAULT_URL}` must be processed with `envsubst` before executing `kubectl apply` (TD-31-02, TD-31-03).
- **Kyverno Security Policies**:
  - **Policy 9**: Rejects any deployment with empty or `:latest` image tags. All image references must use semantic versions or immutable image digests.
- **Helm Configuration**:
  - `charts/university-ecosystem/values.yaml` must remain fully parameterized for frontend, backend, ingress TLS, resources, and HPA autoscaling (MOD-30-04).

---

## 7. Cross-Cutting Security Baseline

- **Three-Tier Secret Rotation (ADR-013)**:
  - Supports dual-key JWT rotation windows (old key remains valid for verification during transition; new key signs outbound tokens).
  - ExternalSecrets refresh interval: `1m`.
- **Centralized Logging & Redaction (ADR-012)**:
  - Grafana Loki + Fluent Bit aggregation.
  - Structlog processor `_redact_pii` automatically masks email addresses (>=2-char TLD) and phone numbers across all backend logs.
- **Path Traversal Defense**:
  - Backend: `StaticFSStorage._validate_resolved_path()` checks symlinks and `is_relative_to(base_dir)`.
  - Frontend SSR: `server-prod.mjs` validates `filePath.startsWith(staticRoot)`.
  - Go File Processor: `sourceKey` and `destKey` sanitized against directory traversal.
- **Cross-Service Identity Assertion**:
  - Edge gateway signs verified user identity into `X-Internal-Signature` via HMAC-SHA256. Backend services verify this signature on internal RPCs.

---

## 8. Subagent Profiles & Progressive Context

The developer harness defines 5 specialized subagents configured in `.agents/subagents.json`:
- `lead_architect` (`inherit` mode): System design, ADR governance, Dishka DI validation.
- `tdd_developer` (`branch` mode): Isolated RED-GREEN-REFACTOR test-driven implementation.
- `qa_e2e_tester` (`share` mode): Browser E2E, Playwright, ARIA compliance, SSR hydration testing.
- `security_auditor` (`inherit` mode): Argon2id, RS256 JWKS, path traversal, SAST, secret leak prevention.
- `perf_optimizer` (`inherit` mode): EXPLAIN ANALYZE, TieredCache tuning, frontend bundle budget (<500 KB).

---

## 9. Audit Trail & Wave History

Canonical audit index and active wave reports are maintained in [`docs/audits/INDEX.md`](docs/audits/INDEX.md).
- Active wave audits: [`AUDIT_PR1249.md`](docs/audits/AUDIT_PR1249.md), [`AUDIT_WAVE211.md`](docs/audits/AUDIT_WAVE211.md), [`AUDIT_WAVE210.md`](docs/audits/AUDIT_WAVE210.md).
- Archived wave audits: `docs/audits/archive/`.
