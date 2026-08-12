from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

TRANSLATIONS: Mapping[str, Mapping[str, str]] = {
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
            "Вы запросили сброс пароля в Экосистеме ГУУ. "
            "Ссылка действует {minutes} минут."
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
    "email.lockout.subject": {
        "ru": "Учетная запись заблокирована — Экосистема ГУУ",
        "en": "Account locked — GUU Ecosystem",
    },
    "email.lockout.heading": {
        "ru": "Учетная запись заблокирована",
        "en": "Account Locked",
    },
    "email.lockout.greeting": {
        "ru": "Здравствуйте{name}!",
        "en": "Hello{name}!",
    },
    "email.lockout.body": {
        "ru": "Ваша учетная запись была временно заблокирована из-за слишком большого количества неудачных попыток входа.",
        "en": "Your account has been temporarily locked due to too many failed login attempts.",
    },
    "email.lockout.action": {
        "ru": "Пожалуйста, подождите или обратитесь в службу поддержки для разблокировки.",
        "en": "Please wait or contact support to unlock your account.",
    },
    "email.lockout.plain": {
        "ru": "Ваша учетная запись временно заблокирована из-за слишком большого количества неудачных попыток входа.",
        "en": "Your account has been temporarily locked due to too many failed login attempts.",
    },
    "errors.already_exists": {
        "ru": "Запись уже существует: {identifier}",
        "en": "Record already exists: {identifier}",
    },
    "errors.not_found": {
        "ru": "Не найдено",
        "en": "Not found",
    },
    "titles.bad_request": {
        "ru": "Некорректный запрос",
        "en": "Bad Request",
    },
    "titles.unauthorized": {
        "ru": "Не авторизован",
        "en": "Unauthorized",
    },
    "titles.forbidden": {
        "ru": "Доступ запрещён",
        "en": "Access Denied",
    },
    "titles.not_found": {
        "ru": "Ресурс не найден",
        "en": "Resource Not Found",
    },
    "titles.conflict": {
        "ru": "Конфликт ресурсов",
        "en": "Resource Conflict",
    },
    "titles.method_not_allowed": {
        "ru": "Метод не поддерживается",
        "en": "Method Not Allowed",
    },
    "titles.validation_error": {
        "ru": "Ошибка валидации",
        "en": "Validation Error",
    },
    "titles.rate_limit_exceeded": {
        "ru": "Лимит запросов исчерпан",
        "en": "Rate Limit Exceeded",
    },
    "titles.internal_server_error": {
        "ru": "Внутренняя ошибка сервера",
        "en": "Internal Server Error",
    },
    "titles.http_error": {
        "ru": "Ошибка протокола HTTP",
        "en": "HTTP Error",
    },
    "errors.csrf.mismatch": {
        "ru": "Несоответствие CSRF-токена",
        "en": "CSRF token mismatch",
    },
    "errors.config.payload_too_large": {
        "ru": "Размер запроса слишком велик (макс. {limit} МБ)",
        "en": "Payload Too Large (max {limit} MB)",
    },
    "errors.config.invalid_content_length": {
        "ru": "Некорректный заголовок Content-Length",
        "en": "Invalid Content-Length header",
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
            "Администратор отключил ваши MFA-методы. "
            "Настройте защиту повторно при следующем входе."
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
    "errors.mfa.invalid_challenge": {
        "ru": "Недействительный или просроченный запрос проверки.",
        "en": "Invalid or expired verification challenge.",
    },
    "errors.mfa.code_required": {
        "ru": "Введите код подтверждения.",
        "en": "Confirmation code is required.",
    },
    "errors.mfa.invalid_code": {
        "ru": "Неверный код подтверждения.",
        "en": "Invalid confirmation code.",
    },
    "errors.mfa.totp_limit_reached": {
        "ru": "У вас уже подключено приложение-аутентификатор.",
        "en": (
            "Only one authenticator app can be connected at a time. "
            "Remove the existing app before starting a new setup."
        ),
    },
    "errors.mfa.enrollment_pending": {
        "ru": "У вас уже есть незавершенная настройка MFA.",
        "en": (
            "A TOTP enrollment is already pending. "
            "Confirm or reuse it before starting a new one."
        ),
    },
    "errors.auth.user_deactivated": {
        "ru": "Пользователь деактивирован",
        "en": "User account is deactivated",
    },
    "errors.auth.password_policy": {
        "ru": "Пароль не соответствует требованиям безопасности.",
        "en": "Password does not meet the security requirements.",
    },
    "errors.auth.password_policy_length": {
        "ru": "Пароль должен содержать от {min_length} до {max_length} символов.",
        "en": "Password must be between {min_length} and {max_length} characters long.",
    },
    "errors.auth.password_policy_required_classes": {
        "ru": "Пароль должен содержать: {classes}.",
        "en": "Password must include: {classes}.",
    },
    "errors.auth.password_policy_min_classes": {
        "ru": (
            "Пароль должен содержать минимум {min_classes} из следующих категорий: "
            "{classes}."
        ),
        "en": (
            "Password must include at least {min_classes} of the following "
            "categories: {classes}."
        ),
    },
    "errors.auth.password_policy_strength": {
        "ru": "Пароль слишком простой. Используйте более сложный пароль.",
        "en": "Password is too weak. Use a stronger password.",
    },
    "errors.auth.password_policy_compromised": {
        "ru": "Пароль был обнаружен в утечках данных. Выберите другой пароль.",
        "en": (
            "This password has appeared in data breaches. Choose a different password."
        ),
    },
    "errors.auth.password_policy_hibp_unavailable": {
        "ru": "Не удалось проверить пароль по базе утечек. Попробуйте позже.",
        "en": (
            "Unable to check the password against the breach database. Try again later."
        ),
    },
    "password.class.uppercase": {
        "ru": "заглавные буквы",
        "en": "uppercase letters",
    },
    "password.class.lowercase": {
        "ru": "строчные буквы",
        "en": "lowercase letters",
    },
    "password.class.digit": {
        "ru": "цифры",
        "en": "digits",
    },
    "password.class.symbol": {
        "ru": "специальные символы",
        "en": "symbols",
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
    "errors.chat.group_name_required": {
        "ru": "Требуется название группы",
        "en": "Group name is required",
    },
    "errors.chat.group_too_few_members": {
        "ru": "В группе должно быть не менее 3 участников",
        "en": "A group needs at least 3 members",
    },
    "errors.chat.group_too_many_members": {
        "ru": "В группе не может быть более 100 участников",
        "en": "A group cannot exceed 100 members",
    },
    "errors.chat.not_a_group": {
        "ru": "Это действие доступно только в групповых чатах",
        "en": "This action is only allowed in group chats",
    },
    "errors.chat.remove_forbidden": {
        "ru": "Удалять других участников может только владелец группы",
        "en": "Only the group owner can remove other members",
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
    "errors.common.bad_request": {
        "ru": "Некорректный запрос: {status_details}",
        "en": "Bad request: {status_details}",
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
    "notifications.push.validation.endpoint_invalid": {
        "ru": "Endpoint должен быть безопасным HTTPS-адресом",
        "en": "Endpoint must be a safe HTTPS URL",
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
    "errors.events.attendance_registration_failed": {
        "ru": "Не удалось зарегистрироваться на мероприятие",
        "en": "Failed to register for the event",
    },
    "errors.dlq.invalid_status": {
        "ru": "Некорректный статус. Допустимые значения: {statuses}",
        "en": "Invalid status. Must be one of: {statuses}",
    },
    "success.dlq.retry_queued": {
        "ru": "Задание {job_id} поставлено в очередь на повтор",
        "en": "Job {job_id} queued for retry",
    },
    "errors.spotify.service_unavailable": {
        "ru": "Служба Spotify временно недоступна",
        "en": "Spotify service is temporarily unavailable",
    },
    "errors.spotify.api_error": {
        "ru": "Ошибка API Spotify (код {status_code})",
        "en": "Spotify API error (status {status_code})",
    },
}
