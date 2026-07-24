import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.auth.security import get_password_hash
from app.services.audit_service import get_secure_audit_service

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_empirical_hmac_chain_continuity(db_session):
    """
    Empirical Verification 1: HMAC Hash Chaining ($H_n$)
    Verify that sequential domain events form a strict cryptographic HMAC hash chain,
    where event n+1 prev_hash matches event n hash, and initial event prev_hash is 64 zeros.
    """
    audit_service = get_secure_audit_service()
    agg_id = uuid.uuid4()

    t0 = datetime.now(UTC) - timedelta(minutes=15)
    t1 = t0 + timedelta(minutes=2)
    t2 = t1 + timedelta(minutes=2)
    t3 = t2 + timedelta(minutes=2)

    # 1. Record sequence of events
    e0 = await audit_service.record_domain_event(
        db_session,
        event_type="USER_CREATED",
        aggregate_type="user",
        aggregate_id=agg_id,
        payload={"email": "test-user@university.edu", "role": "student"},
        created_at=t0,
    )
    e1 = await audit_service.record_domain_event(
        db_session,
        event_type="USER_UPDATED",
        aggregate_type="user",
        aggregate_id=agg_id,
        payload={"changes": {"role": {"old": "student", "new": "teacher"}}},
        created_at=t1,
    )
    e2 = await audit_service.record_domain_event(
        db_session,
        event_type="USER_UPDATED",
        aggregate_type="user",
        aggregate_id=agg_id,
        payload={
            "current_state": {"email": "prof-user@university.edu", "role": "teacher"}
        },
        created_at=t2,
    )
    e3 = await audit_service.record_domain_event(
        db_session,
        event_type="USER_DELETED",
        aggregate_type="user",
        aggregate_id=agg_id,
        payload={"reason": "graduated"},
        created_at=t3,
    )
    await db_session.flush()

    # 2. Verify hash chain linkages
    assert e0.prev_hash == "0" * 64
    assert len(e0.hash) == 64
    assert e1.prev_hash == e0.hash
    assert len(e1.hash) == 64
    assert e2.prev_hash == e1.hash
    assert len(e2.hash) == 64
    assert e3.prev_hash == e2.hash
    assert len(e3.hash) == 64

    # 3. Verify sequence number monotonicity
    assert (
        e0.sequence_number
        < e1.sequence_number
        < e2.sequence_number
        < e3.sequence_number
    )

    # 4. Verify chain integrity passes on unmodified stream
    is_valid, failed_id, err_msg = await audit_service.verify_chain_integrity(
        db_session, aggregate_type="user", aggregate_id=agg_id
    )
    assert is_valid is True
    assert failed_id is None
    assert err_msg is None


async def test_empirical_canonicalization_determinism():
    """
    Empirical Verification 2: Canonical Payload Determinism
    Verify canonicalize_event_payload yields identical JSON strings regardless of dictionary key order.
    """
    audit_service = get_secure_audit_service()

    payload_dict1 = {"b": 2, "a": 1, "nested": {"z": 10, "y": 20}}
    payload_dict2 = {"nested": {"y": 20, "z": 10}, "a": 1, "b": 2}

    canon1 = audit_service.canonicalize_event_payload(
        aggregate_type="schedule",
        aggregate_id="123e4567-e89b-12d3-a456-426614174000",
        event_type="SCHEDULE_CREATED",
        payload=payload_dict1,
        version=1,
    )

    canon2 = audit_service.canonicalize_event_payload(
        aggregate_type="schedule",
        aggregate_id="123e4567-e89b-12d3-a456-426614174000",
        event_type="SCHEDULE_CREATED",
        payload=payload_dict2,
        version=1,
    )

    assert canon1 == canon2
    assert '"aggregate_id":"123e4567-e89b-12d3-a456-426614174000"' in canon1


