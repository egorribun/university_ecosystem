from datetime import UTC, datetime

import pytest

from app.api.schedule import _SCHEDULE_CACHE_CONTROL
from app.localization import translate, translate_lesson_type
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
        start_time=datetime(2024, 1, 1, 9, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 1, 10, 30, tzinfo=UTC),
        parity="both",
        lesson_type="lecture",
    )

    ics = generate_schedule_ics(group, [lesson], weeks=1, locale="en")

    assert "BEGIN:VCALENDAR" in ics
    assert "END:VCALENDAR" in ics
    expected_type = translate_lesson_type("lecture", locale="en") or "lecture"
    assert f"SUMMARY:Алгебра ({expected_type})" in ics
    assert "DTSTART:" in ics
    assert "DTEND:" in ics
    expected_type_line = translate(
        "schedule.ics.description.lesson_type",
        locale="en",
        lesson_type=expected_type,
    )
    assert expected_type_line in ics
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
        start_time=datetime(2024, 1, 1, 9, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 1, 10, 30, tzinfo=UTC),
        parity="both",
        lesson_type="practice",
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
    expected_type_en = translate_lesson_type("practice", locale="en")
    expected_en = translate("schedule.ics.description.room", locale="en", room="А-101")
    assert expected_en in response.text
    assert expected_type_en in response.text

    response_ru = await async_client.get(
        f"/schedule/ics?group={group.id}", headers={"Accept-Language": "ru"}
    )
    assert response_ru.status_code == 200
    assert response_ru.headers.get("content-language") == "ru"
    expected_ru = translate(
        "schedule.ics.description.teacher", locale="ru", teacher="Проф. Смирнов"
    )
    assert expected_ru in response_ru.text


def _contains_cyrillic(text: str) -> bool:
    return any("а" <= ch <= "я" or "А" <= ch <= "Я" for ch in text)


def test_generate_schedule_ics_english_avoids_cyrillic_labels() -> None:
    group = models.Group(id=2, name="IU-22", course=1, faculty="IT")
    lesson = models.Schedule(
        id=42,
        group_id=group.id,
        subject="Mathematics",
        teacher="Dr. Smith",
        room="B-202",
        weekday="Tuesday",
        start_time=datetime(2024, 1, 2, 11, 0, tzinfo=UTC),
        end_time=datetime(2024, 1, 2, 12, 30, tzinfo=UTC),
        parity="both",
        lesson_type="ПЗ",
    )

    ics = generate_schedule_ics(group, [lesson], weeks=1, locale="en")

    lines = ics.split("\r\n")
    prodid_line = next(line for line in lines if line.startswith("PRODID:"))
    assert "//RU" not in prodid_line

    summary_line = next(line for line in lines if line.startswith("SUMMARY:"))
    assert not _contains_cyrillic(summary_line)

    description_line = next(line for line in lines if line.startswith("DESCRIPTION:"))
    assert not _contains_cyrillic(description_line)


@pytest.mark.anyio
async def test_schedule_endpoint_localizes_lesson_type(
    async_client, db_session
) -> None:
    group = models.Group(name="EN-01", course=1, faculty="IT")
    db_session.add(group)
    await db_session.commit()
    await db_session.refresh(group)

    lesson = models.Schedule(
        group_id=group.id,
        subject="Physics",
        teacher="Dr. Brown",
        room="Room 101",
        weekday="monday",
        start_time=datetime(2024, 3, 4, 9, 0, tzinfo=UTC),
        end_time=datetime(2024, 3, 4, 10, 30, tzinfo=UTC),
        parity="both",
        lesson_type="lecture",
    )
    db_session.add(lesson)
    await db_session.commit()

    response_en = await async_client.get(f"/schedule/{group.id}")
    assert response_en.status_code == 200
    payload_en = response_en.json()
    assert payload_en[0]["lesson_type"] == "lecture"
    expected_en = translate_lesson_type("lecture", locale="en")
    assert payload_en[0]["lesson_type_display"] == expected_en

    response_ru = await async_client.get(
        f"/schedule/{group.id}", headers={"Accept-Language": "ru"}
    )
    assert response_ru.status_code == 200
    payload_ru = response_ru.json()
    expected_ru = translate_lesson_type("lecture", locale="ru")
    assert payload_ru[0]["lesson_type_display"] == expected_ru


@pytest.mark.anyio
async def test_schedule_endpoint_preserves_existing_vary_values(
    async_client, db_session, fake_cache
) -> None:
    _ = fake_cache
    group = models.Group(name="VU-01", course=2, faculty="Physics")
    db_session.add(group)
    await db_session.commit()
    await db_session.refresh(group)

    lesson = models.Schedule(
        group_id=group.id,
        subject="Astronomy",
        teacher="Dr. Stone",
        room="Planetarium",
        weekday="tuesday",
        start_time=datetime(2024, 4, 2, 14, 0, tzinfo=UTC),
        end_time=datetime(2024, 4, 2, 15, 30, tzinfo=UTC),
        parity="both",
        lesson_type="seminar",
    )
    db_session.add(lesson)
    await db_session.commit()

    headers = {
        "Origin": "http://localhost:5173",
        "Accept-Language": "ru",
    }
    fresh_response = await async_client.get(f"/schedule/{group.id}", headers=headers)
    assert fresh_response.status_code == 200
    assert fresh_response.headers.get("Cache-Control") == _SCHEDULE_CACHE_CONTROL
    assert fresh_response.headers.get("Expires")
    fresh_vary_values = {
        value.strip()
        for value in fresh_response.headers.get("Vary", "").split(",")
        if value.strip()
    }
    assert {"Origin", "Accept-Language"} <= fresh_vary_values

    etag = fresh_response.headers.get("ETag")
    assert etag

    cached_response = await async_client.get(
        f"/schedule/{group.id}",
        headers={**headers, "If-None-Match": etag},
    )
    assert cached_response.status_code == 304
    assert cached_response.headers.get("Cache-Control") == _SCHEDULE_CACHE_CONTROL
    assert cached_response.headers.get("Expires")
    cached_vary_values = {
        value.strip()
        for value in cached_response.headers.get("Vary", "").split(",")
        if value.strip()
    }
    assert {"Origin", "Accept-Language"} <= cached_vary_values
