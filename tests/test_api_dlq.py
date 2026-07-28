from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

from app.models import DeadLetterJob, JobStatus


@pytest_asyncio.fixture
async def job_factory(db_session):
    async def _factory(**kwargs):
        import json

        from app.workers.dead_letter_queue import compute_job_hash

        job_type = kwargs.get("job_type", "test_job")
        payload = kwargs.get("payload", {"key": "value"})

        defaults = {
            "job_type": job_type,
            "job_hash": compute_job_hash(job_type, payload),
            "payload": json.dumps(payload),
            "error_message": "Some error",
            "retry_count": 0,
            "max_retries": 3,
            "status": JobStatus.PENDING.value,
            "next_retry_at": datetime.now(UTC) + timedelta(minutes=5),
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        # Only update non-payload fields or handle payload carefully
        for k, v in kwargs.items():
            if k == "payload":
                defaults["payload"] = json.dumps(v)
            else:
                defaults[k] = v

        job = DeadLetterJob(**defaults)
        db_session.add(job)
        await db_session.commit()
        await db_session.refresh(job)
        return job

    return _factory


async def _login_admin(async_client, user_factory, password="StrongAdminPass123!_"):  # noqa: S107
    from app.auth.security import get_password_hash

    hashed = await get_password_hash(password)
    admin = await user_factory(role="admin", hashed_password=hashed)

    # Login to get token
    login_response = await async_client.post(
        "/auth/login",
        data={"username": admin.email, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert login_response.status_code == 200
    token = login_response.cookies.get("access_token_v2")
    return admin, token


@pytest.mark.asyncio
async def test_get_dlq_stats_empty(async_client, user_factory):
    _, token = await _login_admin(async_client, user_factory)

    response = await async_client.get(
        "/admin/dlq/stats",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Internal-Token": "secret",
            "X-Query-Budget": "15",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["pending"] == 0
    assert data["retrying"] == 0
    assert data["failed"] == 0
    assert data["completed"] == 0
    assert data["total_active"] == 0


@pytest.mark.asyncio
async def test_get_dlq_stats_with_data(async_client, user_factory, job_factory):
    _, token = await _login_admin(async_client, user_factory)

    await job_factory(status=JobStatus.PENDING.value, payload={"id": 1})
    await job_factory(status=JobStatus.PENDING.value, payload={"id": 2})
    await job_factory(status=JobStatus.RETRYING.value, payload={"id": 3})
    await job_factory(status=JobStatus.FAILED.value, payload={"id": 4})
    await job_factory(status=JobStatus.COMPLETED.value, payload={"id": 5})

    response = await async_client.get(
        "/admin/dlq/stats",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Internal-Token": "secret",
            "X-Query-Budget": "15",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["pending"] == 2
    assert data["retrying"] == 1
    assert data["failed"] == 1
    assert data["completed"] == 1
    assert data["total_active"] == 3


@pytest.mark.asyncio
async def test_list_dlq_jobs_no_filter(async_client, user_factory, job_factory):
    _, token = await _login_admin(async_client, user_factory)

    for i in range(5):
        await job_factory(payload={"id": i}, job_type=f"type_{i}")

    response = await async_client.get(
        "/admin/dlq/jobs",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Internal-Token": "secret",
            "X-Query-Budget": "15",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["jobs"]) == 5
    assert data["total"] == 5
    # Verify fields in one job
    job = data["jobs"][0]
    assert "id" in job
    assert "job_type" in job
    assert "job_hash" in job
    assert job["job_hash"].endswith("...")
    assert "status" in job


@pytest.mark.asyncio
async def test_list_dlq_jobs_with_filter(async_client, user_factory, job_factory):
    _, token = await _login_admin(async_client, user_factory)

    await job_factory(status=JobStatus.PENDING.value, payload={"id": 1})
    await job_factory(status=JobStatus.FAILED.value, payload={"id": 2})

    # Filter by pending
    response = await async_client.get(
        "/admin/dlq/jobs",
        params={"status": "pending"},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Internal-Token": "secret",
            "X-Query-Budget": "15",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["jobs"]) == 1
    assert data["jobs"][0]["status"] == "pending"
    assert data["total"] == 1

    # Filter by failed
    response = await async_client.get(
        "/admin/dlq/jobs",
        params={"status": "failed"},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Internal-Token": "secret",
            "X-Query-Budget": "15",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["jobs"]) == 1
    assert data["jobs"][0]["status"] == "failed"
    assert data["total"] == 1


@pytest.mark.asyncio
async def test_list_dlq_jobs_invalid_status(async_client, user_factory):
    _, token = await _login_admin(async_client, user_factory)

    response = await async_client.get(
        "/admin/dlq/jobs",
        params={"status": "invalid"},
        headers={
            "Authorization": f"Bearer {token}",
            "Accept-Language": "en",
            "X-Internal-Token": "secret",
            "X-Query-Budget": "15",
        },
    )
    assert response.status_code == 400
    assert "Invalid status" in response.json()["detail"]


@pytest.mark.asyncio
async def test_retry_dlq_job_success(
    async_client, user_factory, job_factory, db_session
):
    _, token = await _login_admin(async_client, user_factory)
    job = await job_factory(status=JobStatus.FAILED.value)

    response = await async_client.post(
        f"/admin/dlq/retry/{job.id}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept-Language": "en",
            "X-Internal-Token": "secret",
            "X-Query-Budget": "15",
        },
    )
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert "queued for retry" in response.json()["message"]

    await db_session.refresh(job)
    assert job.status == JobStatus.PENDING.value
    assert job.next_retry_at is not None


@pytest.mark.asyncio
async def test_retry_dlq_job_not_found(async_client, user_factory):
    _, token = await _login_admin(async_client, user_factory)

    response = await async_client.post(
        "/admin/dlq/retry/9999",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Internal-Token": "secret",
            "X-Query-Budget": "15",
        },
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cleanup_dlq(async_client, user_factory, job_factory, db_session):
    _, token = await _login_admin(async_client, user_factory)

    # Old completed job
    old_date = datetime.now(UTC) - timedelta(days=10)
    await job_factory(
        status=JobStatus.COMPLETED.value, updated_at=old_date, payload={"id": "old"}
    )

    # Recent completed job
    await job_factory(
        status=JobStatus.COMPLETED.value,
        updated_at=datetime.now(UTC),
        payload={"id": "recent"},
    )

    response = await async_client.delete(
        "/admin/dlq/cleanup",
        params={"older_than_days": 7},
        headers={
            "Authorization": f"Bearer {token}",
            "X-Internal-Token": "secret",
            "X-Query-Budget": "15",
        },
    )
    assert response.status_code == 200
    assert response.json()["deleted_count"] == 1
    assert response.json()["older_than_days"] == 7
