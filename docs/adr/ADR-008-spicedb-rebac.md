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
   - ALLOW results: cached max 30s during outage (fail-closed after 30s — revoked permissions have ≤30s exposure window)
   - DENY results: cached max 60s (safe to serve stale longer — worst case blocks a legitimate user temporarily)
5. **LRU cache** — `OrderedDict` bounded at 10,000 entries (~2 MB) to prevent OOM.
6. **`check_admin` fails CLOSED** — local `user.role` column is never the sole gate for privileged operations.

**Operational SLA:** SpiceDB must recover within 30s for ALLOW results to remain valid. The runbook must reference 30s, not 60s.

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
- Grace cache can serve stale ALLOW results for up to 30s after permission revocation.

## Implementation

- `app/auth/rbac.py` — `PermissionChecker`, grace cache, circuit breaker
- `app/core/spicedb.py` — gRPC channel factory with keepalive options
- SpiceDB schema: `schema.zed`
