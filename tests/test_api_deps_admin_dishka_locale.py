"""The Dishka admin guard reports refusals in the caller's locale."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request

import app.api.deps.auth as auth_deps
from app.api.deps.auth import get_current_admin_user_from_dishka
from app.core.localization import translate
from app.models import User


def _request(accept_language: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/admin",
            "query_string": b"",
            "headers": [(b"accept-language", accept_language.encode())],
        }
    )


async def test_non_admin_is_refused_in_the_request_locale() -> None:
    user = SimpleNamespace(id=uuid4())
    checker = MagicMock(check_admin=AsyncMock(return_value=False))

    with pytest.raises(HTTPException) as exc:
        await get_current_admin_user_from_dishka(_request("ru"), user, checker)  # type: ignore[arg-type]

    assert exc.value.status_code == 403
    assert exc.value.detail == translate("errors.forbidden", locale="ru")
    assert exc.value.detail != translate("errors.forbidden", locale="en")
    checker.check_admin.assert_awaited_once_with(str(user.id), user=user)


@pytest.mark.asyncio
async def test_legacy_admin_guard_uses_request_locale_for_denial() -> None:
    user = MagicMock(spec=User)
    user.id = uuid4()
    checker = MagicMock(check_admin=AsyncMock(return_value=False))

    with pytest.raises(HTTPException) as exc:
        await auth_deps.get_current_admin_user(_request("ru"), user, checker)

    assert exc.value.status_code == 403
    assert exc.value.detail == translate("errors.forbidden", locale="ru")
    assert exc.value.detail != translate("errors.forbidden", locale="en")
