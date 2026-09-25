# Migration `148642dd1207` and dead-letter UUID audit

Date: 2026-09-08 (Europe/Moscow)

This is a read-only, evidence-first audit of the migration and schema contract
that appeared in the historical CI failure report.  No user-owned audit files,
database state, or migration source were changed by this audit.

## Source and local evidence

- Audited checkout: branch `egorribun`, source SHA
  `1716837085549ab51267d4bd2d2e0207e104f34e`.
- Focused command:

  ```text
  uv run pytest -q tests/test_migration_148642dd1207_safety.py \
    tests/test_schemas_closure.py tests/test_notification_dead_letter_api.py
  ```

  Result: **28 passed in 57.73s**.

The migration safety suite verifies offline upgrade and downgrade SQL, absence
of in-place `groups.id` type changes and column renames, numeric-cast
short-circuiting, composite/non-id foreign-key handling, exact existing-check
matching, lock/cutover guards, and rollback shape.  The dead-letter schema
contract uses valid UUID values for positive and duplicate cases; invalid-format
and empty-list cases remain separate assertions in the API/schema suites.

## PostgreSQL migration design review

`148642dd1207_fix_missing_tables.py` currently uses a transactional, validated
shadow cutover:

1. `groups.id` is copied to additive `id__integer` only after null, syntax,
   32-bit-range, and post-cast uniqueness checks.  A `NOT VALID` check is then
   validated before the key is replaced.
2. Foreign keys referencing `groups.id` are captured from `pg_catalog`,
   converted only after value preflight, and recreated with their original
   column mapping/actions.  Composite references are rejected fail-closed.
3. A transaction-local lock timeout and advisory lock serialize concurrent
   repairs.  The reverse path mirrors the operation through `id__varchar` and
   restores the legacy shape.
4. `active_sessions.signing_key` first rejects existing nulls, adds and
   validates a `NOT VALID` check, and only then promotes the physical `NOT NULL`
   invariant.  Downgrade removes the check and nullability explicitly.

This avoids the unsafe direct `ALTER COLUMN ... TYPE` and unvalidated
non-nullability operations that caused the original Squawk report.  The
migration also declares schema types with SQLAlchemy primitives and does not
load application encryption/configuration at import time.

## CI evidence and boundary

Historical CI run `33681869807` (head
`d654e3f66cd1946910832cba9f3dea88ddcc33d4`) ran Squawk v2.44.0 against
`148642dd1207` and reported `Found 0 issues in 1 file`; its Alembic, PostgreSQL
migration-gate, and rollback jobs all succeeded.

The subsequent remote runs below also passed all three migration jobs, while
their overall failures were in unrelated lanes:

| Workflow run | Head SHA (abbreviated) | Alembic | DB gate | Rollback |
|---|---|---:|---:|---:|
| `34169372392` | `ba42b3d8` | `101887230488` | `101887230444` | `101888635990` |
| `34189435982` | `ff0a3d0a` | `101944701622` | `101944701467` | `101947182892` |
| `34191511980` | `1005b058e` | `101953993496` | `101953993507` | `101960459208` |
| `34194122647` | `6e330e5c` | `101961397245` | `101961397214` | `101972917321` |

Those runs did not change the migration file, so their Squawk step correctly
reported no changed migration; they are baseline/regression evidence, not a
substitute for a changed-file Squawk run on the eventual source SHA.  The
remaining required boundary is therefore a fresh CI run after the current
checkout is pushed: rerun changed-file Squawk plus PostgreSQL upgrade,
downgrade, and schema-drift gates and bind their artifacts to that exact SHA.

## Decision

No source or test fix is warranted from the stale failure description: the
reported migration and UUID defects are already closed and locally/CI verified.
Do not weaken Squawk exclusions or add test skips.  Keep the final-SHA rerun as
an evidence gate.
