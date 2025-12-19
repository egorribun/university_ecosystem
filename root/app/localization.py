"""Simple localization utilities for backend responses."""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
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

_TRANSLATIONS: Mapping[str, Mapping[str, str]] = {
    "email.reset.subject": {
        "ru": "Сброс пароля — Экосистема ГУУ",
        "en": "Password reset — GUU Ecosystem",
    },
    "email.reset.heading": {"ru": "Сброс пароля", "en": "Password reset"},
    "email.reset.greeting": {
        "ru": "Здравствуйте{name}!",
        "en": "Hello{name}!",
    },
    "email.reset.instructions": {
        "ru": (
            "Вы запросили сброс пароля в Экосистеме ГУУ. Ссылка действует {minutes} минут."
        ),
        "en": (
            "You requested a password reset in the GUU Ecosystem. "
            "The link is valid for {minutes} minutes."
        ),
    },
    "email.reset.button": {
        "ru": "Сбросить пароль",
        "en": "Reset password",
    },
    "email.reset.ignore": {
        "ru": "Если вы не запрашивали сброс, проигнорируйте это письмо.",
        "en": "If you did not request this reset, please ignore this email.",
    },
    "email.reset.plain": {
        "ru": "Ссылка для сброса пароля: {link}\nОна действует {minutes} минут.",
        "en": "Password reset link: {link}\nIt is valid for {minutes} minutes.",
    },
    "notifications.schedule.room_label": {
        "ru": "ауд. {room}",
        "en": "room {room}",
    },
    "notifications.schedule.change.no_details": {
        "ru": "Проверьте расписание для актуальной информации.",
        "en": "Check the schedule for the latest information.",
    },
    "notifications.schedule.change.title_with_subject": {
        "ru": "Изменение пары: {subject}",
        "en": "Class change: {subject}",
    },
    "notifications.schedule.change.title": {
        "ru": "Изменение пары",
        "en": "Class change",
    },
    "notifications.schedule.reminder.start_line": {
        "ru": "Начало: {start}",
        "en": "Starts at: {start}",
    },
    "notifications.schedule.reminder.no_details": {
        "ru": "Проверьте расписание для подробностей.",
        "en": "Check the schedule for details.",
    },
    "notifications.schedule.reminder.title_with_subject": {
        "ru": "Скоро пара: {subject}",
        "en": "Upcoming class: {subject}",
    },
    "notifications.schedule.reminder.title": {
        "ru": "Скоро пара",
        "en": "Upcoming class",
    },
    "notifications.news.no_summary": {
        "ru": "Откройте новость, чтобы узнать подробности.",
        "en": "Open the article to learn more.",
    },
    "notifications.news.title_with_headline": {
        "ru": "Новая новость: {headline}",
        "en": "New article: {headline}",
    },
    "notifications.news.title": {
        "ru": "Новая новость",
        "en": "New article",
    },
    "notifications.events.no_details": {
        "ru": "Подробнее в карточке события.",
        "en": "See the event card for more information.",
    },
    "notifications.events.title_with_name": {
        "ru": "Новое мероприятие: {title}",
        "en": "New event: {title}",
    },
    "notifications.events.title": {
        "ru": "Новое мероприятие",
        "en": "New event",
    },
    "notifications.system.no_details": {
        "ru": "Подробности доступны в приложении.",
        "en": "More details are available in the app.",
    },
    "notifications.system.title": {
        "ru": "Системное сообщение",
        "en": "System message",
    },
    "notifications.mfa.reset.title": {
        "ru": "Многофакторная аутентификация сброшена",
        "en": "Multi-factor authentication was reset",
    },
    "notifications.mfa.reset.body": {
        "ru": (
            "Администратор отключил ваши MFA-методы. Настройте защиту повторно при следующем входе."
        ),
        "en": (
            "An administrator removed your MFA methods. "
            "Please set them up again on your next sign-in."
        ),
    },
    "notifications.actions.open_schedule": {
        "ru": "Открыть расписание",
        "en": "Open schedule",
    },
    "notifications.default_title": {
        "ru": "Уведомление",
        "en": "Notification",
    },
    "stats.period.30d": {
        "ru": "За последние {days} дней",
        "en": "Last {days} days",
    },
    "stats.period.90d": {
        "ru": "За последние {days} дней",
        "en": "Last {days} days",
    },
    "stats.period.180d": {
        "ru": "За последние {days} дней",
        "en": "Last {days} days",
    },
    "errors.auth.credentials_invalid": {
        "ru": "Не удалось подтвердить учётные данные",
        "en": "Could not validate credentials",
    },
    "errors.auth.account_locked": {
        "ru": "Слишком много неудачных попыток входа. Аккаунт временно заблокирован.",
        "en": "Too many failed attempts. Your account is temporarily locked.",
    },
    "errors.auth.account_locked_retry": {
        "ru": "Повторите попытку через {duration}.",
        "en": "Try again in {duration}.",
    },
    "errors.auth.mfa_challenge_locked": {
        "ru": "Превышено число попыток подтверждения. Запросите новый челлендж.",
        "en": "Too many incorrect verification attempts. Request a new challenge.",
    },
    "errors.auth.mfa_totp_missing": {
        "ru": "Сначала настройте приложение-аутентификатор, чтобы продолжить.",
        "en": "Set up an authenticator app before continuing.",
    },
    "errors.auth.mfa_step_up_required": {
        "ru": "Требуется дополнительное подтверждение входа.",
        "en": "Additional verification is required to continue.",
    },
    "errors.auth.user_deactivated": {
        "ru": "Пользователь деактивирован",
        "en": "User account is deactivated",
    },
    "errors.auth.password_policy": {
        "ru": "Пароль должен содержать от 8 до 200 символов.",
        "en": "Password must be between 8 and 200 characters long.",
    },
    "errors.forbidden": {
        "ru": "Доступ запрещён",
        "en": "Access denied",
    },
    "errors.files.too_large": {
        "ru": "Размер файла превышает допустимый предел",
        "en": "Uploaded file exceeds the allowed size",
    },
    "errors.files.too_many_attachments": {
        "ru": "Слишком много вложений в сообщении",
        "en": "Too many attachments in the message",
    },
    "errors.chat.empty_message": {
        "ru": "Сообщение должно содержать текст или вложения",
        "en": "Message must contain text or attachments",
    },
    "errors.files.unsupported_type": {
        "ru": "Неподдерживаемый тип файла",
        "en": "Unsupported media type",
    },
    "errors.files.content_type_mismatch": {
        "ru": "Тип содержимого не соответствует объявленному",
        "en": "Content type does not match the declared value",
    },
    "errors.files.unsupported_extension": {
        "ru": "Неподдерживаемое расширение файла",
        "en": "Unsupported file extension",
    },
    "errors.files.infected": {
        "ru": "Файл содержит вредоносное содержимое",
        "en": "The file contains malicious content",
    },
    "errors.files.scanner_unavailable": {
        "ru": "Служба проверки файлов временно недоступна",
        "en": "File scanning service is temporarily unavailable",
    },
    "errors.events.registration_forbidden": {
        "ru": "Регистрация на мероприятия недоступна для вашей роли",
        "en": "Event registration is not available for your role",
    },
    "errors.events.not_found": {
        "ru": "Событие не найдено",
        "en": "Event not found",
    },
    "errors.events.registration_closed": {
        "ru": "Регистрация на событие закрыта",
        "en": "Event registration is closed",
    },
    "errors.events.file_not_found": {
        "ru": "Файл не найден",
        "en": "File not found",
    },
    "errors.news.not_found": {
        "ru": "Новость не найдена",
        "en": "News item not found",
    },
    "errors.notifications.bad_cursor": {
        "ru": "Некорректный курсор",
        "en": "Invalid cursor",
    },
    "errors.notifications.not_found": {
        "ru": "Уведомление не найдено",
        "en": "Notification not found",
    },
    "errors.notifications.admin_required": {
        "ru": "Доступно только администраторам",
        "en": "Administrator privileges are required",
    },
    "errors.push.not_configured": {
        "ru": "Web push не настроен",
        "en": "Web push is not configured",
    },
    "errors.push.subscription_exists": {
        "ru": "Точка подписки уже зарегистрирована",
        "en": "Subscription endpoint already registered",
    },
    "errors.push.subscription_not_found": {
        "ru": "Подписка не найдена",
        "en": "Subscription not found",
    },
    "errors.push.subscription_validation_failed": {
        "ru": "Не удалось проверить данные подписки",
        "en": "Subscription payload validation failed",
    },
    "errors.rate_limit.generic": {
        "ru": "Слишком много запросов",
        "en": "Too many requests",
    },
    "errors.rate_limit.push_subscribe": {
        "ru": "Слишком много запросов подписки. Попробуйте позже.",
        "en": "Too many subscription attempts. Please try again later.",
    },
    "errors.rate_limit.push_unsubscribe": {
        "ru": "Слишком много попыток отключить уведомления.",
        "en": "Too many unsubscribe attempts.",
    },
    "errors.rate_limit.push_test": {
        "ru": "Слишком много тестовых уведомлений",
        "en": "Too many test notifications",
    },
    "errors.schedule.not_found": {
        "ru": "Запись расписания не найдена",
        "en": "Schedule entry not found",
    },
    "errors.schedule.group_not_found": {
        "ru": "Группа не найдена",
        "en": "Group not found",
    },
    "errors.spotify.reconnect_required": {
        "ru": "Требуется переподключить Spotify",
        "en": "Spotify connection needs to be re-authorized",
    },
    "errors.spotify.invalid_state": {
        "ru": "Некорректный параметр state",
        "en": "Invalid state parameter",
    },
    "errors.spotify.user_not_found": {
        "ru": "Пользователь не найден",
        "en": "User not found",
    },
    "errors.spotify.token_exchange_failed": {
        "ru": "Не удалось обменять код на токен",
        "en": "Token exchange failed",
    },
    "errors.spotify.rate_limited": {
        "ru": "Превышен лимит запросов Spotify",
        "en": "Rate limited by Spotify",
    },
    "errors.password.invalid_or_expired_link": {
        "ru": "Недействительная или просроченная ссылка",
        "en": "The reset link is invalid or has expired",
    },
    "errors.password.invalid_link": {
        "ru": "Недействительная ссылка",
        "en": "Invalid link",
    },
    "errors.users.invalid_email": {
        "ru": "Некорректный email",
        "en": "Invalid email address",
    },
    "errors.users.email_in_use": {
        "ru": "Указанный email уже используется",
        "en": "The specified email is already in use",
    },
    "errors.users.email_same": {
        "ru": "Новый email должен отличаться от текущего",
        "en": "The new email must be different from your current address",
    },
    "errors.users.email_confirmation_invalid": {
        "ru": "Ссылка для подтверждения email недействительна или устарела",
        "en": "The email confirmation link is invalid or has expired",
    },
    "errors.users.email_confirmation_conflict": {
        "ru": "Этот email уже используется другим аккаунтом",
        "en": "That email is already used by another account",
    },
    "errors.users.invalid_password": {
        "ru": "Текущий пароль указан неверно",
        "en": "The current password is incorrect",
    },
    "errors.users.password_same": {
        "ru": "Новый пароль должен отличаться от текущего",
        "en": "Choose a new password that's different from the current one",
    },
    "errors.users.create_failed": {
        "ru": "Ошибка создания пользователя",
        "en": "Failed to create user",
    },
    "errors.users.invite_required": {
        "ru": "Необходим уникальный код для регистрации преподавателя/админа",
        "en": "A unique invite code is required to register a teacher or admin",
    },
    "errors.users.invalid_invite": {
        "ru": "Неверный или неактивный код",
        "en": "Invite code is invalid or inactive",
    },
    "errors.users.cannot_delete_self": {
        "ru": "Нельзя удалить самого себя",
        "en": "You cannot delete yourself",
    },
    "errors.users.not_found": {
        "ru": "Пользователь не найден",
        "en": "User not found",
    },
    "errors.sessions.not_found": {
        "ru": "Сессия не найдена",
        "en": "Session not found",
    },
    "errors.sessions.signing_key_missing": {
        "ru": "Активная сессия не содержит ключ подписи",
        "en": "The active session is missing a signing key",
    },
    "errors.profile_cache.invalid_envelope": {
        "ru": "Некорректный конверт кэша профиля",
        "en": "Invalid profile cache envelope",
    },
    "errors.profile_cache.invalid_signature": {
        "ru": "Некорректная подпись конверта профиля",
        "en": "Invalid profile cache envelope signature",
    },
    "notifications.push.test.title_default": {
        "ru": "Тестовое веб-push уведомление",
        "en": "Test web push notification",
    },
    "notifications.push.test.body_default": {
        "ru": "Проверка доставки уведомлений",
        "en": "Delivery check",
    },
    "notifications.push.test.no_subscriptions": {
        "ru": "Активные подписки не найдены",
        "en": "No subscriptions found",
    },
    "notifications.push.test_failure": {
        "ru": "Не удалось отправить тестовое уведомление",
        "en": "Failed to send the test notification",
    },
    "notifications.push.broadcast_failure": {
        "ru": "Не удалось отправить уведомления",
        "en": "Failed to deliver notifications",
    },
    "notifications.push.disable_user.description": {
        "ru": "ID пользователя, для которого нужно отключить push",
        "en": "User ID for which push notifications should be disabled",
    },
    "notifications.push.validation.endpoint_required": {
        "ru": "Endpoint обязателен",
        "en": "Endpoint is required",
    },
    "notifications.push.validation.keys_auth_required": {
        "ru": "keys.auth не может быть пустым",
        "en": "keys.auth must not be empty",
    },
    "notifications.push.validation.keys_p256dh_required": {
        "ru": "keys.p256dh не может быть пустым",
        "en": "keys.p256dh must not be empty",
    },
    "schedule.ics.calendar_name": {
        "ru": "Расписание {group}",
        "en": "Schedule for {group}",
    },
    "schedule.ics.calendar_name_generic": {
        "ru": "Расписание",
        "en": "Schedule",
    },
    "schedule.ics.prodid": {
        "ru": "-//University Ecosystem//Schedule//RU",
        "en": "-//University Ecosystem//Schedule//EN",
    },
    "schedule.ics.lesson_default_subject": {
        "ru": "Занятие",
        "en": "Lesson",
    },
    "schedule.ics.description.lesson_type": {
        "ru": "Тип занятия: {lesson_type}",
        "en": "Lesson type: {lesson_type}",
    },
    "schedule.ics.description.teacher": {
        "ru": "Преподаватель: {teacher}",
        "en": "Teacher: {teacher}",
    },
    "schedule.ics.description.room": {
        "ru": "Аудитория: {room}",
        "en": "Room: {room}",
    },
    "schedule.ics.description.parity_odd": {
        "ru": "Нечётные недели",
        "en": "Odd weeks",
    },
    "schedule.ics.description.parity_even": {
        "ru": "Чётные недели",
        "en": "Even weeks",
    },
    "schedule.lesson.type.lecture": {
        "ru": "Лекция",
        "en": "Lecture",
    },
    "schedule.lesson.type.practice": {
        "ru": "Практическое занятие",
        "en": "Practical class",
    },
    "schedule.lesson.type.lab": {
        "ru": "Лабораторная работа",
        "en": "Lab work",
    },
    "schedule.lesson.type.seminar": {
        "ru": "Семинар",
        "en": "Seminar",
    },
    "schedule.lesson.type.consultation": {
        "ru": "Консультация",
        "en": "Consultation",
    },
    "schedule.lesson.default_type": {
        "ru": "Лекция",
        "en": "Lecture",
    },
    "schedule.weekday.monday": {"ru": "Понедельник", "en": "Monday"},
    "schedule.weekday.monday_short": {"ru": "пн", "en": "mon"},
    "schedule.weekday.tuesday": {"ru": "Вторник", "en": "Tuesday"},
    "schedule.weekday.tuesday_short": {"ru": "вт", "en": "tue"},
    "schedule.weekday.wednesday": {"ru": "Среда", "en": "Wednesday"},
    "schedule.weekday.wednesday_short": {"ru": "ср", "en": "wed"},
    "schedule.weekday.thursday": {"ru": "Четверг", "en": "Thursday"},
    "schedule.weekday.thursday_short": {"ru": "чт", "en": "thu"},
    "schedule.weekday.friday": {"ru": "Пятница", "en": "Friday"},
    "schedule.weekday.friday_short": {"ru": "пт", "en": "fri"},
    "schedule.weekday.saturday": {"ru": "Суббота", "en": "Saturday"},
    "schedule.weekday.saturday_short": {"ru": "сб", "en": "sat"},
    "schedule.weekday.sunday": {"ru": "Воскресенье", "en": "Sunday"},
    "schedule.weekday.sunday_short": {"ru": "вс", "en": "sun"},
    "schedule.query.group_id_description": {
        "ru": "Идентификатор группы",
        "en": "Group identifier",
    },
    "validation.dnd.times_required": {
        "ru": 'Укажите время начала и окончания режима "Не беспокоить"',
        "en": 'Provide both start and end times for "Do Not Disturb" mode',
    },
    "validation.timezone.invalid": {
        "ru": "Укажите корректный идентификатор часового пояса",
        "en": "Enter a valid time zone identifier",
    },
    "validation.events.end_after_start": {
        "ru": "Время окончания должно быть позже времени начала мероприятия",
        "en": "The end time must be later than the start time",
    },
    "validation.events.times_required": {
        "ru": "Укажите время начала и окончания мероприятия одновременно",
        "en": "Provide both start and end times for the event",
    },
}


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
    except Exception:  # pragma: no cover - defensive
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
                except Exception:  # pragma: no cover - defensive
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
            except AttributeError:  # pragma: no cover - defensive
                header_value = None
            normalized = _locale_from_accept_language(header_value)
            if normalized:
                return normalized

    fallback = _normalize_locale(default) or DEFAULT_LOCALE
    return fallback


def translate(
    key: str,
    *,
    locale: str | None = None,
    request: Any = None,
    user: Any = None,
    default: str | None = None,
    **kwargs: Any,
) -> str:
    resolved = resolve_locale(locale=locale, request=request, user=user)
    entry = _TRANSLATIONS.get(key)

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
        except KeyError:  # pragma: no cover - defensive
            return text
    return text


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
            entry = _TRANSLATIONS.get(translation_key)
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


__all__ = [
    "SUPPORTED_LOCALES",
    "DEFAULT_LOCALE",
    "resolve_locale",
    "normalize_locale",
    "localized_text",
    "translate",
    "translate_lesson_type",
    "weekday_aliases",
    "resolve_weekday_index",
]
