import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.core.events import EventCreated, EventUpdated
from app.core.exceptions.domain import EntityNotFound
from app.core.localization import normalize_locale
from app.models import models
from app.repositories.event_repository import EventRepository
from app.schemas import schemas
from app.services import attendance_tokens, stats_cache
from app.services.vector_service import VectorService
from app.utils.pagination import decode_datetime_cursor, encode_datetime_cursor
from app.utils.sanitization import sanitize_optional_text

logger = logging.getLogger(__name__)


def _localized_event_field(
    locale: str | None,
    ru_value: str | None,
    en_value: str | None,
    *,
    required: bool = False,
) -> str | None:
    """Select the appropriate language field based on locale."""
    target = locale or "ru"
    if target == "ru":
        return ru_value or en_value
    return en_value or ru_value


class EventService:
    def __init__(self, repo: EventRepository, vector_service: VectorService):
        self.repo = repo
        self.vector_service = vector_service

    def serialize_event(
        self,
        record: models.Event,
        locale: str | None,
        *,
        participant_count: int = 0,
        files: Sequence[models.EventFile | schemas.EventFileOut] = (),
        is_registered: bool | None = None,
        my_qr_token: str | None = None,
    ) -> schemas.EventOut:
        normalized_locale = normalize_locale(locale)
        prepared_files: list[schemas.EventFileOut] = []
        for f in files:
            if isinstance(f, schemas.EventFileOut):
                prepared_files.append(f)
            else:
                prepared_files.append(schemas.EventFileOut.from_orm(f))

        data: dict[str, Any] = {
            "id": record.id,
            "title": _localized_event_field(
                normalized_locale,
                getattr(record, "title", None),
                getattr(record, "title_en", None),
                required=True,
            ),
            "description": _localized_event_field(
                normalized_locale,
                getattr(record, "description", None),
                getattr(record, "description_en", None),
            ),
            "title_en": sanitize_optional_text(getattr(record, "title_en", None)),
            "description_en": sanitize_optional_text(
                getattr(record, "description_en", None)
            ),
            "location": _localized_event_field(
                normalized_locale,
                getattr(record, "location", None),
                getattr(record, "location_en", None),
            ),
            "location_en": sanitize_optional_text(getattr(record, "location_en", None)),
            "event_type": _localized_event_field(
                normalized_locale,
                getattr(record, "event_type", None),
                getattr(record, "event_type_en", None),
            ),
            "event_type_en": sanitize_optional_text(
                getattr(record, "event_type_en", None)
            ),
            "starts_at": record.starts_at,
            "ends_at": record.ends_at,
            "created_by": record.created_by,
            "created_at": record.created_at,
            "is_active": getattr(record, "is_active", True),
            "speaker": getattr(record, "speaker", None),
            "image_url": getattr(record, "image_url", None),
            "about": _localized_event_field(
                normalized_locale,
                getattr(record, "about", None),
                getattr(record, "about_en", None),
            ),
            "about_en": sanitize_optional_text(getattr(record, "about_en", None)),
            "files": prepared_files,
            "participant_count": participant_count,
            "is_registered": is_registered,
            "my_qr_token": my_qr_token,
        }

        return schemas.EventOut.model_validate(data)

    async def get_events(
        self,
        *,
        user_id: int | None = None,
        search: str = "",
        type: str = "",
        location: str = "",
        is_active: bool | None = True,
        limit: int = 20,
        cursor: str | None = None,
        locale: str | None = None,
    ) -> schemas.PaginatedEvents:
        query_embedding = None
        if search:
            query_embedding = await self.vector_service.get_embedding(search)

        decoded_cursor = decode_datetime_cursor(cursor)

        # Get limit+1 to determine has_more
        results = await self.repo.search_events(
            user_id=user_id,
            search_query=search,
            event_type=type,
            location=location,
            is_active=is_active,
            limit=limit + 1,
            cursor=decoded_cursor,
            query_embedding=query_embedding,
        )

        has_more = len(results) > limit
        items_to_process = results[:limit]

        # Calculate total only on first page
        total = None
        if not cursor:
            total = (
                await self.repo.count_upcoming()
                if is_active is True
                else await self.repo.count()
            )

        output: list[schemas.EventOut] = []
        for row in items_to_process:
            event, p_count, attendance = row
            # If user_id is provided, attendance will be User's record or None
            is_registered = attendance is not None if user_id else None
            my_qr_token = None
            if is_registered and attendance:
                try:
                    my_qr_token = attendance_tokens.issue_token(attendance)
                except Exception:
                    # If token issue fails (missing secret etc),
                    # just ignore for list view
                    pass

            output.append(
                self.serialize_event(
                    event,
                    locale,
                    participant_count=p_count,
                    files=event.files,
                    is_registered=is_registered,
                    my_qr_token=my_qr_token,
                )
            )
        next_cursor = None
        if has_more and items_to_process:
            last_event, *_ = items_to_process[-1]
            next_cursor = encode_datetime_cursor(
                last_event.starts_at, str(last_event.id)
            )

        return schemas.PaginatedEvents(
            items=output,
            total=total,
            limit=limit,
            cursor=cursor,
            next_cursor=next_cursor,
            has_more=has_more,
        )

    async def create_event(
        self, data: schemas.EventCreate, user_id: int
    ) -> models.Event:
        if data.starts_at >= data.ends_at:
            from app.core.localization import translate

            raise ValueError(translate("validation.events.end_after_start"))

        obj_data = data.model_dump()
        obj_data["created_by"] = user_id
        event = await self.repo.create(obj_data)
        event.record_event(EventCreated(event_id_entity=event.id, title=event.title))
        await self.repo.db.commit()
        await self.repo.db.refresh(event)
        return event

    async def update_event(
        self, event_id: int, data: schemas.EventUpdate
    ) -> models.Event:
        event = await self.repo.get(event_id)
        if not event:
            raise EntityNotFound("Event", event_id)

        updates = data.model_dump(exclude_unset=True)
        text_changed = any(
            f in updates for f in ("title", "description", "location", "about")
        )

        if "starts_at" in updates or "ends_at" in updates:
            new_start = updates.get("starts_at", event.starts_at)
            new_end = updates.get("ends_at", event.ends_at)
            if new_start >= new_end:
                from app.core.localization import translate

                raise ValueError(translate("validation.events.end_after_start"))

        updated_event = await self.repo.update(event.id, updates)
        if text_changed:
            updated_event.record_event(
                EventUpdated(
                    event_id_entity=updated_event.id, title=updated_event.title
                )
            )

        await self.repo.db.commit()
        await self.repo.db.refresh(updated_event)
        return updated_event

    async def delete_event(self, event_id: int) -> bool:
        event = await self.repo.get(event_id)
        if not event:
            return False

        # Get file URLs before deletion
        result = await self.repo.db.execute(
            select(models.EventFile.file_url).where(
                models.EventFile.event_id == event_id
            )
        )
        file_urls = [row[0] for row in result.all() if row[0]]
        image_url = event.image_url

        from sqlalchemy import delete

        await self.repo.db.execute(
            delete(models.EventFile).where(models.EventFile.event_id == event_id)
        )
        await self.repo.delete(event_id)
        await self.repo.db.commit()

        from app.utils.files import delete_static_file

        if image_url:
            try:
                await delete_static_file(image_url)
            except Exception:
                pass

        for url in file_urls:
            try:
                await delete_static_file(url)
            except Exception:
                pass

        return True

    async def register_attendance(
        self, data: schemas.EventAttendanceCreate, user_id: int
    ) -> models.EventAttendance:
        cache_kinds = ("attendance", "participation")

        # Check existing using repo/session directly for now
        # as repo might not have this specific method
        # Ideally move this query to repo, but keeping logic here for migration speed
        stmt = (
            select(models.EventAttendance)
            .where(models.EventAttendance.event_id == data.event_id)
            .where(models.EventAttendance.user_id == user_id)
        )
        exist = (await self.repo.db.execute(stmt)).scalar_one_or_none()

        if exist:
            updated = False
            if exist.registered_at is None:
                exist.registered_at = datetime.now(UTC)
                updated = True
            if attendance_tokens.ensure_secret_material(exist):
                updated = True
            if updated:
                self.repo.db.add(exist)
                await self.repo.db.commit()
                await self.repo.db.refresh(exist)

            # Helper logic to set token attribute for response
            exist.qr_token = attendance_tokens.issue_token(exist)
            await stats_cache.invalidate_user_stats_cache(
                user_ids=user_id,
                kinds=cache_kinds,
            )
            return exist

        secret = attendance_tokens.generate_secret()
        record = models.EventAttendance(
            user_id=user_id,
            event_id=data.event_id,
            qr_secret=secret,
            qr_hmac=attendance_tokens.compute_secret_hmac(secret),
            registered_at=datetime.now(UTC),
        )
        self.repo.db.add(record)
        try:
            await self.repo.db.commit()
        except IntegrityError:
            await self.repo.db.rollback()
            # Race condition retry
            exist = (await self.repo.db.execute(stmt)).scalar_one_or_none()
            if not exist:
                event = await self.repo.get(data.event_id)
                if not event:
                    raise EntityNotFound("Event", data.event_id)
                raise ValueError("attendance_registration_failed")

            # Existing found after race
            updated = False
            if exist.registered_at is None:
                exist.registered_at = datetime.now(UTC)
                updated = True
            if attendance_tokens.ensure_secret_material(exist):
                updated = True
            if updated:
                self.repo.db.add(exist)
                await self.repo.db.commit()
                await self.repo.db.refresh(exist)

            exist.qr_token = attendance_tokens.issue_token(exist)
            await stats_cache.invalidate_user_stats_cache(
                user_ids=user_id,
                kinds=cache_kinds,
            )
            return exist

        await self.repo.db.refresh(record)
        record.qr_token = attendance_tokens.issue_token(record)
        await stats_cache.invalidate_user_stats_cache(
            user_ids=user_id,
            kinds=cache_kinds,
        )
        return record

    async def unregister_attendance(
        self, data: schemas.EventAttendanceCreate, user_id: int
    ) -> dict[str, bool]:
        stmt = (
            select(models.EventAttendance)
            .where(models.EventAttendance.event_id == data.event_id)
            .where(models.EventAttendance.user_id == user_id)
        )
        record = (await self.repo.db.execute(stmt)).scalar_one_or_none()
        if not record:
            return {"ok": False}

        await self.repo.db.delete(record)
        await self.repo.db.commit()
        await stats_cache.invalidate_user_stats_cache(
            user_ids=user_id,
            kinds=("attendance", "participation"),
        )
        return {"ok": True}

    async def get_my_events(
        self, user_id: int, *, locale: str | None = None
    ) -> list[schemas.EventOut]:
        # Logic from get_my_events in crud
        stmt = (
            select(models.Event)
            .join(models.EventAttendance)
            .where(models.EventAttendance.user_id == user_id)
            .options(
                selectinload(models.Event.files), selectinload(models.Event.attendance)
            )
        )
        events = (await self.repo.db.execute(stmt)).scalars().all()

        result: list[schemas.EventOut] = []
        for event in events:
            user_attendance = next(
                (a for a in event.attendance if a.user_id == user_id), None
            )
            qr_token = (
                attendance_tokens.issue_token(user_attendance)
                if user_attendance
                else None
            )

            result.append(
                self.serialize_event(
                    event,
                    locale,
                    participant_count=len(event.attendance),
                    files=event.files,
                    is_registered=True,
                    my_qr_token=qr_token,
                )
            )
        return result
