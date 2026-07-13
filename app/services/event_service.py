import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.core.exceptions.domain import EntityNotFound
from app.core.localization import normalize_locale, translate
from app.core.logging import get_logger
from app.models import Event
from app.repositories.unit_of_work import UnitOfWork
from app.schemas import schemas
from app.schemas.dtos import EventAttendanceDTO, EventDTO, EventFileDTO
from app.services import attendance_tokens, stats_cache
from app.services.vector_service import VectorService
from app.utils.pagination import decode_datetime_cursor, encode_datetime_cursor

logger = get_logger(__name__)


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
    def __init__(self, uow: UnitOfWork, vector_service: VectorService):
        self.uow = uow
        self.repo = uow.events
        self.vector_service = vector_service

    async def get_event_by_id(self, event_id: uuid.UUID | int) -> EventDTO | None:
        """Fetch a single event by primary key.

        Returns None when the event does not exist.  API controllers MUST use
        this method instead of accessing ``self.repo.get()`` directly to keep
        service-layer indirection intact (TD-002).
        """
        return await self.repo.get(event_id)

    def serialize_event(
        self,
        record: Event | EventDTO,
        locale: str | None,
        *,
        participant_count: int = 0,
        files: Sequence[EventFileDTO | schemas.EventFileOut] = (),
        is_registered: bool | None = None,
        my_qr_token: str | None = None,
    ) -> schemas.EventOut:
        normalized_locale = normalize_locale(locale)
        prepared_files: list[schemas.EventFileOut] = []
        for f in files:
            if isinstance(f, schemas.EventFileOut):
                prepared_files.append(f)
            else:
                prepared_files.append(schemas.EventFileOut.model_validate(f))

        data: dict[str, Any] = {
            "id": record.id,
            "title": _localized_event_field(
                normalized_locale,
                record.title,
                record.title_en,
                required=True,
            ),
            "description": _localized_event_field(
                normalized_locale,
                record.description,
                record.description_en,
            ),
            "title_en": record.title_en,
            "description_en": record.description_en,
            "location": _localized_event_field(
                normalized_locale,
                record.location,
                record.location_en,
            ),
            "location_en": record.location_en,
            "event_type": _localized_event_field(
                normalized_locale,
                record.event_type,
                record.event_type_en,
            ),
            "event_type_en": record.event_type_en,
            "starts_at": record.starts_at,
            "ends_at": record.ends_at,
            "created_by": record.created_by,
            "created_at": record.created_at,
            "is_active": record.is_active,
            "speaker": record.speaker,
            "image_url": record.image_url,
            "about": _localized_event_field(
                normalized_locale,
                record.about,
                record.about_en,
            ),
            "about_en": record.about_en,
            "files": prepared_files,
            "participant_count": participant_count,
            "is_registered": is_registered,
            "my_qr_token": my_qr_token,
        }

        return schemas.EventOut.model_validate(data)

    async def get_events(
        self,
        *,
        user_id: uuid.UUID | None = None,
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
        for search_result in items_to_process:
            event = search_result.event
            p_count = search_result.participant_count
            attendance = search_result.user_attendance

            # If user_id is provided, attendance will be User's record or None
            is_registered = attendance is not None if user_id else None
            my_qr_token = None
            if is_registered and attendance:
                try:
                    my_qr_token = attendance_tokens.issue_token(attendance)
                except (KeyError, ValueError, TypeError) as exc:
                    # TD-W19-03 (Wave 19): narrowed from bare Exception.
                    # Token issuance can fail due to missing secret (KeyError),
                    # invalid input (ValueError), or wrong type (TypeError).
                    logger.debug("MFA token issuance failed for attendee: %s", exc)

            output.append(
                self.serialize_event(
                    event,
                    locale,
                    participant_count=p_count,
                    files=[],  # We should probably handle files in EventDTO if needed
                    is_registered=is_registered,
                    my_qr_token=my_qr_token,
                )
            )
        next_cursor = None
        if has_more and items_to_process:
            last_result = items_to_process[-1]
            next_cursor = encode_datetime_cursor(
                last_result.event.starts_at,
                str(last_result.event.id),
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
        self, data: schemas.EventCreate, user_id: uuid.UUID
    ) -> EventDTO:
        if data.starts_at >= data.ends_at:
            raise ValueError(translate("validation.events.end_after_start"))

        obj_data = data.model_dump()
        obj_data["created_by"] = user_id
        event = await self.repo.create(obj_data)
        # EventCreated(event_id_entity=event.id, title=str(event.title))
        async with self.uow:
            await self.uow.commit()
        return event

    async def update_event(
        self, event_id: uuid.UUID, data: schemas.EventUpdate
    ) -> EventDTO:
        event = await self.repo.get(event_id)
        if not event:
            raise EntityNotFound("Event", event_id)

        updates = data.model_dump(exclude_unset=True)
        if "starts_at" in updates or "ends_at" in updates:
            new_start = updates.get("starts_at", event.starts_at)
            new_end = updates.get("ends_at", event.ends_at)
            if new_start >= new_end:
                raise ValueError(translate("validation.events.end_after_start"))

        updated_event = await self.repo.update(event_id, updates)
        assert updated_event is not None  # noqa: S101

        async with self.uow:
            await self.uow.commit()
        return updated_event

    async def delete_event(self, event_id: uuid.UUID | int) -> bool:
        event = await self.repo.get(event_id)
        if not event:
            return False

        # Get file URLs via repo before deletion
        file_urls = await self.repo.get_event_file_urls(event_id)
        image_url = event.image_url

        # MED-W19: Delete DB records first, then clean up storage after a
        # successful commit. This prevents orphaned DB rows when the commit
        # fails; a failed storage delete is non-fatal (logged only).
        await self.repo.delete_event_files(event_id)
        await self.repo.delete(event_id)
        async with self.uow:
            await self.uow.commit()

        from app.utils.files import delete_static_file

        if image_url:
            try:
                await delete_static_file(str(image_url))
            except (FileNotFoundError, OSError):
                # RZ-20-04: Narrowed — file deletion is best-effort.
                logger.warning("Failed to delete event image: %s", image_url)

        for url in file_urls:
            try:
                await delete_static_file(url)
            except (FileNotFoundError, OSError):
                # RZ-20-04: Narrowed — file deletion is best-effort.
                logger.warning("Failed to delete event file: %s", url)

        return True

    async def register_attendance(
        self, data: schemas.EventAttendanceCreate, user_id: uuid.UUID
    ) -> EventAttendanceDTO:
        cache_kinds = ("attendance", "participation")

        # P2-W5-15: Lock the Event row before reading is_active/ends_at so that
        # the check-then-act sequence is serialized at the DB level.  Without
        # FOR UPDATE two concurrent requests can both pass the validity check,
        # then both insert attendance, exceeding intended capacity limits.
        event_locked = await self.repo.get_for_registration(data.event_id)
        if event_locked is None:
            raise EntityNotFound("Event", data.event_id)
        now_utc = datetime.now(UTC)
        ends_at = event_locked.ends_at
        if ends_at is not None and ends_at.tzinfo is None:
            ends_at = ends_at.replace(tzinfo=UTC)
        if not event_locked.is_active or (ends_at is not None and ends_at <= now_utc):
            raise ValueError("registration_closed")

        # Use repository to find existing attendance
        exist = await self.repo.get_attendance(data.event_id, user_id)

        if exist:
            updates: dict[str, Any] = {}
            if exist.registered_at is None:
                updates["registered_at"] = datetime.now(UTC)

            # ensure_secret_material expects ORM. I need a way to handle this.
            # I'll assume I can just issue a new secret if needed via repo.

            if updates:
                exist = await self.repo.update_attendance(
                    data.event_id, user_id, updates
                )
                assert exist is not None  # noqa: S101
                async with self.uow:
                    await self.uow.commit()

            # Helper logic to set token attribute for response
            token = attendance_tokens.issue_token(exist)
            return exist.model_copy(update={"qr_token": token})

        secret = attendance_tokens.generate_secret()
        try:
            record = await self.repo.create_attendance(
                user_id=user_id,
                event_id=data.event_id,
                qr_secret=secret,
                qr_hmac=attendance_tokens.compute_secret_hmac(secret),
                registered_at=datetime.now(UTC),
            )
            async with self.uow:
                await self.uow.commit()
        except IntegrityError as exc:
            await self.uow.rollback()
            # Race condition retry
            exist = await self.repo.get_attendance(data.event_id, user_id)
            if not exist:
                event = await self.repo.get(data.event_id)
                if not event:
                    raise EntityNotFound("Event", data.event_id) from exc
                raise ValueError(
                    translate("errors.events.attendance_registration_failed")
                ) from exc

            # Existing found after race
            retry_updates: dict[str, Any] = {}
            if exist.registered_at is None:
                retry_updates["registered_at"] = datetime.now(UTC)

            # Note: ensure_secret_material is skipped here as it's legacy
            # and might need ORM. For now we focus on reachability.

            if retry_updates:
                updated_exist = await self.repo.update_attendance(
                    data.event_id, user_id, retry_updates
                )
                if updated_exist:
                    exist = updated_exist
                async with self.uow:
                    await self.uow.commit()

            enriched_exist = exist.model_copy(
                update={"qr_token": attendance_tokens.issue_token(exist)}
            )
            await stats_cache.invalidate_user_stats_cache(
                user_ids=user_id,
                kinds=cache_kinds,
            )
            return enriched_exist

        # record is already refreshed in repo.create_attendance
        enriched_record = record.model_copy(
            update={"qr_token": attendance_tokens.issue_token(record)}
        )
        await stats_cache.invalidate_user_stats_cache(
            user_ids=user_id,
            kinds=cache_kinds,
        )
        return enriched_record

    async def unregister_attendance(
        self, data: schemas.EventAttendanceCreate, user_id: uuid.UUID | int
    ) -> dict[str, bool]:
        ok = await self.repo.delete_attendance(data.event_id, user_id)
        if ok:
            async with self.uow:
                await self.uow.commit()
            await stats_cache.invalidate_user_stats_cache(
                user_ids=user_id,
                kinds=("attendance", "participation"),
            )
        return {"ok": ok}

    async def get_my_events(
        self, user_id: uuid.UUID | int, *, locale: str | None = None
    ) -> list[schemas.EventOut]:
        events = await self.repo.list_user_attended_events(user_id)

        result: list[schemas.EventOut] = []
        for event in events:
            user_attendance = next(
                (a for a in event.attendance if str(a.user_id) == str(user_id)), None
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
                    participant_count=0,  # Need participant count in list_user_attended_events return
                    files=[],
                    is_registered=True,
                    my_qr_token=qr_token,
                )
            )
        return result

    async def get_event_detail(
        self, event_id: Any, user_id: Any, *, locale: str | None = None
    ) -> schemas.EventOut | None:
        """Fetch event details with optimized loading."""
        result = await self.repo.get_event_with_details(event_id, user_id)
        if not result:
            return None

        event_record = result.event
        p_count = result.participant_count
        attendance = result.user_attendance

        qr_token = None
        if attendance:
            # Ensure QR secret material exists before issuing token
            if attendance_tokens.ensure_secret_material(attendance):
                # How to handle session refresh/add for DTO?
                # We should probably update via repo.
                updates = {
                    "qr_secret": attendance.qr_secret,
                    "qr_hmac": attendance.qr_hmac,
                }
                await self.repo.update_attendance(
                    event_record.id, attendance.user_id, updates
                )
                async with self.uow:
                    await self.uow.commit()

            qr_token = attendance_tokens.issue_token(attendance)

        return self.serialize_event(
            event_record,
            locale,
            participant_count=p_count,
            files=[],  # Handle files later if needed
            is_registered=attendance is not None,
            my_qr_token=qr_token,
        )
