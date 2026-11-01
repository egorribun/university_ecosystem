# ADR-051: MVP migration baseline squash

## Status and date

Accepted by the repository owner on 2026-11-02. The decision is not a passing
check. The baseline's Squawk inventory, its 100% Tier 0 coverage, the Alembic
schema drift gate, the downgrade planner boundary and the amended quality
ledgers are validated only by the hosted checks of the implementing change.

## Context

Through commit `3ff5375fba01b6ff6f2bc18aaf2d6b2ba18e19c9` (the pre-squash
commit), `alembic/versions/` held 143 revisions, from the initial revision
`b05ae64aaeef` to the single head `202610310001`.

Four properties of that chain no longer serve the MVP:

- Historical revisions were corrected in place when defects were found. The
  Squawk gate lints changed migration files, so those corrections produced 846
  Squawk findings on historical files that no forward change touches.
- Revision `148642dd1207` could pass Squawk only through an owner-activated,
  exact-inventory admission with its own scanner, policy, fixtures and test
  family, as recorded in ADR-047.
- ADR-047 carries a finite no-decrease Tier 0 exception for exactly 131
  unchanged Alembic files, source-bound to `ac74e915`. It expires on
  2026-11-13 and does not cover new, modified or PR-touched migrations.
- The platform has never been deployed. No environment is bound to the
  historical chain, and the chain has no production rollback path to protect.

Migration-history audit findings AUD-208, AUD-226, AUD-269, AUD-270, AUD-272,
AUD-274, AUD-275, AUD-277, AUD-278, AUD-327, AUD-348, AUD-350, AUD-351,
AUD-393 and AUD-433 describe defects in specific historical revisions. The
audit register remains the record of those findings.

## Decision

On 2026-11-02 the repository owner decided the following.

1. Replace the 143 revisions with one baseline revision, `202611020000`
   (`alembic/versions/202611020000_mvp_baseline.py`, `down_revision = None`),
   and delete the historical revision files.
2. The baseline reproduces the PostgreSQL schema of the pre-squash chain. It
   adds two owner-approved objects: the eight hot-path indexes that AUD-269
   restores, and the `notification_delivery_once` claim ledger for AUD-272.
3. The baseline declares `downgrade_policy = "irreversible"`. Its
   `downgrade()` raises before it changes any schema. Recovering an earlier
   state uses a consistent backup and restore set, not Alembic.
4. The historical revision tests, their fixtures and the 148-specific
   admission machinery are deleted with the revisions. Their quality-ledger
   entries (detect-secrets dispositions, public git-blob and public revision
   identities, and the 131-file legacy baseline) are removed in the same change.

## Consequences

Databases and rollback

- There is no upgrade path from a pre-squash database. A database whose
  `alembic_version` names a pre-squash revision, such as `202610310001`,
  cannot run `alembic upgrade head`. Local development databases must be
  recreated. This decision does not stamp existing environments.
- Downgrade below the baseline is irreversible by policy. The planner treats
  `202611020000` as the boundary, and a downgrade to base is refused.

Retired controls and their replacements

- The historical-148 Squawk admission for `148642dd1207` ends with the
  revision. The baseline is linted as a changed migration. A Squawk finding on
  it blocks the change. This ADR authorizes no rule suppression.
- The 131-file Tier 0 legacy exception in ADR-047 no longer matches any file.
  It is retired by removing those files, not extended. The baseline is a new
  Tier 0 migration and must reach 100% line, statement, branch and function
  coverage like every other Tier 0 file. This ADR grants no coverage
  exception. The ADR-047 text is not amended here; that amendment is a
  separate ADR-047 change.
- Historical migration tests that asserted the behaviour of retired revisions
  are deleted. No replacement offline check of those revisions is kept. The
  schema-level behaviour they covered is covered only by the schema-equivalence
  proof described below, which compares catalog objects, including row-level
  security policies, triggers, functions, roles and ACLs.

Audit findings

- AUD-208, AUD-226, AUD-270, AUD-274, AUD-275, AUD-277, AUD-278, AUD-327,
  AUD-348, AUD-350, AUD-351, AUD-393 and AUD-433 are resolved by removing the
  defective historical code. The schema-equivalence proof and its catalog
  comparison (including RLS policies) evidence that the baseline carries no
  such defect.
- AUD-269 and AUD-272 are resolved by the two explicit additions in the
  baseline. The equivalence test accepts no other difference from the
  pre-squash schema.
- None of these findings is accepted as a residual risk. This ADR does not
  change their status in `docs/audits/`; that update belongs to the audit
  register's own review.

## Evidence

- Pre-squash commit `3ff5375fba01b6ff6f2bc18aaf2d6b2ba18e19c9`. Permanent
  links to retired migration and test files are pinned to this commit.
- `tests/integration/test_mvp_baseline_schema_equivalence.py` is opt-in
  (`RUN_INTEGRATION_TESTS=1`). It runs the pre-squash chain and the baseline in
  two PostgreSQL databases. `pg_dump --schema-only` may differ only by
  statements that create the two added objects and the partition children of
  the restored notifications index. Catalog facts that `pg_dump`
  omits must match, and both databases must match the models. The baseline's
  downgrade must refuse without changing the schema.
- The owner decision of 2026-11-02 records the equivalence as proven. This ADR
  does not record a run of that test.

## Not decided here

- The baseline's Squawk inventory, its coverage, the schema drift gate result
  and any runbook for an existing environment are validated by the implementing
  change's hosted checks.
- The rollback-boundary section of ADR-036 and the Tier 0 exception text of
  ADR-047 need their own amendments through their ADR processes.
