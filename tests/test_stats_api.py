import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

import app.models as models
from app.auth.security import get_password_hash
from app.core.config import settings
from app.deps import cache as cache_module
from app.services import attendance_tokens, stats_cache


async def _login(async_client, email: str, password: str) -> None:
    response = await async_client.post(
        "/auth/login",
        data={"username": email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    ["/stats/attendance", "/stats/grades", "/stats/participation"],
)
async def test_stats_requires_auth(async_client, path):
    response = await async_client.get(path)
    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/stats/attendance", "/stats/summary"])
async def test_attendance_stats_returns_expected_payload(
    async_client, db_session, user_factory, monkeypatch, path
):
    monkeypatch.setattr(settings, "campus_timezone", "Asia/Kathmandu")
    now = datetime.now(UTC)
    admin = await user_factory(role="admin")
    password = "StatsPass123!"
    hashed = await get_password_hash(password)
    student = await user_factory(hashed_password=hashed, is_active=True)

    def build_event(
        title: str, delta: timedelta, duration_hours: int = 2
    ) -> models.Event:
        starts_at = now - delta
        return models.Event(
            title=title,
            description=f"Session for {title}",
            location="Auditorium A",
            event_type="lecture",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=duration_hours),
            created_by=admin.id,
            is_active=True,
        )

    current_attended_events = [
        build_event("Functional Analysis", timedelta(days=5)),
        build_event("Modern Physics", timedelta(days=4)),
        build_event("Organic Chemistry", timedelta(days=3)),
        build_event("Biology Lab", timedelta(days=2)),
        build_event("Contemporary History", timedelta(days=1)),
        build_event("Philosophy of Science", timedelta(hours=12)),
    ]
    current_missed = build_event("Applied Statistics", timedelta(days=8))
    previous_attended = build_event("Linear Algebra", timedelta(days=35))
    previous_missed = build_event("Computer Science", timedelta(days=50))

    db_session.add_all(
        [*current_attended_events, current_missed, previous_attended, previous_missed]
    )
    await db_session.commit()

    attendances = []
    for event in current_attended_events:
        secret = attendance_tokens.generate_secret()
        attendances.append(
            models.EventAttendance(
                user_id=student.id,
                event_id=event.id,
                registered_at=event.starts_at - timedelta(minutes=30),
                qr_secret=secret,
                qr_hmac=attendance_tokens.compute_secret_hmac(secret),
            )
        )

    secret = attendance_tokens.generate_secret()
    attendances.append(
        models.EventAttendance(
            user_id=student.id,
            event_id=previous_attended.id,
            registered_at=previous_attended.starts_at - timedelta(hours=1),
            qr_secret=secret,
            qr_hmac=attendance_tokens.compute_secret_hmac(secret),
        )
    )
    db_session.add_all(attendances)
    await db_session.commit()

    await _login(async_client, student.email, password)

    response = await async_client.get(path)
    assert response.status_code == 200
    payload = response.json()
    if path == "/stats/summary":
        payload = payload["attendance"]

    # Attendance == registration: 6 of the 7 active events of the current window,
    # against 1 of 2 in the previous window (50 %).
    assert type(payload.get("streak_days")) is int
    assert payload["present"] == 6
    assert payload["total"] == 7
    assert payload["percent"] == pytest.approx(85.71, rel=1e-3)
    assert payload["trend"] == pytest.approx(35.71, rel=1e-3)
    assert payload["period_key"] == "30d"
    assert payload["period_label"] == "Last 30 days"
    assert len(payload["recent"]) == 5
    assert [entry["status"] for entry in payload["recent"]] == ["present"] * 5
    assert payload["recent"][0]["course"] == "Philosophy of Science"
    assert payload["recent"][4]["course"] == "Modern Physics"

    expected_daily: dict[str, dict[str, int]] = {}
    for event in [*current_attended_events, current_missed]:
        day = event.starts_at.astimezone(ZoneInfo("Asia/Kathmandu")).date().isoformat()
        counts = expected_daily.setdefault(day, {"registered": 0, "total": 0})
        counts["total"] += 1
        counts["registered"] += int(event in current_attended_events)
    assert payload.get("daily") == [
        {"date": day, **counts} for day, counts in sorted(expected_daily.items())
    ]


@pytest.mark.asyncio
async def test_attendance_stats_period_label_localized(async_client, user_factory):
    password = "LocalizedPass123!"
    hashed = await get_password_hash(password)
    student = await user_factory(hashed_password=hashed, is_active=True)

    await _login(async_client, student.email, password)
    headers = {"Accept-Language": "ru"}

    response = await async_client.get("/stats/attendance", headers=headers)
    assert response.status_code == 200
    payload = response.json()

    assert payload["period_key"] == "30d"
    assert payload["period_label"] == "За последние 30 дней"


