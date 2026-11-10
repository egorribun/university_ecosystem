from datetime import time
from typing import cast

import pytest
from pydantic import ValidationError

from app.api.deps import get_current_user_auth_dto, get_current_user_full
from app.core.database import async_session
from app.models.users import UserPreferences
from app.repositories.unit_of_work import uow_from_session
from app.schemas.dtos.user import UserDTO
from app.schemas.users import UserOut, UserProfileUpdate, UserPublicOut
from app.services.audit_service import AuditService
from app.services.notification_service import NotificationService
from app.services.user.profile_service import UserProfileService
from tests.conftest import install_dishka_override

_FIELDS = ("dnd_enabled", "dnd_start", "dnd_end", "timezone")


def _assert_preferences(body, expected):
    assert body["preferences"] == {"created_at": None, **expected}
    for field in _FIELDS:
        assert body[field] == expected[field]


@pytest.mark.parametrize("as_dto", [False, True])
@pytest.mark.parametrize("kind", ["missing", "disabled", "enabled", "legacy"])
async def test_user_response_preserves_nested_and_flat_preferences(
    user_factory, as_dto, kind
):
    values = {
        "dnd_enabled": kind in {"enabled", "legacy"},
        "dnd_start": time(22, 15) if kind == "enabled" else None,
        "dnd_end": time(7) if kind == "enabled" else None,
        "timezone": "Europe/Paris" if kind == "enabled" else None,
    }
    user = await user_factory(**(values if kind != "missing" else {}))
    source = UserDTO.model_validate(user) if as_dto else user
    body = UserOut.model_validate(source).model_dump(mode="json")
    if kind == "missing":
        assert body["preferences"] is None
        assert body["dnd_enabled"] is False
        assert body["dnd_start"] is None
        assert body["dnd_end"] is None
        assert body["timezone"] is None
    else:
        expected = {
            **values,
            "dnd_start": "22:15:00" if kind == "enabled" else None,
            "dnd_end": "07:00:00" if kind == "enabled" else None,
        }
        _assert_preferences(body, expected)
    public = UserPublicOut.model_validate(source).model_dump(mode="json")
    assert "preferences" not in public
    assert not set(_FIELDS).intersection(public)
    assert "email" not in public


@pytest.fixture
async def profile_context(app, db_session, user_factory):
    user = await user_factory()
    service = UserProfileService(
        uow_from_session(db_session), AuditService(), cast(NotificationService, None)
    )
    install_dishka_override(app, UserProfileService=service)
    app.dependency_overrides[get_current_user_auth_dto] = lambda: user
    app.dependency_overrides[get_current_user_full] = lambda: user
    return user


@pytest.mark.parametrize("nested", [False, True])
async def test_profile_put_get_round_trip_preferences(
    async_client, profile_context, nested
):
    user = profile_context
    before = await async_client.get("/users/me")
    assert before.status_code == 200
    assert before.json()["preferences"] is None
    enabled = {
        "dnd_enabled": True,
        "dnd_start": "22:15:00",
        "dnd_end": "07:00:00",
        "timezone": "Europe/Paris",
    }
    response = await async_client.put(
        "/users/me", json={"preferences": enabled} if nested else enabled
    )
    assert response.status_code == 200
    _assert_preferences(response.json(), enabled)
    read = await async_client.get("/users/me")
    assert read.status_code == 200
    _assert_preferences(read.json(), enabled)
    async with async_session() as observer:
        stored = await observer.get(UserPreferences, user.id)
        assert stored is not None
        assert stored.dnd_enabled is True
        assert stored.dnd_start == time(22, 15)
        assert stored.dnd_end == time(7)
        assert stored.timezone == "Europe/Paris"

    no_op = await async_client.put("/users/me", json={})
    assert no_op.status_code == 200
    _assert_preferences(no_op.json(), enabled)
    partial = await async_client.put(
        "/users/me", json={"preferences": {"timezone": "UTC"}}
    )
    assert partial.status_code == 200
    _assert_preferences(partial.json(), {**enabled, "timezone": "UTC"})
    disabled = {"dnd_enabled": False, "dnd_start": None, "dnd_end": None}
    response = await async_client.put("/users/me", json={"preferences": disabled})
    assert response.status_code == 200
    _assert_preferences(response.json(), {**disabled, "timezone": "UTC"})


async def test_preferences_response_ignores_unrelated_relationship_attributes(
    user_factory,
):
    user = await user_factory(dnd_enabled=False, timezone="UTC")
    user.preferences.private_marker = "not a public preference"
    user.preferences.user = user
    body = UserOut.model_validate(user).model_dump(mode="json")
    _assert_preferences(
        body,
        {"dnd_enabled": False, "dnd_start": None, "dnd_end": None, "timezone": "UTC"},
    )
    assert "user_id" not in body["preferences"]
    assert "user" not in body["preferences"]
    assert "private_marker" not in body["preferences"]


@pytest.mark.parametrize("nested", [False, True])
def test_profile_input_still_requires_times_when_enabling_dnd(nested):
    values = {"dnd_enabled": True}
    with pytest.raises(ValidationError):
        UserProfileUpdate.model_validate({"preferences": values} if nested else values)
