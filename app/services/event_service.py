import base64
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
        return ru_value or (en_value if not required else ru_value)
    return en_value or (ru_value if not required else en_value)


def _decode_event_cursor(value: str | None) -> tuple[datetime, int] | None:
    if not value:
        return None
    try:
        parts = base64.urlsafe_b64decode(value).decode("utf-8").split(":")
        if len(parts) != 2:
            return None
        ts = float(parts[0])
        event_id = int(parts[1])
        return datetime.fromtimestamp(ts, tz=UTC), event_id
    except Exception:
        return None


def _encode_event_cursor(starts_at: datetime, event_id: int) -> str:
    payload = f"{starts_at.timestamp()}:{event_id}"
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("utf-8")


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
    ) -> list[schemas.EventOut]:
        query_embedding = None
        if search:
            query_embedding = await self.vector_service.get_embedding(search)

        decoded_cursor = _decode_event_cursor(cursor)

        results = await self.repo.search_events(
            user_id=user_id,
            search_query=search,
            event_type=type,
            location=location,
            is_active=is_active,
            limit=limit,
            cursor=decoded_cursor,
            query_embedding=query_embedding,
        )

        output: list[schemas.EventOut] = []
        for row in results:
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
        return output

    async def create_event(
        self, data: schemas.EventCreate, user_id: int
    ) -> models.Event:
        event = await self.repo.create(**data.model_dump(), created_by=user_id)
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

        updated_event = await self.repo.update(event, **updates)
        if text_changed:
            updated_event.record_event(
                EventUpdated(
                    event_id_entity=updated_event.id, title=updated_event.title
                )
            )

        await self.repo.db.commit()
        await self.repo.db.refresh(updated_event)
        return updated_event

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
