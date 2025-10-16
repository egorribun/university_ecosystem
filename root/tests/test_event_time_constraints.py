from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app import crud
from app.localization import translate
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
    with pytest.raises(
        ValueError,
        match=translate("validation.events.end_after_start"),
    ):
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
    with pytest.raises(
        ValueError,
        match=translate("validation.events.end_after_start"),
    ):
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


async def test_get_all_events_respects_locale(db_session, user_factory):
    admin = await user_factory(role="admin")
    student = await user_factory()
    starts = datetime.now(timezone.utc)
    event = models.Event(
        title="Русское название",
        title_en="English title",
        description="Описание",
        description_en="English description",
        location="Москва",
        location_en="Moscow",
        event_type="лекция",
        event_type_en="Lecture",
        about="Русский текст",
        about_en="English text",
        starts_at=starts,
        ends_at=starts + timedelta(hours=2),
        created_by=admin.id,
    )
    db_session.add(event)
    await db_session.commit()
    await db_session.refresh(event)

    ru_events = await crud.get_all_events(db_session, user_id=student.id, locale="ru")
    en_events = await crud.get_all_events(db_session, user_id=student.id, locale="en")

    assert ru_events[0].title == "Русское название"
    assert ru_events[0].title_en == "English title"
    assert en_events[0].title == "English title"
    assert en_events[0].title_en == "English title"
    assert ru_events[0].description == "Описание"
    assert en_events[0].description == "English description"
    assert ru_events[0].location == "Москва"
    assert en_events[0].location == "Moscow"
    assert ru_events[0].event_type == "лекция"
    assert en_events[0].event_type == "Lecture"
    assert ru_events[0].about == "Русский текст"
    assert en_events[0].about == "English text"
