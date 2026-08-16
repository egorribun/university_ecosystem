# Current-HEAD Coverage Closure Implementation Plan

> **Execution rule:** use the repository's native coverage tools, preserve every
> authored source denominator, and change a threshold only after current-HEAD
> evidence reaches the target.

**Goal:** Produce a reproducible coverage manifest for the verified branch SHA,
generate an exact uncovered-code ledger, close every supported coverage metric
to 100% test-first, and retain 100% patch and viable-mutation policy.

**Architecture:** Collect native reports independently for Python, frontend,
Go, and all Rust crates; normalize them through the existing quality manifest;
then close gaps by subsystem in small commits. Declarative files receive their
native contract/schema/security evidence and are never assigned fabricated line
coverage.

---

## Task 1: Capture fresh native reports

- [ ] Run all Python tests with coverage.py branch measurement, an isolated
      data file, and no aggregate threshold during collection.
- [ ] Run the complete Vitest suite with V8 statements, branches, functions,
      and lines enabled and all authored `frontend/src/**/*.{ts,tsx}` retained.
- [ ] Run every authored Go module with a coverprofile and apply the same
      generated/mock filtering as the required CI workflow.
- [ ] Run stable LLVM line/function coverage and nightly LLVM branch coverage
      for `rust-native`, `rust-pyo3-sanitizer`, `rust-wasm-sanitizer`, and
      `rust-crypto` with isolated target directories.
- [ ] Hash and timestamp every report; reject missing, stale, or empty output.

## Task 2: Normalize and inventory gaps

- [ ] Run `scripts/quality/normalize_coverage_reports.py` with the exact local
      `HEAD`, all native reports, and `--ignore-outside-files` only for files
      outside declared component roots.
- [ ] Validate the manifest with `scripts/quality/validate_quality_contract.py`.
- [ ] Generate a deterministic per-component/per-file ledger containing every
      missed line, branch, function, statement, and uncovered Go statement.
- [ ] Reconcile the ledger with `git ls-files`; record generated, vendored,
      declarative, and unsupported dimensions explicitly.

## Task 3: Close Python coverage

- [ ] Write behaviour-focused tests for each uncovered line and branch.
- [ ] Remove only demonstrably unreachable code; do not add coverage pragmas to
      reachable production paths.
- [ ] Re-run focused tests after every change and the complete Python coverage
      contour before raising Python lines and branches to 100.

## Task 4: Close frontend coverage

- [ ] Cover every uncovered statement, line, branch, and function through unit,
      component, browser, or SSR tests according to the code's real runtime.
- [ ] Keep browser-only and generated assets in their existing explicit
      contours; do not narrow the authored-source include glob.
- [ ] Re-run the complete Vitest and browser coverage merge before setting all
      four frontend dimensions to 100.

## Task 5: Close Go and Rust coverage

- [ ] Add Go tests for every uncovered authored statement in gateway, ws-hub,
      file-processor, uni-cli, and shared SPIFFE code.
- [ ] Add Rust tests for every uncovered line/function/region/branch supported
      by LLVM coverage across all four crates and feature contours.
- [ ] Re-run `go test`, `govulncheck`, `cargo test`, clippy, stable LLVM
      coverage, and nightly branch coverage after closure.

## Task 6: Ratchet policy and publish evidence

- [ ] Set each supported component metric in `quality/quality-contract.json` to
      100 only after the fresh manifest proves it.
- [ ] Keep unsupported dimensions at zero and document them as unsupported in
      the manifest rather than claiming synthetic coverage.
- [ ] Run full pre-commit, mutation, differential coverage, and manifest gates.
- [ ] Commit, push to `egorribun`, verify remote SHA equality, and use a main
      post-integration run as the only proof for the main-only Codecov OIDC job.
