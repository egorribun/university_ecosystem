"""Session minting binds the token to the account's locked MFA epoch."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services.session_service import SessionService


def _service(locked_row: tuple[Any, Any] | None) -> tuple[SessionService, MagicMock]:
    result = MagicMock()
    result.one_or_none.return_value = locked_row
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    repo = MagicMock()
    repo.create = AsyncMock(
        return_value=SimpleNamespace(ip_address=None, user_agent=None)
    )
    service = SessionService(SimpleNamespace(sessions=SimpleNamespace(db=db)))  # type: ignore[arg-type]
    service.repo = repo
    service._enforce_concurrent_limit = AsyncMock()  # type: ignore[method-assign]
    service._sync_to_redis = AsyncMock()  # type: ignore[method-assign]
    service._mint_jwt = MagicMock(return_value="jwt")  # type: ignore[method-assign]
    return service, db


async def test_user_row_is_locked_and_its_epoch_is_persisted_on_the_session() -> None:
    user_id = uuid4()
    service, db = _service((user_id, 6))

    await service.create_access_token(user_id, metadata={"mfa_epoch": 6})

    statement = db.execute.await_args.args[0]
    compiled = statement.compile()
    assert str(compiled) == (
        "SELECT users.id, users.mfa_epoch \nFROM users \n"
        "WHERE users.id = :id_1 FOR UPDATE"
    )
    assert compiled.params == {"id_1": user_id}
    assert service.repo.create.await_args.args[0]["mfa_epoch"] == 6


async def test_unknown_user_row_falls_back_to_epoch_zero() -> None:
    service, _ = _service(None)

    await service.create_access_token(uuid4())

    assert service.repo.create.await_args.args[0]["mfa_epoch"] == 0


async def test_unset_epoch_column_is_persisted_as_zero() -> None:
    user_id = uuid4()
    service, _ = _service((user_id, None))

    await service.create_access_token(user_id, metadata={"mfa_epoch": 0})

    assert service.repo.create.await_args.args[0]["mfa_epoch"] == 0


@pytest.mark.parametrize("requested", ["not-an-integer", [], 2])
async def test_stale_or_malformed_epoch_is_refused_before_minting(
    requested: object,
) -> None:
    user_id = uuid4()
    service, _ = _service((user_id, 3))

    with pytest.raises(HTTPException) as exc:
        await service.create_access_token(user_id, metadata={"mfa_epoch": requested})

    assert exc.value.status_code == 401
    assert exc.value.detail == "credentials_invalid"
    service.repo.create.assert_not_awaited()
    service._mint_jwt.assert_not_called()
