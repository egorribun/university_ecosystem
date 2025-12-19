from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from functools import lru_cache

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.deps.cache import BaseCache, etag_matches, format_etag, get_cache
from app.localization import resolve_locale, translate
from app.models import models
from app.services import stats_cache

router = APIRouter(prefix="/stats", tags=["stats"])


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


def _should_skip_cache(requested: bool, user: models.User) -> bool:
    if not requested:
        return False
    return user.role == "admin"


def _period_response_payload(
    *,
    stats: dict[str, object],
    period_key: str,
    period_days: int,
    request: Request,
    user: models.User,
    locale: str | None = None,
) -> dict[str, object]:
    locale = locale or resolve_locale(request=request, user=user)
    label = translate(
        f"stats.period.{period_key}",
        locale=locale,
        default=period_key,
        days=period_days,
    )
    payload = dict(stats)
    payload["period_key"] = stats.get("period_key") or period_key
    payload["period_label"] = label
    return payload


@lru_cache(maxsize=1)
def _get_vary_helper():
    from app.main import _ensure_vary_header

    return _ensure_vary_header


def _compute_payload_etag(payload: dict[str, object]) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _set_stats_headers(response: Response, *, locale: str, etag: str | None = None) -> None:
    _get_vary_helper()(response, "Accept-Language")
    response.headers["Content-Language"] = locale
    response.headers["Cache-Control"] = _STATS_CACHE_CONTROL
    if etag:
        response.headers["ETag"] = format_etag(etag)


async def _maybe_serve_cached(
    *,
    cache_backend,
    kind: str,
    user: models.User,
    period_key: str,
    period_days: int,
    request: Request,
    response: Response,
    if_none_match: str | None,
    skip_cache: bool,
) -> Response | dict[str, object] | None:
    if skip_cache or not cache_backend.enabled:
        return None

    cached = await stats_cache.get_cached_stats(
        cache=cache_backend,
        kind=kind,
        user_id=user.id,
        period_key=period_key,
        skip_cache=skip_cache,
    )
    if cached is None:
        return None

    locale = resolve_locale(request=request, user=user)
    payload = _period_response_payload(
        stats=cached.payload,
        period_key=period_key,
        period_days=period_days,
        request=request,
        user=user,
        locale=locale,
    )
    if etag_matches(cached.etag, if_none_match):
        not_modified = Response(status_code=status.HTTP_304_NOT_MODIFIED)
        _set_stats_headers(not_modified, locale=locale, etag=cached.etag)
        return not_modified

    _set_stats_headers(response, locale=locale, etag=cached.etag)
    return payload


async def _build_stats_response(
    *,
    kind: str,
    period_key: str,
    period_days: int,
    request: Request,
    response: Response,
    user: models.User,
    if_none_match: str | None,
    skip_cache: bool,
    compute_stats: Callable[[BaseCache, bool], Awaitable[dict[str, object]]],
) -> Response | dict[str, object]:
    cache_backend = get_cache()
    skip_cache_effective = _should_skip_cache(skip_cache, user)

    cached_payload = await _maybe_serve_cached(
        cache_backend=cache_backend,
        kind=kind,
        user=user,
        period_key=period_key,
        period_days=period_days,
        request=request,
        response=response,
        if_none_match=if_none_match,
        skip_cache=skip_cache_effective,
    )
    if cached_payload is not None:
        return cached_payload

    stats = await compute_stats(cache_backend, skip_cache_effective)
    locale = resolve_locale(request=request, user=user)
    payload = _period_response_payload(
        stats=stats,
        period_key=period_key,
        period_days=period_days,
        request=request,
        user=user,
        locale=locale,
    )

    etag = _compute_payload_etag(payload)
    if cache_backend.enabled and not skip_cache_effective:
        refreshed = await stats_cache.get_cached_stats(
            cache=cache_backend,
            kind=kind,
            user_id=user.id,
            period_key=period_key,
            skip_cache=skip_cache_effective,
        )
        if refreshed:
            etag = refreshed.etag

    _set_stats_headers(response, locale=locale, etag=etag)
    return payload


@router.get("/attendance")
async def attendance_summary(
    request: Request,
    response: Response,
    period: str = Query("30d"),
    skip_cache: bool = Query(False, alias="skip_cache"),
    if_none_match: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    period_key, days = _resolve_period(period)
    return await _build_stats_response(
        kind="attendance",
        period_key=period_key,
        period_days=days,
        request=request,
        response=response,
        user=user,
        if_none_match=if_none_match,
        skip_cache=skip_cache,
        compute_stats=lambda cache_backend, skip: crud.get_attendance_stats(
            db,
            user_id=user.id,
            period_days=days,
            period_key=period_key,
            cache=cache_backend,
            skip_cache=skip,
        ),
    )


@router.get("/grades")
async def grade_summary(
    request: Request,
    response: Response,
    period: str = Query("30d"),
    skip_cache: bool = Query(False, alias="skip_cache"),
    if_none_match: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    period_key, days = _resolve_period(period)
    return await _build_stats_response(
        kind="grades",
        period_key=period_key,
        period_days=days,
        request=request,
        response=response,
        user=user,
        if_none_match=if_none_match,
        skip_cache=skip_cache,
        compute_stats=lambda cache_backend, skip: crud.get_grade_stats(
            db,
            user_id=user.id,
            period_days=days,
            cache=cache_backend,
            period_key=period_key,
            skip_cache=skip,
        ),
    )


@router.get("/participation")
async def participation_summary(
    request: Request,
    response: Response,
    period: str = Query("30d"),
    skip_cache: bool = Query(False, alias="skip_cache"),
    if_none_match: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    period_key, days = _resolve_period(period)
    return await _build_stats_response(
        kind="participation",
        period_key=period_key,
        period_days=days,
        request=request,
        response=response,
        user=user,
        if_none_match=if_none_match,
        skip_cache=skip_cache,
        compute_stats=lambda cache_backend, skip: crud.get_participation_stats(
            db,
            user_id=user.id,
            period_days=days,
            cache=cache_backend,
            period_key=period_key,
            skip_cache=skip,
        ),
    )
