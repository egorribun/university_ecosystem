"""AUD-340: concurrent domain-event writers keep one PostgreSQL HMAC chain.

These tests use the existing disposable integration database and caller-owned
transactions. They do not repair historical rows or prove mixed-version safety.
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import time
import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.domain_events import StoredEvent
from app.services.audit_service import SecureAuditService

pytestmark = [
    pytest.mark.integration,
    pytest.mark.timeout(45),
    # AUD-340 @egorribun: the required PostgreSQL integration lane runs all cases.
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="Set RUN_INTEGRATION_TESTS=1 for owned PostgreSQL regression tests",
    ),
]


def _sessions(session: AsyncSession) -> async_sessionmaker[AsyncSession]:
    if session.get_bind().dialect.name != "postgresql":
        pytest.fail("AUD-340 writer serialization requires PostgreSQL")
    return async_sessionmaker(session.bind, expire_on_commit=False)


async def _transaction_pid(session: AsyncSession) -> int:
    await session.execute(text("SET TRANSACTION ISOLATION LEVEL READ COMMITTED"))
    await session.execute(text("SET LOCAL lock_timeout = '10s'"))
    await session.execute(text("SET LOCAL statement_timeout = '10s'"))
    return int(await session.scalar(text("SELECT pg_backend_pid()")))


async def _record(
    service: SecureAuditService,
    session: AsyncSession,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    writer: str,
) -> None:
    await service.record_domain_event(
        session,
        event_type="aud340.changed",
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload={"writer": writer},
    )


async def _commit_events(
    factory: async_sessionmaker[AsyncSession],
    service: SecureAuditService,
    aggregates: tuple[tuple[str, uuid.UUID], ...],
    writer: str,
    ready: asyncio.Future[int],
) -> None:
    async with factory() as session:
        ready.set_result(await _transaction_pid(session))
        for aggregate_type, aggregate_id in aggregates:
            await _record(service, session, aggregate_type, aggregate_id, writer)
        await session.commit()


async def _writer_observation(
    factory: async_sessionmaker[AsyncSession],
    writer: asyncio.Task[None],
    writer_pid: int,
    holder_pid: int,
) -> str:
    """Accept old-code completion or server-observed waiting, never force a lock."""
    deadline = time.monotonic() + 5
    async with factory() as observer:
        while time.monotonic() < deadline:
            if writer.done():
                return "completed"
            blockers = await observer.scalar(
                text("SELECT pg_blocking_pids(:pid)"), {"pid": writer_pid}
            )
            if blockers and holder_pid in blockers:
                return "blocked"
            # Observation polling is bounded by the five-second deadline above.
            await asyncio.sleep(0.01)
    return "pending"


async def _finish_writer(writer: asyncio.Task[None]) -> None:
    outcomes = await asyncio.wait_for(
        asyncio.gather(writer, return_exceptions=True), timeout=15
    )
    succeeded = all(outcome is None for outcome in outcomes)
    assert succeeded, "the domain-event writer must complete successfully"


async def _assert_not_visible(
    factory: async_sessionmaker[AsyncSession],
    aggregate_type: str,
    aggregate_id: uuid.UUID,
) -> None:
    async with factory() as observer:
        visible = await observer.scalar(
            select(StoredEvent.id).where(
                StoredEvent.aggregate_type == aggregate_type,
                StoredEvent.aggregate_id == str(aggregate_id),
            )
        )
    assert visible is None, "record_domain_event must not commit for its caller"


async def _assert_chain(
    factory: async_sessionmaker[AsyncSession],
    service: SecureAuditService,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    expected_writers: tuple[str, ...],
) -> None:
    async with factory() as observer:
        rows = list(
            (
                await observer.scalars(
                    select(StoredEvent)
                    .where(
                        StoredEvent.aggregate_type == aggregate_type,
                        StoredEvent.aggregate_id == str(aggregate_id),
                    )
                    .order_by(
                        StoredEvent.sequence_number,
                        StoredEvent.created_at,
                        StoredEvent.id,
                    )
                )
            ).all()
        )
        assert len(rows) == len(expected_writers)
        assert [row.payload for row in rows] == [
            {"writer": writer} for writer in expected_writers
        ]
        assert [row.sequence_number for row in rows] == list(
            range(1, len(expected_writers) + 1)
        )
        assert [row.prev_hash for row in rows] == [
            "0" * 64,
            *(row.hash for row in rows[:-1]),
        ]
        result = await service.verify_chain_integrity(
            observer, aggregate_type, aggregate_id
        )
        chain_is_valid = result == (True, None, None)
        assert chain_is_valid, "committed events must form a valid HMAC chain"


async def test_distinct_aggregate_keys_progress_while_another_writer_is_uncommitted(
    db_session: AsyncSession,
) -> None:
    factory = _sessions(db_session)
    service = SecureAuditService(signing_key=secrets.token_hex(32).encode("ascii"))
    aggregate_id, other_id = uuid.uuid4(), uuid.uuid4()
    ready: asyncio.Future[int] = asyncio.get_running_loop().create_future()
    async with factory() as first:
        holder_pid = await _transaction_pid(first)
        await _record(service, first, "aud340", aggregate_id, "held")
        assert first.in_transaction()
        await _assert_not_visible(factory, "aud340", aggregate_id)
        writer = asyncio.create_task(
            _commit_events(
                factory,
                service,
                (("aud340", other_id), ("aud340-other", aggregate_id)),
                "independent",
                ready,
            )
        )
        try:
            writer_pid = await asyncio.wait_for(ready, timeout=5)
            observation = await _writer_observation(
                factory, writer, writer_pid, holder_pid
            )
        finally:
            try:
                await first.commit()
            finally:
                await _finish_writer(writer)

    assert observation == "completed", "unrelated aggregate keys must not serialize"
    await _assert_chain(factory, service, "aud340", aggregate_id, ("held",))
    await _assert_chain(factory, service, "aud340", other_id, ("independent",))
    await _assert_chain(
        factory, service, "aud340-other", aggregate_id, ("independent",)
    )


async def test_rolled_back_genesis_releases_writer_without_phantom_predecessor(
    db_session: AsyncSession,
) -> None:
    factory = _sessions(db_session)
    service = SecureAuditService(signing_key=secrets.token_hex(32).encode("ascii"))
    aggregate_id = uuid.uuid4()
    ready: asyncio.Future[int] = asyncio.get_running_loop().create_future()
    async with factory() as first:
        holder_pid = await _transaction_pid(first)
        await _record(service, first, "aud340", aggregate_id, "rolled-back")
        assert first.in_transaction()
        await _assert_not_visible(factory, "aud340", aggregate_id)
        writer = asyncio.create_task(
            _commit_events(
                factory, service, (("aud340", aggregate_id),), "survivor", ready
            )
        )
        try:
            writer_pid = await asyncio.wait_for(ready, timeout=5)
            observation = await _writer_observation(
                factory, writer, writer_pid, holder_pid
            )
        finally:
            try:
                await first.rollback()
            finally:
                await _finish_writer(writer)

    assert observation in {"completed", "blocked"}, "writer must reach the database"
    await _assert_chain(factory, service, "aud340", aggregate_id, ("survivor",))


async def test_existing_head_and_snapshot_isolation_obey_the_writer_contract(
    db_session: AsyncSession,
) -> None:
    factory = _sessions(db_session)
    service = SecureAuditService(signing_key=secrets.token_hex(32).encode("ascii"))
    aggregate_id = uuid.uuid4()
    async with factory() as seed:
        await seed.execute(text("SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED"))
        seed_isolation = await seed.scalar(text("SHOW transaction_isolation"))
        assert seed_isolation == "read uncommitted"
        await _record(service, seed, "aud340", aggregate_id, "seed")
        await seed.commit()

    ready: asyncio.Future[int] = asyncio.get_running_loop().create_future()
    async with factory() as first:
        holder_pid = await _transaction_pid(first)
        await _record(service, first, "aud340", aggregate_id, "first")
        assert first.in_transaction()
        await _assert_chain(factory, service, "aud340", aggregate_id, ("seed",))
        writer = asyncio.create_task(
            _commit_events(
                factory, service, (("aud340", aggregate_id),), "second", ready
            )
        )
        try:
            writer_pid = await asyncio.wait_for(ready, timeout=5)
            observation = await _writer_observation(
                factory, writer, writer_pid, holder_pid
            )
        finally:
            try:
                await first.commit()
            finally:
                await _finish_writer(writer)
    assert observation == "blocked", "the contender must wait on the current writer"

    evidence = {}
    for name, isolation, statement in (
        (
            "repeatable_read",
            "repeatable read",
            "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ",
        ),
        (
            "serializable",
            "serializable",
            "SET TRANSACTION ISOLATION LEVEL SERIALIZABLE",
        ),
    ):
        unsupported_id = uuid.uuid4()
        async with factory() as session:
            await session.execute(text(statement))
            assert await session.scalar(text("SHOW transaction_isolation")) == isolation
            transaction = session.get_transaction()
            assert transaction is not None
            rejected = False
            try:
                try:
                    await _record(service, session, "aud340", unsupported_id, name)
                except ValueError as error:
                    rejected = (
                        type(error) is ValueError
                        and str(error)
                        == "Domain event writes require READ COMMITTED semantics"
                    )
                except Exception:  # RZ-22-01-JUSTIFIED: opaque test failure reporting.
                    pytest.fail(
                        "snapshot-isolation writer failed unexpectedly", pytrace=False
                    )
                evidence[f"{name}_rejected"] = rejected
                evidence[f"{name}_transaction_unchanged"] = (
                    session.get_transaction() is transaction
                )
                current_isolation = await session.scalar(
                    text("SHOW transaction_isolation")
                )
                evidence[f"{name}_isolation_unchanged"] = current_isolation == isolation
                visible = await session.scalar(
                    select(StoredEvent.id).where(
                        StoredEvent.aggregate_type == "aud340",
                        StoredEvent.aggregate_id == str(unsupported_id),
                    )
                )
                evidence[f"{name}_no_event"] = visible is None
            finally:
                await session.rollback()
        await _assert_not_visible(factory, "aud340", unsupported_id)

    async with factory() as observer:
        rows = list(
            (
                await observer.scalars(
                    select(StoredEvent)
                    .where(
                        StoredEvent.aggregate_type == "aud340",
                        StoredEvent.aggregate_id == str(aggregate_id),
                    )
                    .order_by(
                        StoredEvent.sequence_number,
                        StoredEvent.created_at,
                        StoredEvent.id,
                    )
                )
            ).all()
        )
        evidence["existing_head_sequence"] = [row.sequence_number for row in rows]
        evidence["existing_head_payloads"] = [row.payload for row in rows] == [
            {"writer": "seed"},
            {"writer": "first"},
            {"writer": "second"},
        ]
        evidence["existing_head_links"] = [row.prev_hash for row in rows] == [
            "0" * 64,
            *(row.hash for row in rows[:-1]),
        ]
        integrity = await service.verify_chain_integrity(
            observer, "aud340", aggregate_id
        )
        evidence["existing_head_hmac"] = integrity == (True, None, None)

    # Closed sequence/boolean receipt: no keys, payloads, hashes or raw errors.
    print("AUD340_WRITER_OBSERVATIONS=" + json.dumps(evidence, sort_keys=True))
    assert evidence == {
        "repeatable_read_rejected": True,
        "repeatable_read_transaction_unchanged": True,
        "repeatable_read_isolation_unchanged": True,
        "repeatable_read_no_event": True,
        "serializable_rejected": True,
        "serializable_transaction_unchanged": True,
        "serializable_isolation_unchanged": True,
        "serializable_no_event": True,
        "existing_head_sequence": [1, 2, 3],
        "existing_head_payloads": True,
        "existing_head_links": True,
        "existing_head_hmac": True,
    }


async def test_concurrent_genesis_writers_commit_one_contiguous_hmac_chain(
    db_session: AsyncSession,
) -> None:
    factory = _sessions(db_session)
    service = SecureAuditService(signing_key=secrets.token_hex(32).encode("ascii"))
    aggregate_id = uuid.uuid4()
    ready: asyncio.Future[int] = asyncio.get_running_loop().create_future()
    async with factory() as first:
        holder_pid = await _transaction_pid(first)
        await _record(service, first, "aud340", aggregate_id, "first")
        assert first.in_transaction()
        await _assert_not_visible(factory, "aud340", aggregate_id)
        writer = asyncio.create_task(
            _commit_events(
                factory, service, (("aud340", aggregate_id),), "second", ready
            )
        )
        try:
            writer_pid = await asyncio.wait_for(ready, timeout=5)
            observation = await _writer_observation(
                factory, writer, writer_pid, holder_pid
            )
        finally:
            try:
                await first.commit()
            finally:
                await _finish_writer(writer)

    assert observation in {"completed", "blocked"}, "writer must reach the database"
    await _assert_chain(factory, service, "aud340", aggregate_id, ("first", "second"))
