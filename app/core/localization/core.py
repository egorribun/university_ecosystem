from __future__ import annotations

from typing import Any

SUPPORTED_LOCALES: set[str] = {"en", "ru"}
DEFAULT_LOCALE = "en"


def normalize_locale(locale: str | None) -> str:
    """Return a supported locale code, falling back to the default."""

    candidate = (locale or "").strip().lower()
    if candidate in SUPPORTED_LOCALES:
        return candidate
    return DEFAULT_LOCALE


def localized_text(
    locale: str | None,
    *,
    ru: str | None = None,
    en: str | None = None,
) -> str | None:
    """Choose a localized string based on the requested locale."""

    normalized = normalize_locale(locale)
    candidates: tuple[str | None, str | None]
    if normalized == "en":
        candidates = (en, ru)
    else:
        candidates = (ru, en)
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate
    return None


_QUERY_PARAM_KEYS: tuple[str, ...] = ("lang", "locale", "language")
_USER_ATTR_KEYS: tuple[str, ...] = (
    "preferred_locale",
    "preferred_language",
    "locale",
    "language",
)


def _normalize_locale(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    for separator in ("-", "_"):
        if separator in text:
            text = text.split(separator, 1)[0]
            break
    return text if text in SUPPORTED_LOCALES else None


def _locale_from_accept_language(header_value: Any) -> str | None:
    if not header_value:
        return None
    try:
        header = str(header_value)
    except Exception:
        return None
    candidates: list[tuple[float, str]] = []
    for part in header.split(","):
        token = part.strip()
        if not token:
            continue
        lang, _, params = token.partition(";")
        quality = 1.0
        if params:
            for param in params.split(";"):
                param = param.strip()
                if param.startswith("q="):
                    try:
                        quality = float(param[2:])
                    except ValueError:
                        quality = 0.0
        normalized = _normalize_locale(lang)
        if normalized:
            candidates.append((quality, normalized))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    for _, locale in candidates:
        if locale in SUPPORTED_LOCALES:
            return locale
    return None


def resolve_locale(
    locale: str | None = None,
    *,
    request: Any = None,
    user: Any = None,
    default: str = DEFAULT_LOCALE,
) -> str:
    candidate = _normalize_locale(locale)
    if candidate:
        return candidate

    if request is not None:
        params = getattr(request, "query_params", None)
        if params is not None:
            for key in _QUERY_PARAM_KEYS:
                try:
                    raw = params.get(key)
                except Exception:
                    raw = None
                normalized = _normalize_locale(raw)
                if normalized:
                    return normalized

    if user is not None:
        for attr in _USER_ATTR_KEYS:
            normalized = _normalize_locale(getattr(user, attr, None))
            if normalized:
                return normalized

    if request is not None:
        headers = getattr(request, "headers", None)
        if headers is not None:
            try:
                header_value = headers.get("Accept-Language")
            except AttributeError:
                header_value = None
            normalized = _locale_from_accept_language(header_value)
            if normalized:
                return normalized

    fallback = _normalize_locale(default) or DEFAULT_LOCALE
    return fallback
