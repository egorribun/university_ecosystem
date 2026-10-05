from __future__ import annotations

import base64
import hashlib
import hmac
import json
from contextlib import AbstractContextManager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request
from starlette.datastructures import State
from starlette.types import Scope

from app.api import users as api
from app.models.enums import UserRole
from app.schemas import schemas
from tests.conftest import call_injected


def _request(headers: dict[str, str] | None = None) -> Request[State]:
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "root_path": "",
        "headers": [
            (key.lower().encode("latin-1"), value.encode("latin-1"))
            for key, value in (headers or {}).items()
        ],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "state": {"active_session": SimpleNamespace(signing_key="secret")},
    }
    return Request(scope)


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


def _patch_user_out(value: object) -> AbstractContextManager[object]:
    return patch.object(schemas.UserOut, "model_validate", return_value=value)


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
    assert await call_injected(
        api.forgot_password,
        schemas.ForgotPasswordIn(email="user@example.com"),
        bg=MagicMock(),
        request=request,
        provides={"AuthService": auth},
    ) == {"ok": True}
    auth.initiate_password_reset.assert_awaited_once()

    auth.perform_password_reset = AsyncMock()
    assert await call_injected(
        api.reset_password,
        schemas.ResetPasswordIn(token="token", password="Password123!"),
        request=request,
        provides={"AuthService": auth},
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
        result = await call_injected(
            api.me,
            request=request,
            user=user,
            provides={"AuthService": auth, "AsyncDatabaseSession": db},
        )
    assert result is expected
    log.assert_awaited_once()

    service = MagicMock()
    service.update_user_profile = AsyncMock(return_value=user)
    with _patch_user_out(expected):
        result = await call_injected(
            api.update_me,
            MagicMock(),
            request=request,
            user=user,
            provides={"UserProfileService": service},
        )
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
        result = await call_injected(
            api.change_email,
            schemas.UserEmailChangeIn(email="new@example.com", password="pw"),
            bg=MagicMock(),
            request=request,
            user=user,
            provides={"AuthService": auth},
        )
        assert result is expected
        result = await call_injected(
            api.verify_email_change,
            schemas.UserEmailConfirmIn(token="token"),
            request=request,
            user=user,
            provides={"AuthService": auth},
        )
    assert result is expected

    auth.change_password = AsyncMock(return_value=(True, 2))
    result = await call_injected(
        api.change_password,
        schemas.UserPasswordChangeIn(
            current_password="old", new_password="Password123!"
        ),
        request=request,
        user=user,
        provides={"AuthService": auth},
    )
    assert result.ok is True
    assert result.revoked_sessions == 2

    compliance = MagicMock()
    compliance.export_user_data = AsyncMock(return_value={"ok": True})
    assert await call_injected(
        api.export_current_user_data,
        request=request,
        user=user,
        provides={"UserComplianceService": compliance},
    ) == {"ok": True}
    compliance.delete_user_data = AsyncMock(return_value={"deleted": True})
    assert await call_injected(
        api.delete_current_user_account,
        schemas.DataDeletionRequest(confirm=True),
        request=request,
        user=user,
        provides={"UserComplianceService": compliance},
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
        assert await call_injected(
            api.upload_avatar,
            file,
            request=request,
            user=user,
            provides={"UserMediaService": media},
        )
        assert await call_injected(
            api.upload_cover,
            file,
            request=request,
            user=user,
            provides={"UserMediaService": media},
        )
        assert (
            await call_injected(
                api.delete_avatar,
                request=request,
                user=user,
                provides={"UserMediaService": media},
            )
            is expected
        )
        assert (
            await call_injected(
                api.delete_cover,
                request=request,
                user=user,
                provides={"UserMediaService": media},
            )
            is expected
        )
    assert scan.await_count == 2


@pytest.mark.asyncio
async def test_create_and_list_users_roles() -> None:
    request = _request()
    user = _user()
    service = MagicMock()
    service.create_user = AsyncMock(return_value=user)
    expected = object()
    with _patch_user_out(expected):
        assert (
            await call_injected(
                api.create_user,
                MagicMock(),
                request=request,
                user=user,
                provides={"UserComplianceService": service},
            )
            is expected
        )

    items = [SimpleNamespace(id=uuid4())]
    service.get_users = AsyncMock(return_value=items)
    bg = MagicMock()
    db = AsyncMock()
    public = object()
    with patch.object(schemas.UserPublicOut, "model_validate", return_value=public):
        result = await call_injected(
            api.get_users,
            checker=_checker(),
            bg=bg,
            request=request,
            filters=schemas.UserSearchFilter(),
            current_user=user,
            provides={"UserProfileService": service, "AsyncDatabaseSession": db},
        )
    assert result == [public]
    bg.add_task.assert_called_once()

    admin = _user(role=UserRole.ADMIN)
    with _patch_user_out(expected):
        result = await call_injected(
            api.get_users,
            checker=_checker(is_admin=True),
            bg=MagicMock(),
            request=request,
            filters=schemas.UserSearchFilter(),
            current_user=admin,
            provides={"UserProfileService": service, "AsyncDatabaseSession": db},
        )
    assert result == [expected]


def _checker(*, is_admin: bool = False, unavailable: bool = False) -> SimpleNamespace:
    from app.auth.rbac import SpiceDBUnavailableError

    check_admin = AsyncMock(
        side_effect=SpiceDBUnavailableError("down") if unavailable else None,
        return_value=is_admin,
    )
    return SimpleNamespace(check_admin=check_admin)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "checker",
    [_checker(is_admin=False), _checker(unavailable=True)],
    ids=["spicedb-denies", "spicedb-unavailable"],
)
async def test_get_users_ignores_stale_admin_role_without_spicedb_admin(
    checker: SimpleNamespace,
) -> None:
    service = MagicMock()
    service.get_users = AsyncMock(return_value=[SimpleNamespace(id=uuid4())])
    public = object()

    with patch.object(schemas.UserPublicOut, "model_validate", return_value=public):
        result = await call_injected(
            api.get_users,
            checker=checker,
            bg=MagicMock(),
            request=_request(),
            filters=schemas.UserSearchFilter(),
            current_user=_user(role=UserRole.ADMIN),
            provides={
                "UserProfileService": service,
                "AsyncDatabaseSession": AsyncMock(),
            },
        )

    assert result == [public]


@pytest.mark.asyncio
async def test_get_users_route_normalizes_legacy_search_before_service_query() -> None:
    from app.services.user.profile_service import UserProfileService

    repo = MagicMock()
    repo.list_users = AsyncMock(return_value=[SimpleNamespace(id=uuid4())])
    service = UserProfileService(MagicMock(users=repo), MagicMock(), AsyncMock())
    filters = schemas.UserSearchFilter(search="  Teacher  ")
    public = object()

    with patch.object(schemas.UserPublicOut, "model_validate", return_value=public):
        result = await call_injected(
            api.get_users,
            checker=_checker(),
            bg=MagicMock(),
            request=_request(),
            filters=filters,
            current_user=_user(),
            provides={
                "UserProfileService": service,
                "AsyncDatabaseSession": AsyncMock(),
            },
        )

    assert result == [public]
    assert filters.full_name == "Teacher"
    assert filters.search is None
    repo.list_users.assert_awaited_once_with(filters=filters)


@pytest.mark.asyncio
async def test_get_users_route_rejects_blank_search_for_non_admin() -> None:
    from app.core.exceptions.domain import PermissionDenied
    from app.services.user.profile_service import UserProfileService

    repo = MagicMock()
    repo.list_users = AsyncMock(return_value=[SimpleNamespace(id=uuid4())])
    service = UserProfileService(MagicMock(users=repo), MagicMock(), AsyncMock())

    with pytest.raises(PermissionDenied):
        await call_injected(
            api.get_users,
            checker=_checker(),
            bg=MagicMock(),
            request=_request(),
            filters=schemas.UserSearchFilter(full_name="  "),
            current_user=_user(),
            provides={
                "UserProfileService": service,
                "AsyncDatabaseSession": AsyncMock(),
            },
        )

    repo.list_users.assert_not_awaited()


@pytest.mark.asyncio
async def test_audit_export_admin_range_and_admin_adapters() -> None:
    request = _request()
    admin = _user(role=UserRole.ADMIN)
    audit = MagicMock()
    db = AsyncMock()
    with patch.object(api, "resolve_locale", return_value="en"):
        with pytest.raises(HTTPException) as exc:
            await call_injected(
                api.export_access_audit,
                request=request,
                start_at=datetime(2024, 1, 1, tzinfo=UTC),
                end_at=datetime(2024, 3, 1, tzinfo=UTC),
                user=admin,
                provides={"AsyncDatabaseSession": db, "AuditService": audit},
            )
    assert exc.value.status_code == 400

    stream = iter([b"id\n", b"1\n"])
    with (
        patch.object(api, "resolve_locale", return_value="en"),
        patch(
            "app.services.data_access.export_access_logs_stream", return_value=stream
        ),
    ):
        response = await call_injected(
            api.export_access_audit,
            request=request,
            start_at=None,
            end_at=None,
            user=admin,
            provides={"AsyncDatabaseSession": db, "AuditService": audit},
        )
    assert response.media_type == "text/csv"
    assert "access_audit.csv" in response.headers["content-disposition"]
    audit.log.assert_called_once()

    profile = MagicMock()
    profile.admin_update_user = AsyncMock(return_value=admin)
    expected = object()
    with _patch_user_out(expected):
        assert (
            await call_injected(
                api.update_user_admin,
                admin.id,
                schemas.UserAdminUpdate(),
                request=request,
                user=admin,
                provides={"UserProfileService": profile},
            )
            is expected
        )

    compliance = MagicMock()
    compliance.admin_delete_user = AsyncMock(return_value={"ok": True})
    assert await call_injected(
        api.delete_user_admin,
        admin.id,
        request=request,
        user=admin,
        provides={"UserComplianceService": compliance},
    ) == {"ok": True}


@pytest.mark.asyncio
async def test_get_groups_maps_service_results() -> None:
    group = SimpleNamespace(id=uuid4(), name="Group", course=1, faculty="Faculty")
    service = MagicMock()
    service.get_groups = AsyncMock(return_value=[group])
    result = await call_injected(api.get_groups, provides={"GroupService": service})
    assert result[0].id == group.id
    assert result[0].name == "Group"


@pytest.mark.asyncio
async def test_admin_user_list_uses_the_authenticated_subject_for_full_profiles() -> (
    None
):
    from fastapi import BackgroundTasks, Request

    from app.schemas.dtos.user import UserDTO

    def make_user(*, role: UserRole, email: str) -> UserDTO:
        return UserDTO(
            id=uuid4(),
            email=email,
            role=role,
            group_id=None,
            is_active=True,
            mfa_required=False,
            mfa_default_method=None,
            mfa_last_verified_at=None,
            created_at=datetime.now(UTC),
        )

    class IdentityBoundChecker:
        def __init__(self, granted_subject: str) -> None:
            self.granted_subject = granted_subject

        async def check_admin(
            self, user_id: str | None, *, user: object | None = None
        ) -> bool:
            return user_id == self.granted_subject

    class UserListService:
        def __init__(self, users: list[UserDTO]) -> None:
            self.users = users

        async def get_users(
            self,
            request: Request,
            current_user: UserDTO | None = None,
            filters: schemas.UserSearchFilter | None = None,
        ) -> list[UserDTO]:
            return self.users

    admin = make_user(role=UserRole.ADMIN, email="admin@example.com")
    listed_user = make_user(role=UserRole.STUDENT, email="student@example.com")
    checker = IdentityBoundChecker(str(admin.id))
    request = Request(
        {"type": "http", "method": "GET", "path": "/users", "headers": []}
    )

    result = await call_injected(
        api.get_users,
        checker=checker,
        bg=BackgroundTasks(),
        request=request,
        filters=schemas.UserSearchFilter(),
        current_user=admin,
        provides={
            "UserProfileService": UserListService([listed_user]),
            "AsyncDatabaseSession": AsyncMock(),
        },
    )

    assert len(result) == 1
    assert isinstance(result[0], schemas.UserOut)
    assert result[0].email == listed_user.email
