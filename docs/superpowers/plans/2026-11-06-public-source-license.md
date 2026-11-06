# Public Source License Implementation Plan

> **For agentic workers:** Execute inline with the executing-plans workflow.

**Goal:** Implement the approved terms for future original material while
preserving existing permissions and all dependency/quality gates.

**Architecture:** A root notice defines scope and exceptions. Packaged copies
carry the same terms and retained MIT notice. Historical provenance and a
component inventory document existing permissions. Local Cargo Deny mappings
recognize only each exact first-party crate/version.

**Tech Stack:** Markdown/plain-text notices, npm JSON, Python/Rust TOML, existing
WASM producer/verifiers, and the GitHub PR workflow.

## Tasks

- [x] Add root terms, `THIRD_PARTY_NOTICES.md`, `docs/licensing/README.md`, and
      the verbatim historical root MIT notice. Preserve earlier permissions and
      include hosted-site permission and contribution-agreement requirements.
- [x] Synchronize both READMEs, contribution guidance, documentation index,
      and ADR-054 without publishing additional personal information.
- [x] Synchronize npm manifests/root lockfile records, Python metadata, and
      the three runtime Rust manifests. Add exact local Cargo Deny license mappings
      without changing dependency resolutions or shared allowlists.
- [x] Bundle notices in Rust/WASM packages, rebuild using the pinned producer,
      and regenerate provenance through the existing script.
- [x] Validate metadata consistency and unchanged dependency records/notices;
      run `python verify_harness.py`, existing WASM script tests from `frontend/`,
      the artifact validator, exact Cargo license scans, and changed-file formatting.
- [x] Run existing commit/push hooks, re-stage `.secrets.baseline` after
      detect-secrets without adding identities, review the staged diff, commit
      with a non-wave scope, and create/attach separate license-only PRs targeting `egorribun` and `main`.
      Report the actual hosted-check state; do not merge or bypass gates.

## Integration status

Preparation, local validation, commit/push hooks, and publication of both PRs
are complete: [development PR #1361](https://github.com/egorribun/university_ecosystem/pull/1361)
and [default-branch PR #1362](https://github.com/egorribun/university_ecosystem/pull/1362).
They remain subject to source-bound hosted checks and the ordinary merge policy.
This checklist does not certify passing hosted checks or completed integration.
