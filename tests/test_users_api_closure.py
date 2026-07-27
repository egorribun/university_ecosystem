from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import users as api
from app.models.enums import UserRole
from app.schemas import schemas


def _request(headers: dict[str, str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        headers=headers or {},
        state=SimpleNamespace(active_session=SimpleNamespace(signing_key="secret")),
    )


def _user(*, role: UserRole = UserRole.STUDENT) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        role=role,
        email="user@example.com",
        is_active=True,
    )


def _signed_envelope(
    *, expires_at: object, data: object = None, version: object = 1
) -> str:
    payload = {"version": version, "expiresAt": expires_at, "data": data}
    payload_json = json.dumps(payload, separators=(",", ":"))
    digest = hmac.new(b"secret", payload_json.encode(), hashlib.sha256).digest()
    return json.dumps(
        {**payload, "signature": base64.b64encode(digest).decode("ascii")}
    )


def _patch_user_out(value: object):
    return patch.object(api.schemas.UserOut, "model_validate", return_value=value)


def test_profile_cache_integrity_environment_and_validation_paths() -> None:
    with patch.object(api, "settings") as settings:
        settings.environment = "testing"
        api._enforce_profile_cache_integrity(_request())

    with patch.object(api, "settings") as settings:
        settings.environment = "production"
        with pytest.raises(HTTPException) as exc:
            api._enforce_profile_cache_integrity(_request())
    assert exc.value.status_code == 400

    with patch.object(api, "settings") as settings:
        settings.environment = "production"
        request = _request({api.PROFILE_CACHE_HEADER: "{}"})
        request.state.active_session.signing_key = ""
        with pytest.raises(HTTPException) as exc:
            api._enforce_profile_cache_integrity(request)
    assert exc.value.status_code == 400

    cases = [
        "[]",
        json.dumps({"version": 1, "expiresAt": 1, "data": {}}),
        json.dumps({"version": 1, "expiresAt": 1, "data": {}, "signature": ""}),
        "{",
        json.dumps({"version": 1, "expiresAt": 1, "data": None, "signature": "bad"}),
    ]
    for raw in cases:
        request = _request({api.PROFILE_CACHE_HEADER: raw})
        with patch.object(api, "settings") as settings:
            settings.environment = "production"
            with pytest.raises(HTTPException) as exc:
                api._enforce_profile_cache_integrity(request)
        assert exc.value.status_code == 400

    oversized = _request({api.PROFILE_CACHE_HEADER: "x" * 8_193})
    with patch.object(api, "settings") as settings:
        settings.environment = "production"
        with pytest.raises(HTTPException) as exc:
            api._enforce_profile_cache_integrity(oversized)
    assert exc.value.status_code == 400

    invalid_signature = json.loads(
        _signed_envelope(
            expires_at=int(
                (datetime.now(UTC) + timedelta(minutes=5)).timestamp() * 1000
            ),
            data={},
        )
    )
    invalid_signature["signature"] = "invalid"
    with patch.object(api, "settings") as settings:
        settings.environment = "production"
        with pytest.raises(HTTPException) as exc:
            api._enforce_profile_cache_integrity(
                _request({api.PROFILE_CACHE_HEADER: json.dumps(invalid_signature)})
            )
    assert exc.value.status_code == 400


def test_profile_cache_integrity_signed_expiry_variants() -> None:
    future = datetime.now(UTC) + timedelta(minutes=5)
    valid = [
        _signed_envelope(
            expires_at=int(future.timestamp() * 1000), data={"name": "user"}
        ),
        _signed_envelope(
            expires_at=future.replace(tzinfo=None).isoformat(), data={"name": "user"}
        ),
        _signed_envelope(expires_at=future.isoformat(), data={"name": "user"}),
    ]
    for raw in valid:
        request = _request({api.PROFILE_CACHE_HEADER: raw})
        with patch.object(api, "settings") as settings:
            settings.environment = "production"
            api._enforce_profile_cache_integrity(request)

    for expires_at in (0, "not-a-date"):
        raw = _signed_envelope(expires_at=expires_at, data={})
        request = _request({api.PROFILE_CACHE_HEADER: raw})
        with patch.object(api, "settings") as settings:
            settings.environment = "production"
            with pytest.raises(HTTPException) as exc:
                api._enforce_profile_cache_integrity(request)
        assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_password_and_profile_adapters() -> None:
    request = _request()
    auth = MagicMock()
    auth.initiate_password_reset = AsyncMock()
    assert await api.forgot_password(
        schemas.ForgotPasswordIn(email="user@example.com"), request, MagicMock(), auth
    ) == {"ok": True}
    auth.initiate_password_reset.assert_awaited_once()

    auth.perform_password_reset = AsyncMock()
    assert await api.reset_password(
        schemas.ResetPasswordIn(token="token", password="Password123!"), request, auth
    ) == {"ok": True}

    user = _user()
    db = AsyncMock()
    auth.refresh_pending_email = AsyncMock()
    expected = object()
    with (
        patch.object(api, "_enforce_profile_cache_integrity"),
        patch.object(api, "log_data_access", AsyncMock()) as log,
        _patch_user_out(expected),
    ):
        result = await api.me(request, db=db, user=user, auth_service=auth)
    assert result is expected
    log.assert_awaited_once()

    service = MagicMock()
    service.update_user_profile = AsyncMock(return_value=user)
    with _patch_user_out(expected):
        result = await api.update_me(MagicMock(), request, user=user, service=service)
    assert result is expected


