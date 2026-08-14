# Main CI and Supply-Chain Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the deterministic Trusted Codecov Upload failure, replace the inaccurate Go vulnerability severity heuristic with reachable-code analysis, and move every active Go build surface to the security-fixed Go 1.26.6 toolchain.

**Architecture:** Keep complete OSV/Python/Rust reports as artifacts, but make the Go blocking gate use the official symbol-aware scanner. Encode all workflow and image assumptions as repository contract tests, and keep every external image/action/tool version immutable and reviewable.

**Tech Stack:** GitHub Actions, PyYAML/pytest, Go 1.26.6, govulncheck 1.7.0, OSV Scanner, Docker Buildx, Codecov OIDC.

---

### Task 1: Lock the Codecov failure into a regression test

**Files:**
- Modify: `tests/test_quality_workflow_contract.py`
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Extend the OIDC contract test with the exact nine report paths**

  Parse `jobs.codecov-upload`, read the Codecov step's `with.files`, and assert it equals this comma-separated value with no newline:

  ```text
  artifacts/coverage/codecov/python.xml,artifacts/coverage/codecov/frontend.lcov,artifacts/coverage/codecov/go-gateway.out,artifacts/coverage/codecov/go-ws-hub.out,artifacts/coverage/codecov/go-file-processor.out,artifacts/coverage/codecov/rust-native.json,artifacts/coverage/codecov/rust-pyo3-sanitizer.json,artifacts/coverage/codecov/rust-wasm-sanitizer.json,artifacts/coverage/codecov/rust-crypto.json
  ```

- [ ] **Step 2: Run the focused test and verify RED**

  Run: `uv run pytest tests/test_quality_workflow_contract.py::test_codecov_oidc_permissions_are_scoped_to_trusted_upload_job -q`

  Expected: failure showing that the current YAML literal contains newline characters and is not the required comma-separated input.

- [ ] **Step 3: Change only the Codecov `files` input**

  Replace the YAML literal block with the exact comma-separated list from Step 1. Retain `use_oidc: true`, `disable_search: true`, and `fail_ci_if_error: true`.

- [ ] **Step 4: Run the focused test and verify GREEN**

  Run the command from Step 2.

  Expected: pass.

### Task 2: Pin the security-fixed Go toolchain everywhere

