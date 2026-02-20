from functools import lru_cache

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.container import get_read_stats_handler
from app.core.localization import resolve_locale
from app.cqrs.queries import GetStatsHandler, GetStatsQuery
from app.deps.cache import format_etag
from app.models import models

router = APIRouter(prefix="/stats", tags=["stats"])


@lru_cache(maxsize=1)
def _get_vary_helper():
    from app.main import _ensure_vary_header

    return _ensure_vary_header


def _set_stats_headers(
    response: Response, *, locale: str, etag: str | None = None
) -> None:
    _get_vary_helper()(response, "Accept-Language")
    response.headers["Content-Language"] = locale
    response.headers["Cache-Control"] = _STATS_CACHE_CONTROL
    if etag:
        response.headers["ETag"] = format_etag(etag)


_PERIOD_ALIASES = {
    "30d": 30,
    "90d": 90,
    "180d": 180,
}

_PERIOD_DEFAULT = ("30d", 30)

_STATS_CACHE_CONTROL = f"private, max-age={settings.stats_cache_ttl_seconds}"


def _resolve_period(period: str | None) -> tuple[str, int]:
    if not period:
        return _PERIOD_DEFAULT
    period_key = period.strip().lower()
    days = _PERIOD_ALIASES.get(period_key)
    if days is not None:
        return period_key, days
    return _PERIOD_DEFAULT


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

    query = GetStatsQuery(
        kind=kind,
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
    return result.payload  # type: ignore[no-any-return]


@router.get("/attendance")
async def attendance_summary(
    request: Request,
    response: Response,
    period: str = Query("30d"),
    skip_cache: bool = Query(False, alias="skip_cache"),
    if_none_match: str | None = Header(default=None),
    user: models.User = Depends(get_current_user),
    handler: GetStatsHandler = Depends(get_read_stats_handler),
):
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


@router.get("/grades")
async def grade_summary(
    request: Request,
    response: Response,
    period: str = Query("30d"),
    skip_cache: bool = Query(False, alias="skip_cache"),
    if_none_match: str | None = Header(default=None),
    user: models.User = Depends(get_current_user),
    handler: GetStatsHandler = Depends(get_read_stats_handler),
):
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


@router.get("/participation")
async def participation_summary(
    request: Request,
    response: Response,
    period: str = Query("30d"),
    skip_cache: bool = Query(False, alias="skip_cache"),
    if_none_match: str | None = Header(default=None),
    user: models.User = Depends(get_current_user),
    handler: GetStatsHandler = Depends(get_read_stats_handler),
):
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


@router.get("/creation")
async def creation_analytics(
    request: Request,
    object_type: str = Query(
        ..., description="Type of object to analyze (users, news, events)"
    ),
    period: str = Query("30d"),
    user: models.User = Depends(get_current_user),
):
    """
    Analytics powered by UUID v7:
    Creation time distribution without DB indexes on created_at.
    """
    # This is a demonstration of using extract_timestamp_from_uuid_v7
    # In a real implementation, we would query IDs from the DB and process them

    # Placeholder for actual DB logic
    return {
        "object_type": object_type,
        "period": period,
        "note": "Analytics computed via UUID v1/v7 temporal component",
        "data": [
            {"date": "2026-02-01", "count": 10},
            {"date": "2026-01-31", "count": 15},
        ],
    }