async def test_empirical_tamper_detection_payload_modification(db_session):
    """
    Empirical Adversarial Test 1: Payload Tampering Injection
    Inject an altered payload into a stored event and confirm verify_chain_integrity flags tamper-evidence.
    """
    audit_service = get_secure_audit_service()
    agg_id = uuid.uuid4()

    _ = await audit_service.record_domain_event(
        db_session,
        event_type="GRADE_ASSIGNED",
        aggregate_type="grade",
        aggregate_id=agg_id,
        payload={"student_id": str(uuid.uuid4()), "score": 75.0, "subject": "Math"},
    )
    e2 = await audit_service.record_domain_event(
        db_session,
        event_type="GRADE_MODIFIED",
        aggregate_type="grade",
        aggregate_id=agg_id,
        payload={"old_score": 75.0, "new_score": 85.0, "reason": "bonus"},
    )
    await db_session.flush()

    # Initial check passes
    is_valid, _, _ = await audit_service.verify_chain_integrity(
        db_session, aggregate_type="grade", aggregate_id=agg_id
    )
    assert is_valid is True

    # Tamper with e2 payload
    e2.payload = {"old_score": 75.0, "new_score": 100.0, "reason": "bonus"}
    await db_session.flush()

    is_valid_tampered, failed_id, err_msg = await audit_service.verify_chain_integrity(
        db_session, aggregate_type="grade", aggregate_id=agg_id
    )
    assert is_valid_tampered is False
    assert failed_id == str(e2.id)
    assert "tampering detected" in err_msg.lower() or "discontinuity" in err_msg.lower()


async def test_empirical_tamper_detection_prev_hash_modification(db_session):
    """
    Empirical Adversarial Test 2: Prev Hash Link Breakage
    Inject a broken prev_hash into an event link and confirm verify_chain_integrity detects chain failure.
    """
    audit_service = get_secure_audit_service()
    agg_id = uuid.uuid4()

    _ = await audit_service.record_domain_event(
        db_session,
        event_type="SCHEDULE_CREATED",
        aggregate_type="schedule",
        aggregate_id=agg_id,
        payload={"room": "101"},
    )
    e2 = await audit_service.record_domain_event(
        db_session,
        event_type="SCHEDULE_UPDATED",
        aggregate_type="schedule",
        aggregate_id=agg_id,
        payload={"room": "102"},
    )
    await db_session.flush()

    # Modify prev_hash of e2 to arbitrary hash
    e2.prev_hash = "f" * 64
    await db_session.flush()

    is_valid, failed_id, err_msg = await audit_service.verify_chain_integrity(
        db_session, aggregate_type="schedule", aggregate_id=agg_id
    )
    assert is_valid is False
    assert failed_id == str(e2.id)
    assert err_msg is not None


async def test_empirical_tamper_detection_created_at_modification(db_session):
    """
    Empirical Adversarial Test 3: Timestamp Tampering Injection
    Inject altered created_at timestamp into an event and confirm HMAC verification fails.
    """
    audit_service = get_secure_audit_service()
    agg_id = uuid.uuid4()

    t_orig = datetime.now(UTC) - timedelta(hours=1)
    e1 = await audit_service.record_domain_event(
        db_session,
        event_type="SCHEDULE_CREATED",
        aggregate_type="schedule",
        aggregate_id=agg_id,
        payload={"room": "301"},
        created_at=t_orig,
    )
    await db_session.flush()

    # Shift created_at by 5 seconds
    e1.created_at = t_orig + timedelta(seconds=5)
    await db_session.flush()

    is_valid, failed_id, _err_msg = await audit_service.verify_chain_integrity(
        db_session, aggregate_type="schedule", aggregate_id=agg_id
    )
    assert is_valid is False
    assert failed_id == str(e1.id)


