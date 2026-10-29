# Historical 148 Squawk preparation — 2026-10-29

**PREPARATION AUTHORIZED — MATCHER INACTIVE — RAW GATES UNCHANGED.**

## Authorized preparation and restricted scope

Preserve historical revision `148642dd1207` byte-for-byte and retain its atomic
parent/child key cutover and FK restoration. The owner authorized preparation of
a finite CI rule and tests on 2026-10-28, limited to creating a **new empty MVP
database** through 2026-11-13 at 00:00 UTC. This is not permission to run the
historical migration against a populated database or to deploy.

This Stage A package is deliberately inactive. Historical operations still carry
blocking-lock, table-rewrite and destructive-column risks; matching their exact
diagnostics does not eliminate those risks or prove a zero-downtime migration.

A separately reviewed, source-bound consumer could eventually account for the
exact historical observations below, only after the missing admission and
all-migration evidence described here exists. These are real operational risks, **not false positives**.
This proposal activates no policy and authorizes no merge, deployment, shutdown,
external-database execution, history rewrite, scanner exclusion or new finding.

Already-authorized additive migration development remains separate. A successor
cannot change earlier historical SQL. Later revisions already convert groups/users
to UUID; moving the old INTEGER conversion to a new head revision would be wrong.

## Complete historical capture and its limits

