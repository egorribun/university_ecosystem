"""Role-Based Access Control via SpiceDB (ReBAC).

All permission checks use the async-native grpclib channel so that gRPC I/O
never blocks the asyncio event loop. (RZ-1: audit 2026-02-26)

The PermissionChecker is injected via Dishka (REQUEST scope) and receives
a pre-opened async grpclib.Channel. This decouples the checker from the
transport layer and makes it trivially testable without FastAPI machinery.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


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
            from authzed.api.v1 import (
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
            return bool(
                resp.permissionship
                == CheckPermissionResponse.PERMISSIONSHIP_HAS_PERMISSION
            )
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
            raise SpiceDBUnavailableError(
                f"SpiceDB unreachable: {resource_type}:{resource_id}#{permission}"
            ) from exc


# ---------------------------------------------------------------------------
# Legacy FastAPI Depends()-based helpers (kept for existing route handlers
# that have not yet migrated to Dishka). New code should use PermissionChecker
# injected via FromDishka[] instead.
# NOTE (2026-03-12): Legacy PermissionCheckerLegacy has been removed entirely.
# ---------------------------------------------------------------------------
