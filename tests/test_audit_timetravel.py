import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.auth.security import get_password_hash
from app.models.domain_events import StoredEvent
from app.services.audit_service import get_secure_audit_service
from app.services.grade_service import GradeService

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_record_domain_event_hmac_chain(db_session):
    audit_service = get_secure_audit_service()
    agg_id = uuid.uuid4()

    t0 = datetime.now(UTC) - timedelta(minutes=10)
    t1 = datetime.now(UTC) - timedelta(minutes=5)
    t2 = datetime.now(UTC)

    # 1. First event (genesis)
    e1 = await audit_service.record_domain_event(
        db_session,
        event_type="SCHEDULE_CREATED",
        aggregate_type="schedule",
        aggregate_id=agg_id,
        payload={"subject": "Math 101", "room": "101"},
        created_at=t0,
    )
    assert e1.prev_hash == "0" * 64
    assert e1.hash is not None
    assert len(e1.hash) == 64

    # 2. Second event
    e2 = await audit_service.record_domain_event(
        db_session,
        event_type="SCHEDULE_UPDATED",
        aggregate_type="schedule",
        aggregate_id=agg_id,
        payload={
            "changes": {"room": {"old": "101", "new": "202"}},
            "current_state": {"subject": "Math 101", "room": "202"},
        },
        created_at=t1,
    )
    assert e2.prev_hash == e1.hash
    assert e2.hash is not None

    # 3. Third event
    e3 = await audit_service.record_domain_event(
        db_session,
        event_type="SCHEDULE_UPDATED",
        aggregate_type="schedule",
        aggregate_id=agg_id,
        payload={
            "changes": {"room": {"old": "202", "new": "303"}},
            "current_state": {"subject": "Math 101", "room": "303"},
        },
        created_at=t2,
    )
    assert e3.prev_hash == e2.hash
    assert e3.hash is not None

    # Verify chain integrity
    is_valid, failed_id, err_msg = await audit_service.verify_chain_integrity(
        db_session, aggregate_type="schedule", aggregate_id=agg_id
    )
    assert is_valid is True
    assert failed_id is None
    assert err_msg is None


async def test_verify_chain_integrity_tamper_detection(db_session):
    audit_service = get_secure_audit_service()
    agg_id = uuid.uuid4()

    _ = await audit_service.record_domain_event(
        db_session,
        event_type="GRADE_ASSIGNED",
        aggregate_type="grade",
        aggregate_id=agg_id,
        payload={"student_id": str(uuid.uuid4()), "score": 85.0},
    )

    e2 = await audit_service.record_domain_event(
        db_session,
        event_type="GRADE_MODIFIED",
        aggregate_type="grade",
        aggregate_id=agg_id,
        payload={"old_score": 85.0, "new_score": 95.0},
    )

    # Initial integrity check passes
    is_valid, _, _ = await audit_service.verify_chain_integrity(
        db_session, aggregate_type="grade", aggregate_id=agg_id
    )
    assert is_valid is True

    # Tamper with e2 payload directly
    e2.payload = {"old_score": 85.0, "new_score": 100.0}
    await db_session.flush()

    is_valid_tampered, failed_id, err_msg = await audit_service.verify_chain_integrity(
        db_session, aggregate_type="grade", aggregate_id=agg_id
    )
    assert is_valid_tampered is False
    assert failed_id == str(e2.id)
    assert "tampering detected" in err_msg


async def test_grade_service_domain_events(db_session, user_factory):
    student = await user_factory(role="student", email="student-grade@example.com")
    teacher = await user_factory(role="teacher", email="teacher-grade@example.com")

    grade_service = GradeService()

    # Assign grade
    grade = await grade_service.assign_grade(
        db_session,
        student_id=student.id,
        subject="Physics",
        score=90.0,
        assessment_type="exam",
        assigned_by=teacher.id,
    )
    await db_session.commit()

    # Verify GRADE_ASSIGNED event
    stmt1 = select(StoredEvent).where(
        StoredEvent.aggregate_type == "grade",
        StoredEvent.aggregate_id == str(grade.id),
        StoredEvent.event_type == "GRADE_ASSIGNED",
    )
    res1 = await db_session.execute(stmt1)
    ev1 = res1.scalars().first()
    assert ev1 is not None
    assert ev1.payload["score"] == 90.0
    assert ev1.payload["subject"] == "Physics"

    # Modify grade
    await grade_service.modify_grade(
        db_session,
        grade_id=grade.id,
        new_score=95.0,
        reason="Extra credit",
        modified_by=teacher.id,
    )
    await db_session.commit()

    # Verify GRADE_MODIFIED event
    stmt2 = select(StoredEvent).where(
        StoredEvent.aggregate_type == "grade",
        StoredEvent.aggregate_id == str(grade.id),
        StoredEvent.event_type == "GRADE_MODIFIED",
    )
    res2 = await db_session.execute(stmt2)
    ev2 = res2.scalars().first()
    assert ev2 is not None
    assert ev2.payload["old_score"] == 90.0
    assert ev2.payload["new_score"] == 95.0


