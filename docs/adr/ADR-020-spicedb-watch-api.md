# ADR-020: SpiceDB Watch API for Real-time Permissions

## Status
Accepted

## Context
`PermissionChecker.check_permission` normally attempts a live SpiceDB
`CheckPermission` call and caches successful responses in bounded process-local
storage. It consults that cache only after a live-call failure or an open circuit
breaker, within permission-specific age limits; an `admin` ALLOW requires a live
grant. The Watch listener supports invalidation and session control while live
checks remain the normal path.

## Decision
Run a SpiceDB Watch listener as an API-process background task to invalidate
permission state after relationship updates and notify the WebSocket hub about
affected sessions.

Mechanism:
1. **Background Task**: A long-lived asyncio task (`spicedb_watch.py`) subscribes to the SpiceDB `Watch` stream.
2. **Event-driven Invalidation**: Each listener evicts matching entries from its
   process-local `_permission_cache`, attempts Redis `auth:perms` invalidation
   for the affected user, and attempts a signed `ws_hub.control` disconnect.
3. **Grace-period Cache**: Successful live checks refresh the local cache. On
   live-call failure or an open circuit, ordinary ALLOW decisions may be used
   while at most 45s old and DENY decisions while at most 60s old. Age is measured
   from the cached live check; an `admin` ALLOW always requires a live grant.

## Implementation

The stream is started from `app.core.lifespan._startup_background_workers` in
configured API processes outside the testing environment and cancelled with the
other background tasks on shutdown. After each stream end (error or clean close),
the listener clears its process-local cache before reconnecting with exponential
back-off because updates may have been missed. Redis invalidation and WS-hub
publication are best-effort per update. Until 2026-10 the task existed but was
never started; see [ADR-046](ADR-046-codebase-consolidation-audit.md).

## Rationale
1. **Bounded fallback**: The cache supports temporary live-call failures without
   becoming the normal authorization path.
2. **Invalidation**: Relationship updates evict matching local decisions in the
   API process consuming them; no fleet-wide millisecond guarantee is established.
3. **Watch gaps**: Clearing local state on stream end prevents decisions from
   being carried across a missed-update window.
4. **Session control**: Watch updates also drive disconnect notifications.

## Consequences
- Each configured API process runs its own listener. High update volume may
  require filtering; fleet-wide delivery timing is not guaranteed.
- Redis invalidation and WS-hub disconnect publication are best-effort.
  Authorization depends on live SpiceDB checks except for bounded fallback.
- Stream reliability affects invalidation and session-control latency.

## References
- `app/core/spicedb_watch.py`
- `app/auth/rbac.py`
