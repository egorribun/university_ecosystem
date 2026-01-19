"""Schedule-specific API routes."""

from __future__ import annotations

import re
from collections.abc import Sequence

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.api.validation import raise_not_found
from app.core.database import get_db
from app.core.localization import resolve_locale, translate
from app.models import models
from app.services.ical import generate_schedule_ics

router = APIRouter(prefix="/schedule", tags=["schedule"])


def _build_filename(group: models.Group) -> str:
    name = getattr(group, "name", None) or f"group-{group.id}"
    normalized = re.sub(r"[^A-Za-z0-9]+", "-", name, flags=re.UNICODE).strip("-")
    safe_name = normalized.lower() or f"group-{group.id}"
    return f"schedule-{safe_name}.ics"


@router.get("/ics", response_class=Response)
async def download_schedule_ics(
    request: Request,
    group: int = Query(
        ..., description=translate("schedule.query.group_id_description")
    ),
    db: AsyncSession = Depends(get_db),
) -> Response:
    locale = resolve_locale(request=request)
    group_obj = await db.get(models.Group, group)
    if not group_obj:
        raise_not_found("Group", group, locale)

    lessons: Sequence[models.Schedule] = await crud.get_schedule_by_group(db, group)
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