@pytest.mark.asyncio
async def test_grade_stats_aggregate_grades_table(
    async_client, db_session, user_factory
):
    now = datetime.now(UTC)
    password = "GradesPass456!"
    hashed = await get_password_hash(password)
    student = await user_factory(hashed_password=hashed, is_active=True)

    db_session.add_all(
        [
            models.Grade(
                student_id=student.id,
                subject=subject,
                score=score,
                created_at=now - timedelta(days=days),
            )
            for subject, score, days in [
                ("Physics", 5, 4),
                ("Chemistry", 4.5, 2),
                ("History", 3, 3),
                # previous window (31-60 days ago): average 4.0
                ("Algebra", 4, 40),
            ]
        ]
    )
    await db_session.commit()

    await _login(async_client, student.email, password)
    response = await async_client.get("/stats/grades")
    assert response.status_code == 200
    payload = response.json()

    # (5 + 4.5 + 3) / 3 = 4.17 now vs 4.0 before.
    assert payload["average"] == pytest.approx(4.17, rel=1e-2)
    assert payload["total_grades"] == 3
    assert payload["trend"] == pytest.approx(0.17, abs=1e-2)
    assert payload["scale"] == "5"
    assert [item["course"] for item in payload["recent"]] == [
        "Chemistry",
        "History",
        "Physics",
    ]


@pytest.mark.asyncio
async def test_participation_stats_summarize_events(
    async_client, db_session, user_factory
):
    now = datetime.now(UTC)
    admin = await user_factory(role="admin")
    password = "Participate789!"
    hashed = await get_password_hash(password)
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

    await _login(async_client, student.email, password)
    response = await async_client.get("/stats/participation")
    assert response.status_code == 200
    payload = response.json()

    assert payload["events"] == 2
    assert payload["hours"] == pytest.approx(9.0, rel=1e-3)  # 4 h + 5 h
    assert payload["groups"] == 2  # club + volunteer
    assert payload["trend"] == 1  # 2 events now vs 1 in the previous window
    assert len(payload["recent"]) == 2
    assert {item["title"] for item in payload["recent"]} == {
        "Hackathon",
        "Volunteer Day",
    }


