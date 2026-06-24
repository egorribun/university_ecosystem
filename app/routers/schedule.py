"""Schedule-specific API routes."""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

import app.models as models
from app.api.deps import get_read_schedule_service
from app.api.validation import raise_not_found
from app.core.database import get_read_db
from app.core.localization import resolve_locale, translate
from app.services.ical import generate_schedule_ics

router = APIRouter(prefix="/schedule", tags=["schedule"])


def _build_filename(group: models.Group) -> str:
    name = getattr(group, "name", None) or f"group-{group.id}"
    normalized = re.sub(r"[^A-Za-z0-9]+", "-", name, flags=re.UNICODE).strip("-")
    safe_name = normalized.lower() or f"group-{group.id}"
    return f"schedule-{safe_name}.ics"


@router.get("/ics", response_class=Response)
# nosec: public_endpoint
async def download_schedule_ics(
    request: Request,
    schedule_service: Annotated[Any, Depends(get_read_schedule_service)],
    group: uuid.UUID = Query(
        ..., description=translate("schedule.query.group_id_description")
    ),
    db: AsyncSession = Depends(get_read_db),
) -> Response:
    locale = resolve_locale(request=request)
    group_obj = await db.get(models.Group, group)
    if not group_obj:
        raise_not_found("Group", locale=locale)

    lessons: Sequence[models.Schedule] = await schedule_service.get_schedule(group)
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
