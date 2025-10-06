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
    )

    assert payload["title"] == "Новая новость: Ректор выступил"
    options = payload["options"]
    assert options["icon"] == "/custom-icon.png"
    assert options["tag"] == "news:news-7"
    assert options["renotify"] is False
    assert options["requireInteraction"] is False
    assert payload["data"]["url"] == "/news"
    assert payload["data"]["foo"] == "bar"


def test_build_payload_system_message_template():
    payload = build_payload(
        "system.message",
        {
            "message": "Технические работы в 23:00",
            "id": "maint",
            "url": "/status",
        },
    )

    assert payload["title"] == "Системное сообщение"
    options = payload["options"]
    assert options["icon"] == "/guu_logo.png"
    assert options["tag"] == "system-message:maint"
    assert options["requireInteraction"] is True
    assert options["renotify"] is False
    assert payload["data"]["url"] == "/status"
