from datetime import datetime

import pytest

from app.localization import translate
from app.models import models
from app.services.ical import generate_schedule_ics


def test_generate_schedule_ics_includes_lessons() -> None:
    group = models.Group(id=1, name="ИУ-21", course=1, faculty="ИТ")
    lesson = models.Schedule(
        id=10,
        group_id=group.id,
        subject="Алгебра",
        teacher="Проф. Смирнов",
        room="А-101",
        weekday="Понедельник",
        start_time=datetime(2024, 1, 1, 9, 0),
        end_time=datetime(2024, 1, 1, 10, 30),
        parity="both",
        lesson_type="Лекция",
    )

    ics = generate_schedule_ics(group, [lesson], weeks=1, locale="en")

    assert "BEGIN:VCALENDAR" in ics
    assert "END:VCALENDAR" in ics
    assert "SUMMARY:Алгебра (Лекция)" in ics
    assert "DTSTART:" in ics
    assert "DTEND:" in ics
    expected_teacher = translate(
        "schedule.ics.description.teacher", locale="en", teacher="Проф. Смирнов"
    )
    assert expected_teacher in ics


@pytest.mark.anyio
async def test_schedule_ics_endpoint(async_client, db_session) -> None:
    group = models.Group(name="ИУ-21", course=1, faculty="ИТ")
    db_session.add(group)
    await db_session.commit()
    await db_session.refresh(group)

    lesson = models.Schedule(
        group_id=group.id,
        subject="Алгебра",
        teacher="Проф. Смирнов",
        room="А-101",
        weekday="Понедельник",
        start_time=datetime(2024, 1, 1, 9, 0),
        end_time=datetime(2024, 1, 1, 10, 30),
        parity="both",
        lesson_type="Лекция",
    )
    db_session.add(lesson)
    await db_session.commit()

    response = await async_client.get(f"/schedule/ics?group={group.id}")

    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("text/calendar")
    disposition = response.headers.get("content-disposition", "")
    assert "schedule-" in disposition.lower()
    assert response.headers.get("content-language") == "en"
    assert "Алгебра" in response.text
    expected_en = translate("schedule.ics.description.room", locale="en", room="А-101")
    assert expected_en in response.text

    response_ru = await async_client.get(
        f"/schedule/ics?group={group.id}", headers={"Accept-Language": "ru"}
    )
    assert response_ru.status_code == 200
    assert response_ru.headers.get("content-language") == "ru"
    expected_ru = translate(
        "schedule.ics.description.teacher", locale="ru", teacher="Проф. Смирнов"
    )
    assert expected_ru in response_ru.text
