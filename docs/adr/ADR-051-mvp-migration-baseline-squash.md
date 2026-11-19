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
- Owner approval of 2026-11-03 (in chat): one exact replacement of the
  `messages_participant_isolation` policy with the `NULLIF` form, so an unbound pooled session denies with zero rows instead of raising 22P02; it is the only approved statement and catalog removal.

## Not decided here

- The baseline's Squawk inventory, its coverage, the schema drift gate result
  and any runbook for an existing environment are validated by the implementing
  change's hosted checks.
- The rollback-boundary section of ADR-036 and the Tier 0 exception text of
  ADR-047 need their own amendments through their ADR processes.


## Delivery claim lifetime

The AUD-272 ledger identifies a notification/subscription/channel pair without
an attempt timestamp. Successful results commit before subscription side effects.
The provider call and database commit cannot be atomic, so a crash between them
still permits at-least-once delivery; this is not an exactly-once transport claim.
Notification retention removes old ledger entries only after the corresponding
notification is absent. In particular, an old unread notification retains its
claim, even after its delivery-attempt history expires, and cannot be replayed
just because cleanup ran. Cleanup uses the existing retention window and bounded
batch size; no new retention setting or schema object is introduced.



## Addendum: exact empty-schema Squawk exception (2026-11-03)

The owner authorizes only `require-concurrent-index-creation`,
`constraint-missing-not-valid`, `adding-foreign-key-constraint`,
`prefer-text-field` and `prefer-bigint-over-int` to be disabled
for `alembic/versions/202611020000_mvp_baseline.py`. This supersedes the earlier
no-suppression statement for this exact path and rule set only. Every other
migration retains the complete rule set; global configuration excludes no rule.
Squawk 2.67.0 uses `excluded_rules`, not `exclude-rules`.

The baseline is for a fresh, quiescent PostgreSQL database. Before schema DDL it
rejects existing application namespaces or public namespace objects, apart from
Alembic version bookkeeping, whose ledger must be empty. Preinstalled extensions
that own public objects are deliberately not admitted. No deployed upgrade path,
concurrent-migrator safety or new schema-equivalence exception is granted.
The bookkeeping exemption presumes Alembic created the empty version ledger;
it does not attest the shape of an arbitrary preexisting relation with that name.

Acceptance still requires the owned PostgreSQL refusal test, exact-scope negative
contracts, unchanged schema equivalence and raw pinned Squawk reporting zero
findings with only these five exclusions. This addendum records authorization,
not passing hosted evidence.

The owner approved the two additional type-style exclusions on 2026-11-03
after hosted CI identified `prefer-text-field` and `prefer-bigint-over-int`
on the baseline. Changing those types would change the approved schema. This
permission preserves the schema and applies only to the same baseline path; it
does not authorize any further rule exclusion, global exception or schema drift.

## Addendum: AUD-272 constraint replacement and retired populated-database criteria (2026-11-04)

Two owner decisions were given in chat on 2026-11-04. This addendum records them. It
does not change the Status section above, and it is not a passing check.

1. Second approved replacement in the schema-equivalence proof. The owner approved
   the removal of the redundant `uq_notification_delivery_once UNIQUE (notification_id,
   channel, subscription_id, attempted_at)` constraint from `notification_deliveries`.
   It is removed from the baseline `202611020000` and from the ORM model. The
   pre-squash chain (`3ff5375fb`) still creates it, so the equivalence proof lists
   exactly this removal as its second approved replacement, after the
   `messages_participant_isolation` NULLIF form approved on 2026-11-03. The removal is
   the parent constraint, the constraint and index-attachment statements of each of the
   26 partitions, and the 26 inherited partition-index catalog rows. No other statement
   or catalog row is allowed to differ.
   The AUD-272 delivery-once guarantee is the claim ledger `notification_delivery_once`,
   keyed on `(notification_id, subscription_id, channel)` with `NULLS NOT DISTINCT`.
   The 2026-11-03 bullet above, which describes the replacement as the only approved
   statement and catalog removal, is superseded by this item. The baseline still adds
   the ledger and the eight restored indexes. It no longer contains the redundant
   attempt-keyed constraint that the pre-squash chain created.