async def test_reconstruct_state_time_travel(db_session):
    audit_service = get_secure_audit_service()
    agg_id = uuid.uuid4()

    t_start = datetime.now(UTC) - timedelta(hours=3)
    t1 = t_start + timedelta(hours=1)
    t2 = t_start + timedelta(hours=2)

    # Event 1: Creation at t1
    await audit_service.record_domain_event(
        db_session,
        event_type="SCHEDULE_CREATED",
        aggregate_type="schedule",
        aggregate_id=agg_id,
        payload={"subject": "Chemistry", "room": "A-101", "teacher": "Prof. Curie"},
        created_at=t1,
    )

    # Event 2: Update at t2
    await audit_service.record_domain_event(
        db_session,
        event_type="SCHEDULE_UPDATED",
        aggregate_type="schedule",
        aggregate_id=agg_id,
        payload={
            "current_state": {
                "subject": "Chemistry",
                "room": "B-202",
                "teacher": "Prof. Curie",
            }
        },
        created_at=t2,
    )
    await db_session.commit()

    # Reconstruct state before creation (t_start)
    state_t0, count_t0, valid_t0 = await audit_service.reconstruct_state(
        db_session,
        aggregate_type="schedule",
        aggregate_id=agg_id,
        target_timestamp=t_start,
    )
    assert state_t0 is None
    assert count_t0 == 0
    assert valid_t0 is True

    # Reconstruct state at t1 (just created)
    state_t1, count_t1, valid_t1 = await audit_service.reconstruct_state(
        db_session,
        aggregate_type="schedule",
        aggregate_id=agg_id,
        target_timestamp=t1 + timedelta(seconds=1),
    )
    assert state_t1 is not None
    assert state_t1["room"] == "A-101"
    assert count_t1 == 1
    assert valid_t1 is True

    # Reconstruct state at t2 (updated)
    state_t2, count_t2, valid_t2 = await audit_service.reconstruct_state(
        db_session,
        aggregate_type="schedule",
        aggregate_id=agg_id,
        target_timestamp=t2 + timedelta(seconds=1),
    )
    assert state_t2 is not None
    assert state_t2["room"] == "B-202"
    assert count_t2 == 2
    assert valid_t2 is True


