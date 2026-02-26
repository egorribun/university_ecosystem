from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import and_, case, func, literal, select, true
from sqlalchemy.orm import aliased

from app.core.protocols import AsyncDatabaseSession
from app.models import models
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
        """
        Execute the complex attendance stats query.
        Returns raw rows for processing by service.
        """
        attendance_alias = aliased(models.EventAttendance)

        # CTE for filtered events
        filtered_events = (
            select(
                models.Event.id.label("event_id"),
                case(
                    (models.Event.starts_at >= window_start, literal("current")),
                    else_=literal("previous"),
                ).label("period"),
            )
            .where(
                models.Event.is_active.is_(True),
                models.Event.starts_at >= previous_start,
                models.Event.starts_at < now,
            )
            .cte("filtered_events")
        )

        attendance_join = filtered_events.outerjoin(
            attendance_alias,
            and_(
                attendance_alias.event_id == filtered_events.c.event_id,
                attendance_alias.user_id == user_id,
            ),
        )

        stats_subquery = (
            select(
                func.coalesce(
                    func.sum(case((filtered_events.c.period == "current", 1), else_=0)),
                    0,
                ).label("current_total"),
                func.coalesce(
                    func.sum(
                        case((filtered_events.c.period == "previous", 1), else_=0)
                    ),
                    0,
                ).label("previous_total"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                and_(
                                    filtered_events.c.period == "current",
                                    attendance_alias.id.isnot(None),
                                ),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("current_attended"),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                and_(
                                    filtered_events.c.period == "previous",
                                    attendance_alias.id.isnot(None),
                                ),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ).label("previous_attended"),
            ).select_from(attendance_join)
        ).subquery()

        recent_attendance_base = (
            select(
                models.EventAttendance.registered_at.label("registered_at"),
                models.Event.starts_at.label("starts_at"),
                models.Event.title.label("title"),
                func.row_number()
                .over(order_by=models.EventAttendance.registered_at.desc())
                .label("rn"),
            )
            .join(models.Event, models.Event.id == models.EventAttendance.event_id)
            .where(
                models.EventAttendance.user_id == user_id,
                models.Event.is_active.is_(True),
                models.Event.starts_at >= window_start,
                models.Event.starts_at < now,
            )
        ).subquery()

        top_recent = (
            select(
                recent_attendance_base.c.registered_at,
                recent_attendance_base.c.starts_at,
                recent_attendance_base.c.title,
                recent_attendance_base.c.rn,
            ).where(recent_attendance_base.c.rn <= 5)
        ).subquery()

        stmt = (
            select(
                stats_subquery.c.current_total,
                stats_subquery.c.previous_total,
                stats_subquery.c.current_attended,
                stats_subquery.c.previous_attended,
                top_recent.c.registered_at,
                top_recent.c.starts_at,
                top_recent.c.title,
                top_recent.c.rn,
            )
            .select_from(stats_subquery.outerjoin(top_recent, true()))
            .order_by(top_recent.c.rn)
        )

        result = await self.db.execute(stmt)
        return result.all()

    async def get_grade_notifications(
        self,
        user_id: uuid.UUID | str,
        start_date: datetime,
        end_date: datetime,
    ) -> Sequence[models.Notification]:
        """Fetch grade notifications for a specific period."""
        stmt = (
            select(models.Notification)
            .where(
                models.Notification.user_id == user_id,
                models.Notification.type == "grade",
                models.Notification.created_at >= start_date,
                models.Notification.created_at < end_date,
            )
            .order_by(models.Notification.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_participation_stats_raw(
        self,
        user_id: uuid.UUID | str,
        window_start: datetime,
        now: datetime,
    ) -> list[ParticipationStatsDTO]:
        """
        Fetch raw participation data: count, hours, and distinct groups.
        """
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


def get_user_stats_repository(db: AsyncDatabaseSession) -> UserStatsRepository:
    return UserStatsRepository(db)
