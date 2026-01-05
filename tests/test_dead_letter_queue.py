"""Tests for dead_letter_queue worker module.

Coverage targets:
- JobStatus: enum values
- compute_job_hash: hash computation
- DeadLetterQueue: various operations
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.workers.dead_letter_queue import (
    DeadLetterQueue,
    JobStatus,
    compute_job_hash,
)

# ============================================================
# JobStatus tests
# ============================================================


def test_job_status_values():
    """Test JobStatus enum values."""
    assert JobStatus.PENDING == "pending"
    assert JobStatus.RETRYING == "retrying"
    assert JobStatus.FAILED == "failed"
    assert JobStatus.COMPLETED == "completed"


# ============================================================
# compute_job_hash tests
# ============================================================


def test_compute_job_hash_consistency():
    """Test hash is consistent for same input."""
    hash1 = compute_job_hash("email", {"to": "user@example.com"})
    hash2 = compute_job_hash("email", {"to": "user@example.com"})
    assert hash1 == hash2


def test_compute_job_hash_different_job_type():
    """Test different job types produce different hashes."""
    hash1 = compute_job_hash("email", {"data": "test"})
    hash2 = compute_job_hash("push", {"data": "test"})
    assert hash1 != hash2


def test_compute_job_hash_different_payload():
    """Test different payloads produce different hashes."""
    hash1 = compute_job_hash("email", {"data": "test1"})
    hash2 = compute_job_hash("email", {"data": "test2"})
    assert hash1 != hash2


def test_compute_job_hash_empty_payload():
    """Test hash with empty payload."""
    result = compute_job_hash("job", {})
    assert len(result) == 64  # SHA256 hex digest


def test_compute_job_hash_nested_payload():
    """Test hash with nested payload."""
    payload = {"user": {"id": 1, "name": "Test"}, "items": [1, 2, 3]}
    result = compute_job_hash("complex", payload)
    assert len(result) == 64


# ============================================================
# DeadLetterQueue tests
# ============================================================


@pytest.fixture
def mock_session():
    """Create mock AsyncSession."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture
def dlq(mock_session):
    """Create DeadLetterQueue instance."""
    return DeadLetterQueue(mock_session)


@pytest.mark.anyio
async def test_add_failed_job_success(dlq, mock_session):
    """Test adding a failed job."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    await dlq.add_failed_job(
        job_type="email",
        payload={"to": "user@example.com"},
        error_message="Connection failed",
    )

    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()


@pytest.mark.anyio
async def test_add_failed_job_duplicate(dlq, mock_session):
    """Test duplicate job is skipped."""
    existing_job = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing_job
    mock_session.execute.return_value = mock_result

    result = await dlq.add_failed_job(
        job_type="email",
        payload={"to": "user@example.com"},
        error_message="Connection failed",
    )

    assert result is None


@pytest.mark.anyio
async def test_get_jobs_ready_for_retry(dlq, mock_session):
    """Test getting jobs ready for retry."""
    mock_jobs = [MagicMock(), MagicMock()]
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = mock_jobs
    mock_session.execute.return_value = mock_result

    result = await dlq.get_jobs_ready_for_retry(limit=10)

    assert result == mock_jobs


@pytest.mark.anyio
async def test_mark_job_retrying(dlq, mock_session):
    """Test marking job as retrying."""
    job = MagicMock()
    job.status = JobStatus.PENDING

    await dlq.mark_job_retrying(job)

    assert job.status == JobStatus.RETRYING
    mock_session.commit.assert_called_once()


@pytest.mark.anyio
async def test_mark_job_completed(dlq, mock_session):
    """Test marking job as completed."""
    job = MagicMock()
    job.status = JobStatus.RETRYING
    job.job_type = "email"

    await dlq.mark_job_completed(job)

    assert job.status == JobStatus.COMPLETED
    mock_session.commit.assert_called_once()


@pytest.mark.anyio
async def test_get_queue_stats(dlq, mock_session):
    """Test getting queue statistics."""
    # Create mock rows with proper attributes
    mock_row1 = MagicMock()
    mock_row1.status = JobStatus.PENDING.value
    mock_row1.count = 5

    mock_row2 = MagicMock()
    mock_row2.status = JobStatus.FAILED.value
    mock_row2.count = 2

    mock_result = MagicMock()
    mock_result.__iter__ = lambda self: iter([mock_row1, mock_row2])
    mock_session.execute.return_value = mock_result

    stats = await dlq.get_queue_stats()

    assert stats[JobStatus.PENDING.value] == 5
    assert stats[JobStatus.FAILED.value] == 2


@pytest.mark.anyio
async def test_cleanup_completed_jobs(dlq, mock_session):
    """Test cleaning up old completed jobs."""
    mock_result = MagicMock()
    mock_result.rowcount = 10
    mock_session.execute.return_value = mock_result

    deleted = await dlq.cleanup_completed_jobs(older_than_days=7)

    assert deleted == 10
    mock_session.commit.assert_called_once()
