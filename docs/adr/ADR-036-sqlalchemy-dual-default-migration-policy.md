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

The current SQLAlchemy metadata contains 45 tables and 134 effective
defaulted columns (computed expressions excluded):

- 24 declarations have both an ORM and server default;
- 91 effective declarations are Python-only;
- 19 declarations are server-only.

The source-level AST inventory is 108 `mapped_column` calls with a default or
server default: 24 both, 65 Python-only and 19 server-only. The difference
between effective metadata and source counts is explained by 37 UUIDv7
primary-key defaults inherited from the mixin and ten `default=None`
declarations. Of the explicit
one-sided declarations, 54 explicit Python-only defaults and 19 server-only defaults
are the measured migration candidates. These figures supersede the external
audit's stale 92-column number and must be regenerated after model changes.

## Decision

We will converge applicable model fields to dual defaults in small, reviewed
phases. No blanket rewrite or guessed SQL expression is permitted. Every
phase starts with a PostgreSQL catalog preflight and ends with upgrade,
downgrade, ORM and direct-write evidence.

## Migration Policy

1. **Inventory first.** Compare SQLAlchemy metadata with `pg_get_expr` /
   `column_default`, nullability, existing NULL counts, enum/string values,
   JSON/JSONB type and the current Alembic head for every candidate.
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

## Exceptions

The following values remain intentionally application-only unless a separate
security/schema decision changes their contract:

- 37 inherited UUIDv7 primary-key defaults: a database fallback could destroy
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
- [`tests/test_model_default_policy.py`](../../tests/test_model_default_policy.py)
- `docs/audits/AUDIT_PLATFORM_FULL.md`, Finding BE-02 (user-owned audit
  artifact; remains untracked and is not a release certificate)
