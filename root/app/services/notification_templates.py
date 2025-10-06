"""High-level notification content scenarios for web push."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


_DEFAULT_ICON = "/maskable-icon-192.png"
_DEFAULT_BADGE = _DEFAULT_ICON
_SYSTEM_ICON = "/guu_logo.png"


@dataclass(slots=True)
class ScenarioContext:
    """Utility wrapper to access fields from a payload mapping."""

    data: Mapping[str, Any]

    def get(self, *keys: str) -> Any:
        for key in keys:
            if key in self.data:
                value = self.data.get(key)
                if value not in (None, ""):
                    return value
        nested = self.data.get("data")
        if isinstance(nested, Mapping):
            for key in keys:
                if key in nested:
                    value = nested.get(key)
                    if value not in (None, ""):
                        return value
        return None

    def get_text(self, *keys: str) -> str | None:
        value = self.get(*keys)
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def get_identifier(self, *keys: str) -> str | None:
        value = self.get(*keys)
        if value is None:
            return None
        if isinstance(value, (int, float)):
            if isinstance(value, bool):
                return None
            return str(int(value))
        text = str(value).strip()
        return text or None

    def get_url(self, *keys: str, default: str = "/") -> str:
        value = self.get(*keys)
        if value is None:
            return default
        text = str(value).strip()
        return text or default


def _build_schedule_change(context: ScenarioContext) -> dict[str, Any]:
    subject = context.get_text("subject", "subject_name", "title", "name")
    group = context.get_text("group", "group_name", "group_title")
    change_summary = context.get_text("summary", "change", "status", "state")
    comment = context.get_text("comment", "note", "details")
    teacher = context.get_text("teacher", "lecturer", "professor")
    date_text = context.get_text("date", "day", "date_text")
    time_text = context.get_text("time", "start_time", "starts_at", "start")
    room = context.get_text("room", "auditory", "location")
    url = context.get_url("url", "link", default="/schedule")
    identifier = context.get_identifier(
        "lesson_id",
        "lessonId",
        "schedule_id",
        "scheduleId",
        "change_id",
        "changeId",
        "id",
    )

    detail_parts: list[str] = []
    if date_text and time_text:
        detail_parts.append(f"{date_text} {time_text}".strip())
    else:
        if date_text:
            detail_parts.append(date_text)
        if time_text:
            detail_parts.append(time_text)
    if room:
        detail_parts.append(f"ауд. {room}")
    if teacher:
        detail_parts.append(teacher)
    if group:
        detail_parts.append(group)

    lines: list[str] = []
    if change_summary:
        lines.append(change_summary)
    if comment and comment != change_summary:
        lines.append(comment)
    if detail_parts:
        lines.append(" · ".join(detail_parts))
    if not lines:
        lines.append("Проверьте расписание для актуальной информации.")

    title = f"Изменение пары: {subject}" if subject else "Изменение пары"
    tag = f"schedule-change:{identifier}" if identifier else "schedule-change"

    data_payload = {
        "url": url,
        "category": "schedule",
    }
    if subject:
        data_payload["subject"] = subject
    if group:
        data_payload["group"] = group
    if identifier:
        data_payload["lessonId"] = identifier

    return {
        "title": title,
        "body": "\n".join(lines),
        "icon": _DEFAULT_ICON,
        "badge": _DEFAULT_BADGE,
        "tag": tag,
        "renotify": True,
        "requireInteraction": False,
        "url": url,
        "topic": "schedule",
        "data": data_payload,
    }


def _build_news(context: ScenarioContext) -> dict[str, Any]:
    headline = context.get_text("headline", "title", "name")
    summary = context.get_text("summary", "body", "excerpt", "description")
    author = context.get_text("author", "source")
    url = context.get_url("url", "link", default="/news")
    identifier = context.get_identifier("id", "slug", "news_id", "newsId")

    detail_parts: list[str] = []
    if author:
        detail_parts.append(author)

    lines: list[str] = []
    if summary:
        lines.append(summary)
    if detail_parts:
        lines.append(" · ".join(detail_parts))
    if not lines:
        lines.append("Откройте новость, чтобы узнать подробности.")

    title = f"Новая новость: {headline}" if headline else "Новая новость"
    tag = f"news:{identifier}" if identifier else "news"

    data_payload = {
        "url": url,
        "category": "news",
    }
    if identifier:
        data_payload["newsId"] = identifier
    if headline:
        data_payload["headline"] = headline

    return {
        "title": title,
        "body": "\n".join(lines),
        "icon": _DEFAULT_ICON,
        "badge": _DEFAULT_BADGE,
        "tag": tag,
        "renotify": False,
        "requireInteraction": False,
        "url": url,
        "topic": "news",
        "data": data_payload,
    }


def _build_system(context: ScenarioContext) -> dict[str, Any]:
    subject = context.get_text("title", "subject", "heading")
    message = context.get_text("message", "body", "text")
    url = context.get_url("url", "link", default="/")
    identifier = context.get_identifier("id", "message_id", "messageId", "slug")

    lines: list[str] = []
    if message:
        lines.append(message)
    if not lines:
        lines.append("Подробности доступны в приложении.")

    title = subject or "Системное сообщение"
    tag = f"system-message:{identifier}" if identifier else "system-message"

    data_payload = {
        "url": url,
        "category": "system",
    }
    if identifier:
        data_payload["messageId"] = identifier
    if subject:
        data_payload["title"] = subject

    return {
        "title": title,
        "body": "\n".join(lines),
        "icon": _SYSTEM_ICON,
        "badge": _DEFAULT_BADGE,
        "tag": tag,
        "renotify": False,
        "requireInteraction": True,
        "url": url,
        "topic": "system",
        "data": data_payload,
    }


_BUILDERS: dict[str, Any] = {
    "schedule.change": _build_schedule_change,
    "news.new": _build_news,
    "system.message": _build_system,
}

_ALIASES: dict[str, str] = {
    "lesson.change": "schedule.change",
    "lesson.update": "schedule.change",
    "schedule.lesson_change": "schedule.change",
    "schedule.update": "schedule.change",
    "news.item": "news.new",
    "news.update": "news.new",
    "system.alert": "system.message",
    "system.announcement": "system.message",
    "system.notice": "system.message",
}


def _normalize_type(notification_type: str | None) -> str:
    if not notification_type:
        return ""
    normalized = str(notification_type).strip().lower()
    normalized = normalized.replace("_", ".").replace("-", ".")
    return normalized


def render_notification_template(
    notification_type: str | None,
    data: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Return payload defaults for a known notification scenario."""

    normalized_type = _normalize_type(notification_type)
    key = normalized_type
    if key not in _BUILDERS:
        key = _ALIASES.get(normalized_type, normalized_type)
    builder = _BUILDERS.get(key)
    if not builder:
        return None
    context = ScenarioContext(data or {})
    return builder(context)


__all__ = ["render_notification_template"]
