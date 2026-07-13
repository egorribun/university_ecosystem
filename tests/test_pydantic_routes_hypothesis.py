"""Hypothesis-based API fuzzing tests for FastAPI routes.

Generates structurally correct but extreme inputs to ensure that endpoints return
proper 2xx/4xx/422 status codes and NEVER crash with 500.
"""

from __future__ import annotations

import os
import uuid
import datetime
import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings, HealthCheck
import hypothesis.strategies as st

# Set environment variables before importing app (but do NOT override DATABASE_URL)
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("SECRET_KEY", "fuzzing-placeholder-secret-key-32-chars-long")

# Fix httpx loopback address parsing issue in case it leaks here
for proxy_key in ["no_proxy", "NO_PROXY"]:
    if proxy_key in os.environ:
        os.environ[proxy_key] = ",".join(
            item for item in os.environ[proxy_key].split(",") if ":" not in item
        )

from app.main import app
from app.auth.security import _mint_pure_jwt


@pytest.fixture(scope="module")
def client_with_lifespan():
    """Runs startup/shutdown lifespan events to initialize Dishka container."""
    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="module")
def headers():
    # Mint an admin JWT to bypass authentication constraints
    admin_token = _mint_pure_jwt(subject=uuid.uuid4(), extra_claims={"role": "admin"})
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.mark.filterwarnings("ignore:.*HS256 is not recommended.*")
@settings(
    max_examples=15,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)
@given(
    starts_at=st.datetimes(),
    ends_at=st.datetimes(),
    title=st.text(min_size=1, max_size=100),
    description=st.one_of(st.none(), st.text(max_size=1000)),
    location=st.text(max_size=200),
    max_participants=st.one_of(st.none(), st.integers(min_value=1, max_value=10000)),
)
def test_fuzz_create_event(
    client_with_lifespan,
    headers,
    starts_at: datetime.datetime,
    ends_at: datetime.datetime,
    title: str,
    description: str | None,
    location: str,
    max_participants: int | None,
) -> None:
    if ends_at <= starts_at:
        ends_at = starts_at + datetime.timedelta(seconds=1)
    payload = {
        "title": title,
        "description": description,
        "location": location,
        "starts_at": starts_at.isoformat(),
        "ends_at": ends_at.isoformat(),
        "max_participants": max_participants,
    }
    response = client_with_lifespan.post("/api/v1/events", json=payload, headers=headers)
    assert response.status_code != 500


@pytest.mark.filterwarnings("ignore:.*HS256 is not recommended.*")
@settings(
    max_examples=15,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)
@given(
    starts_at=st.one_of(st.none(), st.datetimes()),
    ends_at=st.one_of(st.none(), st.datetimes()),
    title=st.one_of(st.none(), st.text(min_size=1, max_size=100)),
    description=st.one_of(st.none(), st.text(max_size=1000)),
    location=st.one_of(st.none(), st.text(max_size=200)),
)
def test_fuzz_update_event(
    client_with_lifespan,
    headers,
    starts_at: datetime.datetime | None,
    ends_at: datetime.datetime | None,
    title: str | None,
    description: str | None,
    location: str | None,
) -> None:
    payload = {}
    if title is not None:
        payload["title"] = title
    if description is not None:
        payload["description"] = description
    if location is not None:
        payload["location"] = location

    # The validator: "Provide both start and end times for the event"
    if starts_at is not None or ends_at is not None:
        if starts_at is None:
            starts_at = datetime.datetime.now()
        if ends_at is None or ends_at <= starts_at:
            ends_at = starts_at + datetime.timedelta(seconds=1)
        payload["starts_at"] = starts_at.isoformat()
        payload["ends_at"] = ends_at.isoformat()

    event_id = str(uuid.uuid4())
    response = client_with_lifespan.patch(f"/api/v1/events/{event_id}", json=payload, headers=headers)
    assert response.status_code != 500


@pytest.mark.filterwarnings("ignore:.*HS256 is not recommended.*")
@settings(
    max_examples=15,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)
@given(
    event_id=st.uuids(),
)
def test_fuzz_event_attendance(client_with_lifespan, headers, event_id: uuid.UUID) -> None:
    payload = {
        "event_id": str(event_id),
    }
    response = client_with_lifespan.post("/api/v1/events/attendance", json=payload, headers=headers)
    assert response.status_code != 500


@pytest.mark.filterwarnings("ignore:.*HS256 is not recommended.*")
@settings(
    max_examples=15,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)
@given(
    name=st.one_of(st.none(), st.text(max_size=100)),
    type=st.sampled_from(["direct", "group"]),
    participant_ids=st.lists(st.uuids(), min_size=1, max_size=5),
)
def test_fuzz_create_chat(
    client_with_lifespan,
    headers,
    name: str | None,
    type: str,
    participant_ids: list[uuid.UUID],
) -> None:
    payload = {
        "name": name,
        "type": type,
        "participant_ids": [str(p_id) for p_id in participant_ids],
    }
    response = client_with_lifespan.post("/api/v1/chats", json=payload, headers=headers)
    assert response.status_code != 500


@pytest.mark.filterwarnings("ignore:.*HS256 is not recommended.*")
@settings(
    max_examples=15,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)
@given(
    full_name=st.one_of(st.none(), st.text(max_size=100)),
    email=st.one_of(st.none(), st.emails()),
    timezone=st.one_of(st.none(), st.sampled_from(["UTC", "Europe/London", "America/New_York"])),
    telegram=st.one_of(st.none(), st.text(max_size=50)),
    about=st.one_of(st.none(), st.text(max_size=1000)),
)
def test_fuzz_update_profile(
    client_with_lifespan,
    headers,
    full_name: str | None,
    email: str | None,
    timezone: str | None,
    telegram: str | None,
    about: str | None,
) -> None:
    payload = {}
    if full_name is not None:
        payload["full_name"] = full_name
    if email is not None:
        payload["email"] = email
    if timezone is not None:
        payload["timezone"] = timezone
    if telegram is not None:
        payload["telegram"] = telegram
    if about is not None:
        payload["about"] = about

    response = client_with_lifespan.patch("/api/v1/users/me", json=payload, headers=headers)
    assert response.status_code != 500


@pytest.mark.filterwarnings("ignore:.*HS256 is not recommended.*")
@settings(
    max_examples=15,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)
@given(
    current_password=st.text(min_size=1, max_size=100),
    new_password=st.text(min_size=8, max_size=100),
)
def test_fuzz_change_password(
    client_with_lifespan,
    headers,
    current_password: str,
    new_password: str,
) -> None:
    payload = {
        "current_password": current_password,
        "new_password": new_password,
    }
    response = client_with_lifespan.put("/api/v1/users/me/password", json=payload, headers=headers)
    assert response.status_code != 500
