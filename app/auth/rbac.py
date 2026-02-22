from __future__ import annotations

import logging

from authzed.api.v1 import (
    CheckPermissionRequest,
    CheckPermissionResponse,
    ObjectReference,
    SubjectReference,
)
from fastapi import Depends

from app.core.spicedb import get_spicedb_client

logger = logging.getLogger(__name__)


class SpiceDBUnavailableError(RuntimeError):
    """Raised when SpiceDB cannot be reached.

    Distinct from a 'permission denied' response — callers should surface
    this as HTTP 503 so ops can detect and alert on authorization service
    degradation, rather than silently denying or allowing the request.
    """


class PermissionChecker:
    """
    Standardizes permission checks against SpiceDB.
    """

    def __init__(self, client=Depends(get_spicedb_client)) -> None:
        self.client = client

    async def check_admin(self, user_id: str, *, user=None) -> bool:
        """
        Check if user is a semester admin (mapping to global admin for now).

        Fails CLOSED on SpiceDB outage — denies access without falling back to
        local role fields. The local ``user.role`` column must never be the sole
        authorization gate for privileged operations.

        Raises:
            SpiceDBUnavailableError: propagated from check_permission on connectivity
                failure. Callers should convert this to HTTP 503.
        """
        return await self.check_permission(
            resource_type="semester",
            resource_id="current",
            permission="admin",
            user_id=user_id,
        )

    async def check_permission(
        self, resource_type: str, resource_id: str, permission: str, user_id: str
    ) -> bool:
        """
        Generic permission check against SpiceDB.

        Returns True if SpiceDB confirms the permission, False if explicitly denied.

        Raises:
            SpiceDBUnavailableError: on any connectivity or unexpected error so that
                callers can distinguish "SpiceDB said no" (returns False) from
                "SpiceDB is unreachable" (raises).
        """
        try:
            resp: CheckPermissionResponse = self.client.CheckPermission(
                CheckPermissionRequest(
                    resource=ObjectReference(
                        object_type=resource_type, object_id=resource_id
                    ),
                    permission=permission,
                    subject=SubjectReference(
                        object=ObjectReference(object_type="user", object_id=user_id)
                    ),
                )
            )
            return (
                resp.permissionship
                == CheckPermissionResponse.PERMISSIONSHIP_HAS_PERMISSION
            )
        except Exception as e:
            logger.error(
                "SpiceDB permission check failed (%s:%s#%s for %s): %s",
                resource_type,
                resource_id,
                permission,
                user_id,
                e,
            )
            raise SpiceDBUnavailableError(
                f"SpiceDB unreachable: {resource_type}:{resource_id}#{permission}"
            ) from e


async def is_admin(
    user_id: str,
    checker: PermissionChecker = Depends(PermissionChecker),
) -> bool:
    return await checker.check_admin(user_id)
