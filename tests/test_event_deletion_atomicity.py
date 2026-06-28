from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

import app.models as models
from app.api import events


@pytest.mark.asyncio
async def test_delete_event_file_atomicity_vulnerability_fix(
    db_session, user_factory, monkeypatch
):
    """
    RZ-003 Verification:
    Ensures that storage deletion happens BEFORE DB commit.
    We mock storage deletion to fail, and verify that the DB record
    still exists (was not committed then orphaned).
    """
    # 1. Setup
    admin = await user_factory(role="admin")
    event = models.Event(
        title="Atomicity Test",
        created_by=admin.id,
        event_type="workshop",
        starts_at=datetime.now(UTC),
        ends_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(event)
    await db_session.commit()

    file_record = models.EventFile(
        event_id=event.id,
        file_url="/static/event_files/test.txt",
        description="test.txt",
    )
    db_session.add(file_record)
    await db_session.commit()
    await db_session.refresh(file_record)
    file_id = file_record.id

    # 2. Mock storage deletion to FAIL
    async def failing_delete(url: str):
        raise RuntimeError("Storage failure")

    monkeypatch.setattr(events, "delete_static_file", failing_delete)

    # 3. Execution
    # The new logic in events.py:delete_event_file calls delete_static_file
    # and THEN db.delete(file_record) + db.commit().
    # If the storage delete fails, the handler should raise and NOT commit.

    with pytest.raises(RuntimeError) as excinfo:
        await events.delete_event_file(
            file_id,
            request=None,
            db=db_session,
            user=admin,
            checker=AsyncMock(return_value=True),
        )

    assert "Storage failure" in str(excinfo.value)

    # 4. Verification: DB record must still exist
    # If we find it, it means it wasn't deleted (rollback or just not reached commit).
    # Since we are in a test session, a rollback should happen on exception handling or
    # at least it should NOT be committed.

    # We need to refresh the session or use a fresh query
    from sqlalchemy import select

    stmt = select(models.EventFile).where(models.EventFile.id == file_id)
    result = await db_session.execute(stmt)
    persisted = result.scalar_one_or_none()

    assert persisted is not None, "File record was deleted despite storage failure!"
    assert persisted.file_url == "/static/event_files/test.txt"
