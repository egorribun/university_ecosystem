"""Schedule-specific API routes."""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from typing import Annotated

from dishka import FromComponent
from dishka.integrations.fastapi import inject
from fastapi import APIRouter, Query, Request, Response

import app.models as models
from app.api.validation import raise_not_found
from app.core.di.read_replica import READ_COMPONENT
from app.core.localization import resolve_locale, translate
from app.core.protocols import AsyncDatabaseSession
from app.schemas.dtos import ScheduleDTO
from app.services.ical import generate_schedule_ics
from app.services.schedule_service import ScheduleService

router = APIRouter(prefix="/schedule", tags=["schedule"])


def _build_filename(group: models.Group) -> str:
    name = getattr(group, "name", None) or f"group-{group.id}"
    normalized = re.sub(r"[^A-Za-z0-9]+", "-", name, flags=re.UNICODE).strip("-")
    safe_name = normalized.lower() or f"group-{group.id}"
    return f"schedule-{safe_name}.ics"


@router.get("/ics", response_class=Response, response_model=None)
@inject
# nosec: public_endpoint
async def download_schedule_ics(
    request: Request,
    schedule_service: Annotated[ScheduleService, FromComponent(READ_COMPONENT)],
    db: Annotated[AsyncDatabaseSession, FromComponent(READ_COMPONENT)],
    group: uuid.UUID = Query(
        ..., description=translate("schedule.query.group_id_description")
    ),
) -> Response:
    locale = resolve_locale(request=request)
    group_obj = await db.get(models.Group, group)
    if not group_obj:
        raise_not_found("Group", locale=locale)

    lessons: Sequence[ScheduleDTO] = await schedule_service.get_schedule(group)
    ics_body = generate_schedule_ics(group_obj, lessons, locale=locale)
    filename = _build_filename(group_obj)

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "no-cache",
    }
    if locale:
        headers["Content-Language"] = locale
    return Response(
        content=ics_body, media_type="text/calendar; charset=utf-8", headers=headers
    )
