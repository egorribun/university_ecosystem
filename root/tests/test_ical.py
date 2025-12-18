"""Unit tests for iCalendar export functionality."""

from datetime import UTC, datetime, time, timedelta
from unittest.mock import MagicMock

import pytest

from app.services.ical import (
    _escape,
    _format_dt,
    _iter_lesson_dates,
    generate_schedule_ics,
)


class TestEscape:
    """Tests for _escape function."""

    def test_escape_empty_string(self):
        assert _escape("") == ""

    def test_escape_none(self):
        assert _escape(None) == ""

    def test_escape_plain_text(self):
        assert _escape("Hello World") == "Hello World"

    def test_escape_backslash(self):
        assert _escape("path\\to\\file") == "path\\\\to\\\\file"

    def test_escape_semicolon(self):
        assert _escape("first;second") == "first\\;second"

    def test_escape_comma(self):
        assert _escape("one,two") == "one\\,two"

    def test_escape_newline(self):
        assert _escape("line1\nline2") == "line1\\nline2"

    def test_escape_combined(self):
        assert _escape("a;b,c\\d\ne") == "a\\;b\\,c\\\\d\\ne"


class TestFormatDt:
    """Tests for _format_dt function."""

    def test_format_utc_datetime(self):
        dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        assert _format_dt(dt) == "20240115T103000Z"

    def test_format_naive_datetime(self):
        # Testing naive datetime formatting (without timezone)
        dt = datetime(2024, 1, 15, 10, 30, 0)  # noqa: DTZ001
        assert _format_dt(dt) == "20240115T103000"


class TestIterLessonDates:
    """Tests for _iter_lesson_dates function."""

    def test_iter_both_parity(self):
        from datetime import date

        monday = date(2024, 1, 1)  # Monday
        dates = list(
            _iter_lesson_dates(
                weekday_idx=0,
                parity="both",
                weeks=4,
                start_monday=monday,
                current_week_parity="odd",
            )
        )
        assert len(dates) == 4
        assert dates[0] == monday  # Week 1
        assert dates[1] == monday + timedelta(weeks=1)  # Week 2

    def test_iter_odd_parity_starting_odd(self):
        from datetime import date

        monday = date(2024, 1, 1)
        dates = list(
            _iter_lesson_dates(
                weekday_idx=0,
                parity="odd",
                weeks=6,
                start_monday=monday,
                current_week_parity="odd",
            )
        )
        # Should generate for weeks 0, 2, 4 (odd weeks when starting at odd)
        assert len(dates) == 3

    def test_iter_even_parity_starting_odd(self):
        from datetime import date

        monday = date(2024, 1, 1)
        dates = list(
            _iter_lesson_dates(
                weekday_idx=0,
                parity="even",
                weeks=6,
                start_monday=monday,
                current_week_parity="odd",
            )
        )
        # Should generate for weeks 1, 3, 5 (even weeks when starting at odd)
        assert len(dates) == 3


class TestGenerateScheduleIcs:
    """Tests for generate_schedule_ics function."""

    def _make_mock_group(self, name: str = "Test Group"):
        group = MagicMock()
        group.name = name
        return group

    def _make_mock_lesson(
        self,
        lesson_id: int = 1,
        weekday: str = "Monday",
        subject: str = "Math",
        teacher: str = "Dr. Smith",
        room: str = "101",
        parity: str = "both",
        start_time: time = time(9, 0),
        end_time: time = time(10, 30),
    ):
        lesson = MagicMock()
        lesson.id = lesson_id
        lesson.weekday = weekday
        lesson.subject = subject
        lesson.teacher = teacher
        lesson.room = room
        lesson.parity = parity
        lesson.start_time = start_time
        lesson.end_time = end_time
        lesson.lesson_type = "lecture"
        return lesson

    def test_generate_empty_schedule(self):
        group = self._make_mock_group()
        result = generate_schedule_ics(group, [], weeks=1)
        
        assert "BEGIN:VCALENDAR" in result
        assert "END:VCALENDAR" in result
        assert "VERSION:2.0" in result
        # Should not have any events
        assert "BEGIN:VEVENT" not in result

    def test_generate_single_lesson(self):
        group = self._make_mock_group("CS-101")
        lesson = self._make_mock_lesson(subject="Programming", room="A305")
        
        result = generate_schedule_ics(group, [lesson], weeks=1, locale="en")
        
        assert "BEGIN:VCALENDAR" in result
        assert "BEGIN:VEVENT" in result
        assert "SUMMARY:" in result
        assert "LOCATION:A305" in result
        assert "END:VEVENT" in result

    def test_generate_multiple_lessons(self):
        group = self._make_mock_group()
        lessons = [
            self._make_mock_lesson(lesson_id=1, subject="Math", weekday="Monday"),
            self._make_mock_lesson(lesson_id=2, subject="Physics", weekday="Tuesday"),
        ]
        
        result = generate_schedule_ics(group, lessons, weeks=1)
        
        # Count VEVENT occurrences 
        event_count = result.count("BEGIN:VEVENT")
        assert event_count >= 1

    def test_ics_format_crlf_endings(self):
        group = self._make_mock_group()
        result = generate_schedule_ics(group, [], weeks=1)
        
        # ICS spec requires CRLF line endings
        assert result.endswith("\r\n")

    def test_lesson_with_odd_parity(self):
        group = self._make_mock_group()
        lesson = self._make_mock_lesson(parity="odd")
        
        result = generate_schedule_ics(group, [lesson], weeks=4)
        
        assert "BEGIN:VCALENDAR" in result
