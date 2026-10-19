# Frozen-RC Manifest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Root owns all Git writes.

**Goal:** Replace freeform release-candidate dispatch input with a validated, reviewed tracked SHA without weakening Checkov or full-smoke guards.

**Architecture:** A standard-library CLI resolves one bounded tracked JSON manifest from the trusted workflow checkout. The validation job exports the exact SHA; full smoke checks out and verifies that SHA before setup.

**Tech Stack:** Python standard library, pytest, coverage.py, GitHub Actions.

**Spec:** [Reviewed frozen-RC selection](../specs/2026-10-19-frozen-rc-manifest.md).

## Global Constraints

- GitHub plugin only, branch egorribun, existing PR1306. No local repository execution.
- No actual RC selection, main/bootstrap change, merge or deployment.
- Initially schema_version integer 1 and source_sha null; null blocks selection.
- Manifest maximum 4096 bytes; exact lowercase 40-hex source SHA.
- Preserve 78 required context/app pairs, baseline319, inherited dispositions, blocking CodeQL and existing full coverage gates.
- Runtime checks occur through hosted Actions. A static review does not establish a passing test.

## Review Focus

- Repeated JSON keys must fail, even when values are identical.
- Read failures must not expose input or exception details.
- A symlink/directory/nonregular file must not become a valid manifest.
- A mismatched checkout must stop before dependency installation.
- Cleanup and receipt behavior must survive full-smoke failure.

## Task 1: Pin the resolver and workflow contracts

**Files:** Create tests/test_frozen_rc_manifest.py; modify tests/test_live_acceptance_workflow.py and .github/workflows/reusable-backend-tests.yml.

**Interfaces:** The tests expect parse_manifest(document: object) -> str and CLI --manifest PATH. CLI returns 0 with SHA plus newline, or 1 with empty stdout and the fixed sanitized diagnostic.

- [ ] Publish the reviewed tests for shape/types, null, SHA boundaries, duplicate keys, malformed/UTF-8 data, 4096/4097-byte limits, missing/directory/symlink paths, mocked nonregular rejection before open, a mocked cap-plus-one bounded read, read OSError, excessive JSON nesting, and import without side effects.
- [ ] Require empty dispatch inputs, main-first rejection, trusted workflow checkout verification, validated job output, exact frozen checkout/ref, unchanged Core behavior and always-owned cleanup/metadata receipt.
- [ ] Add the isolated focused coverage step after locked dependency sync in unit shard zero; leave normal full shards and provenance untouched.
- [ ] Observe hosted assertion RED for the missing parser/manifest and old dispatch contract. Fix formatting/collection infrastructure first if it prevents behavioral RED. Do not implement before RED.
- [ ] Record exact source/run/job and failures in audit/status, not an inferred failure.

## Task 2: Implement bounded source selection and exact full-smoke wiring

**Files:** Create scripts/quality/resolve_frozen_rc_manifest.py and quality/frozen-rc.json; modify .github/workflows/live-acceptance.yml, docs/superpowers/plans/MVP_MASTER_PLAN.md, STATUS.md and docs/audits/AUDIT-2026-10.md.

**Interfaces:** parse_manifest(document: object) -> str raises ValueError for invalid data. The CLI loads at most 4097 bytes, rejects duplicate keys, and emits only validated source SHA. Validation-job output source_sha is the sole full-smoke checkout input.

- [ ] Implement exact-key/type/version validation and lowercase full-match SHA checking, rejecting null.
- [ ] Implement bounded regular-file loading, symlink rejection, duplicate detection, stable sanitized read/validation errors and no import-side CLI execution.
- [ ] Add the initial unfrozen manifest and verify source_sha is null before publication.
- [ ] Remove freeform dispatch inputs. Preserve main-first rejection; verify trusted workflow SHA after checkout; resolve the fixed manifest and revalidate output before GITHUB_OUTPUT.
- [ ] Keep frozen job event/main/needs guards. Its first checkout consumes source_sha; its immediate verifier binds subsequent stand --ref and receipt name to that same verified SHA.
- [ ] Preserve full stack/mode, disabled caches, owner state-directory identity, always-run stop and metadata-only receipt/upload. Preserve PR/nightly paths and permissions.
- [ ] Update active instructions for the tracked selection, explicitly retaining unresolved default-branch bootstrap/pre-merge ordering. Do not present null as a selected RC.
- [ ] Obtain independent static review before publishing the narrow implementation.

## Task 3: Verify source acceptance without overstating release acceptance

**Files:** Only targeted corrections and evidence updates in the files above.

- [ ] Confirm focused pytest passes and isolated validator coverage reports 100% line/branch coverage. Add missing behavioral cases rather than exclusions.
- [ ] Wait for all hosted workflows on the implemented SHA; verify required context/app pairs and blocking CodeQL, including Checkov CKV_GHA_7.
- [ ] Verify owned live completion, stop, metadata receipt and synthetic-merge/source tree equivalence before superseding a run.
- [ ] Record passed, failed and unexecuted stages separately. Static workflow tests and PR Core do not prove main-only frozen full smoke.
- [ ] Retain actual release-candidate selection/bootstrap/full-smoke as pending operational acceptance; do not merge or deploy.
