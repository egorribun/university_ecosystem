from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.services.session_service import SessionService


class _FakeResult:
    def __init__(self, user_id: UUID) -> None:
        self.user_id = user_id

    def one_or_none(self) -> tuple[UUID, int, bool]:
        return (self.user_id, 0, True)


class _FakeDB:
    def __init__(self, user_id: UUID) -> None:
        self.user_id = user_id

    async def execute(self, _statement: object) -> _FakeResult:
        return _FakeResult(self.user_id)

    async def commit(self) -> None:
        return None


class _FakeRepository:
    def __init__(self) -> None:
        self.persisted: dict[str, Any] | None = None

    async def create(self, session_data: dict[str, Any]) -> object:
        self.persisted = dict(session_data)
        return object()


async def _no_redis_sync(*_args: object) -> None:
    return None


def _persisted_session_data(user_agent: str | None) -> dict[str, Any]:
    user_id = uuid4()
    service = SessionService.__new__(SessionService)
    service.db = _FakeDB(user_id)
    service.repo = _FakeRepository()
    service._enforce_concurrent_limit = AsyncMock()
    service._mint_jwt = lambda *_args: "test-token"
    service._sync_to_redis = _no_redis_sync

    asyncio.run(
        service.create_access_token(
            str(user_id),
            metadata={
                "ip_address": "203.0.113.7",
                "user_agent": user_agent,
            },
        )
    )
    assert service.repo.persisted is not None
    return service.repo.persisted


@pytest.mark.parametrize(
    ("user_agent", "expected"),
    [
        ("Firefox/129", "Firefox/129"),
        ("A" * 512, "A" * 512),
        ("A" * 513, "A" * 512),
        ("é" * 512, "é" * 512),
        ("é" * 513, "é" * 512),
        (None, None),
        ("", None),
    ],
    ids=[
        "ordinary-ascii",
        "ascii-boundary",
        "ascii-overflow",
        "multibyte-boundary",
        "multibyte-overflow",
        "none",
        "empty",
    ],
)
def test_create_access_token_persists_user_agent_within_database_bound(
    user_agent: str | None, expected: str | None
) -> None:
    persisted = _persisted_session_data(user_agent)

    assert persisted.get("user_agent") == expected
    assert persisted["ip_address"] == "203.0.113.7"
