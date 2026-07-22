"""Negative security contracts for authorization and token claim handling."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, Request

from app.api.deps.auth import get_current_admin_user
from app.models.enums import UserRole
from app.services.auth.token_service import AuthTokenService


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/admin/audit",
            "raw_path": b"/admin/audit",
            "headers": [],
            "query_string": b"",
        }
    )


def test_manipulated_role_claim_never_enters_the_authorization_identity() -> None:
    """JWT role claims are untrusted metadata; only sub/jti identify a session."""
    user_id = uuid4()
    parsed_id, parsed_jti = AuthTokenService.validate_payload(
        {"sub": str(user_id), "jti": "session-1", "role": UserRole.ADMIN.value},
        "en",
    )

    assert parsed_id == user_id
    assert parsed_jti == "session-1"


@pytest.mark.asyncio
async def test_local_admin_role_does_not_bypass_spicedb_denial() -> None:
    """A forged/local admin role is insufficient when the authz provider denies."""
    user = SimpleNamespace(id=uuid4(), role=UserRole.ADMIN)
    checker = SimpleNamespace(check_admin=AsyncMock(return_value=False))

    with pytest.raises(HTTPException) as exc_info:
        await get_current_admin_user(_request(), user, checker)

    assert exc_info.value.status_code == 403
    checker.check_admin.assert_awaited_once_with(str(user.id), user=user)
