from __future__ import annotations

import uuid
from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.repositories.chat_repository import ChatRepository


class SinglePassScalars:
    def __init__(self, values: list[uuid.UUID]) -> None:
        self._values = values
        self.iterations = 0
        self.all_calls = 0

    def __iter__(self) -> Iterator[uuid.UUID]:
        self.iterations += 1
        if self.iterations > 1:
            raise AssertionError("RETURNING scalar result was iterated more than once")
        return iter(self._values)

    def all(self) -> list[uuid.UUID]:
        self.all_calls += 1
        raise AssertionError(
            "RETURNING scalar rows must not be materialized with all()"
        )


@pytest.mark.parametrize("candidate_count", [0, 102])
@pytest.mark.asyncio
async def test_receipt_cleanup_materializes_no_more_than_100_candidate_ids(
    candidate_count: int,
) -> None:
    chat_id, user_id = uuid.UUID(int=10), uuid.UUID(int=20)
    candidate_ids = [uuid.UUID(int=value) for value in range(1, candidate_count + 1)]
    candidate_result = SimpleNamespace(all=MagicMock(return_value=candidate_ids))
    deleted_ids = candidate_ids[:100]
    returning_scalars = SinglePassScalars(deleted_ids)
    delete_result = SimpleNamespace(scalars=MagicMock(return_value=returning_scalars))
    session = SimpleNamespace(
        get_bind=MagicMock(
            return_value=SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
        ),
        in_transaction=MagicMock(return_value=True),
        scalars=AsyncMock(return_value=candidate_result),
        execute=AsyncMock(side_effect=[SimpleNamespace(), delete_result]),
    )
    repository = ChatRepository(session)

    deleted = await repository.prune_expired_send_receipts(
        chat_id, user_id, limit=10_000
    )

    assert deleted == len(deleted_ids)
    candidate_statement = session.scalars.await_args.args[0]
    candidate_sql = str(
        candidate_statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "LIMIT 100 FOR UPDATE SKIP LOCKED" in candidate_sql
    assert "chat_send_receipts.chat_id" in candidate_sql
    assert "chat_send_receipts.user_id" in candidate_sql
    assert "chat_send_receipts.expires_at <= clock_timestamp()" in candidate_sql

    if not candidate_ids:
        session.execute.assert_awaited_once()
        assert returning_scalars.iterations == 0
        assert returning_scalars.all_calls == 0
        return

    assert session.execute.await_count == 2
    delete_statement = session.execute.await_args_list[-1].args[0]
    compiled_params = delete_statement.compile(dialect=postgresql.dialect()).params
    in_values = [value for value in compiled_params.values() if isinstance(value, list)]
    assert in_values == [candidate_ids[:100]]
    assert returning_scalars.iterations == 1
    assert returning_scalars.all_calls == 0


@pytest.mark.asyncio
async def test_receipt_cleanup_rejects_nonpositive_batch_limits() -> None:
    session = SimpleNamespace(
        get_bind=MagicMock(
            return_value=SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
        ),
        scalars=AsyncMock(),
        execute=AsyncMock(),
    )
    repository = ChatRepository(session)

    with pytest.raises(ValueError, match="limit must be positive"):
        await repository.prune_expired_send_receipts(
            uuid.UUID(int=10), uuid.UUID(int=20), limit=0
        )

    session.scalars.assert_not_awaited()
    session.execute.assert_not_awaited()
