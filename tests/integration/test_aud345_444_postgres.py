"""PostgreSQL-only registration uniqueness and invitation contention proofs."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, text

import app.core.database as database
import app.models as models
from app.repositories.user_repository import UserRepository

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


def _require_postgres() -> None:
    if database.engine.dialect.name != "postgresql":
        pytest.skip("registration contention requires PostgreSQL")


def _payload(email: str, **overrides: str) -> dict[str, str]:
    payload = {
        "email": email,
        "password": f"Aa1!{uuid4().hex}",
        "full_name": "PostgreSQL Registration",
    }
    payload.update(overrides)
    return payload


async def test_email_unique_violation_uses_the_postgres_driver_contract(
    async_client, db_session, monkeypatch
) -> None:
    _require_postgres()
    email = "pg-registration-race@example.com"
    payload = _payload(email)
    first = await async_client.post("/auth/register", json=payload)
    assert first.status_code == 200

    async def stale_check(_repo, _email, exclude_user_id=None):
        return False

    monkeypatch.setattr(UserRepository, "check_email_exists", stale_check)
    second = await async_client.post("/auth/register", json=payload)
    assert second.status_code == first.status_code
    assert second.json() == first.json() == {"status": "ok"}
    count = await db_session.scalar(
        select(func.count()).select_from(models.User).where(models.User.email == email)
    )
    assert count == 1


async def test_contended_invite_waits_then_rejects_without_second_account(
    async_client, db_session, monkeypatch
) -> None:
    _require_postgres()
    invite = models.InviteCode(code="AUD444-PG", role="teacher")
    db_session.add(invite)
    await db_session.commit()
    invite_id = invite.id

    loop = asyncio.get_running_loop()
    first_locked = asyncio.Event()
    release_first = asyncio.Event()
    holder_pid = loop.create_future()
    waiter_pid = loop.create_future()
    original_create = UserRepository.create_with_invite
    original_lookup = UserRepository.get_invite_code

    async def observe_lookup(repo, code, *, with_for_update=True):
        if first_locked.is_set() and not waiter_pid.done():
            result = await repo.db.execute(text("SELECT pg_backend_pid()"))
            waiter_pid.set_result(result.scalar_one())
        return await original_lookup(repo, code, with_for_update=with_for_update)

    async def hold_first(repo, user_data, invite_code):
        if user_data["email"] == "pg-invite-first@example.com":
            result = await repo.db.execute(text("SELECT pg_backend_pid()"))
            holder_pid.set_result(result.scalar_one())
            first_locked.set()
            await release_first.wait()
        return await original_create(repo, user_data, invite_code)

    monkeypatch.setattr(UserRepository, "get_invite_code", observe_lookup)
    monkeypatch.setattr(UserRepository, "create_with_invite", hold_first)
    options = {"role": "teacher", "invite_code": "AUD444-PG"}
    first_task = asyncio.create_task(
        async_client.post(
            "/auth/register", json=_payload("pg-invite-first@example.com", **options)
        )
    )
    second_task = None
    try:
        await asyncio.wait_for(first_locked.wait(), timeout=10)
        second_task = asyncio.create_task(
            async_client.post(
                "/auth/register",
                json=_payload("pg-invite-second@example.com", **options),
            )
        )
        competing_pid = await asyncio.wait_for(waiter_pid, timeout=10)
        owning_pid = await asyncio.wait_for(holder_pid, timeout=10)

        async def wait_until_blocked() -> None:
            async with database.async_session() as monitor:
                while True:
                    blocked_by = await monitor.scalar(
                        text("SELECT pg_blocking_pids(:pid)"), {"pid": competing_pid}
                    )
                    if owning_pid in blocked_by:
                        return
                    assert not second_task.done(), "competing registration did not wait"
                    await asyncio.sleep(0.02)

        await asyncio.wait_for(wait_until_blocked(), timeout=10)
    except BaseException:
        release_first.set()
        first_task.cancel()
        if second_task is not None:
            second_task.cancel()
        await asyncio.gather(
            *(task for task in (first_task, second_task) if task is not None),
            return_exceptions=True,
        )
        raise

    release_first.set()
    assert second_task is not None
    first, second = await asyncio.wait_for(
        asyncio.gather(first_task, second_task), timeout=10
    )
    assert first.status_code == 200
    assert first.json() == {"status": "ok"}
    assert second.status_code == 400
    db_session.expire_all()
    saved_invite = await db_session.get(models.InviteCode, invite_id)
    winner = (
        await db_session.execute(
            select(models.User).where(
                models.User.email == "pg-invite-first@example.com"
            )
        )
    ).scalar_one()
    assert saved_invite is not None
    assert saved_invite.is_used and not saved_invite.is_active
    assert saved_invite.used_by_user_id == winner.id
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(models.User)
            .where(models.User.email == "pg-invite-second@example.com")
        )
        == 0
    )


async def test_group_delete_waits_for_registration_transaction(
    async_client, db_session, monkeypatch
) -> None:
    _require_postgres()
    group = models.Group(name="AUD345 Lock Test")
    db_session.add(group)
    await db_session.commit()
    group_id = group.id
    email = "pg-group-lock@example.com"

    loop = asyncio.get_running_loop()
    first_locked = asyncio.Event()
    release_first = asyncio.Event()
    holder_pid = loop.create_future()
    deleter_pid = loop.create_future()
    original_create = UserRepository.create_with_invite

    async def hold_registration(repo, user_data, invite_code):
        if user_data["email"] == email:
            result = await repo.db.execute(text("SELECT pg_backend_pid()"))
            holder_pid.set_result(result.scalar_one())
            first_locked.set()
            await release_first.wait()
        return await original_create(repo, user_data, invite_code)

    async def delete_group() -> int:
        async with database.async_session() as session:
            pid = await session.scalar(text("SELECT pg_backend_pid()"))
            deleter_pid.set_result(pid)
            result = await session.execute(
                delete(models.Group).where(models.Group.id == group_id)
            )
            await session.commit()
            return result.rowcount

    monkeypatch.setattr(UserRepository, "create_with_invite", hold_registration)
    registration = asyncio.create_task(
        async_client.post(
            "/auth/register", json=_payload(email, group_id=str(group_id))
        )
    )
    deletion = None
    try:
        await asyncio.wait_for(first_locked.wait(), timeout=10)
        deletion = asyncio.create_task(delete_group())
        competing_pid = await asyncio.wait_for(deleter_pid, timeout=10)
        owning_pid = await asyncio.wait_for(holder_pid, timeout=10)

        async def wait_until_blocked() -> None:
            async with database.async_session() as monitor:
                while True:
                    blocked_by = await monitor.scalar(
                        text("SELECT pg_blocking_pids(:pid)"), {"pid": competing_pid}
                    )
                    if owning_pid in blocked_by:
                        return
                    assert not deletion.done(), "group deletion did not wait"
                    await asyncio.sleep(0.02)

        await asyncio.wait_for(wait_until_blocked(), timeout=10)
    except BaseException:
        release_first.set()
        registration.cancel()
        if deletion is not None:
            deletion.cancel()
        await asyncio.gather(
            *(task for task in (registration, deletion) if task is not None),
            return_exceptions=True,
        )
        raise

    release_first.set()
    assert deletion is not None
    response, deleted = await asyncio.wait_for(
        asyncio.gather(registration, deletion), timeout=10
    )
    assert response.status_code == 200
    assert deleted == 1
    db_session.expire_all()
    account = await db_session.scalar(
        select(models.User).where(models.User.email == email)
    )
    assert account is not None and account.group_id is None
