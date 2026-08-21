# Project: University Ecosystem Platform — PR #1249 CI/CD Remediation & Zero-Debt Foundation

## Architecture
The University Ecosystem Platform is an enterprise, multi-stack ecosystem spanning:
- **Backend (`app/`)**: Python 3.14, FastAPI, SQLAlchemy 2.0 async (mandatory `lazy="noload"`), Dishka DI, Argon2id authentication, RS256 JWKS, outbox pattern, structlog PII redaction.
- **Frontend (`frontend/`)**: React 19, TypeScript strict, Vite SSR, TanStack Router & Query, Zustand, Valibot-only schemas, ARIA accessibility, Playwright E2E testing.
- **Go Microservices (`services/`)**: Go 1.22+, `gateway` (reverse proxy, JWT/JWKS, rate limiter, XFetch L1 cache), `ws-hub` (real-time WebSocket broadcasting), `file-processor` (gRPC/GraphQL file engine), `caddy` (edge proxy).
- **Native Optimizer (`native/rust_ext/`)**: Rust PyO3 FFI schedule conflict & HMAC acceleration.
- **Harness & Infrastructure (`.agents/`, `charts/`, `k8s/`)**: Antigravity lifecycle hooks, safety gates, subagent profiles, Helm v3 charts, Kyverno policy compliance.

```
university_ecosystem/
├── app/                        # Python 3.14 FastAPI backend
├── frontend/                   # React 19 / TypeScript frontend
├── services/                   # Go microservices (gateway, ws-hub, file-processor, caddy)
├── native/rust_ext/            # Rust PyO3 FFI extensions
├── charts/                     # Helm deployment charts
├── k8s/                        # Kubernetes manifests & Kyverno policies
├── .agents/                    # Antigravity developer harness & subagents
├── quality/                    # Quality contract (100% coverage, 0 viable mutants)
└── verify_harness.py           # Developer harness test suite
```

---

## Feature Inventory

| # | Feature | Description | Milestone | Source |
|---|---|---|---|---|
| F1 | Dynamic Skip Tracking Annotation | Add tracking ticket and owner to dynamic skip in `tests/test_container_image_pinning.py` | M1 | survey_backend_ci |
| F2 | Auth Cookie Security Mode Transport | Extract `_csrf_anon_nonce` from response Set-Cookie headers in `tests/test_auth_cookie_flow.py` | M1 | survey_backend_ci |
| F3 | Helm Dependency Check Bypass | Add `--skip-dependency-check` to Helm template invocations in `tests/test_docker_startup_contracts.py` | M1 | survey_backend_ci |
| F4 | Mutmut Isolation Repo Root Discovery | Robust `_find_repo_root()` in contract tests resolving actual repo root outside `mutants/` | M1 | survey_backend_ci |
| F5 | Pre-Tool Safety Regex Hardening | Add `-InFile` exfiltration pattern to `.agents/hooks/pre_tool_safety.py` | M2 | survey_services_infra |
| F6 | Persistent Harness Asset Tracking | Refactor `.gitignore` to track permanent `.agents/` assets and ignore transient caches | M2 | survey_services_infra |
| F7 | Documentation Parity & Link Accuracy | Synchronize `README.ru.md` with `README.md`, fix operational paths in `docs/DEPLOY*.md`, `ADR-008` | M3 | survey_frontend |
| F8 | WS-Hub Concurrency & Benchmark Tuning | Optimize memory allocations and locks in `services/ws-hub` to eliminate benchmark regression | M4 | survey_backend_ci |
| F9 | Playwright E2E Matrix Stabilization | Resolve timeouts across Chromium, Firefox, WebKit, and Mobile WebKit test shards | M5 | survey_backend_ci |
| F10 | Full PR #1249 CI/CD Green Gate & Audit | Verify all 14 CI/CD check runs, `verify_harness.py`, git commit & push to `egorribun` | M6 | ORIGINAL_REQUEST |

---

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|---|---|---|---|
| M1 | CI/CD Quality Gates & Test Contracts | F1, F2, F3, F4: Anti-pattern skip annotation, auth cookie headers, Helm flags, mutmut root helper | none | DONE |
| M2 | Developer Harness & Safety Gate Hardening | F5, F6: Pre-tool safety regex (`-InFile`), `.gitignore` harness asset tracking | none | DONE |
| M3 | Documentation Synchronization & Audit | F7: `README.ru.md` parity, `docs/DEPLOY*.md`, `ADR-008`, `k8s/README.md`, `API_EXAMPLES.md` | none | DONE |
| M4 | WS-Hub Performance Optimization | F8: `services/ws-hub` memory & lock optimization to satisfy benchmark gate ratio < 1.10 | none | DONE |
| M5 | Frontend Playwright E2E Stabilization | F9: Playwright test timeout adjustments, mockApi reliability, SSR cold-start stabilization | M1 | DONE |
| M6 | Final Verification, Commit & PR Delivery | F10: `verify_harness.py`, all 14 CI/CD checks green, forensic audit, git commit to `egorribun` | M1, M2, M3, M4, M5 | DONE |

---

## Interface Contracts

### 1. Backend Test Contracts
- `tests/test_container_image_pinning.py`: `pytest.skip(..., allow_module_level=True)` MUST include `# QUALITY-123 @egorribun`.
- `tests/test_auth_cookie_flow.py`: `_csrf_anon_nonce` MUST be parsed from `response.headers.get_list("set-cookie")` without relying on HTTP cookie jar retention.
- `tests/test_docker_startup_contracts.py` & `tests/test_quality_workflow_contract.py`: `ROOT` / `REPOSITORY_ROOT` MUST resolve upwards ignoring any parent directory named `mutants`.

### 2. Harness Safety Contract
- `.agents/hooks/pre_tool_safety.py`: Regex pattern MUST match `Invoke-WebRequest ... -InFile <secret_file>` and block secret exfiltration.
- `.gitignore`: Unignore `!.agents/hooks.json`, `!.agents/hooks/`, `!.agents/subagents.json`, `!.agents/subagents/`, `!.agents/skills/`, `!.agents/ORIGINAL_REQUEST.md`, `!verify_harness.py`, `!docs/mcp/`.

### 3. Documentation Parity Contract
- `README.ru.md` MUST include Revocation Valkey topology node/edges, `start-docker.ps1` reference, port 80/8083 access points, and ADR-001—ADR-032 scope.

---

## Code Layout

- `tests/test_container_image_pinning.py`
- `tests/test_auth_cookie_flow.py`
- `tests/test_docker_startup_contracts.py`
- `tests/test_quality_workflow_contract.py`
- `.agents/hooks/pre_tool_safety.py`
- `.gitignore`
- `README.ru.md`
- `docs/DEPLOY.md`
- `docs/DEPLOY.en.md`
- `docs/adr/ADR-008-spicedb-rebac.md`
- `docs/API_EXAMPLES.md`
- `frontend/src/styles/tokens/README.md`
- `k8s/README.md`
- `services/ws-hub/`
- `frontend/tests/e2e/`
- `verify_harness.py`
