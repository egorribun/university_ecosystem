from datetime import UTC, datetime

import pytest

from app.auth.security import get_password_hash
from app.models import models

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_list_audit_logs_as_admin(root_client, user_factory, db_session):
    # Create an admin user with properly hashed password
    password = "StrongAdminPass123!"
    hashed = get_password_hash(password)
    admin = await user_factory(
        role="admin", email="admin-audit@example.com", hashed_password=hashed
    )

    # Login to get token
    login_response = await root_client.post(
        "/api/v1/auth/login",
        data={"username": admin.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    # Create some audit logs
    log1 = models.DataAccessLog(
        actor_user_id=admin.id,
        resource_type="user",
        resource_id="1",
        action="view",
        context={"foo": "bar"},
        created_at=datetime.now(UTC),
    )
    db_session.add(log1)
    await db_session.commit()

    # Test GET /admin/audit
    response = await root_client.get(
        "/admin/audit", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 1
    assert any(item["actor_user_id"] == str(admin.id) for item in data["items"])


async def test_list_audit_logs_forbidden_for_student(root_client, user_factory):
    # Create a student user
    password = "StudentPass123!"
    hashed = get_password_hash(password)
    student = await user_factory(
        role="student", email="student-audit@example.com", hashed_password=hashed
    )

    login_response = await root_client.post(
        "/api/v1/auth/login",
        data={"username": student.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    token = login_response.json()["access_token"]

    response = await root_client.get(
        "/admin/audit", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 403


async def test_list_audit_logs_filtering(root_client, user_factory, db_session):
    password = "FilterPass123!"
    hashed = get_password_hash(password)
    admin = await user_factory(
        role="admin", email="admin-filter@example.com", hashed_password=hashed
    )
    user_subject = await user_factory(role="student", email="subject@example.com")

    login_response = await root_client.post(
        "/api/v1/auth/login",
        data={"username": admin.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    token = login_response.json()["access_token"]

    # Create logs with different attributes
    log_action = models.DataAccessLog(
        actor_user_id=admin.id,
        action="special_action",
        resource_type="test",
        created_at=datetime.now(UTC),
    )
    log_subject = models.DataAccessLog(
        actor_user_id=admin.id,
        subject_user_id=user_subject.id,
        action="view",
        resource_type="user",
        created_at=datetime.now(UTC),
    )
    db_session.add_all([log_action, log_subject])
    await db_session.commit()

    # Filter by action
    response = await root_client.get(
        "/admin/audit?action=special_action",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert all(item["action"] == "special_action" for item in response.json()["items"])

    # Filter by subject_id
    response = await root_client.get(
        f"/admin/audit?subject_id={user_subject.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert all(
        item["subject_user_id"] == str(user_subject.id)
        for item in response.json()["items"]
    )


async def test_list_audit_logs_pagination(root_client, user_factory, db_session):
    password = "PaginationPass123!"
    hashed = get_password_hash(password)
    admin = await user_factory(
        role="admin", email="admin-pagination@example.com", hashed_password=hashed
    )

    login_response = await root_client.post(
        "/api/v1/auth/login",
        data={"username": admin.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    token = login_response.json()["access_token"]

    # Create multiple logs
    for i in range(5):
        db_session.add(
            models.DataAccessLog(
                actor_user_id=admin.id,
                action=f"action_{i}",
                resource_type="pagination",
                created_at=datetime.now(UTC),
            )
        )
    await db_session.commit()

    # Test limit
    response = await root_client.get(
        "/admin/audit?limit=2&resource_type=pagination",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert len(response.json()["items"]) == 2

    # Test offset
    response = await root_client.get(
        "/admin/audit?offset=3&resource_type=pagination",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    # There should be exactly 2 logs left if total is 5 and offset is 3
    assert len(response.json()["items"]) == 2


async def test_list_audit_logs_actor_filtering(root_client, user_factory, db_session):
    password = "ActorPass123!"
    hashed = get_password_hash(password)
    admin = await user_factory(
        role="admin", email="admin-actor@example.com", hashed_password=hashed
    )
    actor_user = await user_factory(role="student", email="actor-test@example.com")

    login_response = await root_client.post(
        "/api/v1/auth/login",
        data={"username": admin.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    token = login_response.json()["access_token"]

    # Create a log with a specific actor
    log = models.DataAccessLog(
        actor_user_id=actor_user.id,
        action="actor_action",
        resource_type="actor_test",
        created_at=datetime.now(UTC),
    )
    db_session.add(log)
    await db_session.commit()

    # Filter by actor_id
    response = await root_client.get(
        f"/admin/audit?actor_id={actor_user.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) >= 1
    assert all(item["actor_user_id"] == str(actor_user.id) for item in data["items"])
    # This also covers the verify_integrity call in the loop
    assert "is_valid" in data["items"][0]
