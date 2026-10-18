import base64
import hashlib
import json
import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.cache_versioning import events_cache_version
from app.core.config import settings
from app.core.exceptions.domain import EntityNotFound
from app.core.localization import normalize_locale, translate
from app.core.logging import get_logger
from app.core.metrics import record_event_registration
from app.models import Event
from app.repositories.unit_of_work import UnitOfWork
from app.schemas import schemas
from app.schemas.dtos import EventAttendanceDTO, EventDTO, EventFileDTO
from app.services import attendance_tokens, stats_cache
from app.services.content_media import delete_unreferenced_owned_event_image
from app.services.vector_service import (
    SemanticSearchUnavailableError,
    VectorService,
)
from app.utils.pagination import (
    decode_datetime_cursor,
    decode_ranked_datetime_cursor,
    encode_datetime_cursor,
    encode_ranked_datetime_cursor,
)

logger = get_logger(__name__)

_LEGACY_MY_EVENTS_BATCH_SIZE = 100


class InvalidMyEventsCursor(ValueError):
    """The cursor is malformed or belongs to a different My-events query."""


class InvalidMyEventsQuery(ValueError):
    """A My-events date/time query value cannot be represented safely."""


def _my_events_cursor_binding(
    *,
    user_id: uuid.UUID | int,
    locale: str,
    limit: int,
    category: str | None,
    date_range: str | None,
    date_anchor: date | None,
    sort: str,
    upcoming_after: datetime | None,
) -> str:
    binding = {
        "user": str(user_id),
        "locale": locale,
        "limit": limit,
        "category": category,
        "date_range": date_range,
        "date_anchor": date_anchor.isoformat() if date_anchor else None,
        "sort": sort,
        "upcoming_after": upcoming_after.isoformat() if upcoming_after else None,
    }
    encoded = json.dumps(binding, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _encode_my_events_cursor(
    *, sort: str, binding: str, event: Event, participant_count: int
) -> str:
    def timestamp_text(value: datetime) -> str:
        aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return aware.astimezone(UTC).isoformat()

    key: dict[str, str | int]
    if sort in {"newest", "upcoming"}:
        key = {"value": timestamp_text(event.starts_at), "id": str(event.id)}
    else:
        key = {"value": participant_count, "id": str(event.id)}
    payload = {"v": 1, "sort": sort, "filter": binding, "key": key}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_my_events_cursor(
    cursor: str | None, *, sort: str, binding: str
) -> tuple[datetime | int, uuid.UUID] | None:
    if cursor is None:
        return None
    try:
        if not cursor or len(cursor) > 1024:
            raise ValueError
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        if base64.urlsafe_b64encode(raw).decode().rstrip("=") != cursor:
            raise ValueError
        payload = json.loads(raw)
        if (
            not isinstance(payload, dict)
            or set(payload) != {"v", "sort", "filter", "key"}
            or isinstance(payload["v"], bool)
            or not isinstance(payload["v"], int)
            or payload["v"] != 1
            or payload["sort"] != sort
            or payload["filter"] != binding
        ):
            raise ValueError
        key = payload["key"]
        if not isinstance(key, dict) or set(key) != {"value", "id"}:
            raise ValueError
        event_id_text = key["id"]
        event_id = uuid.UUID(event_id_text)
        if str(event_id) != event_id_text:
            raise ValueError
        value = key["value"]
        if sort == "popular":
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
                or value > (2**63 - 1)
            ):
                raise ValueError
            return value, event_id
        if not isinstance(value, str):
            raise ValueError
        timestamp = datetime.fromisoformat(value)
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError
        return timestamp.astimezone(UTC), event_id
    except (
        ValueError,
        TypeError,
        AttributeError,
        KeyError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        OverflowError,
    ) as exc:
        raise InvalidMyEventsCursor("Invalid My-events cursor") from exc


