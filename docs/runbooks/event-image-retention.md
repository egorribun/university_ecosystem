# Event image retention under tenant RLS

Event image cleanup first validates the configured storage backend and the
canonical event-owned key. Ownership alone does not prove that deleting the
object is safe: legacy events can share an image URL.

The current HTTP create endpoint refuses supplied image URLs. Updates accept
only the current URL or an image owned by that event. The retention rule protects
existing legacy references; it does not imply that the current API permits
cross-event image reuse.

## Fail-closed deletion boundary

On PostgreSQL, reference-aware cleanup proceeds only when
`pg_catalog.row_security_active('events')` is explicitly false for the current
database session. The unqualified relation name matches the ORM lookup.
A tenant-filtered empty result is not evidence that an object is globally
unreferenced. Unknown database dialects and failed visibility checks retain the
object. SQLite keeps its existing unfiltered reference lookup.

The application does not acquire a privileged role, disable RLS, or change
policies. A normal role subject to FORCE RLS therefore retains **all** replaced
or deleted event images, including genuine orphans. The database event update
or deletion still completes. Canonical ownership and reference checks remain
mandatory when the current session already has complete visibility.

## Operational consequence

There is no automatic reclamation job for these deferred images. Storage use
can grow after image replacements and event deletion. Do not add an age-only
bucket lifecycle rule for this prefix: old objects can still have live
references. A future reclamation process must establish global reference
visibility, preserve canonical ownership checks, and coordinate with writers
before it can safely reclaim candidates.

This change does not make the database reference check and storage deletion
atomic. In particular, it does not resolve concurrent reference insertion after
the check under an already-unfiltered session or on SQLite. No production
privilege escalation or concurrency-safety guarantee is introduced.

The PostgreSQL regression uses the actual baseline, an ordinary non-bypass
role under FORCE RLS, hidden legacy references, and a genuine orphan. An
isolated fixture administrator provides the positive control; its privileges
are not part of the production cleanup path.
