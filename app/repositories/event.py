from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import aliased, selectinload

from app.core.config import settings
from app.models import models
from app.repositories.base import BaseRepository


class EventRepository(BaseRepository[models.Event]):
    def __init__(self, db):
        super().__init__(models.Event, db)

    async def get_with_details(self, event_id: int) -> models.Event | None:
        stmt = (
            select(models.Event)
            .where(models.Event.id == event_id)
            .options(selectinload(models.Event.files))
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def search_events(
        self,
        *,
        user_id: int | None = None,
        search_query: str = "",
        event_type: str | None = None,
        location: str | None = None,
        is_active: bool | None = True,
        limit: int = 20,
        cursor: tuple[datetime, int] | None = None,
        query_embedding: list[float] | None = None,
    ) -> Sequence[tuple[models.Event, int, models.EventAttendance | None]]:
        now = datetime.now(UTC)

        # Build conditions
        conditions = []
        rank_expr = None

        if search_query:
            ts_query = func.plainto_tsquery("simple", search_query)
            conditions.append(models.Event.search_vector.op("@@")(ts_query))
            rank_expr = func.ts_rank(models.Event.search_vector, ts_query)

            if (
                settings.semantic_search_enabled
                and query_embedding
                and any(v != 0.0 for v in query_embedding)
            ):
                sim_score = 1.0 - models.Event.embedding.cosine_distance(
                    query_embedding
                )
                rank_expr = (rank_expr + sim_score * 2.0).label("hybrid_rank")
                conditions = [or_(and_(*conditions), sim_score > 0.6)]

        if event_type:
            conditions.append(
                or_(
                    models.Event.event_type == event_type,
                    models.Event.event_type_en == event_type,
                )
            )

        if location:
            conditions.append(
                or_(
                    models.Event.location.ilike(f"%{location}%"),
                    models.Event.location_en.ilike(f"%{location}%"),
                )
            )

        if is_active is True:
            conditions.append(models.Event.ends_at >= now)
        elif is_active is False:
            conditions.append(models.Event.ends_at < now)

        if cursor:
            last_starts_at, last_id = cursor
            conditions.append(
                or_(
                    models.Event.starts_at > last_starts_at,
                    and_(
                        models.Event.starts_at == last_starts_at,
                        models.Event.id > last_id,
                    ),
                )
            )

        # Attendance counts and current user attendance
        participant_count_sub = (
            select(func.count())
            .where(models.EventAttendance.event_id == models.Event.id)
            .correlate(models.Event)
            .scalar_subquery()
            .label("participant_count")
        )

        user_attendance_alias = aliased(models.EventAttendance)
        join_cond = user_attendance_alias.event_id == models.Event.id
        if user_id:
            join_cond = and_(join_cond, user_attendance_alias.user_id == user_id)
        else:
            # Join with something that never matches to keep the structure
            # but avoid leaks
            join_cond = and_(join_cond, user_attendance_alias.user_id == -1)

        stmt = (
            select(models.Event, participant_count_sub, user_attendance_alias)
            .outerjoin(user_attendance_alias, join_cond)
            .options(selectinload(models.Event.files))
        )

        if conditions:
            stmt = stmt.where(and_(*conditions))

        if rank_expr is not None:
            stmt = stmt.order_by(
                rank_expr.desc(), models.Event.starts_at.asc(), models.Event.id.asc()
            )
        else:
            stmt = stmt.order_by(models.Event.starts_at.asc(), models.Event.id.asc())

        stmt = stmt.limit(limit)
        result = await self.db.execute(stmt)
        return result.all()
