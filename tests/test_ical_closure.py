"""Focused iCalendar closure tests for timezone and empty-description paths."""

from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from app.services.ical import _format_dt, generate_schedule_ics


def test_format_dt_converts_non_utc_aware_datetime_to_utc():
    value = datetime(2026, 7, 26, 15, 30, tzinfo=timezone(timedelta(hours=3)))

    assert _format_dt(value) == "20260726T123000Z"


def test_generate_schedule_ics_omits_empty_description():
    group = SimpleNamespace(name="Group")
    lesson = SimpleNamespace(
        id="lesson-1",
        weekday="monday",
        start_time=time(9, 0),
        end_time=time(10, 0),
        parity="both",
        subject="Mathematics",
        lesson_type="seminar",
        teacher=None,
        room=None,
    )

    with patch("app.services.ical.translate_lesson_type", return_value=None):
        result = generate_schedule_ics(group, [lesson], weeks=1, locale="en")

    assert "BEGIN:VEVENT" in result
    assert "DESCRIPTION:" not in result
    assert "LOCATION:" not in result
