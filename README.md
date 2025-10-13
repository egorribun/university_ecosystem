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
| `SECURITY_CSP` | — | Необязательный шаблон CSP с плейсхолдерами `{nonce}` и `{connect_src}`; по умолчанию backend собирает dev-политику (Report-Only, HMR origin) и prod-политику (nonce + `strict-dynamic`). |
| `SECURITY_CSP_REPORT_ONLY` | `true` | Принудительный режим `Content-Security-Policy-Report-Only` (по умолчанию dev=true, prod=false). |
| `SECURITY_CONNECT_SRC_EXTRA` | `https://api.spotify.com,https://fcm.googleapis.com` | Дополнительные хосты для директивы `connect-src`. |
| `ENABLE_COOP` | `false` | Включает заголовок `Cross-Origin-Opener-Policy: same-origin`; по умолчанию отключён и должен включаться осознанно. |
| `ENABLE_COEP` | `false` | Включает заголовок `Cross-Origin-Embedder-Policy`; по умолчанию отключён, разрешает dev-режим без COEP. |
| `COEP_VALUE` | `require-corp` / `credentialless` | Значение COEP, используется только при `ENABLE_COEP=true`. |
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
>
> По умолчанию backend в dev-режиме включает CSP в режиме Report-Only (с разрешением `http://localhost:5173`, `ws://localhost:5173`, `http://127.0.0.1:8000`) и не выставляет COOP/COEP. В production при `ENABLE_STRICT_SECURITY_HEADERS=true` отдаётся строгая политика с `nonce` + `strict-dynamic`, директивой `require-trusted-types-for 'script'` и белым списком политик `trusted-types app dompurify-news goog#html 'allow-duplicates'`.

### Переменные окружения фронтенда (Vite)

| Переменная | Пример | Назначение |
| --- | --- | --- |
| `VITE_BACKEND_ORIGIN` | `http://127.0.0.1:8000` | Явный origin backend API; dev-сервер Vite проксирует `/api`, `/auth`, `/static` и `/push` на этот адрес. |
| `VITE_ASSETS_BASE` | `http://127.0.0.1:8000` | (Опционально) Базовый origin для медиа/статики, если dev-прокси отключён. |

### HTTPS и origin медиа

- В production фронтенд **и** backend должны обслуживаться по HTTPS. Смешанный контент (`https://app` → `http://api`) блокируется браузерами, поэтому автоматический «даунгрейд» запрещён.
- Все запросы к `/static/...` и `/media/...` собираются в абсолютные URL на основе `VITE_BACKEND_ORIGIN`. В dev-режиме допускается относительный путь только если origin не задан и включён прокси.
- Переменные окружения с префиксом `VITE_` читаются **во время сборки** Vite. Убедитесь, что `VITE_BACKEND_ORIGIN` установлен перед запуском `npm run build`.
- Для продакшена добавлен шаблон `frontend/.env.production`:

```env
VITE_BACKEND_ORIGIN=https://api.example.com
```

- CSP на стороне backend должна разрешать загрузку медиа и статики с API-origin. Пример строгих директив:

```text
Content-Security-Policy:
  default-src 'self';
  img-src 'self' data: https://api.example.com;
  media-src 'self' https://api.example.com;
  connect-src 'self' https://api.example.com;
```

В `docs/DEPLOY.md` приведён пример reverse-proxy конфигурации (Nginx) для проброса `/static` и `/media` к backend, если фронтенд и API находятся на разных доменах.

## Основные команды для разработчиков

- `alembic revision --autogenerate -m "add_feature" && alembic upgrade head` — сгенерировать и применить новую миграцию (использует `Base.metadata`).
- `alembic upgrade head` — привести базу к актуальному состоянию; миграции `push_subscriptions` и тихих часов идемпотентны.
- `uvicorn app.main:app --reload` — запустить backend в dev-режиме (смягчённые заголовки безопасности, статика из `app/static`).
- `npm run dev --prefix frontend` — запустить Vite dev-сервер на `localhost:5173` (прокси к API и статику backend).
- `ENABLE_STRICT_SECURITY_HEADERS=true ENABLE_COOP=true uvicorn app.main:app --host 0.0.0.0 --port 8000` — пример запуска production-инстанса со строгими заголовками (COOP/COEP включайте по необходимости, проксируйте статику через reverse-proxy).
- `pytest` — прогнать автотесты (включая smoke-тесты заголовков, статики и Alembic).

## Проверка

1. В браузере очистите сервис-воркер и хранилище: DevTools → Application → Clear storage → **Clear site data**, затем Unregister.
2. Обновите страницу `/news` и `/events`, убедитесь, что карточки показывают обложки или плейсхолдер.
3. Перейдите на любую детальную страницу новости `/news/:id` и мероприятия `/events/:id`, выполните F5 — обложки и аватары должны появляться стабильно.
4. В DevTools → Network убедитесь, что запросы к изображениям идут на нужный HTTPS-origin backend и не получают `404` или `blocked:mixed-content`. Ответы должны приходить из сети (или из кэша `backend-static` при повторе), но не из устаревшего Service Worker.
