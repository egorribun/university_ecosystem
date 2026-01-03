from app.services.webpush import build_payload


def test_build_payload_schedule_change_template():
    payload = build_payload(
        "schedule.change",
        {
            "subject": "Математика",
            "lesson_id": 42,
            "summary": "Перенос занятия на 10:00",
            "date": "12.09",
            "time": "10:00",
            "room": "101",
        },
        locale="ru",
    )

    assert payload["title"] == "Изменение пары: Математика"
    options = payload["options"]
    assert options["tag"] == "schedule-change:42"
    assert options["renotify"] is True
    assert options["requireInteraction"] is False
    assert options["icon"] == "/maskable-icon-192.png"
    assert payload["data"]["url"] == "/schedule"
    assert payload["data"]["type"] == "schedule.change"
    assert "Перенос занятия" in options["body"]


def test_build_payload_news_template_merges_overrides():
    payload = build_payload(
        "news.new",
        {
            "headline": "Ректор выступил",
            "summary": "Состоялась встреча со студентами",
            "id": "news-7",
            "data": {"foo": "bar"},
            "icon": "/custom-icon.png",
        },
        locale="ru",
    )

    assert payload["title"] == "Новая новость: Ректор выступил"
    options = payload["options"]
    assert options["icon"] == "/custom-icon.png"
    assert options["tag"] == "news:news-7"
    assert options["renotify"] is False
    assert options["requireInteraction"] is False
    assert payload["data"]["url"] == "/news"
    assert payload["data"]["foo"] == "bar"


def test_build_payload_schedule_reminder_template():
    payload = build_payload(
        "schedule.reminder",
        {
            "subject": "Менеджмент",
            "lesson_type": "Семинар",
            "teacher": "Иванов И.И.",
            "room": "203",
            "starts_at": "2025-03-25T09:40:00+03:00",
            "date": "25.03",
            "time": "09:40",
            "lesson_id": 512,
        },
        locale="ru",
    )

    assert payload["title"] == "Скоро пара: Менеджмент"
    options = payload["options"]
    assert options["tag"].startswith("schedule-reminder:512")
    assert options["renotify"] is True
    assert "Семинар" in options["body"]
    assert "Иванов" in options["body"]
    data = payload["data"]
    assert data["category"] == "schedule"
    assert data["lessonId"] == "512"
    assert data["subject"] == "Менеджмент"
    assert data["room"] == "ауд. 203"


def test_build_payload_events_template():
    payload = build_payload(
        "events.new",
        {
            "title": "День открытых дверей",
            "summary": "Презентация новых программ",
            "location": "Актовый зал",
            "speaker": "Команда приёмной комиссии",
            "event_type": "Презентация",
            "starts_at": "2025-04-10T15:00:00+03:00",
            "id": 77,
        },
        locale="ru",
    )

    assert payload["title"] == "День открытых дверей"
    options = payload["options"]
    assert options["renotify"] is False
    assert options["tag"] == "event:77"
    assert "Презентация" in options["body"]
    data = payload["data"]
    assert data["eventId"] == "77"
    assert data["location"] == "Актовый зал"
    assert data["category"] == "events"


def test_build_payload_system_message_template():
    payload = build_payload(
        "system.message",
        {
            "message": "Технические работы в 23:00",
            "id": "maint",
            "url": "/status",
        },
        locale="ru",
    )

    assert payload["title"] == "Системное сообщение"
    options = payload["options"]
    assert options["icon"] == "/guu_logo.png"
    assert options["tag"] == "system-message:maint"
    assert options["requireInteraction"] is True
    assert options["renotify"] is False
    assert payload["data"]["url"] == "/status"


def test_build_payload_schedule_change_english_locale():
    payload = build_payload("schedule.change", None, locale="en")

    assert payload["title"] == "Class change"
    assert (
        payload["options"]["body"] == "Check the schedule for the latest information."
    )


def test_build_payload_schedule_reminder_english_locale():
    payload = build_payload(
        "schedule.reminder",
        {
            "subject": "Management",
            "lesson_type": "Seminar",
            "teacher": "John Doe",
            "room": "203",
            "starts_at": "2025-03-25T09:40:00+03:00",
            "date": "25.03",
            "time": "09:40",
        },
        locale="en",
    )

    assert payload["title"] == "Upcoming class: Management"
    assert "Starts at:" in payload["options"]["body"]
    assert payload["data"]["room"] == "room 203"
