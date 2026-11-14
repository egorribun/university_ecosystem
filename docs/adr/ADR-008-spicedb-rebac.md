# ADR-008: SpiceDB for Relationship-Based Access Control (ReBAC)

## Status
Accepted (Wave 13, 2026-03-17)

## Context

The initial authorization model used a flat `user.role` column (`admin`, `teacher`, `student`) checked inline in route handlers. This model fails to capture:

- Resource-level permissions (student can view chat A but not chat B)
- Delegated permissions (teacher can manage students in their own courses only)
- Cross-resource relationships (chat participants inherit permissions from course enrollment)
- Audit trail (no record of who changed which permission when)

A purely RBAC model (Casbin, custom middleware) lacks the graph traversal needed to answer "does user X have permission Y on resource Z given transitively inherited memberships?"

## Decision

Adopted **SpiceDB** (authzed/spicedb) as the authorization service, using gRPC via `authzed-py`.

**Key implementation choices:**

1. **gRPC async channel** — `grpc.aio.Channel` injected via Dishka DI (REQUEST scope), never blocking the asyncio event loop.
2. **Hard per-call timeout** — `asyncio.timeout(2.0)` wraps each `CheckPermission` call. A slow SpiceDB never blocks a request indefinitely.
3. **Circuit breaker** — `CircuitBreaker("spicedb", failure_threshold=3, recovery_timeout=15s)` — after 3 consecutive failures, the circuit opens and subsequent calls bypass the network.
4. **Two-tier grace-period cache:**
   - Ordinary ALLOW results: outage fallback accepts a cached live decision at most 45s old, then fails closed; `admin` ALLOW results require a live check.
   - DENY results: cached max 60s (safe to serve stale longer — worst case blocks a legitimate user temporarily)
5. **LRU cache** — `OrderedDict` bounded at 10,000 entries (~2 MB) to prevent OOM.
6. **`check_admin` fails CLOSED** — local `user.role` column is never the sole gate for privileged operations.

**Operational recovery bound:** Ordinary ALLOW fallback is bounded by 45s since the cached live check, not since outage onset; `admin` ALLOW results require a live SpiceDB check. The code exports the ordinary bound as `SPICEDB_MAX_TOLERABLE_DOWNTIME_SECONDS`.

## Alternatives Rejected

- **Casbin** — No graph/relationship model; flat RBAC only.
- **OPA (Open Policy Agent)** — Excellent for policy-as-code, but lacks native relationship traversal (requires building relationship tables manually in Rego).
- **Custom RBAC** — Would require building graph traversal and audit infrastructure ourselves.
- **Oso** — Good ReBAC support but less mature Go/Python dual-stack integration.

## Consequences

**Positive:**
- Native relationship graph (course → chat → participant) without manual joins.
- Centralized permission store; all services check the same SpiceDB instance.
- Audit log built into SpiceDB schema.

**Negative:**
- Additional infrastructure dependency (SpiceDB + its PostgreSQL datastore).
- 2s timeout ceiling on permission checks — operations that need many checks may accumulate latency.
- Grace cache can serve a revoked ordinary ALLOW until its cached live decision reaches 45s old; `admin` ALLOW results do not use stale fallback.

## Implementation

- `app/auth/rbac.py` — `PermissionChecker`, grace cache, circuit breaker
- `app/core/spicedb.py` — gRPC channel factory with keepalive options
- SpiceDB schema: `schema.zed`
- `app/auth/relationships.py` — event `creator` / `attendee` relationship writer

## 2026-11-14: relationship writes

`schema.zed` grants event permissions through the `event#creator` and `event#attendee` relations, but no application code wrote them before this addendum. Creators were denied PATCH/DELETE on their own events, and attendees could not view event files; only admins passed through `semester->admin`. The writes below close that gap.

- **Creator (best effort, backend request path).** `EventService.create_event` TOUCHes `event:{id}#creator@user:{created_by}` after the event commit. A SpiceDB failure logs `event_creator_relationship_sync_failed` and does not fail the request. A missing creator is a no-op.
- **Attendee (best effort, backend request path).** Attendance has no domain event. `register_attendance` TOUCHes `event:{id}#attendee@user:{uid}` after the participation commit, and `unregister_attendance` DELETEs it. A failure logs `event_attendee_relationship_sync_failed` and does not fail the request.
- **Outbox worker has no SpiceDB access.** The outbox-worker container is not on the SpiceDB network and receives no SpiceDB configuration, and the Helm NetworkPolicies grant it no SpiceDB egress. Relationship writes therefore never go through the outbox. Changing worker networking is out of scope for this addendum.
- **Backfill repairs missing grants only.** `scripts/backfill_event_relationships.py` TOUCHes creator relations for every event with `created_by` and attendee relations for every attendance row. It runs under the configured MVP tenant context (`tenant_id_ctx`, validated by `require_mvp_tenant`) and never enables the RLS bypass. Pages are keyset-ordered by primary key, and writes are chunked below SpiceDB's per-request update limit. Repeated TOUCHes are idempotent for an unchanged database, but the script does not remove stale relations. Run it with membership changes quiesced; a concurrent removal can otherwise be followed by a stale TOUCH.
- **Consistency.** `PermissionChecker` uses SpiceDB's default consistency, which minimizes latency. A just-created event may therefore need a few seconds before the creator check passes, and a new attendee may see the same delay. Checks do not request `at_least_as_fresh`.
- **Unresolved revocation gap.** A failed best-effort TOUCH leaves a missing grant that the backfill can restore. A failed DELETE after attendance cancellation or a group move leaves a stale grant that neither backfill removes; this can continue granting `event#view` or the old `group#view`. Concurrent request-path writes can also arrive out of commit order. These are not bounded by the permission-check grace-cache TTL because the stale relation remains in SpiceDB. Durable revocation reconciliation or an authoritative membership check is still required before treating this writer as a complete access-synchronization solution. Deleting an event also leaves its creator relation, although no live event row exposes that deleted ID.
- **Group participants.** `group:{group_id}#participant@user:{user_id}` is the membership relation that `group#view` (`schema.zed`) grants schedule access through. Before this change no code wrote it, so non-admin students received an empty GraphQL group schedule. `sync_group_participant(user_id, old_group_id, new_group_id)` in `app/auth/relationships.py` DELETEs the old membership and TOUCHes the new one in a single WriteRelationships request. It is a no-op when the group is unchanged or absent, and it is best effort: a `RelationshipWriteError` logs `group_participant_relationship_sync_failed` and is swallowed.
- **Group call sites.** The sync runs in the registration API handler (`app/api/auth/login.py`) after `UserComplianceService.register_user` returns, in the admin create-user API handler (`app/api/users.py`) after `UserComplianceService.create_user` returns (both old `None`), and in `UserProfileService.admin_update_user` after commit (old value captured before the update). The compliance service itself is unchanged. The self-service profile update cannot change `group_id`, so it has no call site.
- **Group backfill.** `scripts/backfill_group_participants.py` TOUCHes a participant relation for every user with a non-null `group_id`. It reuses the keyset pager and chunked writer from `scripts/backfill_event_relationships.py`, runs under the MVP tenant context, and never enables the RLS bypass. Reruns are idempotent for unchanged memberships; old-group grants and concurrent membership changes retain the revocation limits above. The backend GraphQL endpoint remains unmounted in the MVP, so group schedule access through that endpoint is not an accepted live product surface.
