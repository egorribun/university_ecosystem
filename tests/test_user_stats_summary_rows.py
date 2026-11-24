from __future__ import annotations

import itertools
import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy.dialects import postgresql, sqlite

import app.models as models
from app.repositories.user_stats_repository import UserStatsRepository, _as_utc
from app.services import attendance_tokens


def norm(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def attendance_key(row):
    return (
        norm(row.starts_at),
        row.title,
        norm(row.registered_at) if row.registered_at else None,
        bool(row.is_registered),
    )


def grade_key(row):
    return norm(row.created_at), row.subject, float(row.score)


def participation_key(row):
    return (
        row.event_id,
        row.title,
        row.event_type,
        norm(row.starts_at),
        norm(row.ends_at),
    )


class CountingDB:
    def __init__(self, session):
        self.session = session
        self.statements = []

    async def execute(self, statement):
        self.statements.append(statement)
        return await self.session.execute(statement)


def test_timezone_normalization():
    naive = datetime(2026, 11, 24, 12)
    assert _as_utc(naive) == naive.replace(tzinfo=UTC)
    local = naive.replace(tzinfo=timezone(timedelta(hours=3)))
    assert _as_utc(local) == datetime(2026, 11, 24, 9, tzinfo=UTC)


@pytest.mark.asyncio
async def test_summary_rows_empty_and_invalid_kinds(db_session):
    database = CountingDB(db_session)
    repo = UserStatsRepository(database)
    now = datetime(2026, 11, 24, 12, tzinfo=UTC)
    args = (uuid.uuid4(), now - timedelta(days=30), now - timedelta(days=60), now)
    empty = await repo.get_summary_rows(*args, kinds=[])
    assert (empty.attendance, empty.grades, empty.participation) == ([], [], [])
    assert not database.statements
    with pytest.raises(ValueError):
        await repo.get_summary_rows(*args, kinds=["attendance", "unexpected"])
    assert not database.statements
    empty_data = await repo.get_summary_rows(
        *args, kinds=["attendance", "grades", "participation"]
    )
    assert (empty_data.attendance, empty_data.grades, empty_data.participation) == (
        [],
        [],
        [],
    )
    assert len(database.statements) == 1


@pytest.mark.asyncio
async def test_summary_all_kind_subsets_match_existing_rows(db_session, user_factory):
    now = datetime(2026, 11, 24, 12, tzinfo=UTC)
    window = now - timedelta(days=30)
    previous = now - timedelta(days=60)
    owner = await user_factory()
    other = await user_factory()
    creator = await user_factory(role="admin")

    def event(title, when, active=True):
        return models.Event(
            title=title,
            starts_at=when,
            ends_at=when + timedelta(hours=1),
            event_type="lecture",
            created_by=creator.id,
            is_active=active,
        )

    events = [
        event("old user history", previous - timedelta(days=2)),
        event("previous boundary", previous),
        event("window boundary", window),
        event("other registration", now - timedelta(days=2)),
        event("owner registration", now - timedelta(days=1)),
        event("upper boundary", now),
        event("inactive", now - timedelta(hours=2), active=False),
    ]
    events[3].event_type = None
    db_session.add_all(events)
    await db_session.flush()
    for e, who in zip(
        events, (owner, owner, owner, other, owner, owner, owner), strict=True
    ):
        token = attendance_tokens.generate_secret()
        db_session.add(
            models.EventAttendance(
                event_id=e.id,
                user_id=who.id,
                registered_at=e.starts_at - timedelta(minutes=5),
                qr_secret=token,
                qr_hmac=attendance_tokens.compute_secret_hmac(token),
            )
        )
    db_session.add_all(
        [
            models.Grade(
                student_id=owner.id,
                subject="too old",
                score=1,
                created_at=previous - timedelta(microseconds=1),
            ),
            models.Grade(
                student_id=owner.id,
                subject="previous boundary",
                score=2,
                created_at=previous,
            ),
            models.Grade(
                student_id=owner.id,
                subject="window boundary",
                score=3,
                created_at=window,
            ),
            models.Grade(
                student_id=owner.id,
                subject="current",
                score=4.5,
                created_at=now - timedelta(hours=1),
            ),
            models.Grade(
                student_id=owner.id, subject="upper boundary", score=5, created_at=now
            ),
            models.Grade(
                student_id=other.id,
                subject="other user",
                score=4,
                created_at=now - timedelta(minutes=10),
            ),
        ]
    )
    await db_session.commit()

    reference = UserStatsRepository(db_session)
    valid_kinds = ("attendance", "grades", "participation")
    for user in (owner, other):
        attendance = await reference.get_attendance_stats_raw(
            user.id, window, previous, now
        )
        grades = await reference.get_grades(user.id, previous, now)
        participation = await reference.get_participation_stats_raw(
            user.id, previous, now
        )
        assert len(attendance) == (5 if user is owner else 4)
        assert [x.subject for x in grades] == (
            ["current", "window boundary", "previous boundary"]
            if user is owner
            else ["other user"]
        )
        assert [x.title for x in participation] == (
            ["owner registration", "window boundary", "previous boundary"]
            if user is owner
            else ["other registration"]
        )
        if user is other:
            assert participation[0].event_type is None
        for count in (1, 2, 3):
            for kinds in itertools.combinations(valid_kinds, count):
                database = CountingDB(db_session)
                actual = await UserStatsRepository(database).get_summary_rows(
                    user.id, window, previous, now, kinds=kinds
                )
                assert len(database.statements) == 1
                for dialect in (sqlite.dialect(), postgresql.dialect()):
                    compiled = str(database.statements[0].compile(dialect=dialect))
                    assert "summary_rows" in compiled
                    assert ("AS attendance" in compiled) == ("attendance" in kinds)
                    assert ("grades." in compiled) == ("grades" in kinds)
                    assert ("events.ends_at" in compiled) == ("participation" in kinds)
                    assert ("UNION ALL" in compiled) == (
                        "attendance" in kinds or len(kinds) > 1
                    )
                assert Counter(map(attendance_key, actual.attendance)) == (
                    Counter(map(attendance_key, attendance))
                    if "attendance" in kinds
                    else Counter()
                )
                assert list(map(grade_key, actual.grades)) == (
                    list(map(grade_key, grades)) if "grades" in kinds else []
                )
                assert list(map(participation_key, actual.participation)) == (
                    list(map(participation_key, participation))
                    if "participation" in kinds
                    else []
                )
                assert all(x.starts_at.tzinfo == UTC for x in actual.attendance)
                assert all(
                    x.registered_at is None or x.registered_at.tzinfo == UTC
                    for x in actual.attendance
                )
                assert all(
                    x.created_at.tzinfo == UTC and isinstance(x.score, float)
                    for x in actual.grades
                )
                assert all(
                    isinstance(x.event_id, uuid.UUID)
                    and x.starts_at.tzinfo == UTC
                    and x.ends_at.tzinfo == UTC
                    for x in actual.participation
                )
