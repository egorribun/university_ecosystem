# AGENTS.md — University Ecosystem Platform Root Standards

Welcome to the **University Ecosystem Platform** repository. This document defines workspace-wide architectural invariants, quality gates, CI/CD requirements, Git workflows, and cross-cutting security baselines.

Subsystem-specific rules are hierarchically partitioned into domain `AGENTS.md` files:
- **Backend Domain (`app/`)**: [`app/AGENTS.md`](app/AGENTS.md) — Python 3.14, FastAPI, SQLAlchemy 2.0 async (`lazy="noload"`), Dishka DI, Argon2id, Outbox pattern.
- **Frontend Domain (`frontend/`)**: [`frontend/AGENTS.md`](frontend/AGENTS.md) — React 19, TypeScript strict, TanStack Router/Query, Zustand, Valibot-only, SSR, ARIA standards.
- **Go Microservices (`services/`)**: [`services/AGENTS.md`](services/AGENTS.md) — Go 1.26.4+ (CI pins 1.26.9; fuzz jobs may use 1.27.2), `ws-hub`, `gateway`, `file-processor`, `caddy` edge proxy.

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
│   │   ├── hooks/              # Custom hooks (useDebounced, useFocusTrap)
│   │   └── stores/             # Zustand state stores (useAuthStore)
│   └── AGENTS.md               # Frontend domain invariants & guidelines
├── services/                   # Go microservices & edge infrastructure
│   ├── gateway/                # Reverse proxy, JWT/JWKS validation, rate limiter, XFetch L1 cache
│   ├── ws-hub/                 # Real-time WebSocket hub (goroutine tracking, frame limits)
│   ├── file-processor/         # gRPC file processing & GraphQL engine
│   ├── caddy/                  # Caddy v2 reverse proxy & TLS termination
│   └── AGENTS.md               # Go microservices invariants & guidelines
├── native/rust_ext/            # Rust native optimizer (PyO3 FFI — schedule conflicts, partitions, audit-signature HMAC)
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
uv run ruff check app/
uv run ruff format app/
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
- Quality, security, CI, documentation, and testing maintenance are explicit
  non-wave scopes. Use a scope such as `fix(quality):`, `fix(security):`,
  `test(contracts):`, or `docs(quality):`; the `waveXX` form is reserved for
  core business-feature work.
- **STRICT PROHIBITION**: NEVER include `Co-Authored-By` trailers under any circumstances.
- **Testing & Waves Association**: Testing coverage and roadmaps do **NOT** belong to waves (waves are strictly reserved for main business features). Do not associate testing work with waves in commit messages, branch names, or logs.
- **Clean Git State**: After running `detect-secrets` or pre-commit hooks, always re-stage `.secrets.baseline` via `git add .secrets.baseline`.

---

## 4. Quality & Zero-Warning Contract

All contributions must comply with `quality/quality-contract.json` and
[ADR-047](docs/adr/ADR-047-risk-based-quality-policy.md) (risk-based quality policy
for the MVP release; the current plan is
[`docs/superpowers/plans/MVP_MASTER_PLAN.md`](docs/superpowers/plans/MVP_MASTER_PLAN.md)):

1. **Coverage**:
   - Tier 0 files (`tier0_rules` in `quality/ownership-mapping.json`) require 100% line,
     statement, branch and function coverage, except for the exact 131 unchanged
     Alembic files in the 2026-10-14 owner-approved, source-bound no-decrease baseline from
     commit ac74e915; the approved contract
     retains its per-file evidence and provenance. The exception expires
     2026-11-13. New, modified, or unmatched migrations (including PR-touched
     migrations), and every other Tier 0 file remain at 100% for all metrics.
     See [ADR-047](docs/adr/ADR-047-risk-based-quality-policy.md).
   - Other components keep their current contract floors until ADR-047 stage Q3 replaces
     them with a no-decrease ratchet and a 90% patch floor for changed lines.