2. Populated-database criteria retired for the MVP baseline. The owner stated in chat on
   2026-11-04 that no populated pre-squash database exists anywhere: not in production,
   staging or with testers. The platform has never been deployed, and the baseline
   has no upgrade path from a pre-squash database (see Consequences above). The
   upgrade-of-populated-database criteria of AUD-275, AUD-327, AUD-348, AUD-350,
   AUD-393 and AUD-433 are therefore retired for the MVP baseline. Closure for those
   IDs is the removal of the defective historical code together with the
   schema-equivalence receipt described in the Evidence section. No populated-data
   migration test or runbook is required for them. This addendum does not change
   their status in `docs/audits/`.


## Addendum: AUD-269 exact lower-email index replacement (approved 2026-11-05 UTC; recorded 2026-11-06 Europe/Istanbul)

On 2026-11-05 UTC (2026-11-06 Europe/Istanbul), the repository owner approved
this exact additional schema-equivalence delta. Approval is limited to the DDL
statements and catalog rows listed below; it does not change AUD-269's audit
status or establish the owned-PostgreSQL schema-equivalence receipt.

The approved additional schema-equivalence difference is limited to the
pre-squash index statement and catalog row for
ix_users_email_lower being replaced by the baseline statement and catalog row
for ux_users_lower_email:

- Removed DDL: CREATE UNIQUE INDEX ix_users_email_lower ON public.users USING btree (lower((email)::text))
- Added DDL: CREATE UNIQUE INDEX ux_users_lower_email ON public.users USING btree (lower((email)::text))
- Removed catalog projection `(table, index, access method, unique, valid, ready, live, primary, definition)`: ('users', 'ix_users_email_lower', 'btree', True, True, True, True, False, 'CREATE UNIQUE INDEX ix_users_email_lower ON public.users USING btree (lower((email)::text))')
- Added catalog projection `(table, index, access method, unique, valid, ready, live, primary, definition)`: ('users', 'ux_users_lower_email', 'btree', True, True, True, True, False, 'CREATE UNIQUE INDEX ux_users_lower_email ON public.users USING btree (lower((email)::text))')

Both definitions preserve one unique btree index on the users lower(email)
expression; at the PostgreSQL DDL/catalog level, the index name is the only
difference. This does not claim application error-diagnostic equivalence across
app revisions. The service pinned to the pre-squash commit
`3ff5375fba01b6ff6f2bc18aaf2d6b2ba18e19c9` recognizes both
ix_users_email_lower and ux_users_lower_email, while current
app/services/user/compliance_service.py recognizes
ux_users_lower_email but not ix_users_email_lower. The current
registration regression at tests/test_aud345_444_registration.py:263-264
expects ix_users_email_lower to map to 400 and ux_users_lower_email to map to
200. The baseline is fresh-schema-only and has no pre-squash upgrade path.
The catalog projection includes `indislive`; in the sequential fresh-schema
comparison each captured index must be live, valid, and ready. The
2026-11-01 AUD269 source review records ux_users_lower_email and
ix_users_email_lower as source-equivalent unique lower(email) indexes. The
pinned chain creates ux in 202507310004, later creates ix in
f2d2414a6b67, then drops ux in 202603280001. The current ORM and
duplicate-email conflict mapping use the ux name.

The equivalence proof may allow only this exact removal/addition
pair and the catalog rows above, with all other DDL and catalog facts still
identical. This approval does not authorize other renames, schema drift,
populated-database upgrades, or historical migration rewrites. The actual
owned-PostgreSQL schema-equivalence receipt remains mandatory and is not
established by the source-only harness.
