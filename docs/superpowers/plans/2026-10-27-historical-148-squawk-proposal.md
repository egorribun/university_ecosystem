# Historical 148 Squawk proposal — 2026-10-27

**PROPOSED — NOT APPROVED — NOT ACTIVE.**

## Proposed decision and scope

Preserve historical revision `148642dd1207` byte-for-byte and retain its atomic
parent/child key cutover and FK restoration. Treat this path as a controlled
offline/maintenance operation, **not a zero-downtime migration**.

A separate finite, source-bound policy could account for the exact historical
observations below. These are real operational risks, **not false positives**.
This proposal activates no policy and authorizes no merge, deployment, shutdown,
external-database execution, history rewrite, scanner exclusion or new finding.

Already-authorized additive migration development remains separate. A successor
cannot change earlier historical SQL. Later revisions already convert groups/users
to UUID; moving the old INTEGER conversion to a new head revision would be wrong.

## Evidence and missing prerequisite

The inventory comes from
[the historical Alembic job](https://github.com/egorribun/university_ecosystem/actions/runs/40504891903/job/122193711183):
PR source e671440, actual tested merge ceaf5b5, PostgreSQL 17.11 and checksum-verified
Squawk 2.67.0. Ninety focused tests passed; both raw lint streams failed.

Migration, renderer, trace helper, populated fixture and Squawk configuration blobs
were identical at source 88509ed. This is source-equivalent historical migration
evidence, not fresh hosted validation of a later full source. Exact scanner and
trace digests are retained in the linked job, not inferred from version labels.

Immutable reviewed sources:

- [Migration](https://github.com/egorribun/university_ecosystem/blob/88509ed/alembic/versions/148642dd1207_fix_missing_tables.py).
- [Ordinary renderer](https://github.com/egorribun/university_ecosystem/blob/88509ed/scripts/quality/render_live_alembic_sql.py).
- [Trace helper](https://github.com/egorribun/university_ecosystem/blob/88509ed/tests/helpers/migration_148642dd1207_trace.py).
- [Populated fixture](https://github.com/egorribun/university_ecosystem/blob/88509ed/tests/integration/test_migration_148642dd1207.py).
- [Scanner configuration](https://github.com/egorribun/university_ecosystem/blob/88509ed/.squawk.toml).

**Before activation:** obtain the complete ordinary SQL capture and source-bound
digest. The historical log exposes ordinary diagnostic snippets, not a complete
ordinary capture manifest. Do not invent that digest or substitute the expanded
SQL digest. Short displayed Git identities are not sufficient future validator pins.

## Exact observed inventory

There are **37 occurrences**, **24 rule/statement groups**, and **20 statements**.
Thirteen groups occur in both streams; eleven occur only in expanded SQL.
Deduplication is explanatory only: a validator must compare both full multisets.

- **O:** ordinary live renderer, scratch database at parent `f7aa476e968a`,
  followed by execution of `148642dd1207`.
- **E:** populated instrumented
  `test_expanded_ddl_inventory_matches_unmodified_populated_control`, including
  uninstrumented-control equivalence.

| Symbol | Rule |
| --- | --- |
| C | constraint-missing-not-valid |
| I+ | require-concurrent-index-creation |
| I- | require-concurrent-index-deletion |
| F | adding-foreign-key-constraint |
| T | changing-column-type |
| D | ban-drop-column |

Statements below retain case, quoting, schema, clauses and internal whitespace.
Only the terminal semicolon is omitted.

```sql
-- S01
ALTER TABLE groups VALIDATE CONSTRAINT ck_groups_id_not_null
-- S02
CREATE UNIQUE INDEX IF NOT EXISTS groups_pkey_idx ON groups (id)
-- S03
ALTER TABLE active_sessions VALIDATE CONSTRAINT ck_active_sessions_signing_key_not_null
-- S04
DROP INDEX ix_active_sessions_user_last_seen
-- S05
CREATE INDEX ix_failed_login_attempts_user_id ON failed_login_attempts (user_id)
-- S06
DROP INDEX ix_mfa_challenges_session_id
-- S07
CREATE INDEX ix_notification_queue_jobs_kind ON notification_queue_jobs (kind)
-- S08
DROP INDEX ix_user_push_topics_updated_at
-- S09
CREATE INDEX ix_user_push_topics_user_id ON user_push_topics (user_id)
-- S10
DROP INDEX ix_users_id
-- S11
CREATE INDEX ix_users_group_id ON users (group_id)
-- S12
ALTER TABLE users ADD CONSTRAINT fk_users_group_id_groups FOREIGN KEY(group_id) REFERENCES groups (id) ON DELETE SET NULL
-- S13
ALTER TABLE aud148_fixture.child_cascade ALTER COLUMN group_id TYPE INTEGER USING group_id::INTEGER
-- S14
ALTER TABLE aud148_fixture."child quoted" ALTER COLUMN "group key" TYPE INTEGER USING "group key"::INTEGER
-- S15
ALTER TABLE aud148_fixture.child_unvalidated ALTER COLUMN group_id TYPE INTEGER USING group_id::INTEGER
-- S16
ALTER TABLE groups DROP COLUMN id
-- S17
ALTER TABLE groups DROP COLUMN id__integer
-- S18
ALTER TABLE aud148_fixture.child_cascade ADD CONSTRAINT aud148_child_cascade_fk FOREIGN KEY (group_id) REFERENCES groups (id) ON UPDATE CASCADE ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED
-- S19
ALTER TABLE aud148_fixture."child quoted" ADD CONSTRAINT aud148_child_quoted_fk FOREIGN KEY ("group key") REFERENCES groups (id) MATCH FULL ON DELETE SET NULL
-- S20
ALTER TABLE aud148_fixture.child_unvalidated ADD CONSTRAINT aud148_child_unvalidated_fk FOREIGN KEY (group_id) REFERENCES groups (id)
```

The log's SQL line numbers below are **one-based diagnostic locators**, not future
policy identities.

| Group | Statement | Rule | Ordinary occurrence / line | Expanded occurrence / line |
| --- | --- | --- | --- | --- |
| G01 | S01 | C | O01 / 50 | E05 / 62 |
| G02 | S02 | I+ | O02 / 51 | E06 / 63 |
| G03 | S03 | C | O03 / 351 | E14 / 368 |
| G04 | S04 | I- | O04 / 353 | E15 / 370 |
| G05 | S05 | I+ | O05 / 355 | E16 / 372 |
| G06 | S06 | I- | O06 / 356 | E17 / 373 |
| G07 | S07 | I+ | O07 / 357 | E18 / 374 |
| G08 | S08 | I- | O08 / 358 | E19 / 375 |
| G09 | S09 | I+ | O09 / 359 | E20 / 376 |
| G10 | S10 | I- | O10 / 373 | E21 / 390 |
| G11 | S11 | I+ | O11 / 374 | E22 / 391 |
| G12 | S12 | C | O12 / 375 | E23 / 392 |
| G13 | S12 | F | O13 / 375 | E24 / 392 |
| G14 | S13 | T | — | E01 / 54 |
| G15 | S14 | T | — | E02 / 55 |
| G16 | S15 | T | — | E03 / 56 |
| G17 | S16 | D | — | E04 / 58 |
| G18 | S17 | D | — | E07 / 65 |
| G19 | S18 | C | — | E08 / 66 |
| G20 | S18 | F | — | E09 / 66 |
| G21 | S19 | C | — | E10 / 67 |
| G22 | S19 | F | — | E11 / 67 |
| G23 | S20 | C | — | E12 / 68 |
| G24 | S20 | F | — | E13 / 68 |

The ordinary multiset contains 13 occurrences, expanded contains 24.
The three fixture table names do not authorize arbitrary production child tables.
A production FK inventory is a separate preflight requirement.

## Maintenance risks and execution prerequisites

Index creation/deletion and constraint/FK validation hold blocking locks.
Child-column type changes can rewrite tables. Dropping the old key representation
breaks old clients. Adding `CONCURRENTLY`, `COMMIT` or `autocommit_block()`
mechanically would destroy the existing rollback invariant, not prove equivalence.

Any future execution requires:

1. An explicitly owned target and secret-backed identity, with no credentials in
   argv/logs; verified applied revision and supported catalog state.
2. Read-only parent/child type, FK, index, CHECK and validation-state inventory;
   NULL, cast-range, cast-duplicate, orphan and stale-shadow checks. Unsupported
   composite FKs and unknown state must fail closed.
3. All readers and writers stopped, including external clients and workers,
   with reconnection prevented throughout the maintenance window.
4. A separately tested backup/restore plan; critical conditions rechecked under
   migration locks to avoid preflight TOCTOU.
5. Unchanged 10-second lock and 60-second statement timeouts. These are failure
   limits, not a proven downtime budget or authorization to increase them.

`live_stand.quiesce` stops signed owned Core services and explicitly says external
writers are not verified; it cannot certify all external readers/writers absent.
`be02_catalog_preflight.py` supports ADR-036 phases 1, 3 and 4, not historical148.

Rollback here means rollback of an uncommitted transaction after error. It does not
establish full-chain downgrade safety after commit, override ADR-036 irreversible
boundaries, or prove paired database/object-store restoration.

If downtime is unacceptable, a separate expand/backfill/dual-write/validate/cutover/
contract path needs compatibility and forward-recovery proofs. It is substantially
more complex and still does not eliminate the existing historical lint input.

## Proposed narrow validator — not implemented

After approval of an exact diff, use one historical148-specific validator and
inventory, not a general exception framework. Keep this separate from finite131
coverage, secret dispositions and unsupported-downgrade policy.

The eventual contract must bind full migration/config/helper/fixture pins, scanner
version and binary digest, relevant consumer arguments, both complete SQL digests,
scenario IDs, all 37 occurrences with multiplicity, normalization version, owner
approval evidence and expiry. Record source/run/attempt/job and workflow provenance;
unrelated workflow edits must not silently broaden the relevant consumer contract.

Use Squawk 2.67.0's
[JSON reporter](https://github.com/sbdchd/squawk/blob/v2.67.0/crates/squawk/src/reporter.rs),
not ANSI parsing. JSON positions are zero-based. Preserve raw JSON, stderr and exit
status separately from any policy verdict.

Required fail-closed behavior:

- Reject missing, symlink, oversized, malformed, truncated or invalid-UTF-8 inputs;
  wrong source/provenance/path/span and unsupported scanner exits.
- Preserve real ordinary execution, five bounded instrumentation sites,
  uninstrumented-control equality and successful transaction evidence.
- Require exact known warning rules. Syntax errors, crashes, timeouts, unexpected
  stderr and warnings in other migrations remain blocking.
- Match each complete physical SQL line. Strip only framing newline and one final
  semicolon; do not collapse whitespace, lowercase, remove schema or unquote names.
- Compare each scenario's exact multiset independently. Extra, missing, duplicate,
  changed or substituted observations fail; fewer findings also require review.
- Reject missing approval, draft status and expired or ambiguous UTC expiry.
- Keep every migration in the lint loop. No `continue-on-error`, `|| true`,
  `--exclude`, changed diff base or conditional bypass.
- Keep raw Squawk exit 1 visible even if an explicitly approved policy verdict later
  accepts the exact historical risk. Never label raw failure as scanner success.

Negative tests must cover changed source/scanner/config/fixture pins; changed clauses
and quoting; extra/missing/duplicate observations; scenario/table substitution;
forged manifest/path/span; malformed output, crash and timeout; absent approval and
expiry boundaries; trace/control mismatch; unrelated migration warnings; preservation
of raw failure, all 78 required context/app pairs, blocking CodeQL, hooks and floors.

**Proposed, not approved expiry:** 2026-11-13 at 00:00 UTC. Sharing the finite131
review horizon grants no Squawk permission. Expiration fails closed; no automatic
extension or expansion is authorized.

## Owner decision and remaining boundaries

Complete the ordinary capture and present the exact inventory/validator/tests/
consumer diff before requesting a narrow owner decision:

> Разрешить только конечную source-bound обработку перечисленных historical148
> findings для документированного offline/maintenance-пути; сохранить неизменную
> миграцию, raw Squawk evidence и блокировку новых/изменённых результатов.
> Не разрешать deployment, merge, глобальные exclusions или изменение rollback
> boundaries.

This document records no approval. Raw migration gates remain unchanged and red.

AUD-164/AUD-167 still require actual trusted-peer, two-client and spoof evidence;
AUD-169 requires actual CNI positive/negative reachability. Render/unit contracts and
generic Core smoke success do not replace these receipts. Deployed migration proof,
paired restore, full CI and release readiness remain separate.
