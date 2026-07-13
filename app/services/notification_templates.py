"""High-level notification content scenarios for web push."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from html import unescape
from textwrap import shorten
from typing import Any, Protocol

from app.core.localization import SUPPORTED_LOCALES, translate

_DEFAULT_ICON = "/maskable-icon-192.png"
_DEFAULT_BADGE = _DEFAULT_ICON
_SYSTEM_ICON = "/guu_logo.png"


_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


def _room_label_prefixes() -> set[str]:
    prefixes: set[str] = set()
    for locale_code in SUPPORTED_LOCALES:
        template = translate(
            "notifications.schedule.room_label", locale=locale_code, room=""
        )
        for variant in (template, template.replace(".", "")):
            normalized = variant.strip().lower()
            if normalized:
                prefixes.add(normalized)
    prefixes.update({"room", "aud"})
    return prefixes


_ROOM_LABEL_PREFIXES = _room_label_prefixes()


def _clean_text(value: Any, *, limit: int | None = None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = unescape(_TAG_RE.sub(" ", text))
    text = _SPACE_RE.sub(" ", text).strip()
    if not text:
        return None
    if limit is not None and len(text) > limit:
        return shorten(text, width=limit, placeholder="…")
    return text


def _format_room(value: Any, *, locale: str | None = None) -> str | None:
    room = _clean_text(value)
    if not room:
        return None
    normalized = room.lower().strip()
    if any(normalized.startswith(prefix) for prefix in _ROOM_LABEL_PREFIXES):
        return room
    return translate("notifications.schedule.room_label", locale=locale, room=room)


def _parse_datetime_like(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, int | float):
        try:
            return datetime.fromtimestamp(float(value), UTC)
        except OSError, OverflowError, ValueError:
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        for candidate in (text, text.replace("Z", "+00:00")):
            try:
                return datetime.fromisoformat(candidate)
            except ValueError:
                continue
    return None


def _datetime_details(value: Any) -> tuple[str | None, str | None, str | None]:
    parsed = _parse_datetime_like(value)
    if not parsed:
        return None, None, None
    aware = parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    local = aware.astimezone()
    return local.strftime("%d.%m"), local.strftime("%H:%M"), aware.isoformat()


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
        if isinstance(value, int | float):
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


def _build_schedule_change(
    context: ScenarioContext, *, locale: str | None = None
) -> dict[str, Any]:
    subject = context.get_text("subject", "subject_name", "title", "name")
    group = context.get_text("group", "group_name", "group_title")
    change_summary = context.get_text("summary", "change", "status", "state")
    comment = context.get_text("comment", "note", "details")
    teacher = context.get_text("teacher", "lecturer", "professor")
    date_text = context.get_text("date", "day", "date_text")
    time_text = context.get_text("time", "start_time", "starts_at", "start")
    room_text = context.get_text("room", "auditory", "location")
    room_display = _format_room(room_text, locale=locale)
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
    if room_display:
        detail_parts.append(room_display)
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
        lines.append(
            translate("notifications.schedule.change.no_details", locale=locale)
        )

    if subject:
        title = translate(
            "notifications.schedule.change.title_with_subject",
            locale=locale,
            subject=subject,
        )
    else:
        title = translate("notifications.schedule.change.title", locale=locale)
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


def _build_schedule_reminder(
    context: ScenarioContext, *, locale: str | None = None
) -> dict[str, Any]:
    subject = context.get_text("subject", "subject_name", "title", "name")
    group = context.get_text("group", "group_name", "group_title")
    lesson_type = context.get_text("lesson_type", "type", "format")
    teacher = context.get_text("teacher", "lecturer", "professor")
    room_text = context.get_text("room", "auditory", "location")
    room = _format_room(room_text, locale=locale)
    manual_date = context.get_text("date", "day", "date_text")
    manual_time = context.get_text("time", "start_time_text", "start_text")
    start_source = context.get(
        "starts_at",
        "start_time",
        "startTime",
        "start",
        "time",
    )
    auto_date, auto_time, start_iso = _datetime_details(start_source)
    date_text = manual_date or auto_date
    time_text = manual_time or auto_time
    url = context.get_url("url", "link", default="/schedule")
    identifier = context.get_identifier(
        "lesson_id",
        "schedule_id",
        "lessonId",
        "scheduleId",
        "id",
    )

    when_parts: list[str] = []
    if date_text:
        when_parts.append(date_text)
    if time_text:
        when_parts.append(time_text)
    when_line = " · ".join(when_parts)

    summary_parts: list[str] = []
    if lesson_type:
        summary_parts.append(lesson_type)
    if room:
        summary_parts.append(room)
    if teacher:
        summary_parts.append(teacher)
    if group:
        summary_parts.append(group)

    lines: list[str] = []
    if when_line:
        lines.append(
            translate(
                "notifications.schedule.reminder.start_line",
                locale=locale,
                start=when_line,
            )
        )
    if summary_parts:
        lines.append(" · ".join(summary_parts))
    if not lines:
        lines.append(
            translate("notifications.schedule.reminder.no_details", locale=locale)
        )

    if subject:
        title = translate(
            "notifications.schedule.reminder.title_with_subject",
            locale=locale,
            subject=subject,
        )
    else:
        title = translate("notifications.schedule.reminder.title", locale=locale)
    tag = f"schedule-reminder:{identifier}" if identifier else "schedule-reminder"

    data_payload = {
        "url": url,
        "category": "schedule",
    }
    if identifier:
        data_payload["lessonId"] = identifier
    if subject:
        data_payload["subject"] = subject
    if group:
        data_payload["group"] = group
    if lesson_type:
        data_payload["lessonType"] = lesson_type
    if teacher:
        data_payload["teacher"] = teacher
    if room:
        data_payload["room"] = room
    elif room_text:
        data_payload["room"] = room_text
    if when_line:
        data_payload["startText"] = when_line
    if start_iso:
        data_payload["startsAt"] = start_iso
    elif time_text:
        data_payload["startsAt"] = time_text

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


def _build_news(
    context: ScenarioContext, *, locale: str | None = None
) -> dict[str, Any]:
    headline = context.get_text("headline", "title", "subject", "name")
    summary = _clean_text(
        context.get("summary", "body", "excerpt", "description"),
        limit=220,
    )
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
        lines.append(translate("notifications.news.no_summary", locale=locale))

    if headline:
        title = translate(
            "notifications.news.title_with_headline", locale=locale, headline=headline
        )
    else:
        title = translate("notifications.news.title", locale=locale)
    tag = f"news:{identifier}" if identifier else "news"

    data_payload = {
        "url": url,
        "category": "news",
    }
    if identifier:
        data_payload["newsId"] = identifier
    if headline:
        data_payload["headline"] = headline
    if summary:
        data_payload["summary"] = summary

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


def _build_event(
    context: ScenarioContext, *, locale: str | None = None
) -> dict[str, Any]:
    title = context.get_text("title", "name", "headline")
    summary = _clean_text(
        context.get("summary", "description", "about", "details"),
        limit=220,
    )
    location = _clean_text(context.get("location", "place", "room", "venue"))
    speaker = _clean_text(context.get("speaker", "host", "lecturer"))
    event_type = _clean_text(context.get("event_type", "type", "category"))
    start_source = context.get(
        "starts_at",
        "start_time",
        "startTime",
        "start",
        "time",
    )
    auto_date, auto_time, start_iso = _datetime_details(start_source)
    manual_date = context.get_text("date", "day")
    manual_time = context.get_text("time", "start_time_text")
    date_text = manual_date or auto_date
    time_text = manual_time or auto_time
    url = context.get_url("url", "link", "event_url", default="/events")
    identifier = context.get_identifier("id", "event_id", "eventId", "slug")

    when_parts: list[str] = []
    if date_text:
        when_parts.append(date_text)
    if time_text:
        when_parts.append(time_text)
    when_line = " · ".join(when_parts)

    details: list[str] = []
    if when_line:
        details.append(when_line)
    if location:
        details.append(location)
    if speaker:
        details.append(speaker)
    if event_type:
        details.append(event_type)

    lines: list[str] = []
    if summary:
        lines.append(summary)
    if details:
        lines.append(" · ".join(details))
    if not lines:
        lines.append(translate("notifications.events.no_details", locale=locale))

    if title:
        notif_title = translate(
            "notifications.events.title_with_name", locale=locale, title=title
        )
    else:
        notif_title = translate("notifications.events.title", locale=locale)
    tag = f"event:{identifier}" if identifier else "event"

    data_payload = {
        "url": url,
        "category": "events",
    }
    if identifier:
        data_payload["eventId"] = identifier
    if title:
        data_payload["title"] = title
    if summary:
        data_payload["summary"] = summary
    if location:
        data_payload["location"] = location
    if speaker:
        data_payload["speaker"] = speaker
    if event_type:
        data_payload["eventType"] = event_type
    if when_line:
        data_payload["startText"] = when_line
    if start_iso:
        data_payload["startsAt"] = start_iso
    elif time_text:
        data_payload["startsAt"] = time_text

    return {
        "title": notif_title,
        "body": "\n".join(lines),
        "icon": _DEFAULT_ICON,
        "badge": _DEFAULT_BADGE,
        "tag": tag,
        "renotify": False,
        "requireInteraction": False,
        "url": url,
        "topic": "events",
        "data": data_payload,
    }


def _build_system(
    context: ScenarioContext, *, locale: str | None = None
) -> dict[str, Any]:
    subject = context.get_text("title", "subject", "heading")
    message = context.get_text("message", "body", "text")
    url = context.get_url("url", "link", default="/")
    identifier = context.get_identifier("id", "message_id", "messageId", "slug")

    lines: list[str] = []
    if message:
        lines.append(message)
    if not lines:
        lines.append(translate("notifications.system.no_details", locale=locale))

    title = subject or translate("notifications.system.title", locale=locale)
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


class NotificationBuilder(Protocol):
    def __call__(
        self, context: ScenarioContext, *, locale: str | None = ...
    ) -> dict[str, Any] | None:
        """Build a notification payload for the given scenario."""


def _build_comment(
    context: ScenarioContext, *, locale: str | None = None
) -> dict[str, Any]:
    news_title = context.get_text("news_title", "headline", "title")
    comment_body = _clean_text(context.get("comment_body", "body", "text"), limit=220)
    user_name = context.get_text("user_name", "author")
    news_id = context.get_identifier("news_id", "newsId")
    url = f"/news/{news_id}" if news_id else "/news"

    lines: list[str] = []
    if comment_body:
        lines.append(comment_body)
    if user_name:
        lines.append(
            translate(
                "notifications.news.comment.from_author",
                locale=locale,
                author=user_name,
            )
        )

    if news_title:
        title = translate(
            "notifications.news.comment.title_with_news",
            locale=locale,
            news=news_title,
        )
    else:
        title = translate("notifications.news.comment.title", locale=locale)

    tag = f"news-comment:{news_id}" if news_id else "news-comment"

    return {
        "title": title,
        "body": "\n".join(lines),
        "icon": _DEFAULT_ICON,
        "badge": _DEFAULT_BADGE,
        "tag": tag,
        "renotify": True,
        "requireInteraction": False,
        "url": url,
        "topic": "news",
        "data": {
            "url": url,
            "category": "news",
            "newsId": news_id,
        },
    }


_BUILDERS: dict[str, NotificationBuilder] = {
    "schedule.change": _build_schedule_change,
    "schedule.reminder": _build_schedule_reminder,
    "news.new": _build_news,
    "news.comment": _build_comment,
    "events.new": _build_event,
    "system.message": _build_system,
}

_ALIASES: dict[str, str] = {
    "lesson.change": "schedule.change",
    "lesson.update": "schedule.change",
    "schedule.lesson_change": "schedule.change",
    "schedule.update": "schedule.change",
    "lesson": "schedule.reminder",
    "lesson.reminder": "schedule.reminder",
    "schedule.lesson_reminder": "schedule.reminder",
    "news.item": "news.new",
    "news.update": "news.new",
    "event.new": "events.new",
    "event.created": "events.new",
    "events.create": "events.new",
    "events.update": "events.new",
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
    *,
    locale: str | None = None,
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
    return builder(context, locale=locale)


__all__ = ["render_notification_template"]
