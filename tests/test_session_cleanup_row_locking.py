"""Session revocation locks rows only when the caller asks for it."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import ActiveSession
from app.services.session_cleanup import revoke_sessions_matching


@pytest.mark.parametrize(
    ("kwargs", "locked"),
    [({}, False), ({"lock_rows": False}, False), ({"lock_rows": True}, True)],
)
async def test_rows_are_locked_only_on_request(
    kwargs: dict[str, bool], locked: bool
) -> None:
    result = MagicMock()
    result.scalars.return_value = []
    db = AsyncMock()
    db.execute.return_value = result

    with patch(
        "app.services.session_cleanup.get_session_backend", return_value=AsyncMock()
    ):
        revoked = await revoke_sessions_matching(
            db=db, whereclause=ActiveSession.id == ActiveSession.id, **kwargs
        )

    assert revoked == 0
    statement = str(db.execute.await_args.args[0].compile())
    assert statement.endswith("FOR UPDATE") is locked
