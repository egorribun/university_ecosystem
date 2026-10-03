"""Grade management: persistence, audit trail, student notification, cache."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from app.core.protocols import AsyncDatabaseSession
from app.models.grade import Grade
from app.models.users import User
from app.services import stats_cache
from app.services.audit_service import get_secure_audit_service
from app.services.notifications.delivery import create_notifications_for_users


class GradeNotFoundError(LookupError):
    """The grade does not exist."""


class GradeStudentNotFoundError(LookupError):
    """The target student does not exist or is deactivated."""


class GradeService:
    """Assign and modify grades.

    The ``grades`` table is the single source of truth consumed by the statistics
    layer.  Mutations are flush-only: the caller owns the transaction and must call
    :meth:`invalidate_stats` after a successful commit.
    """

    def __init__(self, db: AsyncDatabaseSession) -> None:
        self.db = db

    async def get_grade(self, grade_id: uuid.UUID) -> Grade | None:
        result = await self.db.execute(select(Grade).where(Grade.id == grade_id))
        return result.scalars().first()

    async def assign_grade(
        self,
        *,
        student_id: uuid.UUID,
        subject: str,
        score: float,
        assessment_type: str = "exam",
        assigned_by: uuid.UUID | None = None,
    ) -> Grade:
        student = await self.db.get(User, student_id)
        if student is None or not student.is_active:
            raise GradeStudentNotFoundError(str(student_id))

        grade = Grade(
            student_id=student_id,
            subject=subject,
            score=score,
            assessment_type=assessment_type,
            assigned_by=assigned_by,
        )
        self.db.add(grade)
        await self.db.flush()

        payload: dict[str, Any] = {
            "student_id": str(student_id),
            "subject": subject,
            "score": score,
            "assessment_type": assessment_type,
            "assigned_by": str(assigned_by) if assigned_by else None,
        }
        await get_secure_audit_service().record_domain_event(
            self.db,
            event_type="GRADE_ASSIGNED",
            aggregate_type="grade",
            aggregate_id=grade.id,
            payload=payload,
            actor_id=assigned_by,
        )
        await create_notifications_for_users(
            self.db,
            title=f"Новая оценка: {subject}",
            body=f"{score:g}",
            title_translations={
                "ru": f"Новая оценка: {subject}",
                "en": f"New grade: {subject}",
            },
            body_translations={"ru": f"{score:g}", "en": f"{score:g}"},
            type="grade",
            user_ids=[student_id],
        )
        return grade

    async def modify_grade(
        self,
        *,
        grade_id: uuid.UUID,
        new_score: float,
        reason: str | None = None,
        modified_by: uuid.UUID | None = None,
    ) -> Grade:
        grade = await self.get_grade(grade_id)
        if grade is None:
            raise GradeNotFoundError(str(grade_id))

        old_score = grade.score
        grade.score = new_score
        await self.db.flush()

        payload: dict[str, Any] = {
            "old_score": old_score,
            "new_score": new_score,
            "reason": reason,
            "modified_by": str(modified_by) if modified_by else None,
            "current_state": {
                "student_id": str(grade.student_id),
                "subject": grade.subject,
                "score": new_score,
                "assessment_type": grade.assessment_type,
            },
        }
        await get_secure_audit_service().record_domain_event(
            self.db,
            event_type="GRADE_MODIFIED",
            aggregate_type="grade",
            aggregate_id=grade.id,
            payload=payload,
            actor_id=modified_by,
        )
        return grade

    @staticmethod
    async def invalidate_stats(student_id: uuid.UUID) -> None:
        await stats_cache.invalidate_user_stats_cache(
            user_ids=[student_id], kinds=("grades",)
        )