@pytest.mark.asyncio
async def test_attendance_stats_uses_cache(
    async_client, fake_cache, user_factory, monkeypatch
):
    from app.repositories.user_stats_repository import UserStatsRepository
    from app.services.stats_fill_fence import StatsFillFence
    from app.services.user import analytics_service as analytics_module

    password = "CachePass123!"
    hashed = await get_password_hash(password)
    student = await user_factory(hashed_password=hashed, is_active=True)
    await _login(async_client, student.email, password)

    # The request fixture is a RedisCache subclass. Bind the real adapter to
    # an exact RedisCache using the request cache's in-memory Redis client.
    request_caches = []

    def fixture_fence(cache):
        assert isinstance(cache, cache_module.RedisCache)
        request_caches.append(cache)
        exact_cache = cache_module.RedisCache(url="unused", default_ttl=180)
        exact_cache._client = cache._client
        return StatsFillFence(exact_cache)

    monkeypatch.setattr(analytics_module, "StatsFillFence", fixture_fence)
    calls = 0
    original_read = UserStatsRepository.get_attendance_stats_raw

    async def tracked_read(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        return await original_read(self, *args, **kwargs)

    monkeypatch.setattr(UserStatsRepository, "get_attendance_stats_raw", tracked_read)

    first = await async_client.get("/stats/attendance")
    assert first.status_code == 200
    key = stats_cache.make_stats_cache_key("attendance", student.id, "30d")
    assert len(request_caches) == 1
    request_cache = request_caches[0]
    entry = await request_cache.get(key)
    assert entry is not None and isinstance(entry.payload, dict)
    assert entry.payload == {
        key: value for key, value in first.json().items() if key != "period_label"
    }
    assert entry.ttl_seconds == float(settings.stats_cache_ttl_seconds)
    assert calls == 1

    second = await async_client.get("/stats/attendance")
    assert second.status_code == 200
    assert second.json() == first.json()
    assert second.headers["etag"] == first.headers["etag"]
    assert calls == 1

    bypass = await async_client.get("/stats/attendance?skip_cache=true")
    assert bypass.status_code == 200
    assert bypass.json() == first.json()
    assert calls == 2
    after = await request_cache.get(key)
    assert after is not None
    assert (after.payload, after.etag, after.stored_at, after.ttl_seconds) == (
        entry.payload,
        entry.etag,
        entry.stored_at,
        entry.ttl_seconds,
    )


@pytest.mark.asyncio
async def test_registering_for_event_invalidates_stats_cache(
    async_client,
    fake_cache,
    user_factory,
    db_session,
    monkeypatch,
):
    now = datetime.now(UTC)
    admin = await user_factory(role="admin")
    password = "CacheInvalidate456!"
    hashed = await get_password_hash(password)
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

    await _login(async_client, student.email, password)

    invalidated: list[tuple[str, ...]] = []
    original_invalidate = fake_cache.invalidate

    async def tracked_invalidate(*keys):
        invalidated.append(keys)
        return await original_invalidate(*keys)

    monkeypatch.setattr(fake_cache, "invalidate", tracked_invalidate)

    response = await async_client.post(
        "/events/attendance",
        json={"event_id": str(event.id)},
    )
    assert response.status_code == 200

    flattened = [key for call in invalidated for key in call]
    assert any(key.startswith("stats:attendance") for key in flattened)
    assert any(key.startswith("stats:participation") for key in flattened)


@pytest.mark.asyncio
async def test_stats_cache_invalidation_includes_default_and_custom_periods(fake_cache):
    user_id = 77
    kind = "attendance"

    await fake_cache.set(
        stats_cache.make_stats_cache_key(kind, user_id, "default"),
        {"value": "default"},
    )
    await fake_cache.set(
        stats_cache.make_stats_cache_key(kind, user_id, "7d"),
        {"value": "custom"},
    )

    assert (
        await stats_cache.get_cached_stats(
            cache=fake_cache,
            kind=kind,
            user_id=user_id,
            period_key="default",
        )
        is not None
    )
    assert (
        await stats_cache.get_cached_stats(
            cache=fake_cache,
            kind=kind,
            user_id=user_id,
            period_key="7d",
        )
        is not None
    )

    await stats_cache.invalidate_user_stats_cache(
        cache=fake_cache,
        user_ids=user_id,
        kinds=(kind,),
        period_keys=("7D",),
    )

    assert (
        await stats_cache.get_cached_stats(
            cache=fake_cache,
            kind=kind,
            user_id=user_id,
            period_key="default",
        )
        is None
    )
    assert (
        await stats_cache.get_cached_stats(
            cache=fake_cache,
            kind=kind,
            user_id=user_id,
            period_key="7d",
        )
        is None
    )


@pytest.mark.asyncio
async def test_activity_populated_summary_combines_persisted_sections(
    async_client, db_session, user_factory, monkeypatch
):
    """The R40 summary combines the student's real rows for both locales."""
    from app.services.user import analytics_service

    now = datetime(2026, 11, 14, 12, tzinfo=UTC)

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now.astimezone(tz) if tz is not None else now.replace(tzinfo=None)

    monkeypatch.setattr(analytics_service, "datetime", FixedDatetime)
    monkeypatch.setattr(settings, "campus_timezone", "UTC")
    password = f"Aa1!{uuid.uuid4().hex}"
    creator = await user_factory(role="admin")
    student = await user_factory(hashed_password=await get_password_hash(password))
    other = await user_factory()
    events = [
        models.Event(
            title=f"Synthetic event {days}",
            starts_at=now - timedelta(days=days),
            ends_at=now - timedelta(days=days) + timedelta(hours=2),
            event_type="lecture",
            created_by=creator.id,
            is_active=True,
        )
        for days in (2, 1, 100)
    ]
    db_session.add_all(events)
    await db_session.flush()
    for event, owner in zip(events, (student, other, student), strict=True):
        token = attendance_tokens.generate_secret()
        db_session.add(
            models.EventAttendance(
                user_id=owner.id,
                event_id=event.id,
                registered_at=event.starts_at - timedelta(minutes=30),
                qr_secret=token,
                qr_hmac=attendance_tokens.compute_secret_hmac(token),
            )
        )
    db_session.add_all(
        [
            models.Grade(
                student_id=owner.id,
                subject=f"Synthetic subject {days}",
                score=score,
                created_at=now - timedelta(days=days),
            )
            for owner, score, days in (
                (student, 4.5, 2),
                (student, 4.0, 100),
                (other, 1.0, 2),
            )
        ]
    )
    await db_session.commit()
    await _login(async_client, student.email, password)

    for locale, label in (("ru", "За последние 90 дней"), ("en", "Last 90 days")):
        response = await async_client.get(
            "/stats/summary",
            params={"period": "90d", "skip_cache": "true"},
            headers={"Accept-Language": locale},
        )
        assert response.status_code == 200
        assert response.headers["content-language"] == locale
        payload = response.json()
        attendance = payload["attendance"]
        grades = payload["grades"]
        participation = payload["participation"]
        for section in (attendance, grades, participation):
            assert section["period_key"] == "90d"
            assert section["period_label"] == label
            assert len(section["recent"]) == 1
        assert (
            attendance["present"],
            attendance["total"],
            attendance["percent"],
            attendance["trend"],
        ) == (1, 2, 50.0, -50.0)
        assert attendance["daily"] == [
            {"date": "2026-11-12", "registered": 1, "total": 1},
            {"date": "2026-11-13", "registered": 0, "total": 1},
        ]
        assert (
            grades["average"],
            grades["total_grades"],
            grades["scale"],
            grades["trend"],
        ) == (4.5, 1, "5", 0.5)
        assert (
            participation["events"],
            participation["hours"],
            participation["groups"],
            participation["trend"],
        ) == (1, 2.0, 1, 0)
        # The UI merges the ISO date prefix of all three recent lists.
        recent_dates = [
            item["date"][:10]
            for section in (attendance, grades, participation)
            for item in section["recent"]
        ]
        assert recent_dates == ["2026-11-12"] * 3
        assert attendance["percent"] - attendance["trend"] == 100.0
        assert grades["average"] - grades["trend"] == 4.0
        assert participation["events"] - participation["trend"] == 1
