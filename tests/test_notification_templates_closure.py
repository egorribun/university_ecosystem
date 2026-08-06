"""Direct branch coverage for notification scenario template builders."""

from __future__ import annotations

from datetime import UTC, datetime

from app.services import notification_templates as templates


def test_text_datetime_and_context_helpers_cover_fallbacks():
    assert templates._clean_text(None) is None
    assert templates._clean_text("   ") is None
    assert templates._clean_text("<p>&amp; value</p>") == "& value"
    assert templates._clean_text("<br>") is None
    truncated = templates._clean_text("abcdefgh", limit=5)
    assert truncated is not None and truncated.endswith("…") and len(truncated) <= 5
    assert templates._format_room("room 101") == "room 101"
    assert templates._parse_datetime_like(datetime(2026, 1, 1, tzinfo=UTC))
    assert templates._parse_datetime_like(1_700_000_000)
    assert templates._parse_datetime_like(float("inf")) is None
    assert templates._parse_datetime_like("") is None
    assert templates._parse_datetime_like("2026-01-01T12:00:00Z")
    assert templates._parse_datetime_like("not-a-date") is None
    assert templates._parse_datetime_like(object()) is None
    assert templates._datetime_details(None) == (None, None, None)
    assert templates._datetime_details(datetime(2026, 1, 1, 12, 0))[2]

    context = templates.ScenarioContext(
        {
            "empty": "",
            "data": {"name": " Nested ", "id": True, "first": "", "second": "ok"},
        }
    )
    assert context.get("empty", "name") == " Nested "
    assert context.get("missing") is None
    assert context.get_text("name") == "Nested"
    assert context.get_identifier("id") is None
    assert context.get_identifier("missing") is None
    assert context.get("first", "second") == "ok"
    assert context.get_url("empty", default="/fallback") == "/fallback"


def test_room_prefix_builder_handles_empty_translations(monkeypatch):
    monkeypatch.setattr(templates, "SUPPORTED_LOCALES", ("xx",))
    monkeypatch.setattr(templates, "translate", lambda *args, **kwargs: "")

    assert templates._room_label_prefixes() == {"room", "aud"}


def test_render_dispatches_aliases_and_rejects_unknown_types():
    schedule = templates.render_notification_template(
        "lesson-change",
        {"subject": "Math", "id": 7},
        locale="en",
    )
    assert schedule is not None
    assert schedule["topic"] == "schedule"
    assert templates.render_notification_template(None, None) is None
    assert templates.render_notification_template("unknown-type", {}) is None


def test_schedule_builders_cover_populated_and_empty_payloads():
    changed = templates.render_notification_template(
        "schedule.change",
        {
            "subject": "Math",
            "group": "A-1",
            "summary": "Moved",
            "comment": "Moved",
            "teacher": "Teacher",
            "date": "01.01",
            "time": "10:00",
            "room": "101",
            "id": 7,
        },
        locale="en",
    )
    assert changed is not None
    assert changed["data"]["lessonId"] == "7"

    empty_change = templates.render_notification_template(
        "schedule.update", {"comment": "only"}, locale="ru"
    )
    assert empty_change is not None
    assert empty_change["tag"] == "schedule-change"
    assert templates.render_notification_template("schedule.change", {"date": "01.01"})
    assert templates.render_notification_template("schedule.change", {"time": "10:00"})

    reminder = templates.render_notification_template(
        "schedule.reminder",
        {
            "subject": "Math",
            "group": "A-1",
            "lesson_type": "Lecture",
            "teacher": "Teacher",
            "room": "203",
            "starts_at": "2026-01-01T12:00:00Z",
            "id": 8,
        },
        locale="en",
    )
    assert reminder is not None
    assert reminder["data"]["startsAt"]

    empty_reminder = templates.render_notification_template(
        "lesson", {"room": "", "time": ""}, locale="ru"
    )
    assert empty_reminder is not None
    assert empty_reminder["tag"] == "schedule-reminder"


def test_schedule_builders_cover_raw_room_and_manual_time_fallback(monkeypatch):
    monkeypatch.setattr(templates, "_format_room", lambda *args, **kwargs: None)
    raw_room = templates.render_notification_template(
        "schedule.reminder", {"room": "raw-room", "time": "10:00"}
    )
    assert raw_room is not None
    assert raw_room["data"]["room"] == "raw-room"
    assert raw_room["data"]["startsAt"] == "10:00"


def test_news_event_system_and_comment_builders_cover_optional_fields():
    news = templates.render_notification_template(
        "news.item",
        {
            "headline": "Headline",
            "summary": "Summary",
            "author": "Author",
            "id": 1,
        },
        locale="en",
    )
    assert news is not None
    assert news["data"]["newsId"] == "1"

    empty_news = templates.render_notification_template("news.new", {}, locale="ru")
    assert empty_news is not None
    assert empty_news["tag"] == "news"

    event = templates.render_notification_template(
        "event.created",
        {
            "title": "Event",
            "summary": "Summary",
            "location": "Hall",
            "speaker": "Speaker",
            "event_type": "Talk",
            "starts_at": 1_700_000_000,
            "id": 2,
        },
        locale="en",
    )
    assert event is not None
    assert event["data"]["eventId"] == "2"

    empty_event = templates.render_notification_template("events.new", {}, locale="ru")
    assert empty_event is not None
    assert empty_event["tag"] == "event"
    manual_time_event = templates.render_notification_template(
        "events.new", {"time": "10:00"}, locale="ru"
    )
    assert manual_time_event is not None
    assert manual_time_event["data"]["startsAt"] == "10:00"

    system = templates.render_notification_template(
        "system.alert", {"subject": "Notice", "message": "Body", "id": "m"}
    )
    assert system is not None
    assert system["data"]["messageId"] == "m"
    assert system["requireInteraction"] is True

    empty_system = templates.render_notification_template("system.notice", {})
    assert empty_system is not None
    assert empty_system["tag"] == "system-message"

    comment = templates.render_notification_template(
        "news.comment",
        {
            "news_title": "News",
            "comment_body": "Comment",
            "user_name": "Author",
            "news_id": 3,
        },
    )
    assert comment is not None
    assert comment["data"]["newsId"] == "3"

    empty_comment = templates.render_notification_template("news.comment", {})
    assert empty_comment is not None
    assert empty_comment["tag"] == "news-comment"
