# Quality Closure and MVP Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Every task ends with fresh verification evidence; do not claim completion from an old artifact.

**Goal:** Bring the current `egorribun` checkout to a reproducible, zero-warning MVP foundation whose complete quality evidence is generated for the exact commit being verified and satisfies the repository quality contract.

**Architecture:** Treat the repository as one quality system with independently verifiable Python, React/TypeScript, Go, Rust, infrastructure, workflow, security, Docker, and developer-harness gates. Each stack owns native tests and coverage; a single provenance-bound quality manifest aggregates the results and fails closed when a report is missing, stale, partial, or generated for another commit.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy 2 async, Dishka, pytest/coverage.py/mutmut; React 19, TypeScript 7, Vite 8/Rolldown, Vitest/Stryker, Playwright; Go 1.22+, race detector, golangci-lint; Rust/cargo-llvm-cov/nightly branch instrumentation; Docker Compose, Kubernetes/Helm, GitHub Actions, Semgrep, Bandit, gitleaks, detect-secrets, Codecov.

**Spec:** [`AGENTS.md`](../../../AGENTS.md), [`app/AGENTS.md`](../../../app/AGENTS.md), [`frontend/AGENTS.md`](../../../frontend/AGENTS.md), [`services/AGENTS.md`](../../../services/AGENTS.md), [`quality/quality-contract.json`](../../../quality/quality-contract.json), [`quality/coverage-manifest.schema.json`](../../../quality/coverage-manifest.schema.json).

## Global Constraints

- Work only from the intended commit SHA; every coverage, mutation, SBOM, and quality-manifest artifact must identify that SHA.
- Preserve the active branch `egorribun`; use `feat(...)`, `fix(...)`, or `refactor(...)` commit prefixes and never add a `Co-Authored-By` trailer.
- Keep `quality/quality-contract.json` as the acceptance authority: policy patch coverage `100`, viable mutation score `100`, required PR matrix enabled, and no exclusions or quarantines.
- Honor the domain invariants: SQLAlchemy relationships use `lazy="noload"`; Python defaults have both `default` and `server_default`; Argon2id/RS256/JWKS rules remain intact; frontend uses Valibot only; Go services pass race detection; Rust FFI and sanitizer boundaries remain fail-closed.
- Do not convert an incomplete, targeted, stale, or skipped run into a green artifact. Missing evidence is a failure until the corresponding gate is executed or an explicitly documented alternative gate is validated.
- Keep generated caches and dependency trees outside the tracked evidence set. Never delete user work or stash data as part of quality cleanup.

## Current Baseline and Explicit Blockers

The last measured checkout had a clean worktree, 4,434 tracked files, and 888,387 physical text lines. The available reports are mixed snapshots rather than one current run:

| Area | Evidence currently available | Required closure |
|---|---|---|
| Provenance | `quality-manifest.json` was generated for SHA `39233f...`, not the current HEAD | Regenerate every report and the manifest for the exact HEAD under test; reject SHA mismatch |
| Python coverage | `coverage.xml`: 28,680/28,759 lines and 6,891/6,908 branches | Fresh run must reach the configured 100% lines/branches floor; record and cover every remaining line/branch |
| Python mutation | 20 killed, 2 timeout, 0 survived in the saved snapshot | Complete all selected mutants with zero timeout/survived/no-test/unclassified outcomes; `check_mutation_score.py --min-score 100` must pass |
| Frontend type safety | `npm run typecheck` fails in `frontend/tsconfig.json` with TS5102/TS5090 because TypeScript 7 removed `baseUrl` semantics | Repair path configuration, then resolve all compiler errors until `tsc --noEmit` exits 0 |
| Frontend coverage | Full saved report is below 100%; the newest local report is a targeted partial run (`0.99%` statements) | Run the complete shard matrix, merge it, and produce 100% statements/branches/functions/lines for the declared scope |
| Rust crypto | Lines/functions are 100%, but branch evidence is `0/0` and the normalizer marks the component failed | Either measure real branches and cover them, or implement/test a fail-closed zero-branch derivation that reports 100% only when source analysis proves there are no branches |
| Go | Native statement profiles are 100%; branch/function counters are not native Go metrics | Keep statement gate at 100%, document derived line metrics, and ensure the manifest does not silently treat unsupported metrics as measured |
| Infrastructure/scripts/workflows | Manifest marks these reports missing and requires an alternative gate | Run and archive their declared validators; make the alternative gate explicit and machine-checked |
| API contract | Schemathesis is a required four-shard gate | Run all four shards plus the aggregate job; cancelled or missing shards are failures |
| Docker | `start-docker.ps1 -Build` is the user-facing path | Validate every compose variant, backend readiness, dependency health, and startup logs from a clean build |
| Harness/docs | `verify_harness.py` covers hooks, safety gates, subagents, and MCP configuration | Run repo-only harness, add regression coverage for every discovered failure, and reconcile active docs with actual workflows |

