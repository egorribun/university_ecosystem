# ADR-036: SQLAlchemy Dual-Defaults Migration Policy

## Status

Accepted

## Date

2026-09-10

## Context

The backend convention requires a model default and a PostgreSQL server
default to agree for values that may be created by either the ORM or a direct
SQL/microservice writer. An independent platform audit reported 92 columns
without this dual declaration. That number was taken from an older snapshot and
cannot be reproduced on the current source; changing dozens of model fields
without inspecting the deployed PostgreSQL catalog could overwrite business
semantics, create migration locks or introduce unsafe defaults for secrets and
identifiers.

The purpose of this decision is to replace the stale count with a measured
inventory and to define a safe, owner-scoped migration boundary. It does not
pretend that source metadata alone proves the DDL of every deployed database.

## Inventory

The current SQLAlchemy metadata (re-measured 2026-09-20 after phase two)
contains 45 tables and 134 effective defaulted columns (computed expressions
and `default=None` excluded):

- 53 declarations have both an ORM and server default;
- 81 effective declarations are Python-only;
- 0 declarations are server-only.

The source-level AST inventory contains 108 `mapped_column` calls with a
`default` or `server_default` keyword: 53 both, 55 Python-only and 0
server-only. The effective/source difference includes UUIDv7 primary-key
defaults inherited from the mixin and explicit `default=None` declarations;
the candidate list must therefore be generated from both metadata and the
PostgreSQL catalog rather than inferred by subtracting totals. These figures
supersede the external audit's stale 92-column number and must be regenerated
after model changes. Phase one intentionally leaves the remaining owner-scoped
candidates pending their own catalog-backed migrations.

## Decision

We will converge applicable model fields to dual defaults in small, reviewed
phases. No blanket rewrite or guessed SQL expression is permitted. Every
phase starts with a PostgreSQL catalog preflight and ends with upgrade,
downgrade, ORM and direct-write evidence.

## Migration Policy

1. **Inventory first.** Compare SQLAlchemy metadata with `pg_get_expr` /
   `column_default`, nullability, existing NULL counts, enum/string values,
   JSON/JSONB type and the current Alembic head for every candidate.
   The checked-in `quality/model-default-policy.json` and the CI-generated
   `model-default-inventory.json` provide the source/metadata baseline and
   bind it to the current commit SHA and migration head; they intentionally
   report the PostgreSQL catalog as not checked.
2. **Backfill before constraints.** For existing rows, use a bounded,
   idempotent backfill, then add `CHECK ... NOT VALID`, validate it, and only
   then set a server default or `NOT NULL` where the domain contract requires
   it. Avoid table rewrites and long blocking locks.
3. **Low-risk scalar phase.** Handle flags, counters and statuses with
   unambiguous values first, reusing already deployed DDL where possible.
4. **Python-side completion phase.** Add ORM defaults to server-only
   timestamps/scalars, including composite-key and partition columns, using
   timezone-aware UTC values that match PostgreSQL `CURRENT_TIMESTAMP`.
5. **Timestamp phase.** Verify clock-skew, timezone and serialization behavior
   on PostgreSQL and SQLite test paths before changing `created_at` or
   `updated_at` declarations.
6. **JSON phase.** Add dialect-aware expressions only after confirming the
   column is JSON/JSONB and round-trip semantics are tested; never use a text
   literal as a guessed JSON default.
7. **Operational bounds.** Every migration documents lock/statement timeouts,
   idempotent preflight output, rollback behavior and downgrade policy. A
   migration warning must be eliminated by its construction, not ignored.

### Phase one: authentication and registration boolean flags

Revision `202609150001` covers the following ten non-secret scalar columns:

```text
active_sessions.mfa_required
mfa_totp_enrollments.is_active
password_reset_tokens.used
email_change_tokens.used
recovery_codes.is_used
login_history.is_suspicious
users.is_active
users.mfa_required
invite_codes.is_active
invite_codes.is_used
```

