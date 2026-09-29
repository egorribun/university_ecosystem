# ADR-044: Retire the Unused Native Sanitizer

## Status

Accepted

## Date

2026-09-29

## Context

The repository carried two server-side HTML sanitizers:

- `app/utils/sanitization.py` sanitizes with `nh3` and is wired into the
  application through the validators in `app/schemas/validators.py`.
- `crates/pyo3-sanitizer` (the PyO3 extension `pyo3_sanitizer`), reached only
  through `app/services/content_processing.py`. That module tried the native
  extension first and fell back to `nh3`.

An inventory on 2026-09-29 found that nothing under `app/` imports
`app.services.content_processing`; only tests imported it. The crate had no
other consumer, and the `frontend/wasm-sanitizer` parity script that compared
against it was a development-only script that no workflow ran.

The crate nevertheless carried a complete pipeline of its own:

- Rust lint, clippy and `cargo-udeps` legs in `ci.yml`, plus a cargo-deny
  matrix leg, an SBOM lockfile entry and a Miri run in the nightly gate.
- The `rust-pyo3-sanitizer` coverage component: exact-100 line and branch
  gates, the Codecov flag and upload, the coverage manifest schema, the
  normalizer, the quality contract and the retry layout.
- ASan and TSan test invocations, three cargo-fuzz targets, an OSS-Fuzz
  integration stub that existed only for those targets, and Criterion
  benchmarks with a published history.
- A workspace member, a dev dependency and two Docker test-image copy steps
  that kept the extension built in the disposable test image.

The production image installs with `--no-dev`, so the native branch never ran
in production. Development and CI exercised a code path production did not
use, and every gate above protected code that no request could reach.

## Decision

Remove the native sanitizer end to end:

- Delete `crates/pyo3-sanitizer`, `app/services/content_processing.py` and
  the tests and fuzz harness that covered only them.
- Drop the workspace member, the `pyo3_sanitizer` dev dependency, its mypy
  override, the deptry exception and the mutmut `also_copy` entries, and
  regenerate `uv.lock`.
- Remove the `rust-pyo3-sanitizer` coverage component from the quality
  contract, the manifest schema, the normalizer, the validator, the retry
  layout, the ownership mapping and Codecov.
- Remove its CI legs and jobs: lint, clippy and udeps legs, the coverage step,
  the cargo-deny and fuzz matrix legs, the SBOM lockfile entries, the Miri
  step, the `rust-criterion` benchmark jobs (PR and manual) with their history
  publishing, and the required-check names that only they produced.
- Remove the ASan and TSan invocations of the deleted tests. The runners keep
  exercising `rust_ext`.
- Remove `infra/oss-fuzz`. It was a stub whose only fuzz root was the removed
  crate, with a placeholder contact and no upstream project.
- Keep the WASM sanitizer smoke test in `frontend/wasm-sanitizer/tests`, but
  assert safety invariants of the browser sanitizer itself instead of parity
  with the removed crate.

What stays:

- `nh3` in `app/utils/sanitization.py` remains the single server-side
  sanitizer.
- `frontend/wasm-sanitizer` remains the browser sanitizer, with its coverage,
  fuzz and cargo-deny legs.
- `native/rust_ext` remains the schedule, partition and audit-signature
  extension.

A future native sanitizer must be adopted by application code first. Only
after `app/` imports it on a production code path does it get its own crate,
coverage component and fuzz or benchmark pipeline, and the production image
must then install it.

## Consequences

- One sanitizer path in production, development and CI. The
  "production uses `nh3`, CI uses the extension" ambiguity is gone.
- The Rust coverage contract covers three components (`rust-native`,
  `rust-wasm-sanitizer`, `rust-crypto`). The exact-100 thresholds for these
  are unchanged.
- The required check `Rust Criterion Benchmarks (pyo3-sanitizer)` no longer
  exists. Branch protection must not require it; the remaining performance
  contexts are unchanged.
- The `cargo-deny` matrix, the RustSec lockfile inventory and the fuzz matrix
  each shrink by one crate. No remaining lockfile or fuzz target is dropped.
- The disposable test image no longer builds a second maturin project, which
  shortens its build.
- OSS-Fuzz registration, if wanted later, is a new decision that starts from a
  crate application code depends on.

## References

- `app/utils/sanitization.py`, `app/schemas/validators.py`
- `frontend/wasm-sanitizer`, `native/rust_ext`
