"""Chat creation service — DM creation with Redis lock and presence hydration.

TD-W9-01 (audit 2026-03-16): Extracted from ChatCommandService to satisfy SRP.
Creating a chat has fundamentally different dependencies (Redis distributed lock,
presence map, DM deduplication) from sending messages or maintaining chat state.
Separating it allows each service to be tested and evolved independently.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from typing import TYPE_CHECKING, Any, cast  # TD-23-04 (audit 2026-03-25 Wave 23)

if TYPE_CHECKING:
    from app.models.models import User
    from app.repositories.unit_of_work import UnitOfWork
    from app.schemas.chat import ChatParticipant, ChatResponse

from app.api.validation import ensure_exists, raise_validation_error
from app.api.ws.presence import (
    build_presence_map,
    invalidate_chat_participants_cache,
    invalidate_presence_audience_cache,
)
from app.core.exceptions import BusinessRuleViolation
from app.core.protocols import AsyncDatabaseSession
from app.deps.cache import BaseCache
from app.schemas.chat import ChatResponse, PresenceStatus


class ChatCreationService:
    """Handles chat creation with Redis-based DM deduplication.

    TD-W9-01: Single responsibility — create a DM chat between two users,
    ensuring exactly one chat per pair via a distributed Redis lock.

    TD-W10-01: cache is injected via Dishka (DIP) — no hidden module-level
    get_cache_client() call inside create_chat().  Tests can supply a mock
    BaseCache without patching any module globals.
    """

    def __init__(
        self, uow: UnitOfWork, session: AsyncDatabaseSession, cache: BaseCache
    ) -> None:
        self.uow = uow
        self.session = session
        self.repository = uow.chats
        self._cache = cache

    async def create_chat(
        self, user: User, participant_id: uuid.UUID | None, locale: str
    ) -> ChatResponse:
        """Create a new DM chat or return the existing one.

        Uses a Redis distributed lock keyed on the sorted pair of user IDs to
        prevent duplicate DM chats under concurrent creation requests.
        """
        if not participant_id:
            raise_validation_error("errors.chat.missing_participant", locale)

        if participant_id == user.id:
            raise_validation_error("errors.chat.self_chat", locale)

        participant = await self.repository.get_user(participant_id)
        ensure_exists(participant, "users", locale)
        assert participant is not None  # nosec B101  # noqa: S101

        # TD-W10-01: use the injected cache to obtain the underlying Redis client
        # so that locks can be acquired without a hidden module-level import.
        cache_obj: Any = self._cache
        if hasattr(cache_obj, "l2"):
            cache_obj = cache_obj.l2
        if not hasattr(cache_obj, "_get_client"):
            raise RuntimeError(
                "ChatCreationService requires a Redis-backed cache for distributed locks."
            )
        # LOW-W19: _get_client() is a private method on the internal Redis-backed
        # cache implementation.  There is no public API for obtaining the raw
        # redis.asyncio.Redis client from BaseCache at this time.  This access
        # is intentional and guarded by the hasattr check above.  Track
        # https://github.com/egorribun/university_ecosystem/issues/XXX to expose
        # a public `get_redis_client()` method on BaseCache so this can be
        # replaced with a stable API call.
        cache_client = await cache_obj._get_client()

        if not user.id or not participant_id:
            raise BusinessRuleViolation("errors.chat.invalid_participants")

        min_id, max_id = sorted([user.id, participant_id])
        lock_name = f"chat_init:{min_id}:{max_id}"

        # RZ-W10-02: Use explicit acquire/release with try/finally so the
        # distributed lock is guaranteed to be released even when
        # asyncio.TimeoutError fires mid-lock.  Using `async with lock` +
        # outer asyncio.timeout is unsafe because TimeoutError (a subclass of
        # CancelledError in Python 3.11+) can interrupt __aexit__ before
        # lock.release() executes, leaving a ghost key in Valkey until TTL.
        lock = cache_client.lock(lock_name, timeout=5, blocking_timeout=4)
        acquired = False
        try:
            async with asyncio.timeout(5.5):
                acquired = await lock.acquire()
                if not acquired:
                    raise_validation_error("errors.chat.lock_timeout", locale)

                existing_chat = await self.repository.find_existing_dm(
                    user.id, participant_id
                )
                if existing_chat:
                    return ChatResponse(
                        id=existing_chat.id,
                        participants=cast(
                            "list[ChatParticipant]", existing_chat.participants
                        ),
                        created_at=existing_chat.created_at,
                        updated_at=existing_chat.updated_at,
                    )

                new_chat = await self.repository.create_chat([user, participant])
                async with self.uow:
                    await self.uow.commit()
        except TimeoutError:
            raise_validation_error("errors.chat.lock_timeout", locale)
        finally:
            # Always release the lock — suppress errors since the chat operation
            # may have completed successfully even if release fails.
            if acquired:
                with contextlib.suppress(Exception):
                    await lock.release()

        participant_ids: list[uuid.UUID] = [p.id for p in new_chat.participants]
        await invalidate_chat_participants_cache(new_chat.id)
        await invalidate_presence_audience_cache(*participant_ids)

        presence_map = await build_presence_map(
            [p.id for p in new_chat.participants], db=self.session
        )

        return ChatResponse(
            id=new_chat.id,
            participants=cast("list[ChatParticipant]", new_chat.participants),
            created_at=new_chat.created_at,
            updated_at=new_chat.updated_at,
            presence={
                p.id: presence_map.get(p.id, PresenceStatus())
                for p in new_chat.participants
            },
        )
