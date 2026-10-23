# University Ecosystem contributor standards

This file records repository-wide requirements. Follow the more specific instructions in each domain file:

- Backend (`app/`): [app/AGENTS.md](app/AGENTS.md) — Python, FastAPI, SQLAlchemy, DI, security and data-access rules.
- Frontend (`frontend/`): [frontend/AGENTS.md](frontend/AGENTS.md) — React, TypeScript, routing, state, validation, SSR and accessibility.
- Services (`services/`): [services/AGENTS.md](services/AGENTS.md) — Go services, Caddy, testing and host tooling.

The main components are the Python backend, React frontend, Go services, Rust extension (`native/rust_ext/`), database migrations (`alembic/`), deployment charts (`charts/`), Kubernetes manifests (`k8s/`) and quality policies (`quality/`). Domain files and the referenced policies are the source of detailed implementation rules.

## Common commands

Run these commands from the repository root.

```bash
# Python backend
uv run ruff check app/
uv run mypy --config-file pyproject.toml app/
pytest --cov=app --cov-report=term-missing

# Frontend
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run test -- --silent=true
npm --prefix frontend run build

# Go services
(cd services/gateway && go test -v -race ./...)
(cd services/ws-hub && go test -v -race ./...)
(cd services/file-processor && go test -v -race ./...)

# Repository harness
python verify_harness.py
```

Use the pinned tool versions and container guidance in the domain files and CI workflows.

## Git and review

- The active development branch is `egorribun`. Follow the existing pull-request workflow.
- Feature commits use `feat(waveXX):`, `fix(waveXX):` or `refactor(waveXX):`. Quality, security, CI, documentation and test maintenance use a non-wave scope such as `fix(quality):`, `fix(security):`, `test(contracts):` or `docs(quality):`.
- NEVER include `Co-Authored-By` trailers. Testing coverage and roadmaps are not wave work.
- Integrate through pull requests and required checks. Do not force-push or delete `egorribun`; rebase only local commits that have never been pushed. Use the admin bypass only when the owner explicitly authorizes the named pull request. Never run `scripts/merge-as-admin.ps1` to work around a failed or unavailable check; diagnose the gate or wait for recovery. Preserve all other branch-protection rules.
- After `detect-secrets` or pre-commit hooks run, re-stage `.secrets.baseline` with `git add .secrets.baseline`.

## Quality & Zero-Warning Contract

The authoritative coverage policy is [ADR-047](docs/adr/ADR-047-risk-based-quality-policy.md), implemented by [quality/quality-contract.json](quality/quality-contract.json) and [quality/ownership-mapping.json](quality/ownership-mapping.json). Keep existing thresholds and required checks, with no new warnings. A policy change requires the ADR process and explicit owner authorization.

- Tier 0 files require 100% line, statement, branch and function coverage. The only migration exception is the exact set of 131 unchanged Alembic files in the source-bound no-decrease baseline from `ac74e915`; it expires on 2026-11-13. New, modified or unmatched migrations, including PR-touched migrations, and every other Tier 0 file remain at 100% for all metrics.
- Other components keep their current contract floors until ADR-047 stage Q3. The current 100% patch-coverage requirement remains until ADR-047 stage Q3; the planned Q3 no-decrease ratchet and 90% changed-line floor are not active early.
- ADR-047 stage Q1 keeps full Python `mutmut` and frontend Stryker in nightly/manual lanes outside the MVP release gate. The Q1/Q4 source migration is integrated; every new source SHA still needs its own required-check evidence. The nightly no-regression check is planned for stage Q2; it is not implemented by adopting this policy. Verify the remaining required checks for the current MVP source. Do not move them into the release gate or spend MVP effort raising the global mutation score. Equivalent-mutant exclusions require an owner, evidence and expiry in `quality/mutation-exclusions.json`; quarantine and manual `Killed` reclassification are forbidden.
- The detect-secrets baseline contains 319 identities. The separate disposition policy contains exactly 298 finite approved path/type/digest identities in [quality/security-false-positive-dispositions.json](quality/security-false-positive-dispositions.json). Gitleaks has a separate set of exactly 25 immutable historical commit/path/rule/line fingerprints in [.gitleaksignore](.gitleaksignore). These inventories do not authorize new or changed findings.
- Matching is exact and fail-closed: changed or unmatched findings block; expired dispositions do not match. Do not add baseline entries, inline pragmas, automatic approvals, broad exclusions, wildcards, reclassifications, expiry extensions or scanner bypasses. Keep each finding in its existing category.
- Preserve all 78 required CI context/app pairs, blocking CodeQL `code_scanning` and the existing hooks. Do not remove, rename or weaken a required context or hook without the explicit owner authorization recorded in ADR-047.
- Keep final-source validation and required checks for every new source SHA. Policy records alone do not establish a passing scan, test or hosted check.

The principal source-bound checks are [tests/test_quality_contract.py](tests/test_quality_contract.py), [tests/test_verify_secrets_baseline.py](tests/test_verify_secrets_baseline.py), [tests/test_gitleaks_dispositions_contract.py](tests/test_gitleaks_dispositions_contract.py) and [tests/test_ci_check_catalog.py](tests/test_ci_check_catalog.py). Current implementation and audit state is recorded in [STATUS.md](docs/superpowers/plans/STATUS.md); audit references are indexed in [docs/audits/INDEX.md](docs/audits/INDEX.md).

## Infrastructure and cross-service security

- Use the Python backend base `python:3.14-slim-bookworm` and frontend SSR base `node:24-alpine`. Go builders use digest-pinned `golang:1.26.10-alpine`; the runtime is `distroless/static-debian12` (file processor also ships `grpc_health_probe`). Kyverno Policy 9 rejects empty and `:latest` tags; image references must use semantic versions or immutable digests.
- Preserve health checks: backend `/health/ready`; file processor `grpc_health_probe -addr=:50051`; Prometheus `/-/healthy`; Grafana `/api/health`; imgproxy `imgproxy health`; Tempo and Loki HTTP health endpoints. Temporal runs with `BIND_ON_IP=0.0.0.0` on the Compose bridge network.
- Process Kubernetes `${...}` variables through `scripts/apply_raw_k8s.sh` before `kubectl apply`. The wrapper allowlists manifests, requires variables, validates the registry and accepts `IMAGE_TAG` only as a 40-character commit SHA or semantic version. Direct `envsubst | kubectl apply` is forbidden.
- Keep `charts/university-ecosystem/values.yaml` parameterized for frontend, backend, ingress TLS, resources and HPA.
- Preserve ADR-013 dual-key JWT rotation: the old key verifies during transition and the new key signs; ExternalSecrets refresh every minute. Preserve centralized logging redaction for email and phone data (ADR-012).
- Retain path-traversal checks in backend storage, frontend SSR and the Go file processor. The gateway signs verified internal identity with HMAC-SHA256; receiving services verify `X-Internal-Signature`.

## Documentation and private material

Use [docs/README.md](docs/README.md), [docs/audits/INDEX.md](docs/audits/INDEX.md), ADR-047 and `STATUS.md` for current policy and audit detail rather than copying approval history here. Preserve Git history. Keep credential-shaped rescue material private and isolated; do not commit session logs or superseded snapshots.
