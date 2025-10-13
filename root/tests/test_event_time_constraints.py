from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app import crud
from app.models import models
from app.schemas import schemas

pytestmark = pytest.mark.anyio("asyncio")


async def test_create_event_guard(db_session, user_factory):
    user = await user_factory()
    starts = datetime.now(timezone.utc)
    payload = schemas.EventCreate.model_construct(
        title="Invalid",
        description=None,
        location=None,
        event_type=None,
        starts_at=starts,
        ends_at=starts,
        speaker=None,
        image_url=None,
        about=None,
    )
    with pytest.raises(ValueError, match="Время окончания"):
        await crud.create_event(db_session, payload, user_id=user.id)


async def test_update_event_guard(db_session, user_factory):
    user = await user_factory()
    starts = datetime.now(timezone.utc)
    ends = starts + timedelta(hours=1)
    valid = schemas.EventCreate(
        title="Valid",
        starts_at=starts,
        ends_at=ends,
    )
    record = await crud.create_event(db_session, valid, user_id=user.id)
    invalid_update = schemas.EventUpdate.model_construct(
        starts_at=starts,
        ends_at=starts,
        fields_set={"starts_at", "ends_at"},
    )
    with pytest.raises(ValueError, match="Время окончания"):
        await crud.update_event(db_session, record, invalid_update)


async def test_event_model_check_constraint(db_session, user_factory):
    user = await user_factory()
    starts = datetime.now(timezone.utc)
    event = models.Event(
        title="Broken",
        starts_at=starts,
        ends_at=starts,
        created_by=user.id,
    )
    db_session.add(event)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
