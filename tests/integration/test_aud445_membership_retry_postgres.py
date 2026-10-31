"""AUD-445 membership locks and transactional repair with real PostgreSQL."""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.events import ChatParticipantCacheInvalidation, ChatParticipantRemoved
from app.models import Message
from app.models.domain_events import StoredEvent
from app.models.users import User
from app.repositories.chat_repository import ChatRepository
from app.repositories.unit_of_work import uow_from_session
from app.services.chat.attachment_service import ChatAttachmentService
from app.services.chat.command_service import ChatMaintenanceService

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="Set RUN_INTEGRATION_TESTS=1 for owned PostgreSQL regression tests",
    ),
]


def _require_postgres(session: AsyncSession) -> None:
    if session.get_bind().dialect.name != "postgresql":
        pytest.fail("AUD-445 lock semantics require PostgreSQL")


def _patch_fast_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.chat.command_service.invalidate_participant_caches_strict",
        AsyncMock(return_value="shared"),
    )
    monkeypatch.setattr(
        "app.services.chat.command_service.invalidate_chat_participants_cache",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.services.chat.command_service.invalidate_presence_audience_cache",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "app.services.ws_hub_client.invalidate_ws_hub_cache", AsyncMock()
    )


async def _seed_group(
    db_session: AsyncSession, user_factory: Callable[..., Awaitable[User]]
) -> tuple[uuid.UUID, User, User]:
    _require_postgres(db_session)
    owner, member = await user_factory(), await user_factory()
    chat = await ChatRepository(db_session).create_group(owner, "aud445-pg", [member])
    await db_session.commit()
    return chat.id, owner, member


async def _blocked_by(
    factory: async_sessionmaker[AsyncSession], application_name: str, blocker_pid: int
) -> bool:
    deadline = time.monotonic() + 5
    async with factory() as observer:
        while time.monotonic() < deadline:
            blockers = await observer.scalar(
                text(
                    "SELECT pg_blocking_pids(pid) FROM pg_stat_activity WHERE application_name = :name"
                ),
                {"name": application_name},
            )
            if blockers and blocker_pid in blockers:
                return True
            await asyncio.sleep(0.01)
    return False


async def _events(
    factory: async_sessionmaker[AsyncSession], chat_id: uuid.UUID
) -> list[StoredEvent]:
    async with factory() as observer:
        return list(
            (
                await observer.scalars(
                    select(StoredEvent).where(
                        StoredEvent.event_type.in_(
                            [
                                ChatParticipantRemoved.EVENT_TYPE,
                                ChatParticipantCacheInvalidation.EVENT_TYPE,
                            ]
                        ),
                        StoredEvent.payload["chat_id"].as_string() == str(chat_id),
                    )
                )
            ).all()
        )


@pytest.mark.parametrize("racing_operation", ["add", "remove"])
async def test_concurrent_membership_change_waits_and_preserves_events(
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    monkeypatch: pytest.MonkeyPatch,
    racing_operation: str,
) -> None:
    chat_id, owner, member = await _seed_group(db_session, user_factory)
    member_id = member.id
    _patch_fast_effects(monkeypatch)
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    deletion_ready, release_commit = asyncio.Event(), asyncio.Event()
    removal_pid: asyncio.Future[int] = asyncio.get_running_loop().create_future()
    add_pid: asyncio.Future[int] = asyncio.get_running_loop().create_future()
    add_name = f"aud445-add-{uuid.uuid4().hex[:20]}"

    async def remove() -> None:
        async with factory() as session:
            await session.execute(
                text("SELECT set_config('lock_timeout', '10s', true)")
            )
            removal_pid.set_result(
                await session.scalar(text("SELECT pg_backend_pid()"))
            )
            uow = uow_from_session(session)
            commit = uow.commit

            async def pause_before_commit() -> None:
                deletion_ready.set()
                await release_commit.wait()
                await commit()

            uow.commit = pause_before_commit
            await ChatMaintenanceService(
                uow, ChatAttachmentService()
            ).remove_participant(chat_id, owner, member_id, "en")

    async def add() -> None:
        async with factory() as session:
            await session.execute(
                text("SELECT set_config('application_name', :name, false)"),
                {"name": add_name},
            )
            await session.execute(
                text("SELECT set_config('lock_timeout', '10s', true)")
            )
            add_pid.set_result(await session.scalar(text("SELECT pg_backend_pid()")))
            service = ChatMaintenanceService(
                uow_from_session(session), ChatAttachmentService()
            )
            await getattr(service, f"{racing_operation}_participant")(
                chat_id, owner, member_id, "en"
            )

    removal = asyncio.create_task(remove())
    addition: asyncio.Task[None] | None = None
    blocked = False
    outcomes: list[object] = []
    try:
        await asyncio.wait_for(deletion_ready.wait(), timeout=5)
        addition = asyncio.create_task(add())
        await asyncio.wait_for(add_pid, timeout=5)
        blocked = await _blocked_by(factory, add_name, await removal_pid)
    finally:
        release_commit.set()
        tasks = [removal] + ([addition] if addition is not None else [])
        outcomes = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True), timeout=15
        )
    assert all(not isinstance(outcome, BaseException) for outcome in outcomes), outcomes
    assert blocked
    async with factory() as session:
        assert await ChatRepository(session).check_participant(chat_id, member_id) is (
            racing_operation == "add"
        )
    rows = await _events(factory, chat_id)
    assert [row.event_type for row in rows].count(
        ChatParticipantRemoved.EVENT_TYPE
    ) == 1
    cache_rows = [
        row
        for row in rows
        if row.event_type == ChatParticipantCacheInvalidation.EVENT_TYPE
    ]
    assert len(cache_rows) == 1
    assert set(cache_rows[0].payload["participant_ids"]) == {
        str(owner.id),
        str(member_id),
    }