The [15eaaa Alembic job](https://github.com/egorribun/university_ecosystem/actions/runs/40787466183/job/123165735779)
captured both complete SQL inputs and the Squawk JSON reporter. PR source
`15eaaa5194642a4f3e52b5207f57235df968cb8e` was tested as merge
`37b82de67516752bb8c11462759b381c533db7fd`. The independent fixture
[`historical148-squawk-capture-15eaaa.json`](../../../tests/fixtures/historical148-squawk-capture-15eaaa.json)
retains the ordinary capture, expanded diagnostic metadata/SQL, both raw JSON
streams, their exit codes and provenance. No credentials or database row values
are introduced by this fixture.

The [114df35 Alembic job](https://github.com/egorribun/university_ecosystem/actions/runs/40795451774/job/123191731137)
repeated exactly the same ordinary SQL (17,031 bytes) and expanded SQL (18,373
bytes), with 13 and 24 warnings respectively. Both raw exits were 1 and both
JSON-reporter stderr streams were empty. SQL digests, source pins, full warnings,
locations and the seven existing ordered `--exclude` arguments are recorded
in [the inactive policy](../../../quality/historical148-squawk-policy.json).
The rule does not introduce an exclusion; the existing arguments are not
misrepresented as an exclusion-free scan.

The old missing-ordinary-capture prerequisite is resolved for this historical
inventory only. Neither captured run proves that `template1` is empty, that an
arbitrary target is owned, or that all other revisions have strict lint receipts.
The fixture describes the 15eaaa source, not a new source's successful scan.
Changed migration/configuration/helper/fixture/scanner or consumer identities
require explicit review and a new source-bound capture.

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

## Stage A: inactive compiled historical diagnostic recognizer

This package prepares one historical148-specific recognizer and inventory, not a
general exception framework. Keep it separate from finite131 coverage, secret
dispositions and unsupported-downgrade policy. The
[pure matcher](../../../scripts/quality/validate_historical148_squawk.py) recognizes
only the compiled fingerprints of the exact prepared policy and historical
capture. A caller cannot authorize a replacement policy by supplying matching
changed findings. No CLI, subprocess, database, file reader or migration-gate
consumer is connected.

Its only positive return is `matched-diagnostic-inventory`: neither scanner
success nor migration permission. The source accepts two bounded byte strings
and checks the real UTC clock internally, with no caller clock or expiry
override. Tests can monkeypatch the module clock to exercise the boundary. Policy
status remains `prepared-inactive`, never an active waiver.

The fingerprints retain all migration/config/helper/fixture pins, scanner version
and binary digest, existing ordered arguments, both complete SQL inputs, scenario
IDs, all 37 occurrences with multiplicity, normalization version, owner/scope/
decision fields, expiry and source/run/attempt/job/workflow declarations. This is
recognition of one historical capture, not authentication of a new run, file
ownership, freshness or empty-database admission.

The reproducible recipe is compact ASCII JSON with sorted object keys and no
terminal newline. Preserve every field and all array order except each raw
warning array: parse it strictly, sort complete rows by their canonical JSON
strings without deduplicating, and serialize that array back to its JSON string.
SQL strings are not normalized. The two source constants are derived from the
committed [policy](../../../quality/historical148-squawk-policy.json) and
[capture](../../../tests/fixtures/historical148-squawk-capture-15eaaa.json), never
from caller-supplied approval data. The
[contract tests](../../../tests/test_historical148_squawk_policy.py) and required
checks need exact published-source receipts; this source description is not a
passing test, scanner, full-CI or deployment receipt.

Use Squawk 2.67.0's
[JSON reporter](https://github.com/sbdchd/squawk/blob/v2.67.0/crates/squawk/src/reporter.rs),
not ANSI parsing. JSON positions are zero-based. Preserve raw JSON, stderr and exit
status separately from any policy verdict.

Required fail-closed behavior and later-consumer constraints follow. Operational
requirements still belong to Stage B; recognizing the historical bytes does not
supply those receipts:

- Future file adapters must reject missing/symlink inputs; the Stage A pure
  byte interface does not authenticate file ownership or freshness.
- Reject oversized, malformed, truncated or invalid-UTF-8 inputs;
  wrong source/provenance/path/span and unsupported scanner exits.
- Preserve real ordinary execution, five bounded instrumentation sites,
  uninstrumented-control equality and successful transaction evidence.
- Require exact known warning rules. Syntax errors, crashes, timeouts, unexpected
  stderr and warnings in other migrations remain blocking.
- Preserve both complete SQL strings byte-for-byte. Historical policy statement
  extraction removed only line framing and one terminal semicolon; the recognizer
  does not re-render or normalize SQL, lowercase, remove schema or unquote names.
- Compare each scenario's exact multiset independently. Extra, missing, duplicate,
  changed or substituted observations fail; fewer findings also require review.
- Keep preparation approval distinct from activation. The diagnostic matcher
  accepts only the exact prepared-inactive policy; a future gate must reject
  inactive policy and cannot infer activation from a successful match.
- Reject changed owner/scope/decision fields and expired or ambiguous UTC expiry.
- Keep every migration in the lint loop. No `continue-on-error`, `|| true`,
  new `--exclude`, changed diff base or conditional bypass.
- Keep raw Squawk exit 1 visible even if an explicitly approved policy verdict later
  accepts the exact historical risk. Never label raw failure as scanner success.

Negative tests must cover changed source/scanner/config/fixture pins; changed clauses
and quoting; extra/missing/duplicate observations; scenario/table substitution;
forged manifest/path/span; malformed output, crash and timeout; absent approval and
expiry boundaries; trace/control mismatch; unrelated migration warnings; preservation
of raw failure, all 78 required context/app pairs, blocking CodeQL, hooks and floors.

**Preparation horizon:** 2026-11-13 at 00:00 UTC. Sharing the finite131 review
horizon does not merge the two policies. Expiration fails closed; no automatic
extension or expansion is authorized.

## Stage B prerequisites — not implemented or activated

A later exact consumer diff still requires review. Before any narrow risk
disposition can affect a CI result, it must establish:

1. A separately owned fresh database created from `template0`, with verified
   empty user-object/data catalogs before preparation and checked expected state
   afterwards. Self-declared JSON is not admission evidence.
2. A new SQL/JSON capture after changing the renderer, while keeping the
   historical migration and transaction boundaries immutable.
3. Graph-aware handling of merge revisions and strict coverage of all 141 other
   migration files in the current 142-file inventory. The current
   `read_alembic_revision.py` supports only a string or `None` parent and does
   not yet support merge-parent tuples.
4. Source-bound preservation of ordinary execution, all five diagnostic trace
   sites and the successful uninstrumented-control comparison.
5. Real shell failure-propagation tests: unexpected, changed, missing or
   duplicate warnings; scanner errors; expired policy; unrelated migration
   failures; and failed admission must block. A later successful step cannot
   erase an earlier raw failure.

The current renderer inherits `template1`; that is not an empty-database proof.
This Stage A adds none of these missing operational receipts and changes no
migration workflow logic, scanner exit handling, migration, active policy or accepted audit ID.
Raw migration gates remain blocking. No populated-database execution, merge,
deployment, atomicity rewrite, new exclusion or coverage reduction is authorized.

AUD-164/AUD-167 still require actual trusted-peer, two-client and spoof evidence;
AUD-169 requires actual CNI positive/negative reachability. Render/unit contracts and
generic Core smoke success do not replace these receipts. Deployed migration proof,
paired restore, full CI and release readiness remain separate.
