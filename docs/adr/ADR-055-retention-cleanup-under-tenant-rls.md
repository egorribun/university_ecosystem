# ADR-055: Retention cleanup under tenant RLS

## Status

Accepted on 2026-11-19. Records the rules introduced by PR #1456 (notification
claims) and PR #1464 (event images).

## Context

Tenant row-level security (RLS) filters what an ordinary application session can
see. A retention job that reads "no parent row" or "no reference row" under an
active RLS policy cannot tell a true orphan from a row that belongs to another
tenant. Deleting on that evidence destroys data that is still in use.

## Decision

Retention cleanup deletes only on evidence gathered with complete visibility.
On PostgreSQL the check is `pg_catalog.row_security_active('<relation>')`, using
the same unqualified relation name as the ORM query. When it is not explicitly
false, cleanup retains the candidate. The application does not acquire
`BYPASSRLS`, turn off `FORCE ROW LEVEL SECURITY`, change policies, or add a
privileged function. SQLite keeps its existing unfiltered behaviour; unknown
dialects fail closed.

### Notification delivery claims

Both the orphan candidate query and the final `DELETE` require
`row_security_active('notifications')` to be false in the current session.
Policy-level `ue_rls_bypass` membership still reports active RLS and does not
override this guard. Live unread notifications keep their deduplication evidence
after delivery-attempt history expires. Provider acceptance and the database
commit remain non-atomic.

### Event images

Reference-aware deletion of an event image proceeds only when
`row_security_active('events')` is false. A tenant-filtered empty result is not
evidence that an object is unreferenced; legacy events can share an image URL.
Canonical event ownership and the reference check stay mandatory when the
session already has complete visibility. The database update or deletion of the
event still completes. Details and operator guidance:
[event image retention runbook](../runbooks/event-image-retention.md).

## Consequences

- Under the normal runtime role (subject to FORCE RLS) old claims and replaced or
  deleted event images are retained, including true orphans. Storage and the claim
  ledger can grow; this decision does not claim complete reclamation.
- Reclamation needs a separately authorized maintenance session with demonstrably
  unfiltered visibility. It reuses the same bounded cleanup and must coordinate
  with writers. Do not add an age-only bucket lifecycle rule for event images:
  old objects can still have live references.
- The reference check and the storage deletion are not atomic. Concurrent
  reference insertion after the check is not resolved by this decision.
- Owned-PostgreSQL integration tests cover both rules with an ordinary non-bypass
  role under FORCE RLS, hidden references and a genuine orphan
  (`tests/integration/test_aud277_360_450_tenant_rls_postgres.py`).

Semantics checked against PostgreSQL's
[row security implementation](https://github.com/postgres/postgres/blob/REL_18_STABLE/src/backend/utils/misc/rls.c)
and the [information function documentation](https://github.com/postgres/postgres/blob/master/doc/src/sgml/func/func-info.sgml).
