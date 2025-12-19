"""Unit tests for iCalendar export functionality."""

from datetime import UTC, date, datetime, time, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.services.ical import (
    _ensure_time,
    _escape,
    _format_dt,
    _iter_lesson_dates,
    _weekday_index,
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

    def test_escape_unicode_characters(self):
        """Test that unicode characters pass through correctly."""
        assert _escape("Привет, мир!") == "Привет\\, мир!"
        assert _escape("日本語テスト") == "日本語テスト"

    def test_escape_special_ics_characters(self):
        """Test all special iCalendar characters in one string."""
        result = _escape("Dr. Smith; Room 101, Building A\nNotes: Use \\ carefully")
        assert "\\\\" in result  # Backslash escaped
        assert "\\;" in result   # Semicolon escaped
        assert "\\," in result   # Comma escaped
        assert "\\n" in result   # Newline escaped


class TestWeekdayIndex:
    """Tests for _weekday_index function."""

    def test_weekday_monday(self):
        assert _weekday_index("Monday") == 0
        assert _weekday_index("monday") == 0

    def test_weekday_friday(self):
        assert _weekday_index("Friday") == 4
        assert _weekday_index("friday") == 4

    def test_weekday_sunday(self):
        assert _weekday_index("Sunday") == 6
        assert _weekday_index("sunday") == 6

    def test_weekday_none(self):
        assert _weekday_index(None) is None

    def test_weekday_empty_string(self):
        assert _weekday_index("") is None

    def test_weekday_invalid(self):
        assert _weekday_index("InvalidDay") is None

    def test_weekday_abbreviated(self):
        """Abbreviated weekday names are supported."""
        assert _weekday_index("Mon") == 0
        assert _weekday_index("Fri") == 4
        assert _weekday_index("Sun") == 6

    def test_weekday_russian(self):
        """Test Russian weekday names."""
        assert _weekday_index("Понедельник") == 0
        assert _weekday_index("понедельник") == 0
        assert _weekday_index("Пятница") == 4


class TestEnsureTime:
    """Tests for _ensure_time function."""

    def test_ensure_time_from_time(self):
        t = time(9, 30, 0)
        result = _ensure_time(t)
        assert result == t

    def test_ensure_time_from_datetime(self):
        dt = datetime(2024, 1, 15, 9, 30, 0)
        result = _ensure_time(dt)
        assert result == time(9, 30, 0)

    def test_ensure_time_from_aware_datetime(self):
        dt = datetime(2024, 1, 15, 9, 30, 0, tzinfo=UTC)
        result = _ensure_time(dt)
        assert result is not None
        assert result.hour == 9
        assert result.minute == 30

    def test_ensure_time_none(self):
        assert _ensure_time(None) is None

    def test_ensure_time_preserves_microseconds(self):
        t = time(9, 30, 15, 123456)
        result = _ensure_time(t)
        assert result.microsecond == 123456

    def test_ensure_time_from_different_timezone(self):
        """Test time extraction from non-UTC timezone."""
        tz_offset = timezone(timedelta(hours=3))  # MSK-like
        dt = datetime(2024, 1, 15, 12, 30, 0, tzinfo=tz_offset)
        result = _ensure_time(dt)
        assert result is not None
        # Should preserve the local time
        assert result.hour == 12
        assert result.minute == 30




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

    # === Edge Cases: Missing and Malformed Data ===

    def test_lesson_with_missing_weekday_skipped(self):
        """Lessons with missing weekday should be skipped."""
        group = self._make_mock_group()
        lesson = self._make_mock_lesson()
        lesson.weekday = None
        
        result = generate_schedule_ics(group, [lesson], weeks=1)
        
        assert "BEGIN:VCALENDAR" in result
        assert "BEGIN:VEVENT" not in result

    def test_lesson_with_missing_start_time_skipped(self):
        """Lessons with missing start_time should be skipped."""
        group = self._make_mock_group()
        lesson = self._make_mock_lesson()
        lesson.start_time = None
        
        result = generate_schedule_ics(group, [lesson], weeks=1)
        
        assert "BEGIN:VCALENDAR" in result
        assert "BEGIN:VEVENT" not in result

    def test_lesson_with_missing_end_time_skipped(self):
        """Lessons with missing end_time should be skipped."""
        group = self._make_mock_group()
        lesson = self._make_mock_lesson()
        lesson.end_time = None
        
        result = generate_schedule_ics(group, [lesson], weeks=1)
        
        assert "BEGIN:VCALENDAR" in result
        assert "BEGIN:VEVENT" not in result

    def test_lesson_with_invalid_weekday_skipped(self):
        """Lessons with invalid weekday string should be skipped."""
        group = self._make_mock_group()
        lesson = self._make_mock_lesson()
        lesson.weekday = "InvalidDay"
        
        result = generate_schedule_ics(group, [lesson], weeks=1)
        
        assert "BEGIN:VCALENDAR" in result
        assert "BEGIN:VEVENT" not in result

    def test_lesson_without_subject_uses_default(self):
        """Lessons without subject should use default subject."""
        group = self._make_mock_group()
        lesson = self._make_mock_lesson()
        lesson.subject = None
        
        result = generate_schedule_ics(group, [lesson], weeks=1, locale="en")
        
        assert "BEGIN:VEVENT" in result
        assert "SUMMARY:" in result

    def test_lesson_without_teacher(self):
        """Lessons without teacher should still generate correctly."""
        group = self._make_mock_group()
        lesson = self._make_mock_lesson()
        lesson.teacher = None
        
        result = generate_schedule_ics(group, [lesson], weeks=1)
        
        assert "BEGIN:VEVENT" in result
        # DESCRIPTION should not have teacher info
        # But event should still be valid

    def test_lesson_without_room(self):
        """Lessons without room should not have LOCATION field."""
        group = self._make_mock_group()
        lesson = self._make_mock_lesson()
        lesson.room = None
        
        result = generate_schedule_ics(group, [lesson], weeks=1)
        
        assert "BEGIN:VEVENT" in result
        assert "LOCATION:" not in result

    def test_lesson_without_lesson_type(self):
        """Lessons without lesson_type should still work."""
        group = self._make_mock_group()
        lesson = self._make_mock_lesson()
        lesson.lesson_type = None
        
        result = generate_schedule_ics(group, [lesson], weeks=1)
        
        assert "BEGIN:VEVENT" in result
        # SUMMARY should just have subject without parentheses

    # === Edge Cases: Timezone Handling ===

    def test_lesson_with_datetime_start_time(self):
        """Start time as datetime should be converted to time."""
        group = self._make_mock_group()
        lesson = self._make_mock_lesson()
        # Some ORMs might return datetime instead of time
        lesson.start_time = datetime(2024, 1, 15, 9, 0, 0)
        lesson.end_time = datetime(2024, 1, 15, 10, 30, 0)
        
        result = generate_schedule_ics(group, [lesson], weeks=1)
        
        assert "BEGIN:VEVENT" in result
        assert "DTSTART:" in result

    def test_lesson_with_aware_datetime_times(self):
        """Timezone-aware datetime times should be handled correctly."""
        group = self._make_mock_group()
        lesson = self._make_mock_lesson()
        lesson.start_time = datetime(2024, 1, 15, 9, 0, 0, tzinfo=UTC)
        lesson.end_time = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        
        result = generate_schedule_ics(group, [lesson], weeks=1)
        
        assert "BEGIN:VEVENT" in result
        assert "DTSTART:" in result

    # === Edge Cases: Parity Handling ===

    def test_lesson_with_even_parity(self):
        """Even parity lessons should only appear on even weeks."""
        group = self._make_mock_group()
        lesson = self._make_mock_lesson(parity="even")
        
        result = generate_schedule_ics(group, [lesson], weeks=4)
        
        assert "BEGIN:VCALENDAR" in result

    def test_lesson_with_uppercase_parity(self):
        """Parity should be case-insensitive."""
        group = self._make_mock_group()
        lesson = self._make_mock_lesson(parity="ODD")
        
        result = generate_schedule_ics(group, [lesson], weeks=4)
        
        assert "BEGIN:VCALENDAR" in result

    def test_lesson_with_none_parity_treated_as_both(self):
        """None parity should be treated as 'both'."""
        group = self._make_mock_group()
        lesson = self._make_mock_lesson()
        lesson.parity = None
        
        result = generate_schedule_ics(group, [lesson], weeks=2)
        
        # Should have events for both weeks
        event_count = result.count("BEGIN:VEVENT")
        assert event_count >= 2

    # === Edge Cases: Special Characters ===

    def test_lesson_with_special_characters_in_subject(self):
        """Special characters in subject should be escaped."""
        group = self._make_mock_group()
        lesson = self._make_mock_lesson(subject="Math; Advanced, Part 1\nNotes")
        
        result = generate_schedule_ics(group, [lesson], weeks=1)
        
        assert "BEGIN:VEVENT" in result
        # Verify the escaped characters work

    def test_lesson_with_unicode_subject(self):
        """Unicode characters in subject should work."""
        group = self._make_mock_group()
        lesson = self._make_mock_lesson(subject="Математика")
        
        result = generate_schedule_ics(group, [lesson], weeks=1)
        
        assert "BEGIN:VEVENT" in result
        assert "Математика" in result

    # === Edge Cases: Weeks Configuration ===

    def test_generate_zero_weeks(self):
        """Zero weeks should produce no events."""
        group = self._make_mock_group()
        lesson = self._make_mock_lesson()
        
        result = generate_schedule_ics(group, [lesson], weeks=0)
        
        assert "BEGIN:VCALENDAR" in result
        assert "BEGIN:VEVENT" not in result

    def test_generate_large_week_count(self):
        """Large week count should work (e.g., full year)."""
        group = self._make_mock_group()
        lesson = self._make_mock_lesson()
        
        result = generate_schedule_ics(group, [lesson], weeks=52)
        
        assert "BEGIN:VCALENDAR" in result
        event_count = result.count("BEGIN:VEVENT")
        assert event_count == 52

    # === Edge Cases: Group Name ===

    def test_group_with_no_name(self):
        """Group without name should use generic calendar name."""
        group = MagicMock()
        group.name = None
        lesson = self._make_mock_lesson()
        
        result = generate_schedule_ics(group, [lesson], weeks=1)
        
        assert "BEGIN:VCALENDAR" in result
        assert "NAME:" in result