async def test_empirical_state_reconstruction_lifecycle(db_session):
    """
    Empirical Verification 3: Historical State Reconstruction (reconstruct_state)
    Verify accurate state snapshot folding across creation, update (partial changes), update (state override), and deletion.
    """
    audit_service = get_secure_audit_service()
    agg_id = uuid.uuid4()

    base_t = datetime.now(UTC) - timedelta(hours=10)
    t_create = base_t + timedelta(hours=1)
    t_update1 = base_t + timedelta(hours=2)
    t_update2 = base_t + timedelta(hours=3)
    t_delete = base_t + timedelta(hours=4)

    # 1. Event 1: Creation
    await audit_service.record_domain_event(
        db_session,
        event_type="SCHEDULE_CREATED",
        aggregate_type="schedule",
        aggregate_id=agg_id,
        payload={"subject": "Physics 101", "room": "Hall A", "capacity": 50},
        created_at=t_create,
    )

    # 2. Event 2: Partial update via changes
    await audit_service.record_domain_event(
        db_session,
        event_type="SCHEDULE_UPDATED",
        aggregate_type="schedule",
        aggregate_id=agg_id,
        payload={"changes": {"capacity": {"old": 50, "new": 75}}},
        created_at=t_update1,
    )

    # 3. Event 3: Full state replacement
    await audit_service.record_domain_event(
        db_session,
        event_type="SCHEDULE_UPDATED",
        aggregate_type="schedule",
        aggregate_id=agg_id,
        payload={
            "current_state": {"subject": "Physics 102", "room": "Lab B", "capacity": 75}
        },
        created_at=t_update2,
    )

    # 4. Event 4: Deletion
    await audit_service.record_domain_event(
        db_session,
        event_type="SCHEDULE_DELETED",
        aggregate_type="schedule",
        aggregate_id=agg_id,
        payload={"reason": "cancelled"},
        created_at=t_delete,
    )
    await db_session.commit()

    # Reconstruct prior to creation
    s0, c0, v0 = await audit_service.reconstruct_state(
        db_session,
        aggregate_type="schedule",
        aggregate_id=agg_id,
        target_timestamp=base_t,
    )
    assert s0 is None
    assert c0 == 0
    assert v0 is True

    # Reconstruct after creation (t_create)
    s1, c1, v1 = await audit_service.reconstruct_state(
        db_session,
        aggregate_type="schedule",
        aggregate_id=agg_id,
        target_timestamp=t_create + timedelta(seconds=1),
    )
    assert s1 is not None
    assert s1["subject"] == "Physics 101"
    assert s1["room"] == "Hall A"
    assert s1["capacity"] == 50
    assert c1 == 1
    assert v1 is True

    # Reconstruct after update 1 (t_update1)
    s2, c2, v2 = await audit_service.reconstruct_state(
        db_session,
        aggregate_type="schedule",
        aggregate_id=agg_id,
        target_timestamp=t_update1 + timedelta(seconds=1),
    )
    assert s2["subject"] == "Physics 101"
    assert s2["capacity"] == 75
    assert c2 == 2
    assert v2 is True

    # Reconstruct after update 2 (t_update2)
    s3, c3, v3 = await audit_service.reconstruct_state(
        db_session,
        aggregate_type="schedule",
        aggregate_id=agg_id,
        target_timestamp=t_update2 + timedelta(seconds=1),
    )
    assert s3["subject"] == "Physics 102"
    assert s3["room"] == "Lab B"
    assert c3 == 3
    assert v3 is True

    # Reconstruct after deletion (t_delete)
    s4, c4, v4 = await audit_service.reconstruct_state(
        db_session,
        aggregate_type="schedule",
        aggregate_id=agg_id,
        target_timestamp=t_delete + timedelta(seconds=1),
    )
    assert s4["_deleted"] is True
    assert c4 == 4
    assert v4 is True