Before changing any column, the revision checks that the live PostgreSQL
catalog reports a boolean type and either no default or the exact reviewed
literal. NULL rows are updated in `ctid` batches of 1,000 under a 60-second
statement timeout. A nullable column receives a `CHECK (column IS NOT NULL)
NOT VALID`, the check is validated, and only then is `SET NOT NULL` issued;
the server default is installed last. Every identifier is validated and
quoted, and an advisory transaction lock serializes concurrent applications.
The downgrade is deliberately contract-preserving: it verifies the same
catalog invariants and retains matching defaults/constraints because Alembic
cannot prove ownership of equivalent objects that pre-date this revision.

### Phase two: Python-side completion for server-only defaults

Every column that carried a PostgreSQL default but no ORM default now declares
one. This is the class the audit's stated impact actually describes: a freshly
instantiated entity left the attribute unpopulated, so `model_validate(
from_attributes=True)` forced a database roundtrip and raised `MissingGreenlet`
on async paths. The seventeen columns are:

```text
data_access_logs.created_at            news_likes.created_at
event_attendance.registered_at         notification_deliveries.attempted_at
events.created_at                      notification_queue_jobs.enqueued_at
invite_codes.created_at                notifications.created_at
news.created_at                        push_subscriptions.created_at
news_comments.created_at               tenants.created_at
tenants.is_active                      user_push_topics.updated_at
user_stats.last_computed_at            users.created_at
vector_chunks.created_at
```

Sixteen are `DateTime(timezone=True)` columns whose server default is `now()`;
they receive `default=lambda: datetime.now(UTC)`, matching both the existing
dual-declared timestamps in `app/models/auth.py` and PostgreSQL's
`CURRENT_TIMESTAMP` semantics. `tenants.is_active` receives `default=True` to
mirror its `server_default="true"`.

This phase deliberately emits **no DDL and no migration**. A Python-side
`default=` is applied by the ORM before the INSERT and never renders into
`CREATE TABLE`; only `server_default` does. `tests/test_alembic_schema_drift.py`
passes unchanged, which is the evidence that the deployed catalog is untouched
and that no lock, backfill or rewrite was required. The catalog preflight
mandated for DDL phases therefore does not gate this one -- but it still gates
every remaining phase.

`user_push_topics.updated_at` and `user_stats.last_computed_at` keep their
server-side `onupdate=func.now()`. Adding a Python-side `onupdate` would move
UPDATE-time clock authority from PostgreSQL to the application, which is a
separate contract change and is out of scope here.

At the close of phase two the 81 Python-only declarations were still
untouched. They are the low-risk scalar, timestamp and JSON phases, and each
requires its own catalog-backed migration; phase three below takes the first
of them.

### Phase three: literal non-secret scalar defaults

Revision `202609220001` converges the class named in step 3 above: the
Python-only declarations whose default is a literal, non-secret scalar.
Twenty-nine columns qualify -- seven booleans, eleven integers, five floats
and six short enumerated strings -- across the dead-letter, events, chat,
notification, schedule, Spotify, stats and vector domains:

```text
dead_letter_jobs.max_retries           user_stats.attendance_percent
dead_letter_jobs.retry_count           user_stats.attendance_present
dead_letter_jobs.status                user_stats.attendance_total
events.is_active                       user_stats.attendance_trend
failed_outbox_events.retry_count       user_stats.grades_average
grades.assessment_type                 user_stats.grades_trend
messages.read_status                   user_stats.participation_events
notification_deliveries.channel        user_stats.participation_groups
notification_deliveries.status         user_stats.participation_hours
notifications.read                     user_stats.participation_trend
schedule.parity                        vector_chunks.chunk_index
spotify_integrations.is_connected      vector_chunks.is_active
spotify_integrations.is_playing
stored_events.error_count
stored_events.status
stored_events.version
user_preferences.dnd_enabled
```

The structure mirrors phase one exactly: fail-closed catalog preflight,
bounded NULL backfill in `ctid` batches, `CHECK ... NOT VALID` validated
before `SET NOT NULL`, the server default installed last, and a
contract-preserving downgrade. It adds one guard phase one did not need --
each spec declares a type family, and a column whose deployed type falls
outside it aborts the phase rather than receiving a literal PostgreSQL might
coerce differently than the ORM does.

