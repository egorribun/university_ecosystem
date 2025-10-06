Единая цифровая платформа университета: расписание занятий, события и новости, карта кампуса, профиль пользователя и уведомления — всё в одном месте. Проект создан для студентов, преподавателей и администраторов, чтобы ускорить коммуникацию и упростить повседневные задачи.

[![Backend image size badge](https://img.shields.io/badge/image%20size-slim%20runtime-0AA660?logo=docker)](root/backend.Dockerfile)
[![Container vuln badge](https://img.shields.io/badge/vulns-trivy%20scan-7E22CE?logo=trivy)](.github/workflows/container-security.yml)

## Что внутри (коротко)
- 🗓️ Расписание группы с учётом чётности недель и быстрым просмотром «сегодня».
- 📰 Новости и объявления с поддержкой изображений.
- 🎟️ События: афиша, регистрация, вложения.
- 🗺️ Карта кампуса (корпуса, аудитории, точки интереса).
- 🔔 Уведомления: web-push и email.
- 👤 Профиль: аватар/обложка, базовые настройки.
- 🎧 Интеграция со Spotify (OAuth, now playing).
- Адаптивный минималистичный интерфейс с плавными анимациями.

> Цель проекта — собрать ключевые сервисы студента и преподавателя в удобной экосистеме с современным UX и открытой архитектурой для дальнейших интеграций.

## Безопасность хранения паролей

- 🔐 Новые и мигрированные пароли хранятся в формате `argon2id` (Passlib), параметры: time cost `3`, memory cost `65536 KiB` (~64 MB) и параллелизм `4`. Эти настройки соответствуют рекомендациям OWASP по адаптивным алгоритмам.
- 🔄 Легаси-хеши `bcrypt` автоматически проверяются и при успешном входе пересчитываются в `argon2id`, что устраняет ограничение bcrypt на 72 байта.
- 📏 Политика длины: от 8 до 200 символов, поддерживается полный Unicode (пароли не нормализуются и не обрезаются по пробелам).
- 🧪 Покрыты автоматическими тестами: валидные и невалидные длины, миграция при логине, поддержка Unicode и демонстрация ограничения `bcrypt`.

## Dev Container

- 🔄 Предустановленные Python и Node зависимости собираются на этапе создания контейнера, а повторная установка берёт пакеты из прокешированных каталогов.
- 📦 В контейнер автоматически монтируются отдельные volume-диски для pip (`/home/vscode/.cache/pip`) и npm (`/home/vscode/.npm`), поэтому повторные `pip install`/`npm ci` работают быстрее.
- ▶️ В VS Code доступны готовые задачи: **Run API** (UVicorn + auto-reload), **Run Web** (Vite dev-сервер) и **Test All** (pytest + фронтовые тесты).

## Supply chain & контейнерная безопасность

- 🧱 **Multi-stage Dockerfile**: сборка Python-зависимостей проходит в отдельном builder-слое, а рантайм образ получает только готовый `venv` и приложение без build-инструментов. Это уменьшает итоговый размер и ускоряет rebuild за счёт кэша `pip`/`apt`.
- 🔍 **Trivy в CI**: новый workflow `Container security` собирает backend-образ, запускает сканирование образа и файловой системы (`vuln`, `config`, `secret` проверки) и выгружает отчёты в формате SARIF + артефакты.
- 🚦 **Политика по уровням**: по умолчанию пайплайн падает при находке `HIGH`/`CRITICAL`, но порог можно поменять через репозиторский variable `TRIVY_FAIL_SEVERITIES`.
- 📊 **Отчётность и бейджи**: SARIF отправляется в Code Scanning, а бейджи выше ведут к Dockerfile и пайплайну, где доступны размер образа и свежие результаты сканов.

## Переменные окружения

| Переменная | Пример | Назначение |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host/db` | Подключение к основной БД (используется SQLAlchemy и Alembic). |
| `SECRET_KEY` | `super-secret` | Ключ подписи JWT и внутренних токенов. |
| `FRONTEND_ORIGINS` | `https://app.example.com,https://admin.example.com` | Список доверенных origin для CORS и CSP (`FRONTEND_ORIGIN`/`APP_BASE_URL` дополняют этот список). |
| `ENABLE_STRICT_SECURITY_HEADERS` | `true`/`false` | Принудительно включает или отключает строгий режим безопасности (по умолчанию prod=ON, dev=OFF). |
| `SECURITY_CSP` | см. `.env.example` | Базовая CSP-политика; шаблон содержит плейсхолдеры `{nonce}` и `{connect_src}`. |
| `SECURITY_CSP_REPORT_ONLY` | `true` | Переключение в режим `Content-Security-Policy-Report-Only` (по умолчанию включается в development). |
| `SECURITY_CONNECT_SRC_EXTRA` | `https://api.spotify.com,https://fcm.googleapis.com` | Дополнительные хосты для директивы `connect-src`. |
| `ENABLE_COOP` | `false` | Управление заголовком `Cross-Origin-Opener-Policy`; если не задан, следует режиму strict headers. |
| `ENABLE_COEP` | `true` | Управление заголовком `Cross-Origin-Embedder-Policy`; по умолчанию выключается в dev. |
| `COEP_VALUE` | `require-corp` / `credentialless` | Значение заголовка COEP при включении. |
| `SECURITY_HSTS_ENABLED` | `true` | Разрешает HSTS (автоматически отключается для не-HTTPS хостов). |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` | `smtp.example.com` / `587` / ... | Настройки SMTP-отправки писем. |
| `SMTP_SECURITY` | `ssl` / `starttls` / `none` | Тип защиты SMTP-сессии. |
| `SMTP_STARTTLS` | `true` | Принудительное включение STARTTLS (для старых конфигураций). |
| `MAIL_FROM` | `no-reply@example.com` | Отправитель уведомлений по email. |
| `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` | — | Ключи для Web Push VAPID. |
| `VAPID_SUBJECT` | `mailto:admin@example.com` | Контакт для push-подписок. |
| `SENTRY_DSN` / `SENTRY_ENVIRONMENT` | — | Интеграция с Sentry (опционально). |
| `ENABLE_OTEL` / `OTEL_EXPORTER_OTLP_ENDPOINT` | `true` / `https://otel.example.com` | Экспорт метрик и трасс в OpenTelemetry. |
| `SECURITY_CSP_REPORT_URI` | `https://csp.example.com/report` | Добавляет `report-uri` к CSP для сбора отчётов. |

> Списки значений указываются через запятую. Для переменных, связанных с безопасностью, значения по умолчанию подходят для production; в development можно переопределить их в `.env.local`.