## Definition of Done

- [ ] `git status --short` is empty after the final commit, and the final report names the verified commit SHA.
- [ ] All required artifacts listed in `quality/quality-contract.json` exist, are non-empty, are schema-valid, and carry the same commit SHA.
- [ ] `artifacts/coverage/quality-manifest.json` reports `validation.valid: true`; every component is `passed`; `missing_reports` is empty; Tier-0 is measured across all four dimensions.
- [ ] Python meets its component floors and the global Tier-0 floor; no unclassified coverage gap remains.
- [ ] Frontend `tsc`, lint, unit/integration tests, WASM tests, build, SSR smoke, accessibility checks, and declared mutation scope all pass.
- [ ] Go gateway, ws-hub, file-processor, and shared packages pass formatting, lint, vet/static analysis, `go test -race ./...`, and 100% statement coverage.
- [ ] Rust native, PyO3 sanitizer, WASM sanitizer, and crypto crates pass tests, line/function/branch gates, and security/audit checks.
- [ ] Schemathesis, OpenAPI drift, contract tests, E2E, Docker health probes, SBOM/provenance, secret scans, SAST, and dependency policy gates are green.
- [ ] No workflow is accidentally skipped; every skip is explained by its `if:` condition and is not a required gate for the event.
- [ ] `verify_harness.py --repo-only` passes; its tests cover all harness behavior actually relied on by CI.
- [ ] Active documentation contains one current roadmap/quality closure record; obsolete handoffs and reports are archived only after link/reference checks.

---

## Task 1: Freeze the baseline and make evidence provenance fail closed

**Files:**
- Inspect/modify: `scripts/quality/normalize_coverage_reports.py`
- Inspect/modify: `scripts/quality/validate_quality_contract.py`
- Inspect/modify: `quality/coverage-manifest.schema.json`
- Test: `tests/test_coverage_manifest.py`, `tests/test_quality_contract.py`
- Workflow: `.github/workflows/ci.yml`, `.github/workflows/nightly-full-gate.yml`, `.github/workflows/reusable-backend-tests.yml`, `.github/workflows/reusable-frontend-tests.yml`

**Steps:**

- [ ] Record `git rev-parse HEAD`, `git status --short`, `git diff --check`, and the selected toolchain versions before starting any stack run.
- [ ] Make the normalizer include `commit_sha`, generation time, source-root mapping, report hashes, and component status for every report.
- [ ] Add a validator test that changes the manifest SHA and proves validation fails; add a second test for a missing, empty, or partial report.
- [ ] Ensure the CI aggregate downloads only artifacts from the current workflow run and never reuses workspace coverage left by a prior run.
- [ ] Ensure the validator distinguishes `unsupported` from `passed`; unsupported metrics may be accepted only where the component contract explicitly sets that dimension to zero, never for Tier-0.
- [ ] Run:

```powershell
git diff --check
uv run pytest tests/test_coverage_manifest.py tests/test_quality_contract.py -q
uv run python scripts/quality/validate_quality_contract.py --help
```

**Acceptance:** a manifest created for any other SHA, with any missing required report, or with an unmeasured Tier-0 dimension exits non-zero; a complete current run is the only path to `validation.valid: true`.

## Task 2: Close Python line/branch coverage and mutation evidence

**Files:**
- Source/tests: `app/**/*.py`, `tests/**/*.py`
- Configuration: `pyproject.toml`, `.coveragerc` if present
- Mutation tooling: `scripts/plan_mutmut_shards.py`, `scripts/mutmut_shard_budget.py`, `scripts/export_mutmut_shard_stats.py`, `scripts/merge_mutmut_cicd_stats.py`, `scripts/check_mutation_score.py`
- Workflow: `.github/workflows/ci.yml`, `.github/workflows/nightly-full-gate.yml`

**Steps:**

- [ ] Generate a fresh backend report without reusing saved data:

```powershell
uv sync --frozen --group dev
uv run pytest --cov=app --cov-branch `
  --cov-report=term-missing `
  --cov-report=xml:coverage.xml `
  --cov-report=json:artifacts/coverage/python/coverage.json
```

- [ ] Use the new `term-missing` output as the only source of the missing-line list; write a focused test for each missing branch and executable line, preserving security and error-path behavior.
- [ ] Run backend static gates: `uv run ruff check app/`, `uv run ruff format --check app/`, strict mypy, `python -m py_compile app/main.py`, `python scripts/custom_ast_linter.py app/`, and `python scripts/check_no_python2_except.py`.
- [ ] Rebuild the complete mutmut universe using the repository planners, execute every planned shard, export exact execution proof, merge all shards, and run `uv run python scripts/check_mutation_score.py --min-score 100`.
- [ ] Treat timeout, no-test, suspicious, skipped, unclassified, and survivor counts as failures; do not mark a timeout as killed.
- [ ] Add regression tests for every timeout root cause before rerunning the affected shard.

**Acceptance:** fresh `coverage.xml` and `artifacts/coverage/python/coverage.json` carry the current SHA; Python line/branch floors and Tier-0 pass; mutmut has no timeout/survivor/unclassified result and the checker exits 0.

## Task 3: Repair the frontend compiler baseline, then close the full frontend gate

**Files:**
- Modify: `frontend/tsconfig.json`
- Inspect/modify: compiler-reported files under `frontend/src/`, `frontend/tests/`, `frontend/scripts/`, `frontend/vitest.config.ts`
- Inspect/modify: `frontend/stryker.config.mjs`
- Coverage tooling: `frontend/scripts/merge-vitest-coverage.mjs`, `frontend/scripts/merge-playwright-coverage.mjs`
- Workflow: `.github/workflows/reusable-frontend-tests.yml`, `.github/workflows/ci.yml`

**Steps:**

- [ ] Remove the TypeScript 7-incompatible `baseUrl` option and make the alias mapping explicitly relative (`"@/*": ["./src/*"]`); preserve Vite/Vitest alias resolution and add a typecheck regression test for the alias.
- [ ] Re-run `npm run typecheck` and fix every compiler error, including dependency API drift (web-vitals v6, TanStack Table v9, DOM typings, and modern ES library methods) in the owning source file rather than suppressing the error.
- [ ] Run `npm ci` from `frontend/` and verify the lockfile is the installed dependency graph; do not mix old `node_modules` with the current lockfile.
- [ ] Run the full client test matrix, including WASM and all Vitest shards, then merge the generated reports into both `frontend/coverage/lcov.info` and `frontend/coverage/coverage-final.json`.
- [ ] Run `npm run lint`, `npm run lint:all`, `npm run build`, `npm run test:e2e`, accessibility checks, SSR hydration smoke, and `npm run test:e2e:coverage-tool`.
- [ ] Make Stryker scope explicit. For the required whole-frontend interpretation, expand `frontend/stryker.config.mjs` from the current sanitizer Tier-0 slice in deterministic batches; for every batch retain a complete mutant inventory and merge evidence. The final report must state the exact scope and prove no production file was silently omitted.
- [ ] Run `npm run test:mutation` (or the CI-equivalent sharded command) and require 100% viable mutants with zero no-test, timeout, survivor, or error statuses.

**Acceptance:** `npx tsc --noEmit`, lint, build, complete tests, merged coverage, and the declared Stryker scope all pass; the coverage manifest reports frontend lines/statements/branches/functions at exactly 100%.

## Task 4: Re-verify Go services under race and statement coverage gates

**Files:**
- `services/gateway/**/*.go`
- `services/ws-hub/**/*.go`
- `services/file-processor/**/*.go`
- `services/pkg/**/*.go`
- `.golangci.yml`, `scripts/go-coverage-report.ps1`, `scripts/go-coverage-report.sh`
- Workflow: `.github/workflows/reusable-go-tests.yml`, `.github/workflows/reusable-go-integration-tests.yml`, `.github/workflows/ci.yml`

**Steps:**

- [ ] Run `gofmt -w` only on files that need formatting, then `go vet ./...`, configured `golangci-lint run`, and `go test -race ./...` in each Go module.
- [ ] Generate fresh `coverage.out` files for gateway, ws-hub, file-processor, and shared; merge shared-input profiles with `scripts/quality/merge_go_coverprofiles.py`.
- [ ] Confirm the profiles contain the intended packages and that every statement counter is covered; add tests for uncovered error, cancellation, health-probe, path-traversal, HMAC, cache, and WebSocket-size paths.
- [ ] Verify the Go manifest labels branch/function metrics as unsupported only where the contract says so and never promotes derived line coverage to native statement coverage.

**Acceptance:** all four services pass race tests and lint; every required Go statement profile is current and 100%; no package is silently omitted from the profile.

## Task 5: Close Rust line/function/branch evidence, including rust-crypto

**Files:**
- `native/rust_ext/**`
- `crates/pyo3-sanitizer/**`
- `frontend/wasm-sanitizer/**`
- `frontend/rust-crypto/**`
- `fuzz/**`
- `scripts/quality/normalize_coverage_reports.py`, `scripts/quality/validate_quality_contract.py`
- Workflow: `.github/workflows/ci.yml`, `.github/workflows/rust-fuzz.yml`, `.github/workflows/go-fuzz.yml`

**Steps:**

- [ ] Run the same cargo-llvm-cov commands used by CI for each crate, including nightly `--branch` reports; never substitute a line-only report for a branch report.
- [ ] For `rust-crypto`, inspect the source branch inventory. If the crate truly has no branch constructs, add a tested zero-denominator derivation (`0/0` => 100% only after source analysis proves zero branches) and schema/normalizer tests. If branches exist, fix instrumentation and add KAT/property tests until every branch is hit.
- [ ] Add/retain tests for invalid lengths, malformed encodings, key rotation, constant-time failure paths, WASM boundary errors, and PyO3 conversion failures.
- [ ] Run `cargo test --all-targets` in each workspace and `cargo deny check`; run fuzz smoke jobs with bounded budgets.
- [ ] Validate that every Rust report references current source paths and current SHA before aggregation.

**Acceptance:** all four declared Rust components pass lines/functions/branches at their contract floors; rust-crypto no longer fails solely because an unmeasured `0/0` branch counter is misclassified.

## Task 6: Make API, Schemathesis, contract, and generated-schema gates deterministic

**Files:**
- `tests/test_schemathesis_api.py`
- `tests/test_openapi_contract.py` and related contract tests
- `app/main.py`, API routers, schemas, and OpenAPI generation code only where a failing case identifies a real contract defect
- Workflow: `.github/workflows/ci.yml`, `.github/workflows/contract-tests.yml`, `.github/workflows/contract-validation.yml`, `.github/workflows/generate-openapi.yml`

**Steps:**

- [ ] Run all four Schemathesis shards with the same environment as CI (`ENVIRONMENT=testing`, SQLite test database, `SCHEMATHESIS_MAX_EXAMPLES=25`, shard count/index) and save each result.
- [ ] Run the aggregate job even when a shard fails; make cancellation, timeout, and missing shard evidence a hard failure rather than a silent skip.
- [ ] Regenerate OpenAPI/types/mocks from the current backend and verify no generated file drift remains.
- [ ] Run contract tests against the generated schema and add a regression test for each mismatch before changing production behavior.

**Acceptance:** four shards plus aggregate are green, generated schema is deterministic, and every required PR contract job reports success.

## Task 7: Validate Docker, Compose, readiness, and backend startup end-to-end

**Files:**
- `start-docker.ps1`
- `backend.Dockerfile`, `frontend.Dockerfile`, service Dockerfiles, `Dockerfile.test`
- `docker-compose.yml`, `docker-compose.full.yml`, `docker-compose.test.yml`, `docker-compose.prod.yml`, `docker-compose.go.yml`, `docker-compose.infra.yml`, `docker-compose.observability.yml`, `docker-compose.sandbox.yml`
- `.dockerignore`, `.env.docker.example`, Caddy configuration, healthcheck definitions

**Steps:**

- [ ] Validate every supported compose file with `docker compose -f <file> config --quiet`; ensure all interpolated variables have documented safe defaults or fail with an actionable message.
- [ ] Run the user path from a clean dependency state: `./start-docker.ps1 -Build` (PowerShell) and capture the backend container logs until readiness.
- [ ] Confirm backend `/health/ready`, Caddy `/healthz`, file-processor gRPC health, Prometheus, Grafana, Tempo/Loki, and frontend SSR endpoints using the ports declared by the selected compose file.
- [ ] Exercise one authenticated API request, one WebSocket ticket/connection path, one file-processing request, and one frontend SSR page; verify no readiness probe reports healthy before dependencies are usable.
- [ ] Rebuild with pinned base images and inspect image tags/digests against Kyverno policy 9; run image vulnerability and SBOM/provenance gates.
- [ ] Stop the stack cleanly and verify no orphan containers, volumes, or generated credentials are left in the tracked tree.

**Acceptance:** build, startup, health, API, WebSocket, file-processing, SSR, and shutdown paths succeed without backend crash loops or hidden warnings.

## Task 8: Execute security, supply-chain, and infrastructure gates

**Files:**
- `.github/workflows/gitleaks.yml`, `trufflehog.yml`, `codeql.yml`, `semgrep`/SAST workflows, `sbom.yml`, `cargo-deny.yml`, `checkov.yml`, `scorecard.yml`, `zizmor.yml`, `renovate-config-validation.yml`
- `SECURITY.md`, `security/**`, `k8s/**`, `charts/**`, Terraform/IaC files
- `.secrets.baseline`, `quality/ownership-mapping.json`

**Steps:**

- [ ] Run pre-commit hooks, detect-secrets, gitleaks, Bandit, Semgrep SAST, actionlint, Renovate validation, Checkov, CodeQL-compatible local checks, and dependency audits.
- [ ] Re-stage `.secrets.baseline` after detect-secrets, as required by repository policy; do not suppress a finding without an owner, rationale, expiry, and regression test.
- [ ] Validate Kubernetes interpolation with `envsubst`, Helm templates with `helm lint`/`helm template`, Kyverno image policy, ExternalSecrets refresh settings, TLS configuration, and resource/HPA limits.
- [ ] Generate SBOM and provenance for every runtime image and verify no critical/high vulnerability remains untriaged.

**Acceptance:** every security/supply-chain gate is green, every suppression is justified and covered, and all infrastructure/workflow alternative gates are represented in the quality manifest.

## Task 9: Verify the developer harness and remove documentation drift

**Files:**
- `verify_harness.py`
- `.agents/hooks.json`, `.agents/hooks/**`, `.agents/subagents.json`, `.agents/skills/**`
- `docs/mcp/**`, `docs/README.md`, `docs/audits/INDEX.md`, active audit/roadmap files
- All documents discovered by `rg --files docs .agents .opencode | rg -i "roadmap|prompt|handoff|plan|status|backlog"`

**Steps:**

- [ ] Run `python verify_harness.py --repo-only` and record the exact test count, failures, and execution time.
- [ ] Run the harness with `--include-global-config` only when the developer explicitly wants machine-local MCP validation; keep repository CI hermetic by default.
- [ ] Add a harness regression test for every safety, hook, subagent, MCP, and stop-gate behavior relied on by the current workflows.
- [ ] Reconcile `AGENTS.md`, quality contract, workflows, harness documentation, audits, roadmaps, prompts, handoffs, and backlog notes. Keep one active quality-closure record; move completed historical evidence to `docs/audits/archive/` only after `rg` confirms no active link depends on it.
- [ ] Remove stale generated coverage/mutation snapshots from active documentation; retain immutable CI evidence only when it has a commit SHA and a clear archival purpose.
- [ ] Validate Markdown links, JSON/YAML syntax, and document references after cleanup.

**Acceptance:** the harness passes from a clean checkout, documentation describes actual commands and gates, and no active document claims a result that cannot be reproduced from its cited SHA/artifact.

## Task 10: Run the complete matrix and produce the final evidence bundle

**Files:**
- Generated evidence: `coverage.xml`, `artifacts/coverage/**`, `artifacts/quality/**`, mutation evidence, SBOM/provenance reports
- Audit index: `docs/audits/INDEX.md`
- Final report: `docs/audits/AUDIT_QUALITY_CLOSURE_<verified-sha>.md`

**Steps:**

- [ ] Start from the exact commit under review and run the complete backend, frontend, Go, Rust, API, E2E, Docker, security, infrastructure, workflow, and harness matrix.
- [ ] Generate and validate the quality manifest only after all reports are present; verify all report hashes and source roots.
- [ ] Run the final repository checks:

```powershell
git diff --check
python verify_harness.py --repo-only
uv run python scripts/quality/validate_quality_contract.py --manifest artifacts/coverage/quality-manifest.json
git status --short
```

- [ ] Review the final report line by line: verified SHA, tool versions, commands, durations, artifact paths, pass/fail counts, skipped-job reasons, and known limitations. A known limitation is not a complete gate.
- [ ] Commit each coherent implementation batch with the repository message convention, then create one final checkpoint commit containing only the quality-closure changes.
- [ ] Re-run the final matrix after the last commit so the evidence SHA and commit SHA are identical.

**Acceptance:** the final audit names one SHA, the manifest is valid, all required checks are green, the PR matrix is complete, and the final worktree is clean. Only then can the MVP foundation be declared complete.

## Required Final Report Contents

The final audit must include:

- verified commit SHA and branch;
- toolchain versions and runner/OS details;
- tracked file/line inventory and generated-artifact policy;
- per-stack test counts, coverage totals, mutation totals, and exact scopes;
- every command run and its exit code;
- artifact paths, hashes, timestamps, and manifest validation result;
- Docker images, health endpoints, readiness latency, and shutdown result;
- security/SBOM/provenance findings and their disposition;
- CI job matrix with explicit reasons for intentional skips;
- remaining risks, if any, with an owner and a blocking/non-blocking classification.

No final report may use “green”, “complete”, “100%”, or “безупречно” for a stack unless the corresponding fresh command output and SHA-bound artifact are attached or directly reproducible.
