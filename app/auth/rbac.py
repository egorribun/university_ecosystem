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


class PermissionChecker:
    """
    Standardizes permission checks against SpiceDB.
    """

    def __init__(self, client=Depends(get_spicedb_client)) -> None:
        self.client = client

    async def check_admin(self, user_id: str, *, user=None) -> bool:
        """
        Check if user is a semester admin (mapping to global admin for now).
        Falls back to local role check if SpiceDB is unavailable.
        """
        result = await self.check_permission(
            resource_type="semester",
            resource_id="current",
            permission="admin",
            user_id=user_id,
        )
        # Fallback: if SpiceDB fails and user object is provided, check local role
        if not result and user is not None:
            if hasattr(user, "role") and user.role == "admin":
                logger.info(
                    f"SpiceDB unavailable, falling back to local role for {user_id}"
                )
                return True
        return result

    async def check_permission(
        self, resource_type: str, resource_id: str, permission: str, user_id: str
    ) -> bool:
        """
        Generic permission check against SpiceDB.
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
                f"SpiceDB permission check failed ({resource_type}:{resource_id}#{permission} for {user_id}): {e}"
            )
            return False


async def is_admin(
    user_id: str,
    checker: PermissionChecker = Depends(PermissionChecker),
) -> bool:
    return await checker.check_admin(user_id)
