"""GraphQL permission classes for Strawberry declarative authorization.

TD-1 (audit 2026-02-26): Introduced centralized permission classes so that
authorization constraints are expressed once at the field/resolver declaration
rather than scattered as manual ``info.context.is_authenticated`` checks inside
every resolver body.  A missed check in a leaf resolver would silently expose
data; a missing permission_classes argument raises a hard error at schema
validation time.

Usage::

    @strawberry.field(permission_classes=[IsAuthenticated])
    async def me(self, info: Info) -> UserType:
        ...

    @strawberry.field(permission_classes=[IsAuthenticated, IsAdmin])
    async def admin_dashboard(self, info: Info) -> AdminStatsType:
        ...

    # Unauthenticated (public) fields need no annotation — they are the default.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from strawberry.permission import BasePermission

from app.core.logging import get_logger

if TYPE_CHECKING:
    from strawberry.types import Info

    from app.graphql.context import GraphQLContext

logger = get_logger(__name__)


class IsAuthenticated(BasePermission):
    """Allow access only to authenticated users (valid, non-revoked JWT)."""

    message = "Authentication required"

    def has_permission(
        self,
        source: Any,
        info: Info[GraphQLContext, Any],
        **kwargs: Any,
    ) -> bool:
        # GraphQLContext.is_authenticated checks ``current_user is not None``.
        # The context already enforces JTI revocation (RZ-2), so this is the
        # correct single source of truth.
        return info.context.is_authenticated


class IsAdmin(BasePermission):
    """Allow access only to users with global-admin role in SpiceDB.

    Checks are delegated to the SpiceDB PermissionChecker injected into the
    context.  If SpiceDB is unavailable the check fails closed (HTTP 503)
    to avoid silent privilege escalation — the same behaviour as the REST
    ``get_current_admin_user`` dependency in ``deps.py``.

    Note: ``has_permission`` is ``async`` so it can await the gRPC call.
    """

    message = "Admin access required"

    async def has_permission(
        self,
        source: Any,
        info: Info[GraphQLContext, Any],
        **kwargs: Any,
    ) -> bool:
        if not info.context.is_authenticated or info.context.current_user is None:
            return False

        checker = getattr(info.context, "checker", None)
        if checker is None:
            # PermissionChecker not injected into context — fail closed.
            logger.error(
                "IsAdmin: PermissionChecker missing from GraphQL context; "
                "inject it in get_context() to use IsAdmin permission class."
            )
            return False

        try:
            from app.auth.rbac import SpiceDBUnavailableError

            return bool(await checker.check_admin(str(info.context.current_user.id)))
        except SpiceDBUnavailableError:
            # Fail closed — authorization service unavailable must not allow access.
            logger.warning(
                "IsAdmin: SpiceDB unavailable during GraphQL permission check"
            )
            return False
        except Exception:
            logger.exception("IsAdmin: unexpected error during permission check")
            return False


__all__ = ["IsAdmin", "IsAuthenticated"]
