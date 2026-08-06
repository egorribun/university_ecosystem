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
    from app.models import User
    from app.repositories.unit_of_work import UnitOfWork
    from app.schemas.chat import ChatParticipant, ChatResponse

from app.api.validation import ensure_exists, raise_validation_error
from app.api.ws.presence import (
    build_presence_map,
    invalidate_chat_participants_cache,
    invalidate_presence_audience_cache,
)
from app.core.config import settings
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
        assert participant is not None  # noqa: S101

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
        # is intentional and guarded by the hasattr check above.
        # TD-33-01: expose public get_redis_client() on BaseCache so this can
        # be replaced with a stable API call.
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
                        chat_type=existing_chat.chat_type,
                        name=existing_chat.name,
                        created_by=existing_chat.created_by,
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
            # Wave 209 G1 — DMs carry chat_type="dm" (the ChatDTO default) + null
            # name/created_by; passed explicitly per the W203-SW8 5-site discipline.
            chat_type=new_chat.chat_type,
            name=new_chat.name,
            created_by=new_chat.created_by,
            participants=cast("list[ChatParticipant]", new_chat.participants),
            created_at=new_chat.created_at,
            updated_at=new_chat.updated_at,
            presence={
                p.id: presence_map.get(p.id, PresenceStatus())
                for p in new_chat.participants
            },
        )

    async def create_group(
        self,
        user: User,
        name: str,
        participant_ids: list[uuid.UUID],
        locale: str,
    ) -> ChatResponse:
        """Create a named group chat owned by ``user`` (Wave 209 G1).

        No Redis lock — a group has no DM-style find-or-create uniqueness
        invariant. The creator is always a member; ``participant_ids`` are the
        *other* members, de-duplicated with the creator dropped. Enforces the
        settings.chat_group_min_members..max_members total-size bound (creator +
        distinct members), then mirrors create_chat's post-commit
        cache-invalidation + presence-hydration.
        """
        clean_name = name.strip()
        if not clean_name:
            raise_validation_error("errors.chat.group_name_required", locale)

        seen: set[uuid.UUID] = set()
        member_ids: list[uuid.UUID] = []
        for pid in participant_ids:
            if pid == user.id or pid in seen:
                continue
            seen.add(pid)
            member_ids.append(pid)

        total = len(member_ids) + 1  # + the creator
        if total < settings.chat_group_min_members:
            raise_validation_error("errors.chat.group_too_few_members", locale)
        if total > settings.chat_group_max_members:
            raise_validation_error("errors.chat.group_too_many_members", locale)

        get_users_fn = getattr(self.repository, "get_users_by_ids", None)
        fetched_members = None
        if get_users_fn is not None:
            try:
                res = get_users_fn(member_ids)
                if asyncio.iscoroutine(res) or hasattr(res, "__await__"):
                    fetched_members = await res
                elif isinstance(res, (list, tuple, set)):
                    fetched_members = res
            except Exception:  # RZ-22-01-JUSTIFIED: fallback to per-user query if mock or custom repo doesn't support batching
                fetched_members = None

        if isinstance(fetched_members, (list, tuple, set)):
            member_map = {m.id: m for m in fetched_members if hasattr(m, "id")}
        else:
            member_map = {}

        members: list[User] = []
        for pid in member_ids:
            member = member_map.get(pid)
            if member is None:
                member = await self.repository.get_user(pid)
            ensure_exists(member, "users", locale)
            assert member is not None  # noqa: S101
            members.append(member)

        new_chat = await self.repository.create_group(user, clean_name, members)
        async with self.uow:
            await self.uow.commit()

        participant_ids_all: list[uuid.UUID] = [p.id for p in new_chat.participants]
        await invalidate_chat_participants_cache(new_chat.id)
        await invalidate_presence_audience_cache(*participant_ids_all)

        presence_map = await build_presence_map(participant_ids_all, db=self.session)

        return ChatResponse(
            id=new_chat.id,
            chat_type=new_chat.chat_type,
            name=new_chat.name,
            created_by=new_chat.created_by,
            participants=cast("list[ChatParticipant]", new_chat.participants),
            created_at=new_chat.created_at,
            updated_at=new_chat.updated_at,
            presence={
                p.id: presence_map.get(p.id, PresenceStatus())
                for p in new_chat.participants
            },
        )
