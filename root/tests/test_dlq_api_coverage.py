import pytest
from fastapi import status

from app.api.deps import get_current_admin_user
from app.main import app
from app.models.models import User
from app.workers.dead_letter_queue import DeadLetterJob, JobStatus


@pytest.mark.asyncio
async def test_dlq_api_flow(async_client, db_session, monkeypatch):
    """Test DLQ API endpoints with basic flow."""
    # 1. Mock admin user for the dependency
    mock_admin = User(id=1, email="admin@example.com", role="admin")

    # Use dependency override
    app.dependency_overrides[get_current_admin_user] = lambda: mock_admin

    try:
        # 2. Get stats (empty)
        response = await async_client.get("/admin/dlq/stats")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total_active"] == 0

        # 3. List jobs (empty)
        response = await async_client.get("/admin/dlq/jobs")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.json()["jobs"]) == 0

        # 4. Create a job manually to test more paths
        job = DeadLetterJob(
            job_type="test_job",
            job_hash="test_hash",
            payload='{"test": true}',
            status=JobStatus.FAILED.value,
            retry_count=3,
            max_retries=3,
        )
        db_session.add(job)
        await db_session.commit()
        await db_session.refresh(job)

        # 5. List jobs again
        response = await async_client.get("/admin/dlq/jobs?status=failed")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["jobs"]) == 1
        assert data["jobs"][0]["id"] == job.id

        # 6. Retry job
        response = await async_client.post(f"/admin/dlq/retry/{job.id}")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["success"] is True

        # Verify job is now pending
        await db_session.refresh(job)
        assert job.status == JobStatus.PENDING.value

        # 7. Cleanup
        response = await async_client.delete("/admin/dlq/cleanup?older_than_days=0")
        assert response.status_code == status.HTTP_200_OK
        # Should be 0 deleted because job 1 is PENDING now
        assert response.json()["deleted_count"] == 0

    finally:
        # Clean up dependency override
        if get_current_admin_user in app.dependency_overrides:
            del app.dependency_overrides[get_current_admin_user]
