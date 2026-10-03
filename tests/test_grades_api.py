"""Grade assignment API and service behaviour."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

import app.models as models
from app.auth.security import get_password_hash
from app.services import stats_cache
from app.services.grade_service import (
    GradeNotFoundError,
    GradeService,
    GradeStudentNotFoundError,
)

PASSWORD = "GradesApiPass123!"  # pragma: allowlist secret


async def _login_as(async_client, user_factory, role: str):
    hashed = await get_password_hash(PASSWORD)
    user = await user_factory(hashed_password=hashed, is_active=True, role=role)
    response = await async_client.post(
        "/auth/login",
        data={"username": user.email, "password": PASSWORD},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 200
    return user


def _payload(student_id: uuid.UUID, **overrides):
    body = {"student_id": str(student_id), "subject": "Physics", "score": 4.5}
    body.update(overrides)
    return body


@pytest.mark.asyncio
async def test_assign_grade_requires_auth(async_client):
    response = await async_client.post("/grades", json=_payload(uuid.uuid4()))
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_student_cannot_assign_grade(async_client, user_factory):
    student = await _login_as(async_client, user_factory, "student")
    response = await async_client.post("/grades", json=_payload(student.id))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_teacher_assigns_grade_and_student_is_notified(
    async_client, db_session, user_factory, monkeypatch
):
    student = await user_factory(is_active=True)
    teacher = await _login_as(async_client, user_factory, "teacher")
    invalidate = AsyncMock()
    monkeypatch.setattr(stats_cache, "invalidate_user_stats_cache", invalidate)

    response = await async_client.post("/grades", json=_payload(student.id))

    assert response.status_code == 201
    body = response.json()
    assert body["student_id"] == str(student.id)
    assert body["subject"] == "Physics"
    assert body["score"] == 4.5
    assert body["assessment_type"] == "exam"
    assert body["assigned_by"] == str(teacher.id)

    stored = (await db_session.execute(select(models.Grade))).scalars().all()
    assert [(g.student_id, g.score) for g in stored] == [(student.id, 4.5)]
    notifications = (
        (
            await db_session.execute(
                select(models.Notification).where(
                    models.Notification.user_id == student.id,
                    models.Notification.type == "grade",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(notifications) == 1
    assert "Physics" in notifications[0].title
    assert invalidate.await_args.kwargs["kinds"] == ("grades",)


@pytest.mark.asyncio
async def test_assign_grade_unknown_student_is_404(async_client, user_factory):
    await _login_as(async_client, user_factory, "teacher")
    response = await async_client.post("/grades", json=_payload(uuid.uuid4()))
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_assign_grade_inactive_student_is_404(async_client, user_factory):
    inactive = await user_factory(is_active=False)
    await _login_as(async_client, user_factory, "teacher")
    response = await async_client.post("/grades", json=_payload(inactive.id))
    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [{"score": -1}, {"score": 100.5}, {"subject": ""}, {"assessment_type": ""}],
)
async def test_assign_grade_validates_input(async_client, user_factory, overrides):
    student = await user_factory(is_active=True)
    await _login_as(async_client, user_factory, "teacher")
    response = await async_client.post(
        "/grades", json=_payload(student.id, **overrides)
    )
    assert response.status_code == 422


async def _seed_grade(db_session, student_id, assigned_by, score=3.0) -> models.Grade:
    grade = models.Grade(
        student_id=student_id, subject="Math", score=score, assigned_by=assigned_by
    )
    db_session.add(grade)
    await db_session.commit()
    return grade


@pytest.mark.asyncio
async def test_teacher_modifies_own_grade(async_client, db_session, user_factory):
    student = await user_factory(is_active=True)
    teacher = await _login_as(async_client, user_factory, "teacher")
    grade = await _seed_grade(db_session, student.id, teacher.id)

    response = await async_client.patch(
        f"/grades/{grade.id}", json={"score": 5, "reason": "appeal"}
    )

    assert response.status_code == 200
    assert response.json()["score"] == 5
    await db_session.refresh(grade)
    assert grade.score == 5


@pytest.mark.asyncio
async def test_teacher_cannot_modify_foreign_grade(
    async_client, db_session, user_factory
):
    student = await user_factory(is_active=True)
    other_teacher = await user_factory(role="teacher")
    await _login_as(async_client, user_factory, "teacher")
    grade = await _seed_grade(db_session, student.id, other_teacher.id)

    response = await async_client.patch(f"/grades/{grade.id}", json={"score": 5})

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_modifies_any_grade(async_client, db_session, user_factory):
    student = await user_factory(is_active=True)
    teacher = await user_factory(role="teacher")
    await _login_as(async_client, user_factory, "admin")
    grade = await _seed_grade(db_session, student.id, teacher.id)

    response = await async_client.patch(f"/grades/{grade.id}", json={"score": 4})

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_modify_missing_grade_is_404(async_client, user_factory):
    await _login_as(async_client, user_factory, "admin")
    response = await async_client.patch(f"/grades/{uuid.uuid4()}", json={"score": 4})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_student_cannot_modify_grade(async_client, db_session, user_factory):
    student = await _login_as(async_client, user_factory, "student")
    grade = await _seed_grade(db_session, student.id, None)
    response = await async_client.patch(f"/grades/{grade.id}", json={"score": 5})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_modify_grade_deleted_concurrently_is_404(
    async_client, db_session, user_factory, monkeypatch
):
    student = await user_factory(is_active=True)
    teacher = await _login_as(async_client, user_factory, "teacher")
    grade = await _seed_grade(db_session, student.id, teacher.id)
    monkeypatch.setattr(
        GradeService,
        "modify_grade",
        AsyncMock(side_effect=GradeNotFoundError(str(grade.id))),
    )

    response = await async_client.patch(f"/grades/{grade.id}", json={"score": 5})

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_service_rejects_unknown_student(db_session):
    service = GradeService(db_session)
    with pytest.raises(GradeStudentNotFoundError):
        await service.assign_grade(student_id=uuid.uuid4(), subject="Math", score=4.0)


@pytest.mark.asyncio
async def test_service_modify_unknown_grade_raises(db_session):
    service = GradeService(db_session)
    with pytest.raises(GradeNotFoundError):
        await service.modify_grade(grade_id=uuid.uuid4(), new_score=4.0)
    assert await service.get_grade(uuid.uuid4()) is None
