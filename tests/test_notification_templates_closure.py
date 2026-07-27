"""Closure tests for notification template fallback branches."""

from __future__ import annotations

from unittest.mock import patch

from app.services import notification_templates as templates


def test_room_prefix_builder_skips_empty_translations():
    with (
        patch.object(templates, "SUPPORTED_LOCALES", ("en",)),
        patch.object(templates, "translate", return_value=""),
    ):
        assert templates._room_label_prefixes() == {"room", "aud"}


def test_scenario_context_nested_values_skip_empty_and_continue():
    context = templates.ScenarioContext(
        {"data": {"first": "", "second": None, "third": "value"}}
    )
    assert context.get("first", "second", "third") == "value"
    assert context.get("missing", "also_missing") is None


def test_schedule_reminder_preserves_raw_room_when_formatter_returns_none():
    with patch.object(templates, "_format_room", return_value=None):
        result = templates._build_schedule_reminder(
            templates.ScenarioContext({"location": "Main Hall"}), locale="en"
        )

    assert result["data"]["room"] == "Main Hall"


def test_comment_builder_can_render_author_without_comment_body():
    result = templates._build_comment(
        templates.ScenarioContext({"user_name": "Reviewer"}), locale="en"
    )

    assert result["body"]
