# University Ecosystem

[![CI](https://github.com/OWNER/university_ecosystem/actions/workflows/ci.yml/badge.svg)](https://github.com/OWNER/university_ecosystem/actions/workflows/ci.yml)

Единая цифровая платформа университета: расписание занятий, события и новости, карта кампуса, профиль пользователя и уведомления — всё в одном месте. Проект создан для студентов, преподавателей и администраторов, чтобы ускорить коммуникацию и упростить повседневные задачи.

## Что внутри (коротко)
- 🗓️ Расписание группы с учётом чётности недель и быстрым просмотром «сегодня».
- 📰 Новости и объявления с поддержкой изображений.
- 🎟️ События: афиша, регистрация, вложения.
- 🗺️ Карта кампуса (корпуса, аудитории, точки интереса).
- 🔔 Уведомления: web-push и email.
- 👤 Профиль: аватар/обложка, базовые настройки.
- 🎧 Интеграция со Spotify (OAuth, now playing).
- ♿ Адаптивный минималистичный интерфейс с плавными анимациями.

> Цель проекта — собрать ключевые сервисы студента и преподавателя в удобной экосистеме с современным UX и открытой архитектурой для дальнейших интеграций.

## Быстрый старт

1. Склонируйте репозиторий и подготовьте окружение:

   ```bash
   git clone git@github.com:OWNER/university_ecosystem.git
   cd university_ecosystem
   cp root/.env.example root/.env
   cp root/frontend/.env.example root/frontend/.env
   ```

2. Создайте виртуальное окружение, установите Python-зависимости (включая `pre-commit`) и Node-пакеты фронтенда:

   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r root/requirements.txt
   npm --prefix root/frontend install
   npm --prefix root/frontend run prepare
   ```

   Хуки используют [pre-commit](https://pre-commit.com/) для Python и [Husky](https://typicode.github.io/husky) + lint-staged для фронтенда.

3. Запустите приложения разработки:

   ```bash
   uvicorn app.main:app --reload --env-file root/.env --app-dir root/app
   npm --prefix root/frontend run dev
   ```

4. Проверьте тесты:

   ```bash
   pytest -q
   npm --prefix root/frontend run test
   ```

5. Убедитесь, что форматирование и PWA-сборка в порядке:

   ```bash
   pre-commit run --all-files
   npm --prefix root/frontend run lint
   npm --prefix root/frontend run format:check
   npm --prefix root/frontend run build
   ```

## Команды

### Backend (`root/`)

- `uvicorn app.main:app --reload --env-file root/.env --app-dir root/app` — дев-сервер FastAPI.
- `pytest` — юнит- и интеграционные тесты.
- `pre-commit run --all-files` — полный прогон ruff/black/isort.
- `alembic upgrade head` — применение миграций.

### Frontend (`root/frontend/`)

- `npm run dev` — Vite dev server.
- `npm run lint` — проверка ESLint для ключевых экранов.
- `npm run test` / `npm run test:watch` — Vitest.
- `npm run test:e2e` — Playwright.
- `npm run lint:all` и `npm run format:check` — полный прогон ESLint/Prettier при необходимости.
- `npm run build` — продакшн-сборка с генерацией PWA-артефактов.
- `npm run lint-staged` — запуск lint-staged для текущих изменений.
- `npm run prepare` — переустановка Husky-хуков (выполняется автоматически после `npm install`).

### Docker

- `docker compose up --build` — поднять все сервисы (backend, frontend, postgres).
- `docker compose down -v` — остановить и очистить тома.

## Требования к PR

- Перед коммитом дайте Husky выполнить `pre-commit` и `lint-staged`; убедитесь, что `pre-commit run --all-files` и `npm --prefix root/frontend run lint` проходят без ошибок.
- Прогоните тесты: `pytest` и `npm --prefix root/frontend run test` (дополнительно `npm run test:e2e` при изменении e2e).
- Обновляйте `README.md`, `.env.example` и примеры конфигураций при добавлении новых параметров.
- Поддерживайте небольшие осмысленные коммиты, описывайте изменения в PR и следите за зелёным CI.

## Разработка в VS Code Dev Container

> Требования: [Docker Desktop](https://www.docker.com/products/docker-desktop/) или совместимый движок, [Visual Studio Code](https://code.visualstudio.com/) и расширение [Dev Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers).

1. Создайте `root/.env` из примера, как описано выше — файл автоматически пробрасывается во все сервисы.
2. Откройте репозиторий в VS Code и выполните команду **Dev Containers: Reopen in Container**.
3. После сборки образа автоматически установятся Python/Node зависимости, а рекомендуемые расширения (`Python`, `Pylance`, `Docker`, `ESLint`, `Prettier`) будут добавлены в рабочую среду.
4. Бэкенд (FastAPI) и фронтенд (Vite) стартуют внутри контейнеров по адресам `http://localhost:8000` и `http://localhost:5173` соответственно. База данных доступна на `localhost:5432`.

Остановка dev-контейнера автоматически выключит связанные сервисы (`shutdownAction: stopCompose`).

## Обновления зависимостей

- Dependabot автоматически проверяет `npm`, `pip` и GitHub Actions каждую неделю в понедельник в 04:00–06:00 UTC, создавая сгруппированные PR-ы с префиксами `build` и `ci`.
- Обновления приходят единым пулл-реквестом для каждого набора зависимостей, что упрощает ревью и снижает количество конфликтов.
- После мержа обновлений автоматически запускается пайплайн `CI`, что гарантирует прохождение тестов перед деплоем.

## Наблюдаемость и обработка ошибок

- Для проверки живости и готовности сервиса доступны эндпоинты `GET /healthz` (быстрый ответ FastAPI и пинг базы) и `GET /ready` (ожидает восстановление соединения с базой).
- Структурированные логи (JSON) содержат уровни, имена логгеров, `trace_id`, `span_id` и `request_id`. Заголовок корреляции по умолчанию `X-Request-ID`, но можно переопределить через `REQUEST_ID_HEADER`.
- OpenTelemetry включается установкой `ENABLE_OTEL=true`. Дополнительные настройки: `OTEL_SERVICE_NAME`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_HEADERS`, `OTEL_TRACE_SAMPLER_RATIO`, `ENABLE_OTEL_METRICS` и `ENABLE_OTEL_LOGS`. Трейсы FastAPI и SQLAlchemy, метрики и логи отправляются в OTLP-совместимый бекенд.
- Для Sentry задайте `SENTRY_DSN` и, при необходимости, `SENTRY_ENVIRONMENT`, `SENTRY_TRACES_SAMPLE_RATE`, `SENTRY_PROFILES_SAMPLE_RATE`. Ошибки связываются с trace-id из OpenTelemetry.
- SQLAlchemy использует `pool_pre_ping` и повторяет создание сессии при инвалидированном соединении, поэтому кратковременный разрыв подключения к БД не приводит к падению приложения.

## Безопасность и ограничения запросов

- SlowAPI применяет глобальные лимиты (`RATE_LIMIT_DEFAULT`) и отдельные ограничения для чувствительных операций (`RATE_LIMIT_SENSITIVE`, например логин и регистрация). Хранилище счётчиков настраивается через `RATE_LIMIT_STORAGE_URI`, заголовки `Retry-After` — через `RATE_LIMIT_HEADERS_ENABLED`.
- HTTP-ответы дополняются заголовками: строгий CSP (`SECURITY_CSP`, по умолчанию в режиме Report-Only), HSTS (`SECURITY_HSTS_*`), `X-Frame-Options` (`SECURITY_X_FRAME_OPTIONS`) и `Permissions-Policy` (`SECURITY_PERMISSIONS_POLICY`).
- CORS использует whitelisting: списки методов и заголовков управляются переменными `CORS_ALLOW_METHODS`, `CORS_ALLOW_HEADERS`, `CORS_EXPOSE_HEADERS`, а домены — через `FRONTEND_ORIGINS`/`FRONTEND_ORIGIN`.

### Как ослабить политику в разработке

- Отключите лимиты, установив `RATE_LIMIT_ENABLED=false`, либо задайте более мягкие значения в `RATE_LIMIT_DEFAULT`/`RATE_LIMIT_SENSITIVE` (например, `500/minute`).
- Для отладки фронтенда расширьте CSP: укажите `SECURITY_CSP="default-src 'self'; script-src 'self' 'unsafe-inline' http://localhost:5173"` и оставьте `SECURITY_CSP_REPORT_ONLY=true`, чтобы браузер только логировал нарушения. При необходимости добавьте `SECURITY_CSP_REPORT_URI` для сбора отчётов.
- Чтобы избежать проблем с локальным HTTP, установите `SECURITY_HSTS_ENABLED=false` и при необходимости ослабьте `SECURITY_PERMISSIONS_POLICY`/`SECURITY_X_FRAME_OPTIONS`.

## Что пофиксили и почему

- Настроили конфигурацию на Pydantic v2: настройки читаются из `.env`/`.env.local`/`.env.example` в любом каталоге запуска, добавлены вспомогательные списки CORS и доверенных хостов.
- Обновили создание асинхронного движка SQLAlchemy с `NullPool` в dev и проверкой подключения через `wait_db`, что избавляет от ошибок при горячей перезагрузке.
- Перевели FastAPI-приложение на lifespan, добавили `/healthz`, корректную инициализацию статики, CORS и безопасную работу планировщика уведомлений при hot-reload.
- Убрали прямые обращения к `os.getenv` в коде: всё читает настройки через `settings`, что упрощает сопровождение и запуск на Windows.

## Прогрессивное веб-приложение

- Фронтенд переведён на `vite-plugin-pwa` с Workbox: сервис-воркер кеширует HTML, статику и API с подходящими стратегиями, автоматически обновляется и отдаёт офлайн-страницу.
- Для локальной разработки установка и сборка остаются прежними (`npm install`, `npm run dev`). Сборка (`npm run build`) теперь дополнительно генерирует `sw.js`, `manifest.webmanifest` и ресурсы для офлайн-режима.
- В продакшене приложение можно установить на домашний экран: манифест включает иконки, цветовую схему и режим `standalone`.
- Установленная PWA продолжает открывать главную (`/`) и страницу входа (`/login`) даже без сети: сервис-воркер возвращает кешированный app-shell и обновляет его при следующем подключении.
- Маскируемые иконки PWA генерируются во время сборки из base64-данных, поэтому бинарные ассеты не попадают в историю репозитория.
