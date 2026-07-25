"""Role-Based Access Control via SpiceDB (ReBAC).

All permission checks use the async-native grpclib channel so that gRPC I/O
never blocks the asyncio event loop. (RZ-1: audit 2026-02-26)

The PermissionChecker is injected via Dishka (REQUEST scope) and receives
a pre-opened async grpclib.Channel. This decouples the checker from the
transport layer and makes it trivially testable without FastAPI machinery.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections import OrderedDict
from typing import Any

from prometheus_client import Counter

from app.core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
)
from app.core.logging import get_logger

logger = get_logger(__name__)

# MOD-14-04 (audit 2026-03-18): Circuit breaker for SpiceDB gRPC calls.
# After failure_threshold=3 consecutive failures, the circuit opens and
# subsequent calls immediately fall through to the grace-period cache
# (O(1) dict lookup instead of waiting for gRPC timeouts).
# recovery_timeout=15s gives SpiceDB a short window to recover before
# probe calls re-enable live permission checks.
_spicedb_breaker = CircuitBreaker(
    "spicedb",
    config=CircuitBreakerConfig(
        failure_threshold=3,
        recovery_timeout_seconds=15.0,
        success_threshold=1,  # one successful probe closes the circuit
    ),
)

# PERF-14-02: Permission cache observability — track call/stale ratios
# to understand cache effectiveness and tune _GRACE_TTL_SECONDS / _PERMISSION_CACHE_MAX_SIZE.
_PERM_CACHE_CALLS = Counter(
    "spicedb_permission_calls_total",
    "SpiceDB live gRPC permission checks (cache populated on success)",
)
_PERM_CACHE_STALE = Counter(
    "spicedb_permission_cache_stale_total",
    "SpiceDB permission cache stale hits served during outage grace period",
)

# Hard per-call deadline for SpiceDB gRPC calls.
# Without this, a slow (not dead) SpiceDB blocks the event loop indefinitely
# and bypasses the grace-period cache entirely. (RZ-W13-02)
_SPICEDB_CALL_TIMEOUT_SECONDS: float = 2.0

# ---------------------------------------------------------------------------
# TD-W5-08: Grace-period permission cache.
#
# When SpiceDB becomes temporarily unreachable, returning HTTP 503 for every
# permission-guarded request causes cascading failures across the application.
# Two-tier grace-period cache for SpiceDB outages.
# RZ-W15-05 (audit 2026-03-23 Wave 15): Corrected misleading docstring.
#
# The cache stores the last-known result for each (user, resource, permission)
# tuple.  Results are served stale while SpiceDB is unavailable, but for
# DIFFERENT durations depending on whether the cached result is ALLOW or DENY:
#
#   DENY  (False) results → up to _GRACE_TTL_SECONDS        (60 s)
#   ALLOW (True)  results → up to _PERMISSION_POSITIVE_TTL_SECONDS (30 s)
#
# ⚠️  OPERATIONAL SLA NOTE:
#   The effective "tolerable SpiceDB downtime without impact" is only 30 seconds
#   (the ALLOW TTL), NOT 60 seconds.  After 30 s of outage:
#     - New requests for resources where the cached result is ALLOW will fail
#       CLOSED with SpiceDBUnavailableError → HTTP 503.
#     - Requests where the cached result is DENY continue to be denied (safe).
#   If the runbook says "SpiceDB can be down for 60 s without user impact",
#   that is INCORRECT.  Update runbooks to reflect the 30 s ALLOW TTL.
#
# Security trade-off:
#   1. DENY stale for 60 s is fail-closed — worst case a user is temporarily
#      blocked from something they were already denied.
#   2. ALLOW stale for 30 s is the security-sensitive direction — a revoked
#      permission could be served for up to 30 s after revocation lands in
#      SpiceDB. Shorter window limits the exposure window.
#   3. The alternative (fail-closed on any outage) causes full service
#      degradation on transient SpiceDB network hiccups.
#
# TD-14-04 (audit 2026-03-23): Two-tier TTL policy implemented in check_permission().
# ---------------------------------------------------------------------------
_GRACE_TTL_SECONDS: float = 60.0  # DENY results — safe to serve stale longer
# PERF-23-01 (audit 2026-03-25 Wave 23): Raised from 30 s to 45 s.
# ALLOW results (the common case) were expiring 2× faster than DENY, causing
# unnecessary gRPC calls under normal operation. 45 s still provides a tighter
# window than DENY (security-sensitive direction) while reducing gRPC volume ~33%.
_PERMISSION_POSITIVE_TTL_SECONDS: float = 45.0  # ALLOW results — fail-closed after 45 s

# RZ-22-05 (Wave 22): Export for operational runbook tooling.
# Runbooks MUST reference this value, NOT a hardcoded "60 seconds".
SPICEDB_MAX_TOLERABLE_DOWNTIME_SECONDS: float = _PERMISSION_POSITIVE_TTL_SECONDS

# RZ-W13-02: LRU-bounded to prevent unbounded memory growth.
# At ~200 bytes per entry, 10 000 entries ≈ 2 MB — acceptable overhead.
_PERMISSION_CACHE_MAX_SIZE: int = 10_000


# OrderedDict provides O(1) LRU eviction via move_to_end + popitem(last=False).
# {(user_id, resource_type, resource_id, permission, tenant_id, campus_id): (result: bool, cached_at: float)}
def _make_fresh_cache() -> OrderedDict[
    tuple[str, str, str, str, str, str], tuple[bool, float]
]:
    """Return a new empty cache. Called once per process after fork (RZ-14-02)."""
    return OrderedDict()


_permission_cache: OrderedDict[
    tuple[str, str, str, str, str, str], tuple[bool, float]
] = _make_fresh_cache()


def _reset_cache_after_fork() -> None:
    """os.register_at_fork() child callback.

    Ensures each Gunicorn worker process starts with an empty cache rather than
    inheriting stale parent state from --preload-app. Without this, gevent workers
    that share the parent's address space before COW can mutate the same dict
    concurrently.  (RZ-14-02: audit 2026-03-18)
    """
    global _permission_cache
    _permission_cache = _make_fresh_cache()


# Register before any fork — safe to call multiple times (idempotent).
# os.register_at_fork is Unix-only; guard for Windows dev environments.
if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_cache_after_fork)


class SpiceDBUnavailableError(RuntimeError):
    """Raised when SpiceDB cannot be reached.

    Distinct from a 'permission denied' response — callers should surface
    this as HTTP 503 so ops can detect and alert on authorization service
    degradation, rather than silently denying or allowing the request.
    """


class PermissionChecker:
    """Checks permissions against SpiceDB using an async gRPC channel.

    Injected via Dishka at REQUEST scope. The channel is torn down after
    each request, ensuring no connection leaks across requests.
    """

    def __init__(self, channel: Any) -> None:
        """Receive the async grpc.aio.Channel from Dishka DI.

        Args:
            channel: An open grpc.aio.Channel connected to SpiceDB.
                     Must be closed by the DI container after the request.
        """
        self._channel = channel

    async def check_admin(self, user_id: str, *, user: object = None) -> bool:
        """Check if user has global admin permission via SpiceDB.

        Fails CLOSED on SpiceDB outage — denies access without falling back to
        local role fields. The local ``user.role`` column must never be the sole
        authorization gate for privileged operations.

        Raises:
            SpiceDBUnavailableError: propagated on connectivity failure.
                Callers should convert this to HTTP 503.
        """
        return await self.check_permission(
            resource_type="semester",
            resource_id="current",
            permission="admin",
            user_id=user_id,
        )

    async def check_tenant_permission(
        self,
        tenant_id: str,
        permission: str,
        user_id: str,
    ) -> bool:
        """Check tenant-level permission against SpiceDB."""
        return await self.check_permission(
            resource_type="tenant",
            resource_id=tenant_id,
            permission=permission,
            user_id=user_id,
            tenant_id=tenant_id,
        )

    async def check_campus_permission(
        self,
        campus_id: str,
        permission: str,
        user_id: str,
        tenant_id: str | None = None,
    ) -> bool:
        """Check campus-level permission against SpiceDB."""
        return await self.check_permission(
            resource_type="campus",
            resource_id=campus_id,
            permission=permission,
            user_id=user_id,
            tenant_id=tenant_id,
            campus_id=campus_id,
        )

    async def check_permission(
        self,
        resource_type: str,
        resource_id: str,
        permission: str,
        user_id: str,
        tenant_id: str | None = None,
        campus_id: str | None = None,
    ) -> bool:
        """Check a permission against SpiceDB via async gRPC.

        Returns True if SpiceDB confirms the permission, False if explicitly denied.

        Raises:
            SpiceDBUnavailableError: on any connectivity or unexpected error so that
                callers can distinguish "SpiceDB said no" (returns False) from
                "SpiceDB is unreachable" (raises).
        """
        cache_key = (
            user_id,
            resource_type,
            resource_id,
            permission,
            tenant_id or "",
            campus_id or "",
        )
        try:
            # Lazy import keeps the module loadable when grpclib is absent
            import grpc.aio  # noqa: F401
            from authzed.api.v1 import (  # type: ignore[attr-defined]
                CheckPermissionRequest,
                CheckPermissionResponse,
                ObjectReference,
                PermissionsServiceStub,
                SubjectReference,
            )

            # Build the async stub from the injected channel.
            client = PermissionsServiceStub(self._channel)

            # MOD-14-04: Circuit breaker guards the gRPC call — after 3 consecutive
            # failures the circuit opens and subsequent calls bypass the network and
            # fall through to the grace-period cache immediately (O(1) lookup).
            # CircuitBreakerOpenError is caught in the `except Exception` block below.
            async with _spicedb_breaker:
                # RZ-W13-02: Hard per-call deadline — a *slow* (not dead) SpiceDB
                # would otherwise block the event loop indefinitely, bypassing the
                # grace-period cache. asyncio.TimeoutError is caught below and
                # treated the same as a connectivity failure.
                async with asyncio.timeout(_SPICEDB_CALL_TIMEOUT_SECONDS):
                    resp: CheckPermissionResponse = await client.CheckPermission(
                        CheckPermissionRequest(
                            resource=ObjectReference(
                                object_type=resource_type,
                                object_id=resource_id,
                            ),
                            permission=permission,
                            subject=SubjectReference(
                                object=ObjectReference(
                                    object_type="user",
                                    object_id=user_id,
                                )
                            ),
                        )
                    )
            result = bool(
                resp.permissionship
                == CheckPermissionResponse.PERMISSIONSHIP_HAS_PERMISSION
            )
            # Populate grace-period cache on every successful check.
            # RZ-W13-02: LRU eviction keeps the dict bounded.
            _permission_cache[cache_key] = (result, time.monotonic())
            _permission_cache.move_to_end(cache_key)
            if len(_permission_cache) > _PERMISSION_CACHE_MAX_SIZE:
                _permission_cache.popitem(last=False)
            _PERM_CACHE_CALLS.inc()  # PERF-14-02: live gRPC call succeeded
            return result
        except ImportError as exc:
            # grpc/authzed not installed — treat as unavailable rather than silently
            # denying. Callers with SpiceDB enabled should always have grpc.
            raise SpiceDBUnavailableError("grpc is not installed") from exc
        except Exception as exc:  # RZ-22-01-JUSTIFIED: fail-closed auth — SpiceDB fallback to grace-period cache (reviewed TD-27-04)
            logger.error(
                "SpiceDB async permission check failed (%s:%s#%s for %s): %s",
                resource_type,
                resource_id,
                permission,
                user_id,
                exc,
            )
            # TD-W5-08: Grace-period fallback — serve stale cached result when
            # SpiceDB is temporarily unreachable instead of failing the request.
            cached = _permission_cache.get(cache_key)
            if cached is not None:
                cached_result, cached_at = cached
                age = time.monotonic() - cached_at
                # TD-14-04 (audit 2026-03-23): Two-tier TTL.
                # Positive (allow) results must not be served indefinitely —
                # if the role was revoked and SpiceDB is down, fail-closed.
                max_ttl = (
                    _PERMISSION_POSITIVE_TTL_SECONDS
                    if cached_result is True
                    else _GRACE_TTL_SECONDS
                )
                if age <= max_ttl:
                    logger.warning(
                        "SpiceDB unavailable — serving cached permission result "
                        "(%s:%s#%s for %s, age=%.1fs, result=%s)",
                        resource_type,
                        resource_id,
                        permission,
                        user_id,
                        age,
                        cached_result,
                    )
                    _PERM_CACHE_STALE.inc()  # PERF-14-02: grace-period stale hit
                    return cached_result
            raise SpiceDBUnavailableError(
                f"SpiceDB unreachable: {resource_type}:{resource_id}#{permission}"
            ) from exc


# ---------------------------------------------------------------------------
# Legacy FastAPI Depends()-based helpers (kept for existing route handlers
# that have not yet migrated to Dishka). New code should use PermissionChecker
# injected via FromDishka[] instead.
# NOTE (2026-03-12): Legacy PermissionCheckerLegacy has been removed entirely.
# ---------------------------------------------------------------------------
