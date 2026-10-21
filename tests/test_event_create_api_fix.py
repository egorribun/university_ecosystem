from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi import status
from pydantic import ValidationError

from app import models
from app.api.deps.auth import get_permission_checker
from app.auth.rbac import PermissionChecker

from app.auth.security import get_password_hash
from app.main import app
from app.schemas import schemas


async def _login(async_client, email: str, password: str) -> dict[str, str]:
    response = await async_client.post(
        "/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == status.HTTP_200_OK
    token = response.cookies.get("access_token_v2")
    return {"Authorization": f"Bearer {token}", "X-Query-Budget": "15"}


@pytest.mark.asyncio
async def test_create_event_frontend_payload_reproduction(async_client, user_factory):
    password = "EventFix123!"
    teacher = await user_factory(
        role="teacher",
        hashed_password=await get_password_hash(password),
        is_active=True,
    )

    headers = await _login(async_client, teacher.email, password)

    # Simulate Date.now() + 1h
    # Frontend logic allows starts == ends because checks `ends < starts` (not <=)
    # But Backend EventCreate validator checks `ends_at <= starts_at`
    # -> raises ValueError -> returns 422

    now = datetime.now(UTC)
    starts_at = (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
    # Same time for end
    ends_at = starts_at

    # Payload similar to what frontend sends (empty strings for optionals)
    payload = {
        "title": "Frontend Event",
        "title_en": "",
        "description": "",
        "description_en": "",
        "event_type": "",
        "event_type_en": "",
        "location": "Loc",
        "location_en": "",
        "starts_at": starts_at,
        "ends_at": ends_at,
        "speaker": "",
        "image_url": "",
        "about": "",
        "about_en": "",
    }

    # Expecting 422
    response = await async_client.post(
        "/events",
        headers=headers,
        json=payload,
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    # print(f"\nConfimed 422 Error for equal times: {response.json()}")


@pytest.mark.asyncio
async def test_create_event_success_db(async_client, user_factory):
    """
    Test that a fully valid payload successfully creates an event in the DB.
    This verifies that the 'search_vector' (Computed) issue is resolved,
    as we expect the INSERT to succeed now.
    """
    password = "EventFix123!"
    teacher = await user_factory(
        role="teacher",
        hashed_password=await get_password_hash(password),
        is_active=True,
    )

    headers = await _login(async_client, teacher.email, password)

    now = datetime.now(UTC)
    # Explicitly valid times
    starts_at = (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
    ends_at = (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")

    payload = {
        "title": "Valid DB Event",
        "title_en": "Valid DB Event EN",
        "description": "Desc",
        "description_en": "Desc EN",
        "event_type": "lecture",
        "event_type_en": "Lecture",
        "location": "Room 101",
        "location_en": "Room 101",
        "starts_at": starts_at,
        "ends_at": ends_at,
        "speaker": "Prof X",
        "image_url": "",
        "about": "",
        "about_en": "",
    }

    response = await async_client.post(
        "/events",
        headers=headers,
        json=payload,
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    # Use 'in' to handle potential localization (Valid DB Event or Valid DB Event EN)
    assert "Valid DB Event" in data["title"]
    assert data["id"] is not None


_EVENT_MODELS = (schemas.EventCreate, schemas.EventUpdate)
_EVENT_BOUNDED_FIELDS = (
    ("title", 512),
    ("title_en", 512),
    ("location", 512),
    ("location_en", 512),
    ("speaker", 512),
    ("event_type", 128),
    ("event_type_en", 128),
    ("image_url", 2048),
)


def _event_schema_payload(model, starts_at=None, ends_at=None):
    payload = {
        "starts_at": starts_at or datetime(2035, 1, 1, 10, tzinfo=UTC),
        "ends_at": ends_at or datetime(2035, 1, 1, 11, tzinfo=UTC),
    }
    if model is schemas.EventCreate:
        payload["title"] = "Valid event"
    return payload


@pytest.mark.parametrize("model", _EVENT_MODELS, ids=["create", "update"])
@pytest.mark.parametrize(("field", "limit"), _EVENT_BOUNDED_FIELDS)
@pytest.mark.parametrize("character", ["x", "Я"], ids=["ascii", "unicode"])
def test_event_string_limits_count_characters_after_normalization(
    model, field, limit, character
):
    payload = _event_schema_payload(model)
    payload[field] = character * limit
    assert getattr(model.model_validate(payload), field) == character * limit

    payload[field] = character * (limit + 1)
    with pytest.raises(ValidationError):
        model.model_validate(payload)


@pytest.mark.parametrize("model", _EVENT_MODELS, ids=["create", "update"])
@pytest.mark.parametrize("field", ["title", "location", "speaker"])
def test_event_clean_string_bounds_preserve_control_character_removal(model, field):
    payload = _event_schema_payload(model)
    payload[field] = "x" * 512 + "\x00"
    assert getattr(model.model_validate(payload), field) == "x" * 512

    payload[field] = "x" * 513 + "\x00"
    with pytest.raises(ValidationError):
        model.model_validate(payload)


@pytest.mark.parametrize("model", _EVENT_MODELS, ids=["create", "update"])
@pytest.mark.parametrize("field", ["title", "location", "speaker"])
def test_event_clean_string_bounds_count_retained_tabs_and_newlines(model, field):
    payload = _event_schema_payload(model)
    payload[field] = "x" * 510 + "\t\n"
    assert getattr(model.model_validate(payload), field) == payload[field]

    payload[field] = "x" * 511 + "\t\n"
    with pytest.raises(ValidationError):
        model.model_validate(payload)


@pytest.mark.parametrize("model", _EVENT_MODELS, ids=["create", "update"])
@pytest.mark.parametrize(
    ("field", "limit"),
    [
        ("title_en", 512),
        ("location_en", 512),
        ("event_type", 128),
        ("event_type_en", 128),
    ],
)
def test_event_optional_text_preserves_whitespace_normalization(model, field, limit):
    payload = _event_schema_payload(model)
    payload[field] = " " * (limit + 1)
    assert getattr(model.model_validate(payload), field) is None
    payload[field] = None
    assert getattr(model.model_validate(payload), field) is None

    payload[field] = " " + "x" * (limit - 2) + " "
    assert getattr(model.model_validate(payload), field) == payload[field]

    payload[field] = " " + "x" * (limit - 1) + " "
    with pytest.raises(ValidationError):
        model.model_validate(payload)


@pytest.mark.parametrize("model", _EVENT_MODELS, ids=["create", "update"])
@pytest.mark.parametrize(
    "field", ["description", "description_en", "about", "about_en"]
)
def test_event_text_columns_are_not_given_varchar_limits(model, field):
    payload = _event_schema_payload(model)
    payload[field] = "x" * 4096
    assert getattr(model.model_validate(payload), field) == payload[field]


@pytest.mark.parametrize("model", _EVENT_MODELS, ids=["create", "update"])
@pytest.mark.parametrize("tzinfo", [None, UTC], ids=["naive", "aware"])
def test_event_same_awareness_time_pairs_remain_valid(model, tzinfo):
    starts = datetime(2035, 1, 1, 10, tzinfo=tzinfo)
    ends = datetime(2035, 1, 1, 11, tzinfo=tzinfo)
    parsed = model.model_validate(_event_schema_payload(model, starts, ends))
    assert (parsed.starts_at, parsed.ends_at) == (starts, ends)


@pytest.mark.parametrize("model", _EVENT_MODELS, ids=["create", "update"])
@pytest.mark.parametrize("naive_start", [True, False], ids=["naive-start", "naive-end"])
def test_event_mixed_awareness_is_a_validation_error(model, naive_start):
    starts = datetime(2035, 1, 1, 10, tzinfo=None if naive_start else UTC)
    ends = datetime(2035, 1, 1, 11, tzinfo=UTC if naive_start else None)
    with pytest.raises(ValidationError):
        model.model_validate(_event_schema_payload(model, starts, ends))


@pytest.mark.parametrize("model", _EVENT_MODELS, ids=["create", "update"])
def test_event_aware_times_use_absolute_order_not_wall_time(model):
    starts = datetime.fromisoformat("2035-01-01T10:00:00+02:00")
    ends = datetime.fromisoformat("2035-01-01T09:30:00+01:00")
    parsed = model.model_validate(_event_schema_payload(model, starts, ends))
    assert (parsed.starts_at, parsed.ends_at) == (starts, ends)


@pytest.mark.parametrize("model", _EVENT_MODELS, ids=["create", "update"])
@pytest.mark.parametrize(
    "delta", [timedelta(0), -timedelta(minutes=1)], ids=["equal", "reversed"]
)
def test_event_non_increasing_times_remain_invalid(model, delta):
    starts = datetime(2035, 1, 1, 10, tzinfo=UTC)
    with pytest.raises(ValidationError):
        model.model_validate(_event_schema_payload(model, starts, starts + delta))


@pytest.mark.parametrize(
    "payload",
    [
        {"starts_at": "2035-01-01T10:00:00"},
        {"ends_at": "2035-01-01T11:00:00"},
        {"starts_at": None, "ends_at": "2035-01-01T11:00:00"},
        {"starts_at": "2035-01-01T10:00:00", "ends_at": None},
        {"starts_at": None, "ends_at": None},
    ],
)
def test_event_public_update_still_requires_two_non_null_times(payload):
    with pytest.raises(ValidationError):
        schemas.EventUpdate.model_validate(payload)


def test_event_title_only_update_preserves_partial_fields():
    parsed = schemas.EventUpdate.model_validate({"title": "Renamed"})
    assert parsed.model_fields_set == {"title"}


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["overlong-title", "mixed-times"])
async def test_event_create_invalid_request_returns_422(
    async_client, user_factory, case
):
    password = "EventFix123!"
    teacher = await user_factory(
        role="teacher",
        hashed_password=await get_password_hash(password),
        is_active=True,
    )
    headers = await _login(async_client, teacher.email, password)
    payload = {
        "title": "Invalid request",
        "starts_at": "2035-01-01T10:00:00+00:00",
        "ends_at": "2035-01-01T11:00:00+00:00",
    }
    if case == "overlong-title":
        payload["title"] = "x" * 513
    else:
        payload["starts_at"] = "2035-01-01T10:00:00"
    response = await async_client.post("/events", headers=headers, json=payload)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"title": "x" * 513},
        {"starts_at": "2035-01-01T10:00:00"},
        {"ends_at": "2035-01-01T11:00:00"},
        {"starts_at": None, "ends_at": "2035-01-01T11:00:00+00:00"},
        {"starts_at": "2035-01-01T10:00:00+00:00", "ends_at": None},
        {
            "starts_at": "2035-01-01T10:00:00",
            "ends_at": "2035-01-01T11:00:00+00:00",
        },
        {
            "starts_at": "2035-01-01T10:00:00+00:00",
            "ends_at": "2035-01-01T11:00:00",
        },
    ],
)
async def test_event_invalid_patch_preserves_persisted_state(
    async_client, db_session, user_factory, monkeypatch, payload
):
    password = "EventFix123!"
    teacher = await user_factory(
        role="teacher",
        hashed_password=await get_password_hash(password),
        is_active=True,
    )
    record = models.Event(
        title="Before",
        starts_at=datetime(2035, 1, 1, 10, tzinfo=UTC),
        ends_at=datetime(2035, 1, 1, 11, tzinfo=UTC),
        created_by=teacher.id,
        is_active=True,
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)
    before = (record.title, record.starts_at, record.ends_at)
    headers = await _login(async_client, teacher.email, password)
    checker = AsyncMock(spec=PermissionChecker)
    checker.check_permission.return_value = True
    monkeypatch.setitem(
        app.dependency_overrides, get_permission_checker, lambda: checker
    )

    response = await async_client.patch(
        f"/events/{record.id}", headers=headers, json=payload
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    checker.check_permission.assert_not_awaited()
    await db_session.refresh(record)
    assert (record.title, record.starts_at, record.ends_at) == before


@pytest.mark.asyncio
async def test_event_title_only_http_patch_preserves_persisted_times(
    async_client, db_session, user_factory, monkeypatch
):
    password = "EventFix123!"
    teacher = await user_factory(
        role="teacher",
        hashed_password=await get_password_hash(password),
        is_active=True,
    )
    record = models.Event(
        title="Before",
        starts_at=datetime(2035, 1, 1, 10, tzinfo=UTC),
        ends_at=datetime(2035, 1, 1, 11, tzinfo=UTC),
        created_by=teacher.id,
        is_active=True,
    )
    db_session.add(record)
    await db_session.commit()
    await db_session.refresh(record)
    before = (record.starts_at, record.ends_at)
    headers = await _login(async_client, teacher.email, password)
    checker = AsyncMock(spec=PermissionChecker)
    checker.check_permission.return_value = True
    monkeypatch.setitem(
        app.dependency_overrides, get_permission_checker, lambda: checker
    )

    response = await async_client.patch(
        f"/events/{record.id}", headers=headers, json={"title": "After"}
    )
    assert response.status_code == status.HTTP_200_OK
    checker.check_permission.assert_awaited_once_with(
        resource_type="event",
        resource_id=str(record.id),
        permission="edit",
        user_id=str(teacher.id),
    )
    await db_session.refresh(record)
    assert record.title == "After"
    assert (record.starts_at, record.ends_at) == before
