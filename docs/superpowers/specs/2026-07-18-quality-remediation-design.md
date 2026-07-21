# Quality Remediation Design

**Date:** 2026-07-18

## Goal

Make the quality programme truthful and release-safe: no build may ship fake
WASM dependencies, no coverage gate may omit handwritten production code, and
all reported evidence must be reproducible from the checked-out revision.

## Scope

This remediation covers the acceptance findings on `codex/quality-roadmap`:

- the local `wasm-sanitizer` and `uni-wasm-crypto` packages;
- frontend build, unit tests, lint, formatting and coverage configuration;
- Go coverage thresholds and their CI/quality-contract agreement;
- Python test/lint regressions and coverage-only tests introduced by the
  programme;
- Rust native/WASM test reproducibility; and
- roadmap status, quality manifest and required CI evidence.

It does not lower a threshold, add a broad exclusion, add a quarantine, or
mark a roadmap wave complete without fresh evidence.

## Considered approaches

1. **Keep placeholders and tolerate a warning.** This preserves local builds
   but can ship an identity sanitizer and empty cryptographic outputs. It is
   rejected as an unsafe false success.
2. **Replace the Rust packages with a JavaScript fallback.** This can keep a
   build running but creates a second sanitization/cryptography implementation
   with a different security boundary. It is rejected because it weakens the
   existing Rust/WASM architecture.
3. **Require real generated artifacts and fail closed.** `wasm-pack` builds
   both packages, validation checks the WebAssembly magic bytes and required
   JS exports, and the frontend build stops on failure. This is selected.

## Architecture

`frontend/scripts/verify-wasm-artifacts.mjs` will be the single validation
boundary for local development and CI. It validates both package manifests,
the `00 61 73 6d` WASM header, non-trivial binary size, and required generated
exports. `build-orchestrated.mjs` invokes `wasm-pack`, then this validator,
and propagates any error. A checked-in package is only accepted when it is a
real wasm-pack output; generated files are never replaced with stubs.

Frontend coverage returns to the complete handwritten source inventory.
Generated API/route declarations and test/story files remain excluded only
where they are objectively non-production. The quality normalizer compares
the source inventory with LCOV input, so an include whitelist cannot make an
incomplete report appear complete. Go CI thresholds are read from the same
contract values used by the policy gate; a component below its contractual
floor fails its own job before the aggregate gate.

Each coverage increase is behavioural: public API, UI interaction, worker
message, FFI or service boundary tests are preferred. A test that only calls
an internal function or makes a tautological assertion is removed or rewritten
to assert externally visible behaviour.

## Failure handling and security rules

- Missing `wasm-pack`, failed Rust compilation, a malformed `.wasm`, or absent
  required export is a build failure, not a warning.
- Runtime sanitizer initialization failure retains the existing text-only
  fallback; a successfully imported sanitizer must never be accepted merely
  because it returns input unchanged.
- Cryptographic worker failures return an explicit worker error and never use
  empty values as successful results.
- CI publishes reports only after source identity, threshold and freshness
  validation succeeds.

## Verification

Every behaviour change follows red-green-refactor:

1. Add a test that demonstrates the unsafe current outcome or missing policy.
2. Run it and record the expected failure.
3. Make the minimal production/configuration change.
4. Run the focused test, then the relevant language suite, lint/format/type
   checks, build, coverage parser and artifact validator.
5. Run the complete required matrix when its dependencies are available; an
   unavailable environment remains an explicit blocked item, never a pass.

The final acceptance requires a clean worktree, no `git diff --check` output,
all quality lint gates clean, full source coverage scope, contract-aligned
thresholds and fresh artifacts from every required component.
