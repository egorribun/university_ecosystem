"""News and event notifications.

This module handles notifications for new news articles and events.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from app.core.localization import (
    SUPPORTED_LOCALES,
    localized_text,
    normalize_locale,
    resolve_locale,
    translate,
)
from app.services.notification_templates import render_notification_template
from app.services.notifications.core import (
    _ensure_aware,
    _fetch_active_user_ids,
    _plain_text,
)
from app.services.notifications.delivery import create_notifications_for_users

if TYPE_CHECKING:
    from app.core.protocols import AsyncDatabaseSession as AsyncSession
    from app.models import Event, News, NewsComment, User


async def notify_about_news(
    db: AsyncSession, news: News, *, locale: str | None = None
) -> int:
    """Create and send notifications about a new news article."""
    resolved_locale = resolve_locale(locale=locale)

    def _clean_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value)
        return text if text.strip() else None

    def _variant(
        locale_option: str | None,
    ) -> tuple[
        str,
        str,
        str,
        str,
        str,
        dict[str, Any],
        str | None,
        str | None,
    ]:
        normalized = resolve_locale(locale=locale_option)

        def _localized_attr(attr: str) -> str | None:
            ru_value = _clean_text(getattr(news, attr, None))
            en_value = _clean_text(getattr(news, f"{attr}_en", None))
            if normalized == "en":
                return en_value or ru_value
            return ru_value or en_value

        headline = _localized_attr("title")
        summary_source = _localized_attr("content")
        summary = _plain_text(summary_source, limit=220)
        url = f"/news/{news.id}" if getattr(news, "id", None) else "/news"
        template_payload = {
            "headline": headline or getattr(news, "title", None),
            "summary": summary,
            "id": getattr(news, "id", None),
            "url": url,
        }
        template = render_notification_template(
            "news.new", template_payload, locale=normalized
        )
        if headline:
            default_title = translate(
                "notifications.news.title_with_headline",
                locale=normalized,
                headline=headline,
            )
        else:
            default_title = translate("notifications.news.title", locale=normalized)
        default_body = summary or translate(
            "notifications.news.no_summary", locale=normalized
        )
        default_tag = f"news:{news.id}" if getattr(news, "id", None) else "news"
        if template:
            title_value = str(template.get("title") or default_title)
            body_value = str(template.get("body") or default_body)
            resolved_url = str(template.get("url") or url)
            tag_value = str(template.get("tag") or default_tag)
            template_data = (
                template.get("data")
                if isinstance(template.get("data"), Mapping)
                else {}
            )
            payload_data = (
                dict(template_data) if isinstance(template_data, Mapping) else {}
            )
        else:
            title_value, body_value, resolved_url, tag_value = (
                default_title,
                default_body,
                url,
                default_tag,
            )
            payload_data = {}
        payload_data.setdefault("headline", headline or getattr(news, "title", None))
        payload_data.setdefault("newsId", getattr(news, "id", None))
        if summary:
            payload_data.setdefault("summary", summary)
        payload_data.setdefault("url", resolved_url)
        payload_data.setdefault("category", "news")
        filtered_payload = {
            key: value for key, value in payload_data.items() if value not in (None, "")
        }
        return (
            normalized,
            title_value,
            body_value,
            resolved_url,
            tag_value,
            filtered_payload,
            headline,
            summary,
        )

    (
        _,
        title,
        body,
        resolved_url,
        tag,
        payload_data,
        _headline,
        _summary,
    ) = _variant(resolved_locale)

    title_translations: dict[str, str] = {}
    body_translations: dict[str, str] = {}
    for locale_code in SUPPORTED_LOCALES:
        (
            _normalized,
            localized_title,
            localized_body,
            _url,
            _tag,
            _payload,
            _loc_headline,
            _loc_summary,
        ) = _variant(locale_code)
        if localized_title:
            title_translations[locale_code] = localized_title
        if localized_body:
            body_translations[locale_code] = localized_body

    user_ids = await _fetch_active_user_ids(db)
    if not user_ids:
        return 0
    return await create_notifications_for_users(
        db,
        title=title,
        body=body,
        title_translations=title_translations,
        body_translations=body_translations,
        type="news.new",
        url=resolved_url,
        tag=tag,
        payload_data=payload_data,
        user_ids=user_ids,
        topic="news",
    )


async def notify_about_event(
    db: AsyncSession, event: Event, *, locale: str | None = None
) -> int:
    """Create and send notifications about a new event."""

    def _variant(
        locale_option: str | None,
    ) -> tuple[
        str,
        str,
        str,
        str,
        str,
        dict[str, Any],
        str,
        str,
        str | None,
        str | None,
    ]:
        normalized = normalize_locale(locale_option)
        localized_title_value = localized_text(
            normalized,
            ru=getattr(event, "title", None),
            en=getattr(event, "title_en", None),
        )
        if not localized_title_value:
            localized_title_value = (
                getattr(event, "title", None) or getattr(event, "title_en", None) or ""
            )
        localized_description = localized_text(
            normalized,
            ru=getattr(event, "description", None),
            en=getattr(event, "description_en", None),
        )
        localized_about = localized_text(
            normalized,
            ru=getattr(event, "about", None),
            en=getattr(event, "about_en", None),
        )
        localized_location = localized_text(
            normalized,
            ru=getattr(event, "location", None),
            en=getattr(event, "location_en", None),
        )
        localized_event_type = localized_text(
            normalized,
            ru=getattr(event, "event_type", None),
            en=getattr(event, "event_type_en", None),
        )
        summary_source = localized_description or localized_about
        summary = _plain_text(summary_source, limit=220)
        url = f"/events/{event.id}" if getattr(event, "id", None) else "/events"
        start_dt = _ensure_aware(getattr(event, "starts_at", None))
        start_local = start_dt.astimezone()
        template_payload = {
            "title": localized_title_value,
            "summary": summary,
            "location": localized_location,
            "speaker": getattr(event, "speaker", None),
            "event_type": localized_event_type,
            "starts_at": start_dt.isoformat(),
            "date": start_local.strftime("%d.%m"),
            "time": start_local.strftime("%H:%M"),
            "url": url,
            "id": getattr(event, "id", None),
        }
        template = render_notification_template(
            "events.new", template_payload, locale=locale_option
        )
        if localized_title_value:
            default_title = translate(
                "notifications.events.title_with_name",
                locale=locale_option,
                title=localized_title_value,
            )
        else:
            default_title = translate(
                "notifications.events.title", locale=locale_option
            )
        details = [start_local.strftime("%d.%m · %H:%M")]
        if localized_location:
            details.append(str(localized_location))
        if getattr(event, "speaker", None):
            details.append(str(event.speaker))
        if localized_event_type:
            details.append(str(localized_event_type))
        default_lines = []
        if summary:
            default_lines.append(summary)
        default_lines.append(" · ".join(details))
        default_body = "\n".join(default_lines) or translate(
            "notifications.events.no_details", locale=locale_option
        )
        default_tag = f"event:{event.id}" if getattr(event, "id", None) else "event"
        if template:
            title_value = str(template.get("title") or default_title)
            body_value = str(template.get("body") or default_body)
            resolved_url = str(template.get("url") or url)
            tag_value = str(template.get("tag") or default_tag)
            template_data = (
                template.get("data")
                if isinstance(template.get("data"), Mapping)
                else {}
            )
            payload_data = (
                dict(template_data) if isinstance(template_data, Mapping) else {}
            )
        else:
            title_value, body_value, resolved_url, tag_value = (
                default_title,
                default_body,
                url,
                default_tag,
            )
            payload_data = {}
        payload_data.setdefault("eventId", getattr(event, "id", None))
        payload_data.setdefault("title", localized_title_value)
        if summary:
            payload_data.setdefault("summary", summary)
        if localized_location:
            payload_data.setdefault("location", str(localized_location))
        if getattr(event, "speaker", None):
            payload_data.setdefault("speaker", str(event.speaker))
        if localized_event_type:
            payload_data.setdefault("eventType", str(localized_event_type))
        payload_data.setdefault("startsAt", start_dt.isoformat())
        payload_data.setdefault("startText", start_local.strftime("%d.%m · %H:%M"))
        payload_data.setdefault("url", resolved_url)
        payload_data.setdefault("category", "events")
        filtered_payload = {
            key: value for key, value in payload_data.items() if value not in (None, "")
        }
        return (
            normalized,
            title_value,
            body_value,
            resolved_url,
            tag_value,
            filtered_payload,
            start_dt.isoformat(),
            start_local.strftime("%d.%m · %H:%M"),
            localized_title_value,
            summary,
        )

    (
        _,
        title,
        body,
        resolved_url,
        tag,
        payload_data,
        _starts_at,
        _start_text,
        _localized_title,
        _summary,
    ) = _variant(locale)

    title_translations: dict[str, str] = {}
    body_translations: dict[str, str] = {}
    for locale_code in SUPPORTED_LOCALES:
        (
            _normalized,
            localized_title,
            localized_body,
            _url,
            _tag,
            _payload,
            _starts_at,
            _start_text,
            _title_value,
            _summary_value,
        ) = _variant(locale_code)
        if localized_title:
            title_translations[locale_code] = localized_title
        if localized_body:  # pragma: no branch - details always provide event body
            body_translations[locale_code] = localized_body

    user_ids = await _fetch_active_user_ids(db)
    if not user_ids:
        return 0
    return await create_notifications_for_users(
        db,
        title=title,
        body=body,
        title_translations=title_translations,
        body_translations=body_translations,
        type="events.new",
        url=resolved_url,
        tag=tag,
        payload_data=payload_data,
        user_ids=user_ids,
        topic="events",
    )


async def notify_about_comment(
    db: AsyncSession,
    news: News,
    comment: NewsComment,
    author: User,
    *,
    locale: str | None = None,
) -> int:
    """Create and send notifications to admins about a new comment."""
    from app.services.notifications.core import _fetch_admin_ids

    resolved_locale = resolve_locale(locale=locale)
    news_title = localized_text(
        resolved_locale,
        ru=getattr(news, "title", None),
        en=getattr(news, "title_en", None),
    )
    user_name = getattr(author, "full_name", None) or getattr(
        author, "username", "User"
    )

    template_payload = {
        "news_title": news_title or getattr(news, "title", None),
        "comment_body": comment.content,
        "user_name": user_name,
        "news_id": news.id,
    }

    template = render_notification_template(
        "news.comment", template_payload, locale=resolved_locale
    )

    if not template:
        return 0

    admin_ids = await _fetch_admin_ids(db)
    if not admin_ids:
        return 0

    return await create_notifications_for_users(
        db,
        title=str(template["title"]),
        body=str(template["body"]),
        type="news.comment",
        url=str(template["url"]),
        tag=str(template["tag"]),
        payload_data=template.get("data", {}),
        user_ids=admin_ids,
        topic="news",
    )
