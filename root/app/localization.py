"""Simple localization utilities for backend responses."""

from __future__ import annotations

from typing import Any, Mapping

SUPPORTED_LOCALES: set[str] = {"en", "ru"}
DEFAULT_LOCALE = "en"

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
        "ru": "Вы запросили сброс пароля в Экосистеме ГУУ. Ссылка действует {minutes} минут.",
        "en": "You requested a password reset in the GUU Ecosystem. The link is valid for {minutes} minutes.",
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
    "notifications.actions.open_schedule": {
        "ru": "Открыть расписание",
        "en": "Open schedule",
    },
    "notifications.default_title": {
        "ru": "Уведомление",
        "en": "Notification",
    },
    "errors.auth.credentials_invalid": {
        "ru": "Не удалось подтвердить учётные данные",
        "en": "Could not validate credentials",
    },
    "errors.auth.user_deactivated": {
        "ru": "Пользователь деактивирован",
        "en": "User account is deactivated",
    },
    "errors.forbidden": {
        "ru": "Доступ запрещён",
        "en": "Access denied",
    },
    "errors.events.registration_forbidden": {
        "ru": "Регистрация на мероприятия недоступна для вашей роли",
        "en": "Event registration is not available for your role",
    },
    "errors.events.not_found": {
        "ru": "Событие не найдено",
        "en": "Event not found",
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
    "schedule.ics.lesson_default_subject": {
        "ru": "Занятие",
        "en": "Lesson",
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
    "schedule.lesson.default_type": {
        "ru": "Лекция",
        "en": "Lecture",
    },
    "schedule.query.group_id_description": {
        "ru": "Идентификатор группы",
        "en": "Group identifier",
    },
    "validation.dnd.times_required": {
        "ru": 'Укажите время начала и окончания режима "Не беспокоить"',
        "en": 'Provide both start and end times for "Do Not Disturb" mode',
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


__all__ = ["SUPPORTED_LOCALES", "DEFAULT_LOCALE", "resolve_locale", "translate"]