async def test_failed_commit_rolls_back_membership_and_cache_jobs(
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_id, owner, member = await _seed_group(db_session, user_factory)
    member_id = member.id
    _patch_fast_effects(monkeypatch)
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    async with factory() as session:
        uow = uow_from_session(session)
        uow.commit = AsyncMock(side_effect=RuntimeError("owned precommit fault"))
        with pytest.raises(RuntimeError, match="owned precommit fault"):
            await ChatMaintenanceService(
                uow, ChatAttachmentService()
            ).remove_participant(chat_id, owner, member_id, "en")
    async with factory() as observer:
        assert await ChatRepository(observer).check_participant(chat_id, member_id)
    assert await _events(factory, chat_id) == []


async def test_lost_commit_ack_owner_retry_does_not_duplicate_jobs(
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_id, owner, member = await _seed_group(db_session, user_factory)
    member_id = member.id
    _patch_fast_effects(monkeypatch)
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    async with factory() as session:
        uow = uow_from_session(session)
        real_commit = uow.commit

        async def commit_then_lose_ack() -> None:
            await real_commit()
            raise ConnectionError("owned lost acknowledgement")

        uow.commit = commit_then_lose_ack
        with pytest.raises(ConnectionError, match="owned lost acknowledgement"):
            await ChatMaintenanceService(
                uow, ChatAttachmentService()
            ).remove_participant(chat_id, owner, member_id, "en")
    before = await _events(factory, chat_id)
    assert len(before) == 2
    async with factory() as session:
        await ChatMaintenanceService(
            uow_from_session(session), ChatAttachmentService()
        ).remove_participant(chat_id, owner, member_id, "en")
    assert {row.id for row in await _events(factory, chat_id)} == {
        row.id for row in before
    }


async def test_removal_waits_for_sender_timestamp_without_deadlock(
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[User]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chat_id, owner, member = await _seed_group(db_session, user_factory)
    owner_id, member_id = owner.id, member.id
    _patch_fast_effects(monkeypatch)
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    inserted, allow_update = asyncio.Event(), asyncio.Event()
    sender_pid: asyncio.Future[int] = asyncio.get_running_loop().create_future()
    removal_name = f"aud445-remove-{uuid.uuid4().hex[:20]}"

    async def send() -> None:
        async with factory() as session:
            await session.execute(
                text("SELECT set_config('lock_timeout', '10s', true)")
            )
            repository = ChatRepository(session)
            await repository.set_message_rls_user(owner_id)
            await repository.create_message(
                Message(
                    chat_id=chat_id, sender_id=owner_id, content="aud445 lock probe"
                )
            )
            sender_pid.set_result(await session.scalar(text("SELECT pg_backend_pid()")))
            inserted.set()
            await allow_update.wait()
            await repository.update_timestamp_by_id(chat_id, datetime.now(UTC))
            await session.commit()

    async def remove() -> None:
        async with factory() as session:
            await session.execute(
                text("SELECT set_config('application_name', :name, false)"),
                {"name": removal_name},
            )
            await session.execute(
                text("SELECT set_config('lock_timeout', '10s', true)")
            )
            await ChatMaintenanceService(
                uow_from_session(session), ChatAttachmentService()
            ).remove_participant(chat_id, owner, member_id, "en")

    sender = asyncio.create_task(send())
    removal: asyncio.Task[None] | None = None
    blocked = False
    outcomes: list[object] = []
    try:
        await asyncio.wait_for(inserted.wait(), timeout=5)
        removal = asyncio.create_task(remove())
        blocked = await _blocked_by(factory, removal_name, await sender_pid)
    finally:
        allow_update.set()
        tasks = [sender] + ([removal] if removal is not None else [])
        outcomes = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True), timeout=15
        )
    assert all(not isinstance(outcome, BaseException) for outcome in outcomes), outcomes
    assert blocked
    async with factory() as session:
        assert not await ChatRepository(session).check_participant(chat_id, member_id)