def _my_events_date_bounds(
    date_range: str | None, date_anchor: date | None
) -> tuple[datetime | None, datetime | None]:
    if date_range is None:
        if date_anchor is not None:
            raise ValueError("A date anchor requires a date range")
        return None, None
    if date_anchor is None:
        raise ValueError("A date range requires its campus-local anchor date")
    if date_range not in {"today", "week", "month"}:
        raise ValueError("Unsupported date range")

    try:
        if date_range == "today":
            start_date = date_anchor
            end_date = start_date + timedelta(days=1)
        elif date_range == "week":
            start_date = date_anchor - timedelta(days=date_anchor.weekday())
            end_date = start_date + timedelta(days=7)
        else:
            start_date = date(date_anchor.year, date_anchor.month, 1)
            end_date = (
                date(date_anchor.year + 1, 1, 1)
                if date_anchor.month == 12
                else date(date_anchor.year, date_anchor.month + 1, 1)
            )
    except (OverflowError, ValueError) as exc:
        raise InvalidMyEventsQuery("Date range is outside supported bounds") from exc

    try:
        campus_zone = ZoneInfo(settings.campus_timezone)
    except (ZoneInfoNotFoundError, TypeError, ValueError) as exc:
        raise RuntimeError("Configured campus timezone is unavailable") from exc
    try:
        start = datetime.combine(start_date, time.min, tzinfo=campus_zone).astimezone(
            UTC
        )
        end = datetime.combine(end_date, time.min, tzinfo=campus_zone).astimezone(UTC)
    except OverflowError as exc:
        raise InvalidMyEventsQuery("Date range is outside supported bounds") from exc
    return start, end


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
            try:
                query_embedding = await self.vector_service.get_embedding(search)
            except SemanticSearchUnavailableError:
                query_embedding = None

        decoded_cursor = decode_ranked_datetime_cursor(
            cursor
        ) or decode_datetime_cursor(cursor)

        # Keep list and total filters on the same time snapshot.
        filter_time = datetime.now(UTC)

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
            now=filter_time,
        )

        has_more = len(results) > limit
        items_to_process = results[:limit]

        # Calculate total only on first page
        total = None
        if not cursor:
            total = await self.repo.count_search_events(
                search_query=search,
                event_type=type,
                location=location,
                is_active=is_active,
                query_embedding=query_embedding,
                now=filter_time,
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
                    logger.debug(
                        "event.attendance_proof_generation_failed",
                        error_type=exc.__class__.__name__,
                    )

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
            if last_result.rank is not None:
                next_cursor = encode_ranked_datetime_cursor(
                    last_result.event.starts_at,
                    str(last_result.event.id),
                    last_result.rank,
                )
            else:
                next_cursor = encode_datetime_cursor(
                    last_result.event.starts_at, str(last_result.event.id)
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
        self,
        data: schemas.EventCreate,
        user_id: uuid.UUID,
        *,
        locale: str | None = None,
    ) -> EventDTO:
        if data.starts_at >= data.ends_at:
            raise ValueError(translate("validation.events.end_after_start"))

        obj_data = data.model_dump()
        obj_data["created_by"] = user_id
        if locale is None:
            event = await self.repo.create(obj_data)
        else:
            event = await self.repo.create(obj_data, locale=locale)
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

        from app.services import search_indexer

        await search_indexer.remove_document(search_indexer.EVENTS_INDEX, event_id)

        from app.utils.files import delete_static_file

        if image_url:
            try:
                async with self.uow:
                    await delete_unreferenced_owned_event_image(
                        str(image_url),
                        event_id=event_id,
                        db_session=self.uow.session,
                    )
            except (OSError, SQLAlchemyError):
                # RZ-20-04: Retain the object if post-commit cleanup cannot proceed.
                logger.warning("Failed to safely clean event image: %s", image_url)

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

            if updates:
                exist = await self.repo.update_attendance(
                    data.event_id, user_id, updates
                )
                assert exist is not None  # noqa: S101
                async with self.uow:
                    await self.uow.commit()
                await events_cache_version.increment()

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
            await events_cache_version.increment()
            record_event_registration()
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

            if retry_updates:
                updated_exist = await self.repo.update_attendance(
                    data.event_id, user_id, retry_updates
                )
                if updated_exist:
                    exist = updated_exist
                async with self.uow:
                    await self.uow.commit()
                await events_cache_version.increment()

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
            await events_cache_version.increment()
            await stats_cache.invalidate_user_stats_cache(
                user_ids=user_id,
                kinds=("attendance", "participation"),
            )
        return {"ok": ok}

    async def get_my_events(
        self, user_id: uuid.UUID | int, *, locale: str | None = None
    ) -> list[schemas.EventOut]:
        """Return the legacy array response while keeping each database read bounded."""
        normalized_locale = normalize_locale(locale)
        result: list[schemas.EventOut] = []
        cursor_key: tuple[datetime | int, uuid.UUID] | None = None

        while True:
            rows = await self.repo.list_user_attended_events(
                user_id,
                limit=_LEGACY_MY_EVENTS_BATCH_SIZE,
                locale=normalized_locale,
                sort="newest",
                cursor_key=cursor_key,
                include_participant_count=False,
            )
            for event, user_attendance, _participant_count in rows:
                qr_token = attendance_tokens.issue_token(user_attendance)
                result.append(
                    self.serialize_event(
                        event,
                        normalized_locale,
                        participant_count=0,
                        files=[],
                        is_registered=True,
                        my_qr_token=qr_token,
                    )
                )

            if len(rows) < _LEGACY_MY_EVENTS_BATCH_SIZE:
                return result

            last_event = rows[-1][0]
            next_cursor_key = (last_event.starts_at, last_event.id)
            if cursor_key is not None and next_cursor_key <= cursor_key:
                raise RuntimeError("My-events keyset batch did not advance")
            cursor_key = next_cursor_key

    async def get_my_events_page(
        self,
        user_id: uuid.UUID | int,
        *,
        locale: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
        category: str | None = None,
        date_range: str | None = None,
        date_anchor: date | None = None,
        sort: str = "newest",
        upcoming_after: datetime | None = None,
    ) -> schemas.PaginatedEvents:
        """Return one bounded filtered page of the authenticated user's registrations."""
        normalized_locale = normalize_locale(locale)
        if sort not in {"newest", "popular", "upcoming"}:
            raise ValueError("Unsupported event sort")
        if upcoming_after is not None:
            if upcoming_after.tzinfo is None:
                raise InvalidMyEventsQuery("upcoming_after must be timezone-aware")
            try:
                if upcoming_after.utcoffset() is None:
                    raise InvalidMyEventsQuery("upcoming_after must be timezone-aware")
                upcoming_after = upcoming_after.astimezone(UTC)
            except (OverflowError, TypeError, ValueError) as exc:
                raise InvalidMyEventsQuery(
                    "upcoming_after is outside supported bounds"
                ) from exc
        if sort == "upcoming" and upcoming_after is None:
            raise ValueError("upcoming sort requires a time cutoff")
        if sort != "upcoming" and upcoming_after is not None:
            raise ValueError("upcoming_after only applies to upcoming sort")
        starts_at_from, starts_at_before = _my_events_date_bounds(
            date_range, date_anchor
        )
        binding = _my_events_cursor_binding(
            user_id=user_id,
            locale=normalized_locale,
            limit=limit,
            category=category,
            date_range=date_range,
            date_anchor=date_anchor,
            sort=sort,
            upcoming_after=upcoming_after,
        )
        cursor_key = _decode_my_events_cursor(cursor, sort=sort, binding=binding)
        rows = await self.repo.list_user_attended_events(
            user_id,
            limit=limit + 1,
            locale=normalized_locale,
            category=category,
            starts_at_from=starts_at_from,
            starts_at_before=starts_at_before,
            upcoming_after=upcoming_after,
            sort=sort,
            cursor_key=cursor_key,
        )
        has_more = len(rows) > limit
        page_rows = rows[:limit]

        result: list[schemas.EventOut] = []
        for event, user_attendance, participant_count in page_rows:
            qr_token = attendance_tokens.issue_token(user_attendance)
            result.append(
                self.serialize_event(
                    event,
                    normalized_locale,
                    participant_count=participant_count,
                    files=[],
                    is_registered=True,
                    my_qr_token=qr_token,
                )
            )

        next_cursor = None
        if has_more and page_rows:
            last_event, _, last_participant_count = page_rows[-1]
            next_cursor = _encode_my_events_cursor(
                sort=sort,
                binding=binding,
                event=last_event,
                participant_count=last_participant_count,
            )
        return schemas.PaginatedEvents(
            items=result,
            total=None,
            limit=limit,
            cursor=cursor,
            next_cursor=next_cursor,
            has_more=has_more,
        )

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
            updates = attendance_tokens.secret_material_updates(attendance)
            if updates:
                repaired = await self.repo.update_attendance(
                    event_record.id, attendance.user_id, updates
                )
                if repaired is None:
                    raise EntityNotFound("EventAttendance", attendance.id)
                async with self.uow:
                    await self.uow.commit()
                await events_cache_version.increment()
                attendance = repaired

            qr_token = attendance_tokens.issue_token(attendance)

        return self.serialize_event(
            event_record,
            locale,
            participant_count=p_count,
            files=[],  # Handle files later if needed
            is_registered=attendance is not None,
            my_qr_token=qr_token,
        )
