import asyncio
import hashlib
from typing import Any, Literal, cast

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status

import app.models as models
from app.api.deps import get_current_user
from app.core.config import settings
from app.core.container import get_read_stats_handler
from app.core.localization import resolve_locale

# P2-fix (audit 2026-02-26): import _ensure_vary_header from its defining module
# (app.core.middleware) instead of via app.main, which would create a circular
# dependency: stats → main → routers → stats.
from app.core.middleware import _ensure_vary_header
from app.core.ratelimit import sensitive_route_limit
from app.cqrs.queries import GetStatsHandler, GetStatsQuery
from app.deps.cache import format_etag

router = APIRouter(prefix="/stats", tags=["stats"])


def _set_stats_headers(
    response: Response, *, locale: str, etag: str | None = None
) -> None:
    _ensure_vary_header(response, "Accept-Language")
    response.headers["Content-Language"] = locale
    # P3-fix (audit 2026-02-26): compute Cache-Control lazily so that unit tests
    # that override settings.stats_cache_ttl_seconds see the correct value instead
    # of the import-time snapshot.
    response.headers["Cache-Control"] = (
        f"private, max-age={settings.stats_cache_ttl_seconds}"
    )
    if etag:
        response.headers["ETag"] = format_etag(etag)


_PERIOD_ALIASES = {
    "30d": 30,
    "90d": 90,
    "180d": 180,
}

_PERIOD_DEFAULT = ("30d", 30)


def _resolve_period(period: str | None) -> tuple[str, int]:
    if not period:
        return _PERIOD_DEFAULT
    period_key = period.strip().lower()
    days = _PERIOD_ALIASES.get(period_key)
    if days is not None:
        return period_key, days
    return _PERIOD_DEFAULT


_VALID_STAT_KINDS: frozenset[str] = frozenset({"attendance", "grades", "participation"})


async def _handle_stats_query(
    kind: str,
    period: str,
    skip_cache: bool,
    if_none_match: str | None,
    request: Request,
    response: Response,
    user: models.User,
    handler: GetStatsHandler,
) -> Response | dict[str, object]:
    period_key, days = _resolve_period(period)
    locale = resolve_locale(request=request, user=user)

    if kind not in _VALID_STAT_KINDS:
        kind = "attendance"
    validated_kind = cast(Literal["attendance", "grades", "participation"], kind)

    query = GetStatsQuery(
        kind=validated_kind,
        user_id=user.id,
        period_key=period_key,
        period_days=days,
        locale=locale,
        if_none_match=if_none_match,
        skip_cache=skip_cache,
    )
    result = await handler.handle(query)

    if result.not_modified:
        not_modified = Response(status_code=status.HTTP_304_NOT_MODIFIED)
        _set_stats_headers(not_modified, locale=locale, etag=result.etag)
        return not_modified

    _set_stats_headers(response, locale=locale, etag=result.etag)
    return cast(dict[str, object], result.payload)


@router.get(
    "/attendance",
    response_model=None,
    dependencies=[Depends(sensitive_route_limit())],
)
async def attendance_summary(
    request: Request,
    response: Response,
    period: str = Query("30d"),
    skip_cache: bool = Query(False, alias="skip_cache"),
    if_none_match: str | None = Header(default=None),
    user: models.User = Depends(get_current_user),
    handler: GetStatsHandler = Depends(get_read_stats_handler),
) -> Response | dict[str, Any]:
    return await _handle_stats_query(
        kind="attendance",
        period=period,
        skip_cache=skip_cache,
        if_none_match=if_none_match,
        request=request,
        response=response,
        user=user,
        handler=handler,
    )


@router.get(
    "/grades",
    response_model=None,
    dependencies=[Depends(sensitive_route_limit())],
)
async def grade_summary(
    request: Request,
    response: Response,
    period: str = Query("30d"),
    skip_cache: bool = Query(False, alias="skip_cache"),
    if_none_match: str | None = Header(default=None),
    user: models.User = Depends(get_current_user),
    handler: GetStatsHandler = Depends(get_read_stats_handler),
) -> Response | dict[str, Any]:
    return await _handle_stats_query(
        kind="grades",
        period=period,
        skip_cache=skip_cache,
        if_none_match=if_none_match,
        request=request,
        response=response,
        user=user,
        handler=handler,
    )


@router.get(
    "/participation",
    response_model=None,
    dependencies=[Depends(sensitive_route_limit())],
)
async def participation_summary(
    request: Request,
    response: Response,
    period: str = Query("30d"),
    skip_cache: bool = Query(False, alias="skip_cache"),
    if_none_match: str | None = Header(default=None),
    user: models.User = Depends(get_current_user),
    handler: GetStatsHandler = Depends(get_read_stats_handler),
) -> Response | dict[str, Any]:
    return await _handle_stats_query(
        kind="participation",
        period=period,
        skip_cache=skip_cache,
        if_none_match=if_none_match,
        request=request,
        response=response,
        user=user,
        handler=handler,
    )


@router.get(
    "/summary",
    response_model=None,
    dependencies=[Depends(sensitive_route_limit())],
)
async def stats_summary(
    request: Request,
    response: Response,
    period: str = Query("30d"),
    skip_cache: bool = Query(False, alias="skip_cache"),
    if_none_match: str | None = Header(default=None),
    user: models.User = Depends(get_current_user),
    handler: GetStatsHandler = Depends(get_read_stats_handler),
) -> Response | dict[str, Any]:
    """Return attendance, grades and participation stats in a single request.

    PERF-1 (audit 2026-03): replaces three separate client-side round-trips.
    All three sub-queries run concurrently via asyncio.gather and share the
    same Redis cache entries as the individual endpoints.
    """
    period_key, days = _resolve_period(period)
    locale = resolve_locale(request=request, user=user)

    def _make_query(
        kind: Literal["attendance", "grades", "participation"],
    ) -> GetStatsQuery:
        return GetStatsQuery(
            kind=kind,
            user_id=user.id,
            period_key=period_key,
            period_days=days,
            locale=locale,
            # Pass if_none_match only for the combined etag check below.
            if_none_match=None,
            skip_cache=skip_cache,
        )

    attendance_r, grades_r, participation_r = await asyncio.gather(
        handler.handle(_make_query("attendance")),
        handler.handle(_make_query("grades")),
        handler.handle(_make_query("participation")),
    )

    # Build a combined ETag from the three sub-ETags.
    sub_etags = "".join(r.etag or "" for r in (attendance_r, grades_r, participation_r))
    combined_etag = f'"{hashlib.sha256(sub_etags.encode()).hexdigest()[:16]}"'

    if if_none_match == combined_etag:
        not_modified = Response(status_code=304)
        _set_stats_headers(not_modified, locale=locale, etag=combined_etag)
        return not_modified

    _set_stats_headers(response, locale=locale, etag=combined_etag)
    return {
        "attendance": attendance_r.payload,
        "grades": grades_r.payload,
        "participation": participation_r.payload,
    }
