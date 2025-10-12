import asyncio
import io
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import UploadFile

from app.api import routes
from app.core.config import settings
from app.models import models


@pytest.mark.asyncio
async def test_upload_event_file_offloads_io(
    tmp_path, monkeypatch, db_session, user_factory
):
    admin = await user_factory(role="admin")
    event = models.Event(
        title="Test Event",
        description="desc",
        location="",
        event_type="workshop",
        starts_at=datetime.now(timezone.utc),
        ends_at=datetime.now(timezone.utc) + timedelta(hours=1),
        created_by=admin.id,
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)

    payload = b"example data"
    upload = UploadFile(filename="notes.txt", file=io.BytesIO(payload))

    calls: list[tuple[object, tuple[object, ...], dict[str, object]]] = []

    async def fake_to_thread(func, /, *args, **kwargs):  # type: ignore[override]
        calls.append((func, args, kwargs))
        return func(*args, **kwargs)

    monkeypatch.setattr(routes, "asyncio", asyncio)
    monkeypatch.setattr(routes.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(settings, "static_dir_path", tmp_path)

    result = await routes.upload_event_file(event.id, upload, db=db_session, user=admin)

    assert result.event_id == event.id
    assert result.file_url.startswith("/static/event_files/")
    stored_path = tmp_path / "event_files" / result.file_url.rsplit("/", 1)[-1]
    assert stored_path.exists()
    assert stored_path.read_bytes() == payload
    assert any(func.__name__ == "mkdir" for func, _, _ in calls)
    assert any(func.__name__ == "write_bytes" for func, _, _ in calls)
