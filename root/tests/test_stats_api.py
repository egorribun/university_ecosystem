import json
from datetime import datetime, timedelta, timezone

import pytest

from app.auth.security import get_password_hash
from app.deps import cache as cache_module
from app.models import models
from app.services import attendance_tokens


async def _login(async_client, email: str, password: str) -> dict[str, str]:
    response = await async_client.post(
        "/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "path",
    ["/stats/attendance", "/stats/grades", "/stats/participation"],
)
async def test_stats_requires_auth(async_client, path):
    response = await async_client.get(path)
    assert response.status_code == 401


@pytest.mark.anyio
async def test_attendance_stats_returns_expected_payload(
    async_client, db_session, user_factory
):
    now = datetime.now(timezone.utc)
    admin = await user_factory(role="admin")
    password = "StatsPass123!"
    hashed = get_password_hash(password)
    student = await user_factory(hashed_password=hashed, is_active=True)

    current_attended = models.Event(
        title="Functional Analysis",
        description="Lecture",
        location="Auditorium A",
        event_type="lecture",
        starts_at=now - timedelta(days=5),
        ends_at=now - timedelta(days=5) + timedelta(hours=2),
        created_by=admin.id,
        is_active=True,
    )
    current_attended_2 = models.Event(
        title="Modern Physics",
        description="Seminar",
        location="Room 204",
        event_type="seminar",
        starts_at=now - timedelta(days=2),
        ends_at=now - timedelta(days=2) + timedelta(hours=3),
        created_by=admin.id,
        is_active=True,
    )
    current_missed = models.Event(
        title="Statistics",
        description="Workshop",
        location="Room 101",
        event_type="workshop",
        starts_at=now - timedelta(days=8),
        ends_at=now - timedelta(days=8) + timedelta(hours=2),
        created_by=admin.id,
        is_active=True,
    )
    previous_attended = models.Event(
        title="Linear Algebra",
        description="Lecture",
        location="Auditorium B",
        event_type="lecture",
        starts_at=now - timedelta(days=35),
        ends_at=now - timedelta(days=35) + timedelta(hours=2),
        created_by=admin.id,
        is_active=True,
    )
    previous_missed = models.Event(
        title="Computer Science",
        description="Seminar",
        location="Lab 5",
        event_type="seminar",
        starts_at=now - timedelta(days=50),
        ends_at=now - timedelta(days=50) + timedelta(hours=2),
        created_by=admin.id,
        is_active=True,
    )

    db_session.add_all(
        [
            current_attended,
            current_attended_2,
            current_missed,
            previous_attended,
            previous_missed,
        ]
    )
    await db_session.commit()

    attendances = []
    for event_id, registered_at in [
        (current_attended.id, now - timedelta(days=5, hours=1)),
        (current_attended_2.id, now - timedelta(days=2, hours=2)),
        (previous_attended.id, now - timedelta(days=34)),
    ]:
        secret = attendance_tokens.generate_secret()
        attendances.append(
            models.EventAttendance(
                user_id=student.id,
                event_id=event_id,
                registered_at=registered_at,
                qr_secret=secret,
                qr_hmac=attendance_tokens.compute_secret_hmac(secret),
            )
        )
    db_session.add_all(attendances)
    await db_session.commit()

    headers = await _login(async_client, student.email, password)

    response = await async_client.get("/stats/attendance", headers=headers)
    assert response.status_code == 200
    payload = response.json()

    assert payload["present"] == 2
    assert payload["total"] == 3
    assert payload["percent"] == pytest.approx(66.67, rel=1e-2)
    assert payload["trend"] == pytest.approx(16.67, rel=1e-2)
    assert payload["period_key"] == "30d"
    assert payload["period_label"] == "Last 30 days"
    assert len(payload["recent"]) == 2
    assert payload["recent"][0]["status"] == "present"
    assert payload["recent"][0]["course"] == "Modern Physics"


@pytest.mark.anyio
async def test_attendance_stats_period_label_localized(async_client, user_factory):
    password = "LocalizedPass123!"
    hashed = get_password_hash(password)
    student = await user_factory(hashed_password=hashed, is_active=True)

    headers = await _login(async_client, student.email, password)
    headers["Accept-Language"] = "ru"

    response = await async_client.get("/stats/attendance", headers=headers)
    assert response.status_code == 200
    payload = response.json()

    assert payload["period_key"] == "30d"
    assert payload["period_label"] == "За последние 30 дней"


@pytest.mark.anyio
async def test_grade_stats_parse_notifications(async_client, db_session, user_factory):
    now = datetime.now(timezone.utc)
    password = "GradesPass456!"
    hashed = get_password_hash(password)
    student = await user_factory(hashed_password=hashed, is_active=True)

    current_grade_one = models.Notification(
        user_id=student.id,
        title="Physics",
        type="grade",
        body=json.dumps(
            {
                "course": "Physics",
                "score": 5,
                "max": 5,
                "date": (now - timedelta(days=4)).isoformat(),
            }
        ),
        created_at=now - timedelta(days=4),
    )
    current_grade_two = models.Notification(
        user_id=student.id,
        title="Chemistry",
        type="grade",
        body=json.dumps(
            {
                "course": "Chemistry",
                "score": 4.5,
                "max": 5,
                "date": (now - timedelta(days=2)).isoformat(),
            }
        ),
        created_at=now - timedelta(days=2),
    )
    previous_grade = models.Notification(
        user_id=student.id,
        title="History",
        type="grade",
        body=json.dumps({"course": "History", "score": 3, "max": 5}),
        created_at=now - timedelta(days=45),
    )

    db_session.add_all([current_grade_one, current_grade_two, previous_grade])
    await db_session.commit()

    headers = await _login(async_client, student.email, password)
    response = await async_client.get("/stats/grades", headers=headers)
    assert response.status_code == 200
    payload = response.json()

    assert payload["average"] == pytest.approx(4.75, rel=1e-3)
    assert payload["scale"] == "5"
    assert payload["trend"] == pytest.approx(1.75, rel=1e-3)
    assert len(payload["recent"]) == 2
    assert {item["course"] for item in payload["recent"]} == {"Physics", "Chemistry"}