async def test_empirical_time_travel_api_endpoint_full_flow(
    root_client, user_factory, db_session
):
    """
    Empirical Verification 4: Admin Time-Travel API Endpoint
    Verify GET /admin/audit/time-travel returns snapshot, replayed count, and chain verification flag.
    """
    audit_service = get_secure_audit_service()
    agg_id = uuid.uuid4()

    t0 = datetime.now(UTC) - timedelta(minutes=40)
    t1 = datetime.now(UTC) - timedelta(minutes=20)

    await audit_service.record_domain_event(
        db_session,
        event_type="USER_CREATED",
        aggregate_type="user",
        aggregate_id=agg_id,
        payload={"email": "alice@university.edu", "full_name": "Alice Smith"},
        created_at=t0,
    )
    await audit_service.record_domain_event(
        db_session,
        event_type="USER_UPDATED",
        aggregate_type="user",
        aggregate_id=agg_id,
        payload={
            "changes": {"full_name": {"old": "Alice Smith", "new": "Dr. Alice Smith"}}
        },
        created_at=t1,
    )
    await db_session.commit()

    admin_pass = "AdminSecPass123!"
    admin_hash = await get_password_hash(admin_pass)
    admin = await user_factory(
        role="admin",
        email="admin-challenger@university.edu",
        hashed_password=admin_hash,
    )

    login_res = await root_client.post(
        "/api/v1/auth/login",
        data={"username": admin.email, "password": admin_pass},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert login_res.status_code == 200
    token = login_res.cookies.get("access_token_v2")

    # Time travel at latest timestamp
    now_iso = datetime.now(UTC).isoformat()
    res = await root_client.get(
        "/admin/audit/time-travel",
        params={
            "aggregate_type": "user",
            "aggregate_id": str(agg_id),
            "target_timestamp": now_iso,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["aggregate_type"] == "user"
    assert data["aggregate_id"] == str(agg_id)
    assert data["events_replayed"] == 2
    assert data["chain_integrity_valid"] is True
    assert data["state_at_timestamp"]["full_name"] == "Dr. Alice Smith"


async def test_empirical_interleaved_aggregates_chain_integrity(db_session):
    """
    Empirical Adversarial Test: Interleaved Events Across Aggregates
    Test how verify_chain_integrity handles events interleaved across different aggregate IDs/types.
    Global chain verification vs filtered aggregate verification.
    """
    audit_service = get_secure_audit_service()
    agg_a = uuid.uuid4()
    agg_b = uuid.uuid4()

    t0 = datetime.now(UTC) - timedelta(minutes=10)
    t1 = datetime.now(UTC) - timedelta(minutes=5)
    t2 = datetime.now(UTC)

    # 1. Event 1 (Agg A)
    _ = await audit_service.record_domain_event(
        db_session,
        event_type="SCHEDULE_CREATED",
        aggregate_type="schedule",
        aggregate_id=agg_a,
        payload={"room": "101"},
        created_at=t0,
    )

    # 2. Event 2 (Agg B - Interleaved)
    _ = await audit_service.record_domain_event(
        db_session,
        event_type="SCHEDULE_CREATED",
        aggregate_type="schedule",
        aggregate_id=agg_b,
        payload={"room": "999"},
        created_at=t1,
    )

    # 3. Event 3 (Agg A)
    _ = await audit_service.record_domain_event(
        db_session,
        event_type="SCHEDULE_UPDATED",
        aggregate_type="schedule",
        aggregate_id=agg_a,
        payload={"current_state": {"room": "102"}},
        created_at=t2,
    )
    await db_session.commit()

    # Global verification should pass
    is_valid_global, _, _ = await audit_service.verify_chain_integrity(db_session)
    assert is_valid_global is True

    # Filtered verification for Agg A: each aggregate maintains a self-contained per-aggregate HMAC chain,
    # so verifying Agg A in isolation evaluates to True without false-positive chain discontinuity.
    is_valid_agg_a, failed_id, err_msg = await audit_service.verify_chain_integrity(
        db_session, aggregate_type="schedule", aggregate_id=agg_a
    )
    assert is_valid_agg_a is True
    assert failed_id is None
    assert err_msg is None
