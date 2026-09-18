# ADR-033: Dishka request-scoped database session ownership

*Status: accepted — 2026-09-08*

## Context

The FastAPI application currently exposes the legacy `get_db` dependency while
Dishka also provides a request-scoped `AsyncDatabaseSession`.  A route can
therefore authenticate through one `AsyncSession` and execute its
DB-backed service through another.  The BE-04 audit reproduced two distinct
session identities and two independent transactions on one authenticated
request.  The behaviour is an architectural reliability defect: it increases
checkout pressure and makes commit/rollback ownership difficult to reason
about, even though a data-corruption exploit was not reproduced.

Authentication is also a dependency boundary.  Moving route handlers to
Dishka without parameterising the authentication implementation would either
duplicate the session or make FastAPI dependencies reach into the Dishka
container.  The migration therefore needs a single core resolver and
temporary adapters while callers move in bounded domain slices.

## Decision

Dishka `Scope.REQUEST` owns the canonical **primary** database session.  The
authentication implementation is session-parameterised and receives the
session explicitly.  Two adapters delegate to that implementation:

* `get_current_user` remains the compatibility adapter for routes that still
  use `Depends(get_db)`;
* `get_current_user_from_dishka` receives `FromDishka[AsyncDatabaseSession]`
  and is the adapter for migrated routes.

The adapters do not create sessions, call each other, commit, or roll back.
The request provider closes the canonical session; endpoint/service owners
retain their existing explicit transaction boundaries.  A future read owner
will be a distinct typed dependency and is deferred to BE-04 S5; this ADR
does not turn read dependencies into primary sessions.

Fresh-MFA checks follow the same shape.  The legacy adapter remains available
until all callers are migrated, while `require_fresh_mfa_from_dishka` shares
the canonical auth session on migrated routes.

## Alternatives considered

### A — Keep FastAPI factories as the owner

Rejected.  This preserves duplicate ownership wherever a Dishka service is
used and prevents the existing request-scoped provider graph from being the
single lifecycle boundary.

### B — Make Dishka request scope canonical (chosen)

Accepted.  LoginService, CQRS buses, and the domain providers already use the
Dishka request scope.  A session-parameterised auth core lets migration happen
one route domain at a time without changing response or transaction semantics.

### C — Bridge both containers through a global ContextVar

Rejected.  Request-global mutable state is difficult to prove safe across
concurrent requests, background tasks, and cancellation.  It also obscures
ownership in the type/dependency graph.  Explicit Dishka injection is easier to
test and fail closed.

## Consequences

* Migrated routes have one primary session identity for auth and their
  DB-backed service graph.
* Legacy routes remain behaviourally compatible during the migration, but the
  temporary adapters must not be used for new routes.
* Explicit endpoint/service commits stay in place; the provider only owns
  cleanup.  This preserves current UoW semantics and makes rollback tests
  meaningful.
* The read-replica provider and the removal of `get_db`/`get_read_db` are
  separate BE-04 tasks and require their own ledger and PostgreSQL evidence.

## Verification obligations

Every migrated boundary must assert session identity, connection checkout,
commit/rollback behaviour, and exactly-once cleanup on success and failure.
The ownership test harness uses real SQLite `AsyncSession` instances for local
deterministic checks; PostgreSQL integration remains required for the final
BE-04 closure.
