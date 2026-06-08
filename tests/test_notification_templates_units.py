"""Direct unit tests for app/services/notification_templates.py.

Companion to test_notification_templates.py (which exercises the happy paths via
the build_payload wrapper). This file targets the helpers + builder fallback /
edge branches + the render entry point directly. Pure-function module — zero deps
(every builder is a pure transform of a payload Mapping + the file-based
``translate``). Assertions favour DETERMINISTIC structure (tags, topics,
data-payload keys, raw-input-derived body lines) over translated text, so they
don't break when locale files change; translated title/body are only asserted
non-empty.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest

from app.services.notification_templates import (
    ScenarioContext,
    _build_comment,
    _build_event,
    _build_news,
    _build_schedule_change,
    _build_schedule_reminder,
    _build_system,
    _clean_text,
    _datetime_details,
    _format_room,
    _normalize_type,
    _parse_datetime_like,
    render_notification_template,
)

# ─── _clean_text ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("plain", "plain"),
        ("<b>bold</b> text", "bold text"),  # tags stripped
        ("a    b\n\tc", "a b c"),  # whitespace collapsed
        ("Tom &amp; Jerry", "Tom & Jerry"),  # html-unescape
        (42, "42"),  # non-str coerced
    ],
)
def test_clean_text_variants(value, expected) -> None:
    assert _clean_text(value) == expected


def test_clean_text_truncates_to_limit() -> None:
    result = _clean_text("word " * 50, limit=20)
    assert result is not None
    assert len(result) <= 20
    assert result.endswith("…")


def test_clean_text_all_tags_becomes_none() -> None:
    # "<br>" -> " " -> stripped to "" -> None (the second empty-check branch).
    assert _clean_text("<br>") is None


# ─── _format_room ───────────────────────────────────────────────────────────────


def test_format_room_none_and_empty() -> None:
    assert _format_room(None) is None
    assert _format_room("   ") is None


def test_format_room_prefixed_returned_as_is() -> None:
    # Already-labelled room (starts with a known prefix) is returned verbatim,
    # NOT re-wrapped by translate.
    assert _format_room("Room 305") == "Room 305"
    assert _format_room("aud 12") == "aud 12"


def test_format_room_bare_number_is_labelled() -> None:
    labelled = _format_room("101", locale="en")
    assert labelled is not None
    assert "101" in labelled


# ─── _parse_datetime_like ─────────────────────────────────────────────────────


def test_parse_datetime_passthrough() -> None:
    dt = datetime(2026, 1, 15, 10, 0, tzinfo=UTC)
    assert _parse_datetime_like(dt) is dt


def test_parse_datetime_from_timestamp() -> None:
    parsed = _parse_datetime_like(1_700_000_000)
    assert isinstance(parsed, datetime)
    assert parsed.tzinfo is UTC


def test_parse_datetime_overflow_returns_none() -> None:
    assert _parse_datetime_like(1e308 * 10) is None  # inf -> error branch


def test_parse_datetime_iso_string() -> None:
    parsed = _parse_datetime_like("2026-01-15T10:00:00")
    assert isinstance(parsed, datetime)
    assert parsed.year == 2026


def test_parse_datetime_z_suffix() -> None:
    parsed = _parse_datetime_like("2026-01-15T10:00:00Z")
    assert isinstance(parsed, datetime)
    assert parsed.tzinfo is not None  # Z -> +00:00


@pytest.mark.parametrize("value", ["", "   ", "not-a-date", None, ["x"], {"a": 1}])
def test_parse_datetime_invalid_returns_none(value) -> None:
    assert _parse_datetime_like(value) is None


# ─── _datetime_details ────────────────────────────────────────────────────────


def test_datetime_details_none() -> None:
    assert _datetime_details(None) == (None, None, None)
    assert _datetime_details("garbage") == (None, None, None)


def test_datetime_details_aware() -> None:
    date_part, time_part, iso = _datetime_details(
        datetime(2026, 3, 4, 9, 30, tzinfo=UTC)
    )
    assert date_part is not None and re.fullmatch(r"\d{2}\.\d{2}", date_part)
    assert time_part is not None and re.fullmatch(r"\d{2}:\d{2}", time_part)
    assert iso is not None and iso.startswith("2026-03-04")


def test_datetime_details_naive_assumes_utc() -> None:
    # A naive datetime is treated as UTC; the ISO carries a UTC offset.
    _, _, iso = _datetime_details("2026-03-04T09:30:00")
    assert iso is not None
    assert "+00:00" in iso


# ─── ScenarioContext ──────────────────────────────────────────────────────────


def test_scenario_context_get_top_level_and_skip_empty() -> None:
    ctx = ScenarioContext({"a": "", "b": None, "c": "value"})
    # a (empty) + b (None) are skipped, c is returned.
    assert ctx.get("a", "b", "c") == "value"


def test_scenario_context_get_nested_data() -> None:
    ctx = ScenarioContext({"data": {"nested": "deep"}})
    assert ctx.get("nested") == "deep"


def test_scenario_context_get_missing_returns_none() -> None:
    assert ScenarioContext({}).get("missing") is None


def test_scenario_context_get_text_strips() -> None:
    ctx = ScenarioContext({"x": "  hi  ", "blank": "   "})
    assert ctx.get_text("x") == "hi"
    assert ctx.get_text("blank") is None
    assert ctx.get_text("absent") is None


def test_scenario_context_get_identifier_numeric_and_bool() -> None:
    assert ScenarioContext({"id": 7}).get_identifier("id") == "7"
    assert ScenarioContext({"id": 7.9}).get_identifier("id") == "7"
    assert ScenarioContext({"id": True}).get_identifier("id") is None  # bool -> None
    assert ScenarioContext({"id": " abc "}).get_identifier("id") == "abc"
    assert ScenarioContext({}).get_identifier("id") is None


def test_scenario_context_get_url_default() -> None:
    assert ScenarioContext({}).get_url("url", default="/fallback") == "/fallback"
    assert ScenarioContext({"url": "/x"}).get_url("url") == "/x"
    assert ScenarioContext({"url": "  "}).get_url("url", default="/d") == "/d"


# ─── _build_schedule_change ───────────────────────────────────────────────────


def test_build_schedule_change_full() -> None:
    out = _build_schedule_change(
        ScenarioContext(
            {
                "subject": "Calculus",
                "summary": "Cancelled",
                "comment": "Room flooded",
                "date": "04.03",
                "time": "09:30",
                "room": "Room 305",
                "teacher": "Dr. Ada",
                "group": "CS-101",
                "lesson_id": 42,
            }
        ),
        locale="en",
    )
    assert out["topic"] == "schedule"
    assert out["tag"] == "schedule-change:42"
    assert out["renotify"] is True
    assert "Cancelled" in out["body"]
    assert "Room flooded" in out["body"]
    assert "04.03 09:30" in out["body"]
    assert "Room 305" in out["body"]
    assert out["data"]["subject"] == "Calculus"
    assert out["data"]["group"] == "CS-101"
    assert out["data"]["lessonId"] == "42"
    assert isinstance(out["title"], str) and out["title"]


def test_build_schedule_change_minimal_uses_no_details() -> None:
    out = _build_schedule_change(ScenarioContext({}), locale="en")
    assert out["tag"] == "schedule-change"  # no identifier
    assert out["body"]  # no_details fallback line
    assert out["data"] == {"url": "/schedule", "category": "schedule"}


def test_build_schedule_change_date_only_and_time_only() -> None:
    date_only = _build_schedule_change(ScenarioContext({"date": "04.03"}), locale="en")
    assert "04.03" in date_only["body"]
    time_only = _build_schedule_change(ScenarioContext({"time": "09:30"}), locale="en")
    assert "09:30" in time_only["body"]


def test_build_schedule_change_comment_equal_summary_not_duplicated() -> None:
    out = _build_schedule_change(
        ScenarioContext({"summary": "Moved", "comment": "Moved"}), locale="en"
    )
    assert out["body"].count("Moved") == 1


# ─── _build_schedule_reminder ─────────────────────────────────────────────────


def test_build_schedule_reminder_with_auto_datetime() -> None:
    out = _build_schedule_reminder(
        ScenarioContext(
            {
                "subject": "Physics",
                "lesson_type": "Lecture",
                "teacher": "Dr. Bohr",
                "room": "Room 9",
                "group": "PH-2",
                "starts_at": datetime(2026, 5, 1, 14, 0, tzinfo=UTC),
                "id": 5,
            }
        ),
        locale="en",
    )
    assert out["topic"] == "schedule"
    assert out["tag"] == "schedule-reminder:5"
    assert out["data"]["lessonType"] == "Lecture"
    assert out["data"]["room"] == "Room 9"
    assert out["data"]["startsAt"].startswith("2026-05-01")


def test_build_schedule_reminder_room_text_fallback() -> None:
    # location with no recognised prefix is still surfaced in data["room"];
    # "time" feeds the startsAt time_text fallback (not parseable as ISO).
    out = _build_schedule_reminder(
        ScenarioContext({"location": "Main Hall", "time": "10:00"}), locale="en"
    )
    assert out["data"]["room"]  # populated from formatted or raw text
    assert out["data"]["startsAt"] == "10:00"  # time_text fallback (no ISO)


def test_build_schedule_reminder_minimal() -> None:
    out = _build_schedule_reminder(ScenarioContext({}), locale="en")
    assert out["tag"] == "schedule-reminder"
    assert out["body"]


# ─── _build_news ──────────────────────────────────────────────────────────────


def test_build_news_full() -> None:
    out = _build_news(
        ScenarioContext(
            {
                "headline": "Big News",
                "summary": "Something <b>happened</b> today",
                "author": "Press Office",
                "id": "slug-1",
            }
        ),
        locale="en",
    )
    assert out["topic"] == "news"
    assert out["tag"] == "news:slug-1"
    assert out["renotify"] is False
    assert "Something happened today" in out["body"]  # tags stripped
    assert "Press Office" in out["body"]
    assert out["data"]["headline"] == "Big News"


def test_build_news_minimal() -> None:
    out = _build_news(ScenarioContext({}), locale="en")
    assert out["tag"] == "news"
    assert out["body"]  # no_summary fallback


# ─── _build_event ─────────────────────────────────────────────────────────────


def test_build_event_full() -> None:
    out = _build_event(
        ScenarioContext(
            {
                "title": "Hackathon",
                "summary": "48h of code",
                "location": "Lab A",
                "speaker": "Jane",
                "event_type": "Workshop",
                "starts_at": datetime(2026, 6, 10, 18, 0, tzinfo=UTC),
                "event_id": 99,
            }
        ),
        locale="en",
    )
    assert out["topic"] == "events"
    assert out["tag"] == "event:99"
    assert "48h of code" in out["body"]
    assert "Lab A" in out["body"]
    assert out["data"]["speaker"] == "Jane"
    assert out["data"]["eventType"] == "Workshop"
    assert out["data"]["startsAt"].startswith("2026-06-10")


def test_build_event_minimal_and_time_text_fallback() -> None:
    out = _build_event(ScenarioContext({"time": "19:00"}), locale="en")
    assert out["tag"] == "event"
    assert out["data"]["startsAt"] == "19:00"  # no ISO -> time_text


# ─── _build_system ────────────────────────────────────────────────────────────


def test_build_system_full() -> None:
    out = _build_system(
        ScenarioContext({"title": "Maintenance", "message": "Down at 02:00", "id": 3}),
        locale="en",
    )
    assert out["topic"] == "system"
    assert out["requireInteraction"] is True
    assert out["title"] == "Maintenance"  # subject used verbatim as title
    assert "Down at 02:00" in out["body"]
    assert out["tag"] == "system-message:3"
    assert out["data"]["messageId"] == "3"


def test_build_system_minimal() -> None:
    out = _build_system(ScenarioContext({}), locale="en")
    assert out["tag"] == "system-message"
    assert out["body"]  # no_details fallback
    assert isinstance(out["title"], str) and out["title"]


# ─── _build_comment (NOT covered by the build_payload tests) ──────────────────


def test_build_comment_full() -> None:
    out = _build_comment(
        ScenarioContext(
            {
                "news_title": "Launch",
                "comment_body": "Great post!",
                "user_name": "Bob",
                "news_id": 7,
            }
        ),
        locale="en",
    )
    assert out["topic"] == "news"
    assert out["url"] == "/news/7"
    assert out["tag"] == "news-comment:7"
    assert "Great post!" in out["body"]
    assert out["data"]["newsId"] == "7"


def test_build_comment_no_news_id() -> None:
    out = _build_comment(ScenarioContext({"comment_body": "Hi"}), locale="en")
    assert out["url"] == "/news"
    assert out["tag"] == "news-comment"
    assert out["data"]["newsId"] is None


# ─── _normalize_type ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, ""),
        ("", ""),
        ("Schedule.Change", "schedule.change"),
        ("schedule_change", "schedule.change"),
        ("schedule-change", "schedule.change"),
        ("  Lesson_Reminder  ", "lesson.reminder"),
    ],
)
def test_normalize_type(raw, expected) -> None:
    assert _normalize_type(raw) == expected


# ─── render_notification_template (public entry) ──────────────────────────────


def test_render_known_type() -> None:
    out = render_notification_template("news.new", {"headline": "Hi"}, locale="en")
    assert out is not None
    assert out["topic"] == "news"


def test_render_alias_resolution() -> None:
    # "event.created" is an alias for "events.new".
    out = render_notification_template("event.created", {"title": "X"}, locale="en")
    assert out is not None
    assert out["topic"] == "events"


def test_render_underscore_alias() -> None:
    # "lesson_reminder" -> normalize -> "lesson.reminder" -> alias -> schedule.reminder
    out = render_notification_template("lesson_reminder", {}, locale="en")
    assert out is not None
    assert out["topic"] == "schedule"


def test_render_unknown_type_returns_none() -> None:
    assert render_notification_template("totally.unknown", {}, locale="en") is None
    assert render_notification_template(None, {}, locale="en") is None


def test_render_none_data_defaults_to_empty() -> None:
    out = render_notification_template("system.message", None, locale="en")
    assert out is not None
    assert out["topic"] == "system"