@pytest.mark.asyncio
async def test_email_password_compliance_and_media_adapters() -> None:
    request = _request()
    user = _user()
    expected = object()
    auth = MagicMock()
    auth.initiate_email_change = AsyncMock(return_value=user)
    auth.confirm_email_change = AsyncMock(return_value=user)
    with _patch_user_out(expected):
        result = await api.change_email(
            schemas.UserEmailChangeIn(email="new@example.com", password="pw"),
            request,
            MagicMock(),
            None,
            user,
            auth,
        )
        assert result is expected
        result = await api.verify_email_change(
            schemas.UserEmailConfirmIn(token="token"), request, user, auth
        )
    assert result is expected

    auth.change_password = AsyncMock(return_value=(True, 2))
    result = await api.change_password(
        schemas.UserPasswordChangeIn(
            current_password="old", new_password="Password123!"
        ),
        request,
        None,
        user,
        auth,
    )
    assert result.ok is True
    assert result.revoked_sessions == 2

    compliance = MagicMock()
    compliance.export_user_data = AsyncMock(return_value={"ok": True})
    assert await api.export_current_user_data(request, None, user, compliance) == {
        "ok": True
    }
    compliance.delete_user_data = AsyncMock(return_value={"deleted": True})
    assert await api.delete_current_user_account(
        schemas.DataDeletionRequest(confirm=True), request, None, user, compliance
    ) == {"deleted": True}

    media = MagicMock()
    media.upload_avatar = AsyncMock(return_value=user)
    media.upload_cover = AsyncMock(return_value=user)
    media.delete_avatar = AsyncMock(return_value=user)
    media.delete_cover = AsyncMock(return_value=user)
    file = SimpleNamespace(size=10)
    with (
        patch.object(api, "scan_for_malware", AsyncMock()) as scan,
        _patch_user_out(expected),
    ):
        assert await api.upload_avatar(file, request=request, user=user, service=media)
        assert await api.upload_cover(file, request=request, user=user, service=media)
        assert await api.delete_avatar(request, user=user, service=media) is expected
        assert await api.delete_cover(request, user=user, service=media) is expected
    assert scan.await_count == 2


@pytest.mark.asyncio
async def test_create_and_list_users_roles() -> None:
    request = _request()
    user = _user()
    service = MagicMock()
    service.create_user = AsyncMock(return_value=user)
    expected = object()
    with _patch_user_out(expected):
        assert await api.create_user(MagicMock(), request, user, service) is expected

    items = [SimpleNamespace(id=uuid4())]
    service.get_users = AsyncMock(return_value=items)
    bg = MagicMock()
    db = AsyncMock()
    public = object()
    with patch.object(api.schemas.UserPublicOut, "model_validate", return_value=public):
        result = await api.get_users(
            request,
            bg,
            filters=schemas.UserSearchFilter(),
            current_user=user,
            service=service,
            db=db,
        )
    assert result == [public]
    bg.add_task.assert_called_once()

    admin = _user(role=UserRole.ADMIN)
    with _patch_user_out(expected):
        result = await api.get_users(
            request,
            MagicMock(),
            filters=schemas.UserSearchFilter(),
            current_user=admin,
            service=service,
            db=db,
        )
    assert result == [expected]


@pytest.mark.asyncio
async def test_audit_export_admin_range_and_admin_adapters() -> None:
    request = _request()
    admin = _user(role=UserRole.ADMIN)
    audit = MagicMock()
    db = AsyncMock()
    with patch.object(api, "resolve_locale", return_value="en"):
        with pytest.raises(HTTPException) as exc:
            await api.export_access_audit(
                request,
                start_at=datetime(2024, 1, 1, tzinfo=UTC),
                end_at=datetime(2024, 3, 1, tzinfo=UTC),
                db=db,
                user=admin,
                audit=audit,
            )
    assert exc.value.status_code == 400

    stream = iter([b"id\n", b"1\n"])
    with (
        patch.object(api, "resolve_locale", return_value="en"),
        patch(
            "app.services.data_access.export_access_logs_stream", return_value=stream
        ),
    ):
        response = await api.export_access_audit(
            request,
            start_at=None,
            end_at=None,
            db=db,
            user=admin,
            audit=audit,
        )
    assert response.media_type == "text/csv"
    assert "access_audit.csv" in response.headers["content-disposition"]
    audit.log.assert_called_once()

    profile = MagicMock()
    profile.admin_update_user = AsyncMock(return_value=admin)
    expected = object()
    with _patch_user_out(expected):
        assert (
            await api.update_user_admin(
                admin.id, schemas.UserAdminUpdate(), request, admin, profile
            )
            is expected
        )

    compliance = MagicMock()
    compliance.admin_delete_user = AsyncMock(return_value={"ok": True})
    assert await api.delete_user_admin(admin.id, request, admin, compliance) == {
        "ok": True
    }


@pytest.mark.asyncio
async def test_get_groups_maps_service_results() -> None:
    group = SimpleNamespace(id=uuid4(), name="Group", course=1, faculty="Faculty")
    service = MagicMock()
    service.get_groups = AsyncMock(return_value=[group])
    result = await api.get_groups(service)
    assert result[0].id == group.id
    assert result[0].name == "Group"
