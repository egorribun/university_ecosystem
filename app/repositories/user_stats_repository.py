from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import and_, case, literal, select, union_all

import app.models as models
from app.repositories.base import ReadOnlyRepository
from app.schemas.dtos import UserDTO
from app.schemas.dtos.analytics import ParticipationStatsDTO


class UserStatsRepository(ReadOnlyRepository[models.User, UserDTO]):
    """Repository for User Statistics and Analytics."""

    @property
    def model(self) -> type[models.User]:
        return models.User

    @property
    def dto_class(self) -> type[UserDTO]:
        return UserDTO

    async def get_attendance_stats_raw(
        self,
        user_id: uuid.UUID | str,
        window_start: datetime,
        previous_start: datetime,
        now: datetime,
    ) -> Sequence[Any]:
        """Project window events and older user history in one scalar query.

        Disjoint indexed populations avoid a left-join OR over global history.
        There is no synthetic aggregate row when both populations are empty.
        """
        attendance = models.EventAttendance
        registered_current = and_(
            models.Event.starts_at >= window_start,
            attendance.id.isnot(None),
        )
        window_events = (
            select(
                models.Event.starts_at.label("starts_at"),
                case((registered_current, models.Event.title), else_=None).label(
                    "title"
                ),
                case((registered_current, attendance.registered_at), else_=None).label(
                    "registered_at"
                ),
                attendance.id.isnot(None).label("is_registered"),
            )
            .select_from(models.Event)
            .outerjoin(
                attendance,
                and_(
                    attendance.event_id == models.Event.id,
                    attendance.user_id == user_id,
                ),
            )
            .where(
                models.Event.is_active.is_(True),
                models.Event.starts_at >= previous_start,
                models.Event.starts_at < now,
            )
        )
        history_events = (
            select(
                models.Event.starts_at.label("starts_at"),
                literal(None, type_=models.Event.title.type).label("title"),
                literal(None, type_=attendance.registered_at.type).label(
                    "registered_at"
                ),
                literal(True).label("is_registered"),
            )
            .select_from(attendance)
            .join(models.Event, models.Event.id == attendance.event_id)
            .where(
                attendance.user_id == user_id,
                models.Event.is_active.is_(True),
                models.Event.starts_at < previous_start,
                models.Event.starts_at < now,
            )
        )
        # The service sorts only current registered rows for the capped recent feed.
        result = await self.db.execute(union_all(window_events, history_events))
        return result.all()

    async def get_grades(
        self,
        user_id: uuid.UUID | str,
        start_date: datetime,
        end_date: datetime,
    ) -> Sequence[models.Grade]:
        """Fetch the student's grades assigned in ``[start_date, end_date)``."""
        stmt = (
            select(models.Grade)
            .where(
                models.Grade.student_id == user_id,
                models.Grade.created_at >= start_date,
                models.Grade.created_at < end_date,
            )
            .order_by(models.Grade.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_participation_stats_raw(
        self,
        user_id: uuid.UUID | str,
        window_start: datetime,
        now: datetime,
    ) -> list[ParticipationStatsDTO]:
        """Fetch registrations for the supplied half-open event window."""
        stmt = (
            select(
                models.Event.id,
                models.Event.title,
                models.Event.event_type,
                models.Event.starts_at,
                models.Event.ends_at,
            )
            .join(
                models.EventAttendance,
                models.EventAttendance.event_id == models.Event.id,
            )
            .where(
                models.EventAttendance.user_id == user_id,
                models.Event.is_active.is_(True),
                models.Event.starts_at >= window_start,
                models.Event.starts_at < now,
            )
            .order_by(models.Event.starts_at.desc())
        )
        result = await self.db.execute(stmt)
        return [
            ParticipationStatsDTO(
                event_id=row.id,
                title=row.title,
                event_type=row.event_type,
                starts_at=row.starts_at,
                ends_at=row.ends_at,
            )
            for row in result.all()
        ]
