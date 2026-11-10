"""Grade corrections use current locked state for persistence and audit."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_current_user_from_dishka
from app.core.database import async_session
from app.models import Grade, StoredEvent
from app.services.audit_service import get_secure_audit_service
from app.services.grade_service import GradeService


async def _seed_grade(db_session, user_factory):
    student = await user_factory()
    teacher = await user_factory(role="teacher")
    grade = Grade(
        student_id=student.id,
        subject="Algebra",
        score=3.0,
        assigned_by=teacher.id,
    )
    db_session.add(grade)
    await db_session.commit()
    return grade, teacher


@pytest.mark.parametrize("requested_score", [3.0, 4.0])
async def test_http_grade_correction_rechecks_after_concurrent_update(
    app, async_client, db_session, user_factory, monkeypatch, requested_score
):
    grade, teacher = await _seed_grade(db_session, user_factory)
    grade_id, teacher_id = grade.id, teacher.id
    app.dependency_overrides[get_current_user_from_dishka] = lambda: teacher
    monkeypatch.setattr(GradeService, "invalidate_stats", AsyncMock())
    original_read = GradeService.get_grade
    interleaved = False

    async def read_then_interleave_writer(service, target_id, **kwargs):
        nonlocal interleaved
        current = await original_read(service, target_id, **kwargs)
        if not interleaved:
            interleaved = True
            assert current.score == 3.0
            # A's authorization read retains the old ORM object. B commits
            # before A's modification query; no simultaneous SQLite writes.
            async with async_session() as writer:
                await GradeService(writer).modify_grade(
                    grade_id=grade_id,
                    new_score=5.0,
                    reason="Other correction",
                    modified_by=teacher_id,
                )
                await writer.commit()
            assert current.score == 3.0
        return current

    monkeypatch.setattr(GradeService, "get_grade", read_then_interleave_writer)
    response = await async_client.patch(
        f"/grades/{grade_id}",
        json={"score": requested_score, "reason": "Final correction"},
    )
    assert interleaved
    assert response.status_code == 200
    assert response.json()["score"] == requested_score
    async with async_session() as observer:
        persisted = await observer.get(Grade, grade_id)
        assert persisted is not None
        assert persisted.score == requested_score
        events = (
            (
                await observer.execute(
                    select(StoredEvent)
                    .where(
                        StoredEvent.aggregate_type == "grade",
                        StoredEvent.aggregate_id == str(grade_id),
                    )
                    .order_by(StoredEvent.sequence_number)
                )
            )
            .scalars()
            .all()
        )
        assert len(events) == 2
        assert events[0].payload["old_score"] == 3.0
        assert events[0].payload["new_score"] == 5.0
        assert events[1].payload["old_score"] == 5.0
        assert events[1].payload["new_score"] == requested_score
        assert events[1].payload["current_state"]["score"] == requested_score
        assert events[1].payload["modified_by"] == str(teacher_id)
        valid, failed, error = await get_secure_audit_service().verify_chain_integrity(
            observer, aggregate_type="grade", aggregate_id=grade_id
        )
        assert valid, (failed, error)


@pytest.mark.parametrize("commit", [False, True])
async def test_grade_correction_preserves_pending_edits_and_transaction_ownership(
    db_session, user_factory, commit
):
    grade, teacher = await _seed_grade(db_session, user_factory)
    grade_id, teacher_id = grade.id, teacher.id
    grade.subject = "Pending subject"
    assert db_session.autoflush
    changed = await GradeService(db_session).modify_grade(
        grade_id=grade_id, new_score=4.0, modified_by=teacher_id
    )
    assert changed is grade
    assert changed.subject == "Pending subject"
    async with async_session() as observer:
        before_commit = await observer.get(Grade, grade_id)
        assert before_commit is not None
        assert before_commit.score == 3.0
        assert before_commit.subject == "Algebra"
    if commit:
        await db_session.commit()
    else:
        await db_session.rollback()
    async with async_session() as observer:
        saved = await observer.get(Grade, grade_id)
        assert saved is not None
        assert saved.score == (4.0 if commit else 3.0)
        assert saved.subject == ("Pending subject" if commit else "Algebra")
        events = (
            (
                await observer.execute(
                    select(StoredEvent).where(
                        StoredEvent.aggregate_type == "grade",
                        StoredEvent.aggregate_id == str(grade_id),
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(events) == int(commit)
        if commit:
            assert events[0].payload["old_score"] == 3.0
            assert events[0].payload["current_state"]["subject"] == "Pending subject"


async def test_grade_locked_read_does_not_erase_invalid_pending_edits(
    db_session, user_factory
):
    grade, teacher = await _seed_grade(db_session, user_factory)
    grade_id, teacher_id = grade.id, teacher.id
    grade.subject = None
    with pytest.raises(IntegrityError):
        await GradeService(db_session).modify_grade(
            grade_id=grade_id, new_score=4.0, modified_by=teacher_id
        )
    await db_session.rollback()
    async with async_session() as observer:
        saved = await observer.get(Grade, grade_id)
        assert saved is not None
        assert saved.subject == "Algebra"
        assert saved.score == 3.0


async def test_no_op_grade_correction_keeps_existing_audit_semantics(
    db_session, user_factory
):
    grade, teacher = await _seed_grade(db_session, user_factory)
    grade_id = grade.id
    await GradeService(db_session).modify_grade(
        grade_id=grade_id, new_score=3.0, modified_by=teacher.id
    )
    await db_session.commit()
    async with async_session() as observer:
        saved = await observer.get(Grade, grade_id)
        assert saved is not None
        assert saved.score == 3.0
        event = (
            await observer.execute(
                select(StoredEvent).where(
                    StoredEvent.aggregate_type == "grade",
                    StoredEvent.aggregate_id == str(grade_id),
                )
            )
        ).scalar_one()
        assert event.payload["old_score"] == 3.0
        assert event.payload["new_score"] == 3.0
        assert event.payload["reason"] is None


async def test_only_grade_write_lookup_refreshes_under_blocking_row_lock(db_session):
    statements = []

    def collect(execute_state):
        if execute_state.is_select:
            statements.append(execute_state.statement)

    sqlalchemy_event.listen(db_session.sync_session, "do_orm_execute", collect)
    try:
        service = GradeService(db_session)
        missing_id = uuid4()
        assert await service.get_grade(missing_id) is None
        assert await service.get_grade(missing_id, for_update=True) is None
    finally:
        sqlalchemy_event.remove(db_session.sync_session, "do_orm_execute", collect)

    assert len(statements) == 2
    ordinary, locked = statements
    assert "FOR UPDATE" not in str(ordinary.compile(dialect=postgresql.dialect()))
    assert not ordinary.get_execution_options().get("populate_existing", False)
    locked_sql = str(locked.compile(dialect=postgresql.dialect()))
    assert locked_sql.endswith(" FOR UPDATE")
    assert "NOWAIT" not in locked_sql
    assert "SKIP LOCKED" not in locked_sql
    assert "FOR SHARE" not in locked_sql
    assert locked.compile().params == {"id_1": missing_id}
    assert locked.get_execution_options()["populate_existing"] is True
    assert "autoflush" not in locked.get_execution_options()