async def test_admin_time_travel_api_endpoint(root_client, user_factory, db_session):
    audit_service = get_secure_audit_service()
    agg_id = uuid.uuid4()

    t1 = datetime.now(UTC) - timedelta(minutes=30)
    t2 = datetime.now(UTC) - timedelta(minutes=15)

    await audit_service.record_domain_event(
        db_session,
        event_type="GRADE_ASSIGNED",
        aggregate_type="grade",
        aggregate_id=agg_id,
        payload={
            "student_id": str(uuid.uuid4()),
            "subject": "Biology",
            "score": 88.0,
            "assessment_type": "quiz",
        },
        created_at=t1,
    )
    await audit_service.record_domain_event(
        db_session,
        event_type="GRADE_MODIFIED",
        aggregate_type="grade",
        aggregate_id=agg_id,
        payload={"old_score": 88.0, "new_score": 94.0, "reason": "re-grading"},
        created_at=t2,
    )
    await db_session.commit()

    # Admin user auth
    admin_pass = "AdminPass123!_tt"
    admin_hash = await get_password_hash(admin_pass)
    admin = await user_factory(
        role="admin", email="admin-tt@example.com", hashed_password=admin_hash
    )

    login_res = await root_client.post(
        "/api/v1/auth/login",
        data={"username": admin.email, "password": admin_pass},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert login_res.status_code == 200
    token = login_res.cookies.get("access_token_v2")

    # 1. Call GET /admin/audit/time-travel as admin
    target_iso = (datetime.now(UTC)).isoformat()
    resp = await root_client.get(
        "/admin/audit/time-travel",
        params={
            "aggregate_type": "grade",
            "aggregate_id": str(agg_id),
            "target_timestamp": target_iso,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["aggregate_type"] == "grade"
    assert res_data["aggregate_id"] == str(agg_id)
    assert res_data["events_replayed"] == 2
    assert res_data["chain_integrity_valid"] is True
    assert res_data["state_at_timestamp"]["score"] == 94.0

    # 2. Call time-travel at earlier timestamp t1
    t1_iso = (t1 + timedelta(seconds=1)).isoformat()
    resp_t1 = await root_client.get(
        "/admin/audit/time-travel",
        params={
            "aggregate_type": "grade",
            "aggregate_id": str(agg_id),
            "target_timestamp": t1_iso,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_t1.status_code == 200
    res_t1_data = resp_t1.json()
    assert res_t1_data["events_replayed"] == 1
    assert res_t1_data["state_at_timestamp"]["score"] == 88.0

    # 3. Non-admin forbidden
    student_pass = "StudentPass123!_tt"
    student_hash = await get_password_hash(student_pass)
    student = await user_factory(
        role="student", email="student-tt@example.com", hashed_password=student_hash
    )

    stu_login = await root_client.post(
        "/api/v1/auth/login",
        data={"username": student.email, "password": student_pass},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    stu_token = stu_login.cookies.get("access_token_v2")

    resp_forbidden = await root_client.get(
        "/admin/audit/time-travel",
        params={
            "aggregate_type": "grade",
            "aggregate_id": str(agg_id),
            "target_timestamp": target_iso,
        },
        headers={"Authorization": f"Bearer {stu_token}"},
    )
    assert resp_forbidden.status_code == 403

    # 4. Invalid aggregate type -> 400 Bad Request
    resp_bad = await root_client.get(
        "/admin/audit/time-travel",
        params={
            "aggregate_type": "unsupported_type",
            "aggregate_id": str(agg_id),
            "target_timestamp": target_iso,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_bad.status_code == 400

    # 5. Non-existent aggregate -> 404 Not Found
    random_id = uuid.uuid4()
    resp_404 = await root_client.get(
        "/admin/audit/time-travel",
        params={
            "aggregate_type": "grade",
            "aggregate_id": str(random_id),
            "target_timestamp": target_iso,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_404.status_code == 404

    # 6. verify_chain=False flag
    resp_no_verify = await root_client.get(
        "/admin/audit/time-travel",
        params={
            "aggregate_type": "grade",
            "aggregate_id": str(agg_id),
            "target_timestamp": target_iso,
            "verify_chain": "false",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp_no_verify.status_code == 200
    assert resp_no_verify.json()["chain_integrity_valid"] is True


async def test_interleaved_multi_aggregate_events_integrity(db_session):
    """Test interleaved event emissions across multiple aggregates do not cause false-positive chain discontinuities."""
    audit_service = get_secure_audit_service()
    agg_id_a = uuid.uuid4()
    agg_id_b = uuid.uuid4()

    t0 = datetime.now(UTC) - timedelta(minutes=15)
    t1 = datetime.now(UTC) - timedelta(minutes=10)
    t2 = datetime.now(UTC) - timedelta(minutes=5)

    # 1. Schedule A Event 1
    e_a1 = await audit_service.record_domain_event(
        db_session,
        event_type="SCHEDULE_CREATED",
        aggregate_type="schedule",
        aggregate_id=agg_id_a,
        payload={"subject": "Math 101", "room": "101"},
        created_at=t0,
    )
    assert e_a1.prev_hash == "0" * 64

    # 2. Grade B Event 1 (Interleaved between Schedule A events)
    e_b1 = await audit_service.record_domain_event(
        db_session,
        event_type="GRADE_ASSIGNED",
        aggregate_type="grade",
        aggregate_id=agg_id_b,
        payload={"score": 85.0},
        created_at=t1,
    )
    assert e_b1.prev_hash == "0" * 64

    # 3. Schedule A Event 2
    e_a2 = await audit_service.record_domain_event(
        db_session,
        event_type="SCHEDULE_UPDATED",
        aggregate_type="schedule",
        aggregate_id=agg_id_a,
        payload={"current_state": {"subject": "Math 101", "room": "202"}},
        created_at=t2,
    )
    # Schedule A event 2 must link to Schedule A event 1, NOT Grade B event 1
    assert e_a2.prev_hash == e_a1.hash

    await db_session.commit()

    # Verify per-aggregate chain integrity for Schedule A
    valid_a, failed_a, err_a = await audit_service.verify_chain_integrity(
        db_session, aggregate_type="schedule", aggregate_id=agg_id_a
    )
    assert valid_a is True
    assert failed_a is None
    assert err_a is None

    # Verify per-aggregate chain integrity for Grade B
    valid_b, failed_b, err_b = await audit_service.verify_chain_integrity(
        db_session, aggregate_type="grade", aggregate_id=agg_id_b
    )
    assert valid_b is True
    assert failed_b is None
    assert err_b is None

    # Verify global chain integrity (unfiltered)
    valid_global, failed_g, err_g = await audit_service.verify_chain_integrity(
        db_session
    )
    assert valid_global is True
    assert failed_g is None
    assert err_g is None

    # Verify time-travel reconstruction for Schedule A
    state_a, count_a, valid_tt_a = await audit_service.reconstruct_state(
        db_session,
        aggregate_type="schedule",
        aggregate_id=agg_id_a,
        target_timestamp=t2 + timedelta(seconds=1),
    )
    assert state_a is not None
    assert state_a["room"] == "202"
    assert count_a == 2
    assert valid_tt_a is True
