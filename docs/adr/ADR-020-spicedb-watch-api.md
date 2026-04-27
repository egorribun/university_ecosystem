# ADR-020: SpiceDB Watch API for Real-time Permissions

## Status
Accepted

## Context
Permission checks (ReBAC) against SpiceDB happen on almost every API request. Serving these checks purely from a cache leads to stale permissions, while making live gRPC calls on every request adds significant latency.

## Decision
We implemented a **streaming Watch API listener** to maintain a near-real-time permission cache.

Mechanism:
1. **Background Task**: A long-lived asyncio task (`spicedb_watch.py`) subscribes to the SpiceDB `Watch` stream.
2. **Event-driven Invalidation**: When a relationship changes in SpiceDB, the watcher receives an update and evicts corresponding entries from the local `_permission_cache`.
3. **Grace-period Cache**: Live checks are cached for 60s (safety net), but most are invalidated proactively by the Watch stream.

## Rationale
1. **Low Latency**: Most permission checks are resolved from local RAM.
2. **Consistency**: Permission changes (e.g. revoking an "admin" role) take effect across the fleet in milliseconds.
3. **Fault Tolerance**: If the Watch stream disconnects, the cache is fully cleared, and the system falls back to live checks until re-connection.
4. **Scalability**: Reduces the query load on the central SpiceDB cluster.

## Consequences
- Fleet-wide invalidation: Every instance of the gateway receives all updates (high update volume might require filtering).
- Dependency: Reliability depends on the stability of the long-lived gRPC stream.

## References
- `app/core/spicedb_watch.py`
- `app/auth/rbac.py`
