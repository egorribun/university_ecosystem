# Task 5 — CI check catalog expansion report

## Status

DONE. The catalog now models the complete source inventory plus the protected
contexts emitted by reusable workflows, matrix jobs, and external provider
integrations. No workflow execution, branch-protection rule, runner cap, retry
threshold, or test/mutation inventory was changed.

## Root cause

The initial catalog represented one entry per repository workflow/job. GitHub's
protected-check ruleset also contains caller-qualified reusable-workflow checks
and matrix-expanded checks, whose names are not present as one-to-one source
workflow/job names. Four provider-managed contexts (`CodeQL`, `Checkov`,
`spectral`, and `zizmor`) likewise use an externally owned provider integration
context. The old schema and validator had no fail-closed representation for
these 48 protected contexts, so the catalog could not prove that its inventory
matched the protected surface.

## Implementation

Changed files:

- `quality/ci-check-catalog.json`
  - bumped `catalog_version` to `1.1.0`;
  - preserved 55 workflows and 180 source jobs;
  - added four external provider checks with integration ID `57789`, exact
    context names, explicit required classification, owner, source/runbook
    references, and `externally_owned: true`;
  - added eight fail-closed expansions covering 44 exact reusable/matrix
    contexts: backend (4), frontend (13), Chromium E2E (4), Go (8), security
    audit (7), CodeQL (5), and Rust fuzz (1 + 2).
- `quality/ci-check-catalog.schema.json`
  - added strict `external_checks` and `expansions` top-level arrays;
  - required provider integration, ownership, classification, source/runbook,
    and external ownership metadata;
  - required a reusable-workflow or matrix kind, caller reference, and exactly
    one deterministic context template/finite context list;
  - constrained reusable workflow/job references and rejected incompatible
    matrix/reusable fields with `additionalProperties: false`.
- `scripts/quality/validate_ci_check_catalog.py`
  - validates provider context uniqueness and collisions with source checks;
  - validates expansion IDs, caller workflow/job references, reusable
    workflow `workflow_call`, caller `uses` binding, reusable job IDs, matrix
    evidence, owner/profile/classification/runbook, required-event policy, and
    duplicate/colliding expanded contexts;
  - remains fail-closed for malformed paths and malformed list entries.
- `tests/test_ci_check_catalog.py`
  - retained all ten original catalog tests;
  - added valid provider/expansion contract coverage and invalid duplicate,
    malformed path, unknown profile, missing owner/runbook, and missing source
    reference cases.
- `docs/testing/ci-check-catalog-runbook.md`
  - documents the provider/expansion contract and a live ruleset refresh
    procedure that discovers the active ruleset at runtime without storing its
    volatile ID or current conclusions in the catalog.

## Verification

All commands were run from the repository root. The focused suite was run
three times concurrently with its pytest cache provider disabled so repetitions
were isolated:

```text
uv run pytest -p no:cacheprovider tests/test_ci_check_catalog.py -q
RUN 1: 17 passed in 54.43s
RUN 2: 17 passed in 75.83s (0:01:15)
RUN 3: 17 passed in 76.09s (0:01:16)
```

```text
uv run ruff check scripts/quality/validate_ci_check_catalog.py tests/test_ci_check_catalog.py
All checks passed!

uv run ruff format --check scripts/quality/validate_ci_check_catalog.py tests/test_ci_check_catalog.py
2 files already formatted

uv run python -c "... Draft202012Validator.check_schema(schema) ..."
schema OK; catalog errors: 0

uv run python scripts/quality/validate_ci_check_catalog.py
CI check catalog: OK (55 workflows, 180 jobs)

git diff --check
exit 0 (no output)
```

A read-only live ruleset comparison using `gh api` found 92 required contexts;
the catalog's 48 supplemental contexts had 48 unique entries, with zero
catalog-only and zero ruleset-only supplemental contexts. The four provider
contexts reported integration ID `57789`. The active ruleset identifier was
not persisted in the catalog.

## Boundary

This task provides a deterministic repository catalog and a repeatable live
evidence procedure. It does not certify current branch-protection conclusions,
workflow run status, artifact bytes, or the full CI matrix; those remain
current-SHA release gates and must be refreshed by the release audit.

The user-owned untracked paths `.tmp_preflight/`, `.tmp_stryker_18/`,
`.tmp_stryker_22/`, and `docs/audits/AUDIT_PLATFORM_FULL.md` were not edited,
staged, or committed.