**Files:**
- Modify: `go.mod`
- Modify: `go.work`
- Modify: `gen/go/go.mod`
- Modify: `services/cmd/uni-cli/go.mod`
- Modify: `services/file-processor/go.mod`
- Modify: `services/gateway/go.mod`
- Modify: `services/pkg/spiffe/go.mod`
- Modify: `services/ws-hub/go.mod`
- Modify: `services/file-processor/Dockerfile`
- Modify: `services/gateway/Dockerfile`
- Modify: `services/ws-hub/Dockerfile`
- Modify: `Dockerfile.protogen`
- Modify: `scripts/quality/capture_isolated_benchmarks.py`
- Modify: `.github/workflows/benchmark.yml`
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/go-fuzz.yml`
- Modify: `.github/workflows/manual-performance-evidence.yml`
- Modify: `.github/workflows/nilaway.yml`
- Modify: `.github/workflows/reusable-cache-deps.yml`
- Modify: `.github/workflows/reusable-go-integration-tests.yml`
- Modify: `.github/workflows/reusable-go-tests.yml`
- Modify: `.github/workflows/reusable-security-audit.yml`
- Modify: `tests/test_docker_startup_contracts.py`
- Modify: `tests/test_quality_workflow_contract.py`
- Modify: `tests/test_capture_isolated_benchmarks.py`
- Modify: `tests/test_compare_paired_benchmarks.py`

- [ ] **Step 1: Add repository contract assertions for Go 1.26.6**

  Assert that every active `go.mod` and `go.work` directive is `1.26.6`, every literal GitHub Actions Go version is `1.26.6`, every Go builder uses one of these reviewed pins, and the benchmark image matches the Bookworm pin:

  ```text
  golang:1.26.6-alpine3.24@sha256:af8d6740070b8906d12eae1c3e3ea0957fb63f492051ea05e354c38ef9fe88df
  golang:1.26.6-bookworm@sha256:116d58cbd88c1297624acc6e967a060012422bacf9930927e23fb719189c6f36
  ```

- [ ] **Step 2: Run the focused contracts and verify RED**

  Run: `uv run pytest tests/test_docker_startup_contracts.py tests/test_quality_workflow_contract.py tests/test_capture_isolated_benchmarks.py tests/test_compare_paired_benchmarks.py -q`

  Expected: failures identify every remaining 1.26.4/1.26.5 manifest, workflow, image, and fixture.

- [ ] **Step 3: Update all active pins and fixtures mechanically**

  Change only the version/digest values listed in this task. Do not edit archived evidence merely to erase historical version strings.

- [ ] **Step 4: Synchronize and validate the Go workspace**

  Run:

  ```powershell
  $env:GOTOOLCHAIN = 'go1.26.6'
  go work sync
  go test ./services/gateway/... ./services/ws-hub/... ./services/file-processor/... ./services/cmd/uni-cli/... ./services/pkg/spiffe/...
  ```

  Expected: all tests pass and no module or workspace file drifts after the command.

- [ ] **Step 5: Run the focused contracts and verify GREEN**

  Run the pytest command from Step 2.

  Expected: pass.

### Task 3: Replace CVSS guessing with reachable-code vulnerability enforcement

**Files:**
- Modify: `.github/workflows/sbom.yml`
- Modify: `tests/test_quality_workflow_contract.py`

- [ ] **Step 1: Add the SBOM workflow contract test**

  Assert that the vulnerability job installs `golang.org/x/vuln/cmd/govulncheck@v1.7.0`, runs it against all five authored service package patterns, and contains neither `max_cvss` nor the `score < 0` unknown-severity heuristic in the blocking Go step. Also assert that the separate Go SBOM job still runs OSV Scanner and uploads SARIF.

- [ ] **Step 2: Run the focused test and verify RED**

  Run: `uv run pytest tests/test_quality_workflow_contract.py -k 'sbom_go_gate' -q`

  Expected: failure because the current gate uses OSV JSON plus guessed CVSS.

- [ ] **Step 3: Implement the symbol-aware gate**

  In `vuln-gate`, replace the OSV Scanner install and inline Python severity parser with:

  ```bash
  go install golang.org/x/vuln/cmd/govulncheck@v1.7.0
  govulncheck \
    ./services/gateway/... \
    ./services/ws-hub/... \
    ./services/file-processor/... \
    ./services/cmd/uni-cli/... \
    ./services/pkg/spiffe/...
  ```

  Keep the `sbom-go` OSV scan and SARIF upload unchanged so module-only advisories remain visible.

- [ ] **Step 4: Verify GREEN and run the real scanner**

  Run:

  ```powershell
  uv run pytest tests/test_quality_workflow_contract.py -k 'sbom_go_gate' -q
  $env:GOTOOLCHAIN = 'go1.26.6'
  go run golang.org/x/vuln/cmd/govulncheck@v1.7.0 ./services/gateway/... ./services/ws-hub/... ./services/file-processor/... ./services/cmd/uni-cli/... ./services/pkg/spiffe/...
  ```

  Expected: contract pass; `govulncheck` reports zero reachable vulnerabilities.

### Task 4: Validate the complete CI and supply-chain patch

**Files:**
- Verify only: all files modified by Tasks 1-3

- [ ] **Step 1: Validate workflow syntax and repository policy**

  Run:

  ```powershell
  actionlint
  uv run pytest tests/test_quality_workflow_contract.py tests/test_docker_startup_contracts.py tests/test_capture_isolated_benchmarks.py tests/test_compare_paired_benchmarks.py -q
  uv run pre-commit run --all-files
  ```

  Expected: all commands pass without rewriting tracked files.

- [ ] **Step 2: Build every changed Go image**

  Run:

  ```powershell
  docker build -f services/gateway/Dockerfile -t university-gateway:go1266 .
  docker build -f services/ws-hub/Dockerfile -t university-ws-hub:go1266 .
  docker build -f services/file-processor/Dockerfile -t university-file-processor:go1266 .
  docker build -f Dockerfile.protogen -t university-protogen:go1266 .
  ```

  Expected: four successful digest-pinned builds.

- [ ] **Step 3: Re-run dependency scanners**

  Run Python, npm, Rust, OSV reporting, and govulncheck commands from the repository security workflow. Expected: no actionable unaccepted vulnerability and no scanner execution failure.

### Task 5: Publish and obtain remote evidence

**Files:**
- Commit all files from Tasks 1-4

- [ ] **Step 1: Check the staged patch**

  Run: `git diff --check` and then `git diff --cached --check` after staging.

  Expected: no whitespace errors.

- [ ] **Step 2: Commit and push**

  Commit message: `fix(ci): repair trusted coverage and vulnerability gates`

  Push to `origin/egorribun`, then verify `git rev-parse HEAD` equals `git rev-parse origin/egorribun`.

- [ ] **Step 3: Dispatch branch-verifiable workflows**

  Dispatch `sbom.yml` and any dispatch-enabled CI workflow against `egorribun`. Wait for terminal status and inspect failed logs rather than retrying blindly.

- [ ] **Step 4: Record the main-only boundary honestly**

  The Codecov OIDC job is green only after the commit is integrated to `main`, because its security guard intentionally skips every other ref. Until that run exists, report the local contract, staged-artifact, and branch workflow evidence separately from main-only proof.
