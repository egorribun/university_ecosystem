import pytest
from fastapi import HTTPException, status
from starlette.requests import Request

from app.api import sessions


def _make_request(headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers or [],
        "client": ("127.0.0.1", 1234),
    }
    return Request(scope)


@pytest.mark.anyio
async def test_resolve_target_user_rejects_non_admin(db_session, user_factory):
    current_user = await user_factory(role="student")
    target_user = await user_factory(role="student")

    with pytest.raises(HTTPException) as exc:
        await sessions._resolve_target_user(  # noqa: SLF001
            db=db_session,
            current_user=current_user,
            requested_user_id=target_user.id,
            locale="en",
        )

    assert exc.value.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.anyio
async def test_resolve_target_user_allows_admin(db_session, user_factory):
    admin = await user_factory(role="admin")
    target_user = await user_factory(role="student")

    resolved_id, resolved_user = await sessions._resolve_target_user(  # noqa: SLF001
        db=db_session,
        current_user=admin,
        requested_user_id=target_user.id,
        locale="en",
    )

    assert resolved_id == target_user.id
    assert resolved_user.id == target_user.id


def test_extract_jti_prefers_bearer_header(monkeypatch):
    monkeypatch.setattr(
        sessions,
        "decode_token",
        lambda token: {"jti": "header-jti"},  # noqa: ARG005
    )

    request = _make_request(headers=[(b"authorization", b"Bearer token-value")])
    assert sessions._extract_jti(request) == "header-jti"  # noqa: SLF001


def test_extract_jti_uses_cookie_when_header_missing(monkeypatch):
    def _decode(token: str):  # noqa: ANN001
        if token == "cookie-token":
            return {"jti": "cookie-jti"}
        return None

    monkeypatch.setattr(sessions, "decode_token", _decode)

    request = _make_request(headers=[(b"cookie", b"access_token=cookie-token")])
    assert sessions._extract_jti(request) == "cookie-jti"  # noqa: SLF001