Unlike phase two, this phase changes both halves: the migration writes the
catalog default and the mapped columns now declare the matching
`server_default=`. Declaring only one half is worse than neither, because
autogenerate then proposes dropping the default the migration just installed;
`tests/test_be02_literal_scalar_defaults_migration.py` fails closed on that.
The inventory moves accordingly, from `both: 53 / python_only: 81` to
`both: 82 / python_only: 52`.

Deliberately excluded, each awaiting its own phase: the thirty-seven UUIDv7
primary keys (no PostgreSQL equivalent preserves identity semantics), the
eleven timestamps (`now()` and a Python `datetime.now(UTC)` disagree about
clock authority inside a transaction), `active_sessions.signing_key` (secret
material), the two JSON columns defaulting to `list`, and `users.role`, whose
catalog form `'student'::userrole` is a cast to a named enum type rather than
a literal in any of this phase's four families. Those five groups sum to the
fifty-two Python-only columns that remain, so every one is accounted for.

Verification performed against `pgvector/pgvector:pg16`: the full migration
chain applied from scratch, upgrade installing every default and `NOT NULL`,
downgrade then re-upgrade proving idempotency over existing defaults,
restoration of a column stripped of its default and `NOT NULL`, and a NULL
backfill exercised on a real row. That preflight earned its keep immediately:
PostgreSQL stores a float default as the quoted literal `'0'::double
precision`, which the normalizer had to learn to strip on both sides. A
container built from migrations proves correctness, not safety against
production data -- the **deployed** catalog preflight this ADR mandates still
gates acceptance.

## Exceptions

The following values remain intentionally application-only unless a separate
security/schema decision changes their contract:

- inherited UUIDv7 primary-key defaults: a database fallback could destroy
  the time-ordered UUIDv7 invariant;
- `active_sessions.signing_key`: a PostgreSQL default must never replace the
  CSPRNG secret generator;
- `push_subscriptions.topics` and `user_push_topics.topics`: JSON defaults
  require an explicit dialect/type and round-trip decision.

`Computed` columns and `default=None` declarations are not effective defaults
and are excluded from the dual-default denominator. Each exception must be
named in the migration/quality inventory rather than hidden by a broad
coverage exclusion.

## Required Verification

- PostgreSQL catalog preflight proves the actual default, nullability and NULL
  count before and after each migration.
- Raw SQL inserts that omit defaulted fields and normal ORM flush/serialization
  both pass, including async paths without `MissingGreenlet`.
- Exact enum/string values, UTC timestamps and JSON round trips are covered.
- Alembic upgrade and downgrade are exercised on a PostgreSQL integration
  database; constraints are validated before becoming enforced.
- UUIDv7 ordering and signing-key unpredictability regressions remain green.
- Fresh current-SHA coverage, mutation, schema-drift and security evidence is
  required before a phase is accepted.

## Consequences

### Positive

- The external audit's stale metric is replaced with a reproducible, scoped
  inventory.
- Direct SQL and ORM writers converge safely without weakening UUID or secret
  invariants.
- PostgreSQL lock, backfill and rollback risks are explicit and testable.

### Negative

- Several owner-scoped migrations and a live PostgreSQL preflight remain before
  every candidate is dual-declared.
- Source metadata and deployed DDL may differ until the catalog evidence is
  collected, so local SQLite tests cannot certify completion alone.
- JSON, partition and composite-key fields require additional design review.

## Related Decisions

- [ADR-003: Background Jobs](ADR-003-background-jobs.md)
- [ADR-011: PgBouncer Transaction Pooling](ADR-011-pgbouncer-transaction-pooling.md)
- [ADR-013: Secret Rotation](ADR-013-secret-rotation.md)
- [ADR-033: Dishka Request-Scoped Database Session Ownership](ADR-033-request-scoped-database-session-ownership.md)

## References

- [`app/AGENTS.md`](../../app/AGENTS.md)
- [`alembic/`](../../alembic/)
- [`quality/model-default-policy.json`](../../quality/model-default-policy.json)
- [`scripts/quality/audit_model_defaults.py`](../../scripts/quality/audit_model_defaults.py)
- [`tests/test_model_default_policy.py`](../../tests/test_model_default_policy.py)
- `docs/audits/AUDIT_PLATFORM_FULL.md`, Finding BE-02 (user-owned audit
  artifact; remains untracked and is not a release certificate)
