"""Grade management API (teachers and administrators)."""

from __future__ import annotations

import uuid
from typing import Annotated

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Depends, Request, status

import app.models as models
from app.api.deps import get_current_user_from_dishka
from app.api.validation import (
    raise_forbidden,
    raise_not_found,
    require_teacher_or_admin,
)
from app.core.localization import resolve_locale
from app.core.protocols import AsyncDatabaseSession
from app.core.ratelimit import sensitive_route_limit
from app.models.enums import UserRole
from app.schemas import schemas
from app.services.grade_service import (
    GradeNotFoundError,
    GradeService,
    GradeStudentNotFoundError,
)

router = APIRouter(prefix="/grades", tags=["grades"])


@router.post(
    "",
    response_model=schemas.GradeOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(sensitive_route_limit())],
)
@inject
async def assign_grade(
    data: schemas.GradeCreate,
    request: Request,
    service: FromDishka[GradeService],
    db: FromDishka[AsyncDatabaseSession],
    user: Annotated[models.User, Depends(get_current_user_from_dishka)],
) -> schemas.GradeOut:
    locale = resolve_locale(request=request, user=user)
    require_teacher_or_admin(user, locale)

    try:
        grade = await service.assign_grade(
            student_id=data.student_id,
            subject=data.subject,
            score=data.score,
            assessment_type=data.assessment_type,
            assigned_by=user.id,
        )
    except GradeStudentNotFoundError:
        raise_not_found("users", locale)
    await db.commit()
    await service.invalidate_stats(grade.student_id)
    return schemas.GradeOut.model_validate(grade)


@router.patch(
    "/{grade_id}",
    response_model=schemas.GradeOut,
    dependencies=[Depends(sensitive_route_limit())],
)
@inject
async def modify_grade(
    grade_id: uuid.UUID,
    data: schemas.GradeUpdate,
    request: Request,
    service: FromDishka[GradeService],
    db: FromDishka[AsyncDatabaseSession],
    user: Annotated[models.User, Depends(get_current_user_from_dishka)],
) -> schemas.GradeOut:
    locale = resolve_locale(request=request, user=user)
    require_teacher_or_admin(user, locale)

    existing = await service.get_grade(grade_id)
    if existing is None:
        raise_not_found("grades", locale)
    # Teachers may only correct grades they assigned themselves.
    if user.role != UserRole.ADMIN and existing.assigned_by != user.id:
        raise_forbidden(locale)

    try:
        grade = await service.modify_grade(
            grade_id=grade_id,
            new_score=data.score,
            reason=data.reason,
            modified_by=user.id,
        )
    except GradeNotFoundError:  # deleted between the read and the update
        raise_not_found("grades", locale)
    await db.commit()
    await service.invalidate_stats(grade.student_id)
    return schemas.GradeOut.model_validate(grade)
