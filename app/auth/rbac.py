"""Role-Based Access Control via SpiceDB (ReBAC).

All permission checks use the async-native grpclib channel so that gRPC I/O
never blocks the asyncio event loop. (RZ-1: audit 2026-02-26)

The PermissionChecker is injected via Dishka (REQUEST scope) and receives
a pre-opened async grpclib.Channel. This decouples the checker from the
transport layer and makes it trivially testable without FastAPI machinery.
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# TD-W5-08: Grace-period permission cache.
#
# When SpiceDB becomes temporarily unreachable, returning HTTP 503 for every
# permission-guarded request causes cascading failures across the application.
# The cache stores the last-known result for each (user, resource, permission)
# tuple and serves it for up to _GRACE_TTL_SECONDS when SpiceDB is down.
#
# Security trade-off: a role revocation will remain effective in SpiceDB, but
# an in-progress outage means the stale "allow" result may be served for up to
# 60 seconds. This is acceptable because:
#   1. Role changes are rare and deliberate.
#   2. A 60-second window is far narrower than a typical SpiceDB rollout gap.
#   3. The alternative (fail-closed) causes full service degradation on ANY
#      transient network hiccup between the Python backend and SpiceDB.
# ---------------------------------------------------------------------------
_GRACE_TTL_SECONDS: float = 60.0

# {(user_id, resource_type, resource_id, permission): (result: bool, cached_at: float)}
_permission_cache: dict[tuple[str, str, str, str], tuple[bool, float]] = {}


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

    async def check_permission(
        self,
        resource_type: str,
        resource_id: str,
        permission: str,
        user_id: str,
    ) -> bool:
        """Check a permission against SpiceDB via async gRPC.

        Returns True if SpiceDB confirms the permission, False if explicitly denied.

        Raises:
            SpiceDBUnavailableError: on any connectivity or unexpected error so that
                callers can distinguish "SpiceDB said no" (returns False) from
                "SpiceDB is unreachable" (raises).
        """
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
            _permission_cache[(user_id, resource_type, resource_id, permission)] = (
                result,
                time.monotonic(),
            )
            return result
        except ImportError as exc:
            # grpc/authzed not installed — treat as unavailable rather than silently
            # denying. Callers with SpiceDB enabled should always have grpc.
            raise SpiceDBUnavailableError("grpc is not installed") from exc
        except Exception as exc:
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
            cache_key = (user_id, resource_type, resource_id, permission)
            cached = _permission_cache.get(cache_key)
            if cached is not None:
                cached_result, cached_at = cached
                if (time.monotonic() - cached_at) <= _GRACE_TTL_SECONDS:
                    logger.warning(
                        "SpiceDB unavailable — serving cached permission result "
                        "(%s:%s#%s for %s, age=%.1fs)",
                        resource_type,
                        resource_id,
                        permission,
                        user_id,
                        time.monotonic() - cached_at,
                    )
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
