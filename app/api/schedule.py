import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from functools import lru_cache

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import (
    APIRouter,
    Depends,
    Header,
    Request,
    Response,
    status,
)

import app.models as models
from app.api.deps import get_current_user, get_current_user_optional
from app.api.validation import ensure_exists, raise_forbidden, require_teacher_or_admin
from app.core.localization import resolve_locale
from app.cqrs.bus import CommandBus, QueryBus
from app.cqrs.commands.schedule import (
    CreateScheduleCommand,
    DeleteScheduleCommand,
    UpdateScheduleCommand,
)
from app.cqrs.queries import GetScheduleQuery
from app.models.enums import UserRole
from app.schemas import schemas


@lru_cache(maxsize=1)
def _get_vary_helper() -> Callable[[Response, str], None]:
    from app.core.middleware.response_hardening import _ensure_vary_header

    return _ensure_vary_header


_SCHEDULE_CACHE_TTL_SECONDS = 300
_SCHEDULE_CACHE_CONTROL = f"private, max-age={_SCHEDULE_CACHE_TTL_SECONDS}"


router = APIRouter(prefix="/schedule", tags=["schedule"])


def _schedule_cache_key(group_id: uuid.UUID) -> str:
    return f"schedule:group:{group_id}"


def _set_schedule_cache_headers(response: Response) -> None:
    response.headers["Cache-Control"] = _SCHEDULE_CACHE_CONTROL
    expires_at = datetime.now(UTC) + timedelta(seconds=_SCHEDULE_CACHE_TTL_SECONDS)
    response.headers["Expires"] = format_datetime(expires_at, usegmt=True)


@router.post("", response_model=schemas.ScheduleOut)
@inject
async def add_schedule(
    data: schemas.ScheduleCreate,
    request: Request,
    command_bus: FromDishka[CommandBus],
    user: models.User = Depends(get_current_user),
) -> schemas.ScheduleOut:
    locale = resolve_locale(request=request, user=user)
    require_teacher_or_admin(user, locale)

    from app.api.validation import raise_conflict
    from app.core.exceptions.domain import BusinessRuleViolation

    try:
        command = CreateScheduleCommand(data=data, locale=locale, actor_id=user.id)
        result = await command_bus.execute(command)
    except BusinessRuleViolation as e:
        # Map domain exception to API conflict error
        raise_conflict(str(e), locale, exact_key="errors.schedule.conflict")

    return schemas.ScheduleOut.model_validate(result)


@router.get("/{id}", response_model=list[schemas.ScheduleOut])
@inject
async def get_schedule(
    id: uuid.UUID,
    request: Request,
    response: Response,
    query_bus: FromDishka[QueryBus],
    user: models.User | None = Depends(get_current_user_optional),
    if_none_match: str | None = Header(default=None),
) -> list[schemas.ScheduleOut] | Response:
    locale = resolve_locale(request=request)
    _get_vary_helper()(response, "Accept-Language")
    response.headers["Content-Language"] = locale
    _set_schedule_cache_headers(response)

    query = GetScheduleQuery(
        group_id=id,
        locale=locale,
        if_none_match=if_none_match,
    )
    result = await query_bus.execute(query)

    if result.not_modified:
        cached_response = Response(status_code=status.HTTP_304_NOT_MODIFIED)
        cached_response.headers["ETag"] = result.etag
        _get_vary_helper()(cached_response, "Accept-Language")
        _set_schedule_cache_headers(cached_response)
        return cached_response

    if result.etag:
        response.headers["ETag"] = result.etag

    from typing import cast

    return cast(list[schemas.ScheduleOut], result.payload)


@router.patch("/{id}", response_model=schemas.ScheduleOut)
@inject
async def update_schedule(
    id: uuid.UUID,
    data: schemas.ScheduleUpdate,
    request: Request,
    command_bus: FromDishka[CommandBus],
    user: models.User = Depends(get_current_user),
) -> schemas.ScheduleOut:
    locale = resolve_locale(request=request, user=user)
    require_teacher_or_admin(user, locale)

    try:
        command = UpdateScheduleCommand(
            schedule_id=id,
            data=data,
            actor_id=user.id,
            actor_role=UserRole(user.role) if user.role else UserRole.STUDENT,
        )
        updated = await command_bus.execute(command)
    except PermissionError:
        # SEC-BE-01: teacher tried to update another teacher's schedule
        raise_forbidden(locale)
    except ValueError:
        ensure_exists(None, "schedule", locale)  # Will raise 404

    return schemas.ScheduleOut.model_validate(updated)


@router.delete("/{id}", response_model=dict)
@inject
async def delete_schedule(
    id: uuid.UUID,
    request: Request,
    command_bus: FromDishka[CommandBus],
    user: models.User = Depends(get_current_user),
) -> dict[str, bool]:
    locale = resolve_locale(request=request, user=user)
    require_teacher_or_admin(user, locale)

    command = DeleteScheduleCommand(schedule_id=id)
    deleted = await command_bus.execute(command)
    if not deleted:
        ensure_exists(None, "schedule", locale)

    return {"ok": True}


__all__ = ["router"]
