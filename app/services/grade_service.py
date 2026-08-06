import uuid
from typing import Any

from sqlalchemy import select

from app.core.protocols import AsyncDatabaseSession
from app.models.grade import Grade
from app.services.audit_service import get_secure_audit_service


class GradeService:
    """
    Service for managing student grades and emitting event-sourced domain events.
    """

    async def assign_grade(
        self,
        db: AsyncDatabaseSession,
        *,
        student_id: uuid.UUID,
        subject: str,
        score: float,
        assessment_type: str = "exam",
        assigned_by: uuid.UUID | None = None,
    ) -> Grade:
        grade = Grade(
            student_id=student_id,
            subject=subject,
            score=score,
            assessment_type=assessment_type,
            assigned_by=assigned_by,
        )
        db.add(grade)
        await db.flush()

        payload: dict[str, Any] = {
            "student_id": str(student_id),
            "subject": subject,
            "score": score,
            "assessment_type": assessment_type,
            "assigned_by": str(assigned_by) if assigned_by else None,
        }

        audit_service = get_secure_audit_service()
        await audit_service.record_domain_event(
            db,
            event_type="GRADE_ASSIGNED",
            aggregate_type="grade",
            aggregate_id=grade.id,
            payload=payload,
            actor_id=assigned_by,
        )

        return grade

    async def modify_grade(
        self,
        db: AsyncDatabaseSession,
        *,
        grade_id: uuid.UUID,
        new_score: float,
        reason: str | None = None,
        modified_by: uuid.UUID | None = None,
    ) -> Grade:
        stmt = select(Grade).where(Grade.id == grade_id)
        result = await db.execute(stmt)
        grade = result.scalars().first()

        if not grade:
            raise ValueError(f"Grade {grade_id} not found")

        old_score = grade.score
        grade.score = new_score
        await db.flush()

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

        audit_service = get_secure_audit_service()
        await audit_service.record_domain_event(
            db,
            event_type="GRADE_MODIFIED",
            aggregate_type="grade",
            aggregate_id=grade.id,
            payload=payload,
            actor_id=modified_by,
        )

        return grade