2. **Mutation Testing**:
   - ADR-047 stage Q1 keeps full `mutmut` (Python backend) and Stryker (TypeScript frontend)
     in nightly/manual lanes outside the MVP release gate. The Q1/Q4 source migration is
     integrated; every new source SHA still needs its own required-check evidence.
     Do not spend MVP effort on raising the global mutation score.
   - The nightly no-regression check is planned for stage Q2; it is not implemented by
     adopting this policy. Keep the integrated Q1/Q4 migration in force and verify
     the remaining required checks for the current MVP source.
   - A proven equivalent mutant goes to `quality/mutation-exclusions.json` with owner,
     evidence and an expiry date; quarantine and manual `Killed` reclassification stay
     forbidden.
3. **Pre-Commit Enforcement**:
   - `ruff` (v0.14.14 pinned — prevents syntax regressions).
   - `detect-secrets` scans against `.secrets.baseline`; ADR-047 records the
     original finite owner approval for exactly 85 path/type/digest identities
     (83 verified public or synthetic findings and two linked fixtures limited
     to the internal synthetic demo). A separate 2026-10-12 UTC decision
     approved exactly one additional public NATS image digest identity at
     `tests/test_workflow_fail_closed_contracts.py:43`. The original 85 identities
     remain unchanged, for 86 exact policy identities total. On 2026-10-13 UTC,
     the owner separately approved exactly 27 additional identities (12 public
     integrity digests and 15 independent contract fingerprints), bringing the
     approved scope to 113 exact identities at that decision, preserving the prior 86.
     The owner reaffirmed this scope on 2026-10-13. The baseline remains at 319
     identities and the 78 required contexts remain unchanged.
     That decision covered only its exact 27 additions; changed or unmatched
     identities remain fail-closed. It authorized no baseline entry, inline
     pragma, broad scanner exclusion, bypass, or context change. Final-source
     validation remains required.
     Separately, the owner approved one exact Caddy image-digest disposition;
     this distinct decision extended the approved scope from 113 to 114.
     Implementation is tracked in [MVP STATUS](docs/superpowers/plans/STATUS.md). On 2026-10-13
     UTC, the owner also approved exactly four additional exact-match
     dispositions: two synthetic fake Redis `Secret Keyword` findings in
     `tests/test_chat_command_failure_paths.py`, one public NATS image digest,
     and one public imgproxy image digest in
     `tests/test_docker_startup_contracts.py`. These records are scoped to
     exact path, detector type, and finding digest and expire on 2027-01-10;
     changed or unmatched identities remain fail-closed. The approved scope is
     118 exact identities: 113 prior identities + the separately approved
     Caddy identity + four newly approved identities. This changes none of the
     319 baseline identities, 78 required contexts, CodeQL rule, or hooks.
     Approval does not replace policy integration, tests, hosted checks, or
     final-source validation.

     On 2026-10-14 UTC, the owner separately approved exactly 17 additional
     exact-match identities, extending the approved scope from 118 to 135 while
     preserving all prior 118 records. They are the exact path, detector-type, and
     finding-digest tuples in quality/security-false-positive-dispositions.json: 15
     public_integrity_digest / Hex High Entropy String findings at
     quality/quality-contract.json and 2 at
     scripts/quality/validate_quality_contract.py. Each carries reviewed_on
     2026-10-14 and expires_on 2027-01-10. No other identity, baseline entry, inline
     pragma, broad scanner exclusion, bypass, or context change is authorized. The
     baseline remains 319 identities, the 78 required contexts, blocking CodeQL
     rule, and hooks remain unchanged. Approval does not replace policy integration,
     tests, hosted checks, or final-source validation.

     On 2026-10-15 UTC, the owner approved exactly 90 additional exact-match
     dispositions, extending the historically approved 135 identities to exactly
     225. The exact repository-path, detector-type, and finding-digest tuples are
     recorded in quality/security-false-positive-dispositions.json: 54
     public_integrity_digest, 27 independent_contract_fingerprint, and 9
     external_kubernetes_secret_reference identities. The 27 v4 fingerprints extend
     the existing independent_contract_fingerprint category; the external Kubernetes
     reference is the sole new category. Each carries reviewed_on 2026-10-15 and
     expires_on 2027-01-10; the previous 135 records remain unchanged. Changed or
     unmatched identities remain fail-closed. This authorizes no cross-category
     reclassification, other identity, baseline entry, inline pragma, broad scanner
     exclusion, bypass, or context change. The baseline stays at 319 identities and
     78 required contexts; blocking CodeQL and hooks stay unchanged. Validator
     integration, tests, hosted checks, and final-source validation remain separate
     requirements.

     On 2026-10-16 Europe/Istanbul (2026-10-15 UTC), the owner approved
     exactly 18 additional exact-match dispositions, extending the historically
     approved 225 identities to 243. The approved scope is limited to exact
     repository-path, detector-type, and finding-digest tuples: 9 identities in
     the existing external_kubernetes_secret_reference category, 3 in the
     existing ci_test_contract_sentinel category across two new path/type pairs,
     and 6 in the new source_contract_identifier category across five finite
     path/type pairs and requiring both fixed semantic evidence markers. Each
     record carries reviewed_on 2026-10-15 and expires_on 2027-01-10; the prior
     225 records remain unchanged. No raw finding digests are repeated here.
     Changed or unmatched identities remain fail-closed. This approval authorizes
     no category-wide match, automatic identity approval, expiry bypass,
     cross-category reclassification, other identity, baseline entry, inline
     pragma, broad scanner exclusion, bypass, or context change. The finite
     131-file migration baseline is untouched. The baseline remains at 319
     identities, 78 required contexts, blocking CodeQL, and unchanged hooks.
     Authorization does not establish integration, test, scan, or hosted-check
     results; each remains an independent verification requirement.

     On 2026-10-16 Europe/Istanbul (2026-10-15 UTC), the owner separately
     approved exactly seven additional exact-match identities in the existing
     `external_kubernetes_secret_reference` category, extending the approved
     scope from 243 to 250 while preserving the prior 243 records. Each is an
     exact path/type/finding-digest identity with `reviewed_on` 2026-10-15 and
     `expires_on` 2027-01-10; no raw digests are repeated here. This decision
     authorizes no other identity, category-wide match, reclassification, baseline
     entry, inline pragma, exclusion, bypass, or context change. The 21 inline
     detect-secrets pragma comments were removed; the pre-removal 4,408/483/0
     scan is historical and superseded by the unfiltered 4,408/490/7 scan against
     the then-current 243-record overlay. A private conditional 250-overlay scan
     reported 0 unmatched against the candidate overlay. The owner-approved
     250-record policy support is now integrated in source; final-source validation
     and hosted checks remain required for each published source. The baseline remains 319 identities and all 78
     required contexts, blocking CodeQL, and hooks remain unchanged. See the
     [dated audit supplement](docs/audits/AUDIT-2026-10.md#post-pragma-removal-scan-and-seven-identity-owner-update-2026-10-16).

   - `gitleaks` (repo secret scanning).
   - `bandit` (Python security static analysis).
   - `mypy` (strict type-checking for backend auth, services, api, core, repositories, graphql).
   - `no-python2-except` (rejects `except A, B:` comma syntax in favor of `except (A, B):`).
   - `actionlint` (validates GitHub Actions workflow syntax).
   - `semgrep-sast` (Static Application Security Testing).
   - `renovate-config-validator` (validates dependency update configurations).

   The additional `trivy-fs-scan` hook (`trivyfs-docker`) runs only at the manual
   stage. Hosted Trivy image scans are configured separately in CI.

---

## 5. Merge Policy

- Use the ordinary pull-request flow and required checks for changes to `main`.
- **Solo-maintainer mode** (owner decision 2026-10-12): the owner is the only collaborator, so the `main` ruleset does not require a CODEOWNERS approval; the required status checks and the CodeQL `code_scanning` rule are the merge control. CODEOWNERS stays for reviewer auto-assignment.
- **Break-glass bypass**: the Admin bypass in ruleset `8335285` works only through a pull request (`bypass_mode: pull_request`). Use it only when the owner explicitly authorizes it in the conversation for named pull requests. Never initiate a bypass on your own. Force-push and general changes to branch protection remain outside the approved MVP release workflow. Do not invoke `scripts/merge-as-admin.ps1` to work around a failed or unavailable check; diagnose the gate or wait for the external service to recover.
- Ruleset `egorribun-protect` forbids force-push and deletion of `egorribun`. Integrate remote work with a merge, or rebase only local commits that were never pushed.
- On 2026-10-09 the owner explicitly authorized removing the 14 Q1/Q4 required check contexts listed in [ADR-047](docs/adr/ADR-047-risk-based-quality-policy.md#authorized-required-context-removals), from main ruleset `8335285`, after the corresponding CI diff is complete, reviewed and checked. The owner subsequently approved removing exactly one additional context, `Security Audit / Semgrep SAST`, after the reviewed scanner de-duplication change passes its checks. CodeQL remains blocking and Semgrep remains in pre-commit. Preserve every other rule and context; this permission does not authorize bypass, further context removals, or early promotion of advisory live smoke. The owner-approved 2026-10-12 ruleset change (two compatibility contexts removed, four security contexts and a CodeQL `code_scanning` rule added) is recorded in ADR-047.

---

## 6. Docker, Kubernetes & Infrastructure Standards

- **Base Images**:
  - Python backend: `python:3.14-slim-bookworm`
  - Frontend SSR: `node:24-alpine` (running on port 3000)
  - Go microservices: digest-pinned `golang:1.26.9-alpine` builders and a `distroless/static-debian12` runtime; `file-processor` also ships `grpc_health_probe`
- **Healthcheck Standards**:
  - Backend: `/health/ready` (FastAPI readiness probe)
  - File processor: `grpc_health_probe -addr=:50051`
  - Prometheus: `/-/healthy`
  - Grafana: `/api/health`
  - Imgproxy: `imgproxy health`
  - Tempo / Loki: HTTP health endpoints
  - Temporal server (`temporalio/server`): `BIND_ON_IP=0.0.0.0` on the Compose bridge network
- **Kubernetes Variable Interpolation**:
  - `${FRONTEND_HOST}`, `${API_HOST}`, `${TLS_SECRET_NAME}`, `${VAULT_URL}`, `${IMAGE_REGISTRY}` and `${IMAGE_TAG}` must be processed with `envsubst` through `scripts/apply_raw_k8s.sh` before executing `kubectl apply` (TD-31-02, TD-31-03). The wrapper allowlists supporting manifests, requires all variables, validates the registry path, and accepts `IMAGE_TAG` only as a 40-character commit SHA or semantic version. Direct raw `envsubst | kubectl apply` is forbidden.
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
  - Backend: `StaticFSStorage._resolve_validated_path()` checks symlinks and `is_relative_to(base_dir)`.
  - Frontend SSR: `server-prod.mjs` validates `filePath.startsWith(staticRoot)`.
  - Go File Processor: `sourceKey` and `destKey` sanitized against directory traversal.
- **Cross-Service Identity Assertion**:
  - Edge gateway signs verified user identity into `X-Internal-Signature` via HMAC-SHA256. Backend services verify this signature on internal RPCs.

---

## 8. Subagent Profiles & Progressive Context

The developer harness defines 5 specialized subagents configured in `.agents/subagents.json`:
- `lead_architect` (`inherit` mode): System design, ADR governance, Dishka DI validation.
- `tdd_developer` (`share` mode): RED-GREEN-REFACTOR implementation in explicitly assigned files.
- `qa_e2e_tester` (`share` mode): Browser E2E, Playwright, ARIA compliance, SSR hydration testing.
- `security_auditor` (`inherit` mode): Argon2id, RS256 JWKS, path traversal, SAST, secret leak prevention.
- `perf_optimizer` (`inherit` mode): EXPLAIN ANALYZE, TieredCache tuning, frontend bundle budget (<500 KB).

These profiles are guidance, not active processes or enforced timers. The root
assigns at most three GPT-6 Luna Max agents in the current `egorribun` checkout,
with disjoint file ownership and a 30-minute checkpoint budget; root owns Git.
The lifecycle scripts use the Antigravity protocol. They are available through
the explicit runner and are not automatically registered as Codex hooks.

---

## 9. Audit Trail & Documentation Index

The current documentation and audit-retention policy are indexed in [`docs/README.md`](docs/README.md) and [`docs/audits/INDEX.md`](docs/audits/INDEX.md). Legacy archives have been reconciled against the active MVP plan and removed from the working tree after transferring applicable requirements. Preserve Git history; keep the verified rescue bundle private and isolated because it contains credential-shaped history. Do not add session logs or superseded snapshots to the current indexes.
