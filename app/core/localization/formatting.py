from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from typing import Any

from .dictionary import TRANSLATIONS

_LESSON_TYPE_TRANSLATIONS: Mapping[str, str] = {
    "lecture": "schedule.lesson.type.lecture",
    "practice": "schedule.lesson.type.practice",
    "lab": "schedule.lesson.type.lab",
    "seminar": "schedule.lesson.type.seminar",
    "consultation": "schedule.lesson.type.consultation",
}

_LESSON_TYPE_ALIASES: Mapping[str, str] = {
    "лекция": "lecture",
    "лк": "lecture",
    "лекцияонлайн": "lecture",
    "lecture": "lecture",
    "пз": "practice",
    "практика": "practice",
    "практическоезанятие": "practice",
    "семинар": "seminar",
    "семинарское": "seminar",
    "семинарскоезанятие": "seminar",
    "лз": "lab",
    "лр": "lab",
    "лаб": "lab",
    "лабораторная": "lab",
    "лабораторнаяработа": "lab",
    "консультация": "consultation",
    "consultation": "consultation",
}

_WEEKDAY_INDEX: Mapping[str, int] = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

_WEEKDAY_STATIC_ALIASES: Mapping[str, tuple[str, ...]] = {
    "monday": ("monday", "mon"),
    "tuesday": ("tuesday", "tue"),
    "wednesday": ("wednesday", "wed"),
    "thursday": ("thursday", "thu"),
    "friday": ("friday", "fri"),
    "saturday": ("saturday", "sat"),
    "sunday": ("sunday", "sun"),
}


def _normalize_weekday_token(value: str | None) -> str | None:
    if not value:
        return None
    normalized = "".join(ch for ch in str(value).lower() if ch.isalpha())
    return normalized or None


def translate(
    key: str,
    *,
    locale: str | None = None,
    request: Any = None,
    user: Any = None,
    default: str | None = None,
    **kwargs: Any,
) -> str:
    from .core import DEFAULT_LOCALE, resolve_locale

    resolved = resolve_locale(locale=locale, request=request, user=user)
    entry = TRANSLATIONS.get(key)

    text: str | None = None
    if entry:
        for candidate in (resolved, DEFAULT_LOCALE):
            value = entry.get(candidate)
            if value:
                text = value
                break
        if text is None:
            text = next((value for value in entry.values() if value), None)

    if text is None:
        text = default if default is not None else key

    if kwargs and isinstance(text, str):
        try:
            return text.format(**kwargs)
        except KeyError:
            return text
    return text


def translate_lesson_type(
    lesson_type: str | None, *, locale: str | None = None
) -> str | None:
    if lesson_type is None:
        return None

    raw_value = str(lesson_type).strip()
    if not raw_value:
        return raw_value

    normalized = "".join(ch for ch in raw_value.lower() if ch.isalnum())
    canonical = _LESSON_TYPE_ALIASES.get(normalized)
    if canonical is None and normalized in _LESSON_TYPE_TRANSLATIONS:
        canonical = normalized
    if canonical:
        translation_key = _LESSON_TYPE_TRANSLATIONS[canonical]
        return translate(translation_key, locale=locale)

    return raw_value


@lru_cache(maxsize=1)
def weekday_aliases() -> Mapping[str, int]:
    aliases: dict[str, int] = {}
    for canonical, index in _WEEKDAY_INDEX.items():
        for alias in _WEEKDAY_STATIC_ALIASES.get(canonical, ()):
            normalized = _normalize_weekday_token(alias)
            if normalized:
                aliases.setdefault(normalized, index)

        for key_suffix in ("", "_short"):
            translation_key = f"schedule.weekday.{canonical}{key_suffix}"
            entry = TRANSLATIONS.get(translation_key)
            if not entry:
                continue
            for value in entry.values():
                normalized = _normalize_weekday_token(value)
                if normalized:
                    aliases.setdefault(normalized, index)

    return aliases


def resolve_weekday_index(value: str | None) -> int | None:
    normalized = _normalize_weekday_token(value)
    if not normalized:
        return None
    return weekday_aliases().get(normalized)