@pytest.mark.anyio
async def test_participation_stats_summarize_events(
    async_client, db_session, user_factory
):
    now = datetime.now(timezone.utc)
    admin = await user_factory(role="admin")
    password = "Participate789!"
    hashed = get_password_hash(password)
    student = await user_factory(hashed_password=hashed, is_active=True)

    event_one = models.Event(
        title="Hackathon",
        description="Community project",
        location="Innovation Hub",
        event_type="club",
        starts_at=now - timedelta(days=6),
        ends_at=now - timedelta(days=6) + timedelta(hours=4),
        created_by=admin.id,
        is_active=True,
    )
    event_two = models.Event(
        title="Volunteer Day",
        description="City cleanup",
        location="Downtown",
        event_type="volunteer",
        starts_at=now - timedelta(days=3),
        ends_at=now - timedelta(days=3) + timedelta(hours=5),
        created_by=admin.id,
        is_active=True,
    )
    previous_event = models.Event(
        title="STEM Fair",
        description="Science exhibits",
        location="Campus Hall",
        event_type="club",
        starts_at=now - timedelta(days=40),
        ends_at=now - timedelta(days=40) + timedelta(hours=3),
        created_by=admin.id,
        is_active=True,
    )

    db_session.add_all([event_one, event_two, previous_event])
    await db_session.commit()

    attendances = []
    for event_id, registered_at in [
        (event_one.id, now - timedelta(days=6, hours=1)),
        (event_two.id, now - timedelta(days=3, hours=2)),
        (previous_event.id, now - timedelta(days=39)),
    ]:
        secret = attendance_tokens.generate_secret()
        attendances.append(
            models.EventAttendance(
                user_id=student.id,
                event_id=event_id,
                registered_at=registered_at,
                qr_secret=secret,
                qr_hmac=attendance_tokens.compute_secret_hmac(secret),
            )
        )
    db_session.add_all(attendances)
    await db_session.commit()

    headers = await _login(async_client, student.email, password)
    response = await async_client.get("/stats/participation", headers=headers)
    assert response.status_code == 200
    payload = response.json()

    assert payload["events"] == 2
    assert payload["hours"] == pytest.approx(9.0, rel=1e-3)
    assert payload["groups"] == 2
    assert payload["trend"] == 1
    assert len(payload["recent"]) == 2
    assert {item["title"] for item in payload["recent"]} == {
        "Hackathon",
        "Volunteer Day",
    }


@pytest.mark.anyio
async def test_attendance_stats_uses_cache(
    async_client, fake_cache, user_factory, monkeypatch
):
    password = "CachePass123!"
    hashed = get_password_hash(password)
    student = await user_factory(hashed_password=hashed, is_active=True)

    headers = await _login(async_client, student.email, password)

    calls = {"get": 0, "set": 0}
    original_get = cache_module.RedisCache.get
    original_set = cache_module.RedisCache.set

    async def tracked_get(self, key):  # type: ignore[override]
        calls["get"] += 1
        return await original_get(self, key)

    async def tracked_set(self, key, payload, ttl=None):  # type: ignore[override]
        calls["set"] += 1
        return await original_set(self, key, payload, ttl=ttl)

    monkeypatch.setattr(cache_module.RedisCache, "get", tracked_get)
    monkeypatch.setattr(cache_module.RedisCache, "set", tracked_set)

    first = await async_client.get("/stats/attendance", headers=headers)
    assert first.status_code == 200

    second = await async_client.get("/stats/attendance", headers=headers)
    assert second.status_code == 200
    assert second.json() == first.json()

    assert calls["get"] == 2
    assert calls["set"] == 1


@pytest.mark.anyio
async def test_registering_for_event_invalidates_stats_cache(
    async_client,
    fake_cache,
    user_factory,
    db_session,
    monkeypatch,
):
    now = datetime.now(timezone.utc)
    admin = await user_factory(role="admin")
    password = "CacheInvalidate456!"
    hashed = get_password_hash(password)
    student = await user_factory(hashed_password=hashed, is_active=True)

    event = models.Event(
        title="New Seminar",
        description="Discussion",
        location="Hall 1",
        event_type="seminar",
        starts_at=now + timedelta(hours=1),
        ends_at=now + timedelta(hours=3),
        created_by=admin.id,
        is_active=True,
    )
    db_session.add(event)
    await db_session.commit()

    headers = await _login(async_client, student.email, password)

    invalidated: list[tuple[str, ...]] = []
    original_invalidate = cache_module.RedisCache.invalidate

    async def tracked_invalidate(self, *keys):  # type: ignore[override]
        invalidated.append(keys)
        return await original_invalidate(self, *keys)

    monkeypatch.setattr(cache_module.RedisCache, "invalidate", tracked_invalidate)

    response = await async_client.post(
        "/events/attendance",
        json={"event_id": event.id},
        headers=headers,
    )
    assert response.status_code == 200

    flattened = [key for call in invalidated for key in call]
    assert any(key.startswith("stats:attendance") for key in flattened)
    assert any(key.startswith("stats:participation") for key in flattened)
