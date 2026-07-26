"""Context-Aware Access Control (ABAC + ReBAC) for University Ecosystem.

Provides ContextAwareAccessGuard and check_control_work_access function to validate:
1. ReBAC permission via SpiceDB (PermissionChecker).
2. ABAC Subnet membership using client IP resolution and campus CIDR subnets.
3. ABAC Schedule Time Window validation with configurable grace period.

Raises HTTPException(403) on access denial, records Prometheus metrics,
and emits OTEL-compatible structured logs with PII redaction.
"""

from __future__ import annotations

import ipaddress
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, Request, status

from app.auth.rbac import PermissionChecker, SpiceDBUnavailableError
from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import record_abac_access_denied
from app.core.ratelimit.utils import resolve_client_ip

logger = get_logger(__name__)

# Standard detail message required for 403 responses
_DENIAL_DETAIL = "Access denied: outside scheduled time window or untrusted network"


def _to_utc(dt: datetime) -> datetime:
    """Normalize datetime to timezone-aware UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _parse_subnets(
    subnets: list[str] | str,
) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """Parse CIDR strings into IP network objects."""
    if isinstance(subnets, str):
        cidr_list = [s.strip() for s in subnets.split(",") if s.strip()]
    else:
        cidr_list = subnets

    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for cidr in cidr_list:
        try:
            networks.append(ipaddress.ip_network(cidr, strict=False))
        except (ValueError, TypeError) as exc:  # RZ-22-01: invalid CIDR string format
            logger.warning(
                "Invalid CIDR in campus_subnets configuration",
                cidr=cidr,
                error=str(exc),
            )
    return networks


def _check_ip_in_subnets(
    client_ip_str: str,
    subnets: list[str] | str,
) -> bool:
    """Check whether a client IP belongs to any of the specified campus subnets."""
    try:
        ip_obj = ipaddress.ip_address(client_ip_str.strip())
    except (ValueError, TypeError):  # RZ-22-01: invalid client IP address format
        return False

    networks = _parse_subnets(subnets)
    return any(
        ip_obj.version == network.version and ip_obj in network for network in networks
    )


def _check_schedule_window(
    now_utc: datetime,
    start_utc: datetime,
    end_utc: datetime,
    grace_minutes: int,
) -> bool:
    """Check whether current time falls within [start_time, end_time + grace_minutes]."""
    window_start = start_utc
    window_end = end_utc + timedelta(minutes=grace_minutes)
    return window_start <= now_utc <= window_end


class ContextAwareAccessGuard:
    """Access Guard combining ReBAC checks with ABAC context filters."""

    def __init__(
        self,
        permission_checker: PermissionChecker | None = None,
        campus_subnets: list[str] | str | None = None,
        grace_minutes: int | None = None,
    ) -> None:
        self.permission_checker = permission_checker
        self._custom_subnets = campus_subnets
        self._custom_grace_minutes = grace_minutes

    @property
    def campus_subnets(self) -> list[str] | str:
        if self._custom_subnets is not None:
            return self._custom_subnets
        return settings.security.campus_subnets

    @property
    def grace_minutes(self) -> int:
        if self._custom_grace_minutes is not None:
            return self._custom_grace_minutes
        return getattr(settings.security, "control_work_grace_minutes", 15)

    async def check_control_work_access(
        self,
        request: Request,
        user_id: str | uuid.UUID,
        resource_type: str | Any = "control_work",
        resource_id: str | Any | None = None,
        lesson_start: datetime | None = None,
        lesson_end: datetime | None = None,
        permission_checker: PermissionChecker | None = None,
        *,
        permission: str = "submit",
        lesson: Any | None = None,
    ) -> None:
        """Validate ReBAC permission and ABAC context constraints.

        Supports both explicit parameters (resource_type, resource_id, lesson_start, lesson_end)
        and lesson entity objects (with id, start_time, and end_time attributes).

        Args:
            request: Incoming HTTP request for client IP resolution.
            user_id: ID of the user requesting access.
            resource_type: SpiceDB resource type or lesson entity object.
            resource_id: SpiceDB resource ID or PermissionChecker instance when positional.
            lesson_start: Start time of the scheduled lesson / control work.
            lesson_end: End time of the scheduled lesson / control work.
            permission_checker: Optional PermissionChecker override.
            permission: SpiceDB permission (default: "submit").
            lesson: Optional lesson entity object (with id, start_time, end_time).

        Raises:
            HTTPException(403): If any authorization check fails.
            ValueError: If lesson timing parameters cannot be resolved.
        """
        user_str = str(user_id)

        # Resolve lesson object vs explicit parameters
        lesson_obj = lesson
        if lesson_obj is None and hasattr(resource_type, "start_time"):
            lesson_obj = resource_type
            if isinstance(resource_id, PermissionChecker):
                permission_checker = permission_checker or resource_id
            resource_type = "control_work"

        if lesson_obj is not None:
            res_type = (
                resource_type if isinstance(resource_type, str) else "control_work"
            )
            res_id = str(getattr(lesson_obj, "id", "unknown"))
            start_dt = getattr(lesson_obj, "start_time", None)
            end_dt = getattr(lesson_obj, "end_time", None)
        else:
            res_type = (
                str(resource_type) if resource_type is not None else "control_work"
            )
            res_id = str(resource_id) if resource_id is not None else "unknown"
            start_dt = lesson_start
            end_dt = lesson_end

        if start_dt is None or end_dt is None:
            raise ValueError(
                "Lesson start and end times must be provided directly or via a lesson object"
            )

        checker = permission_checker or self.permission_checker

        # 1. ReBAC Check via SpiceDB
        if checker is not None:
            try:
                allowed = await checker.check_permission(
                    resource_type=res_type,
                    resource_id=res_id,
                    permission=permission,
                    user_id=user_str,
                )
            except SpiceDBUnavailableError as exc:
                logger.error(
                    "ABAC ReBAC check failed due to SpiceDB failure",
                    user_id=user_str,
                    resource_id=res_id,
                    exc_info=exc,
                )
                record_abac_access_denied(rule="rebac")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=_DENIAL_DETAIL,
                ) from exc

            if not allowed:
                logger.warning(
                    "ABAC access denied: ReBAC permission check returned False",
                    user_id=user_str,
                    resource_id=res_id,
                    permission=permission,
                )
                record_abac_access_denied(rule="rebac")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=_DENIAL_DETAIL,
                )

        # 2. ABAC Subnet Check
        client_ip = resolve_client_ip(request)
        if not _check_ip_in_subnets(client_ip, self.campus_subnets):
            logger.warning(
                "ABAC access denied: client IP outside campus subnets",
                user_id=user_str,
                client_ip=client_ip,
                resource_id=res_id,
            )
            record_abac_access_denied(rule="subnet")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=_DENIAL_DETAIL,
            )

        # 3. ABAC Schedule Time Window Check
        now_utc = datetime.now(UTC)
        start_utc = _to_utc(start_dt)
        end_utc = _to_utc(end_dt)

        if not _check_schedule_window(now_utc, start_utc, end_utc, self.grace_minutes):
            logger.warning(
                "ABAC access denied: request outside schedule time window",
                user_id=user_str,
                current_time=now_utc.isoformat(),
                start_time=start_utc.isoformat(),
                end_time=end_utc.isoformat(),
                grace_minutes=self.grace_minutes,
                resource_id=res_id,
            )
            record_abac_access_denied(rule="schedule")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=_DENIAL_DETAIL,
            )


async def check_control_work_access(
    request: Request,
    user_id: str | uuid.UUID,
    resource_type: str | Any = "control_work",
    resource_id: str | Any | None = None,
    lesson_start: datetime | None = None,
    lesson_end: datetime | None = None,
    permission_checker: PermissionChecker | None = None,
    *,
    permission: str = "submit",
    lesson: Any | None = None,
) -> None:
    """Helper function to execute context-aware access guard check."""
    guard = ContextAwareAccessGuard(permission_checker=permission_checker)
    await guard.check_control_work_access(
        request=request,
        user_id=user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        lesson_start=lesson_start,
        lesson_end=lesson_end,
        permission_checker=permission_checker,
        permission=permission,
        lesson=lesson,
    )
