# Деплой фронтенда и медиа

_[Русская версия](DEPLOY.md) · [English version](DEPLOY.en.md)_

## Переменные окружения

- Перед сборкой фронтенда установите `VITE_BACKEND_ORIGIN` (например, через `frontend/.env.production`).
- Интерактивная карта использует MapLibre и OpenFreeMap; отдельный ключ конструктора не требуется. Для её загрузки нужен доступ к сети.
- Файл `.env.example` служит только шаблоном: обязательные пароли и ключи намеренно не имеют небезопасных fallback-значений. Для полного локального запуска используйте PowerShell 7: `.\start-docker.ps1 -Build`; скрипт создаст и синхронизирует `.env`/`.env.docker`. Заполненные файлы не коммитьте.
- Все переменные с префиксом `VITE_` подставляются в код на этапе `npm run build`; изменение значений после сборки эффекта не даст.
- Во время CI/CD экспортируйте `SERVICE_VERSION` (или `APP_VERSION`) перед запуском контейнеров, чтобы пробросить идентификатор сборки в OpenTelemetry (`service.version`). Сборка фронтенда автоматически использует эти значения — а также распространённые CI-переменные вроде `SOURCE_VERSION`, `VERCEL_GIT_COMMIT` или `GITHUB_SHA` — если `VITE_APP_RELEASE` не задана явно.
- Чтобы передать идентификатор релиза в Sentry, задайте `VITE_APP_RELEASE`. Значение подставляется на этапе сборки.
- Для включения клиентского мониторинга ошибок задайте `VITE_SENTRY_DSN` и, при необходимости, `VITE_ENVIRONMENT`. В дев-сборке SDK автоматически не активируется.
- Логгер на фронтенде (`src/app/logger.ts`) автоматически отправляет `logError`/`logWarning` в Sentry и дублирует вывод в консоль. Необработанные `Promise`/`axios` ошибки перехватываются глобальными хендлерами (`initGlobalErrorHandlers()` вызывается в `src/main.tsx`).
- Чтобы собирать Web Vitals, установите `VITE_ENABLE_WEB_VITALS=true`. При необходимости отправляйте метрики на собственный эндпоинт через `VITE_WEB_VITALS_ENDPOINT` (иначе они пишутся в консоль). Флаг игнорируется в dev/test средах, поэтому CI не упадёт даже при включённой переменной.
- Release-blocking полевые Core Web Vitals сертифицируются отдельно workflow
  `cwv-field-certification.yml`. URL exporter выводится только из проверенных,
  привязанных к SHA staging deployment metadata; отдельный export URL не
  принимается. Exporter обязан проверять GitHub OIDC audience
  `university-cwv-exporter`, repository, protected `main` ref и environment
  `staging`, а затем возвращать только наблюдения точных `release_sha`, frontend
  image digest и deploy run/attempt. Поддерживаемый collector contract:
  `web-vitals` 6.1.1 и exporter schema version `1`. Deploy workflow создаёт
  неизменяемый `staging-deployment-<sha>` artifact только после rollout, smoke и
  Kyverno-проверок. Сертификация принимает его по точному run ID/attempt,
  отклоняет старое/частичное/чужое evidence, проверяет p75 LCP/INP/CLS и публикует
  SHA-bound artifact с build-provenance attestation. Ручная загрузка отчёта не
  является допустимым источником release evidence.
- Backend и фронтенд должны работать по HTTPS, иначе браузер заблокирует загрузку `/media` и `/static`.
- Для лимитирования запросов настройте backend с помощью `RATE_LIMIT_STORAGE_BACKEND` и `RATE_LIMIT_STORAGE_URI`. Значение `redis` и URI, полученный из защищённого хранилища через переменные окружения, включает общий сторедж для middleware и чувствительных эндпоинтов; не помещайте учётные данные в URL или историю shell. Установите `memory` или `memory://` для простого однопроцессного режима без внешнего Redis.
- Хранилище отзыва сессий обязано быть единым и выделенным для всех сервисов: backend, gateway и ws-hub используют только `REVOCATION_REDIS_URL`. В штатных Compose/Helm-конфигурациях это отдельный Redis/Valkey с AOF, персистентным томом и `maxmemory-policy noeviction`; кэш (`CACHE_REDIS_URL`) и rate-limit Redis (`REDIS_URL`, DB 3) не являются источниками security-state. Совместное использование cache/rate-limit процесса запрещено: вытеснение `revoked:jti:*` может повторно сделать отозванный JWT действительным.
- Для продакшена есть override (`docker-compose.prod.yml`) с обязательными секретами. <!-- pragma: allowlist secret --> Создайте Compose-секреты `secret_key`, `database_url` и `nats_auth_token`, а путь к файлу пароля PostgreSQL передайте через `POSTGRES_PASSWORD_SOURCE_FILE`. Значение `database_url` должно указывать на `postgresql+asyncpg://...@pgbouncer:5432/university`. Затем запускайте `docker compose --profile prod -f docker-compose.yml -f docker-compose.go.yml -f docker-compose.prod.yml up -d`, явно задав `FRONTEND_ORIGIN` и `FRONTEND_ORIGINS`; Go overlay обязателен, потому что Caddy направляет API и WebSocket-трафик через gateway/ws-hub.
- Helm chart читает подключения из заранее созданного Secret `university-connections` (полный список ключей приведён в `charts/university-ecosystem/values.yaml`). <!-- pragma: allowlist secret --> В production обязательно задайте `applicationSecrets.existingSecret`; этот Secret должен содержать JWT/RSA-ключи, отдельные HMAC/интеграционные секреты, MinIO credentials и Temporal API key, перечисленные там же. Production-render отклоняет plaintext MinIO, Temporal, gRPC и OTLP. Так секреты не попадают в Helm release state, а небезопасная конфигурация не доходит до кластера.

## Локальный Docker: режимы ресурсов

Обычный `.\start-docker.ps1` (и `-Build`/`-Rebuild`) остаётся полным production-like
стендом и запускает весь `docker-compose.full.yml`. Для ноутбука или ограниченного
Docker Desktop используйте явный opt-in режим:

```powershell
.\start-docker.ps1 -Core        # или -Lean
.\start-docker.ps1 -Core -Build
```

Core-режим использует тот же проверенный Compose-файл, но запускает только
приложение и необходимые зависимости: PostgreSQL, Valkey, NATS, MinIO,
SpiceDB, flagd, backend, frontend, gateway, ws-hub, workers, imgproxy и Caddy.
Обработка файлов и зависящие от Temporal сценарии вложений намеренно недоступны:
`file-processor` исключён из core-топологии. Он останавливает уже работающие контейнеры поиска, Temporal и observability
(`redis-exporter`, Elasticsearch, Grafana, Prometheus, Tempo, Loki, Alloy,
Pyroscope и их probe-контейнеры) без удаления образов или именованных томов,
поэтому возврат к полному режиму безопасен. Health-check и Prometheus target
проверки для намеренно не запущенных сервисов не выполняются. Core-режим
предназначен только для локального resource-constrained запуска и не изменяет
production Compose/Helm defaults или CI quality gates.

### Ротация MFA-ключей через External Secrets Operator

Production-деплой ожидает установленный External Secrets Operator и переменную
GitHub Environment `APPLICATION_EXTERNAL_SECRET_NAME`. Указанный
`ExternalSecret` должен находиться в `K8S_NAMESPACE`, иметь
`spec.target.name`, равный `APPLICATION_SECRETS_NAME`, и публиковать Secret с
именами ключей из `applicationSecrets.keys`. Роль деплоя должна иметь
`get/patch` для `externalsecrets.external-secrets.io`; Helm Secret storage
требует `get/list/watch/create/update/patch/delete`; каждый ресурс, фактически
отрендеренный выбранными values, требует
`get/list/watch/create/update/patch/delete`.
Наблюдение за Deployment дополнительно требует `get/list/watch/patch`.
Workflow проверяет эти права до мутаций и принудительно запускает reconciliation,
ждёт condition `Ready`, новое `status.refreshTime` и изменение
`resourceVersion` целевого Secret, после чего сверяет каждый фактически
отрендеренный Helm `secretKeyRef` до upgrade.

Порядок безопасной ротации:

1. В хранилище секретов сначала опубликуйте перекрывающиеся кольца
   `MFA_EMAIL_OTP_HMAC_KEYS`, `MFA_EMAIL_DELIVERY_KEKS` и
   `MFA_TRUSTED_DEVICE_HMAC_KEYS`: новый ключ становится active, предыдущий
   остаётся доступен для проверки или расшифровки. В application Secret должны
   измениться `MFA_EMAIL_OTP_ACTIVE_HMAC_KEY_ID`,
   `MFA_EMAIL_DELIVERY_ACTIVE_KEK_ID` и
   `MFA_TRUSTED_DEVICE_ACTIVE_HMAC_KEY_ID`.
2. Настройте обязательный путь к проверенному скрипту
   `MFA_OVERLAP_SMOKE_SCRIPT=.github/deployment-smoke/mfa-key-overlap.sh`, HTTPS
   endpoints `MFA_SMOKE_BASE_URL` и `MFA_SMOKE_MAILBOX_URL`, а также secrets
   окружения `MFA_SMOKE_EMAIL`, `MFA_SMOKE_PASSWORD` и
   `MFA_SMOKE_MAILBOX_TOKEN`. Mailbox probe должен обрабатывать запрос
   `await_email_otp` и возвращать challenge token, шестизначный код, delivery ID
   и время доставки. Пустой, отсутствующий, изменённый, untracked или выходящий
   из разрешённого каталога скрипт отклоняется.
3. Запустите deploy workflow с `rotate-mfa-keys=true`. До ротации он уменьшает
   outbox-worker до нуля и выпускает OTP старым ключом, оставляя зашифрованный
   delivery envelope в очереди. Затем workflow синхронизирует ExternalSecret и
   проверяет не только новое `resourceVersion`, но и переход всех трёх колец:
   каждый active ID обязан измениться и входить в новое кольцо, а предыдущий
   active ID обязан оставаться в post-rotation overlap ring с тем же key
   material. Валидатор сохраняет в закрытом mode-0600 state только SHA-256
   fingerprints и отклоняет одинаковый key material под разными ID, повторное
   использование любого pre-rotation material как нового active и замену
   материала overlap-ключа. Key material, ID и fingerprints не выводятся.
   Workflow восстанавливает outbox-worker, перезапускает backend и
   ограничивает ожидание consumers 90 секундами, чтобы незавершённый
   10-минутный OTP был проверен сразу, до несвязанного Helm/image rollout.
   Outbox-worker
   получает только `MFA_EMAIL_DELIVERY_KEKS`; OTP/trusted signing keys и active
   signing IDs ему не выдаются.
4. Только после успешной проверки старого OTP workflow выполняет атомарный Helm
   upgrade и остальные release gates, затем выпускает, доставляет и проверяет
   OTP новым ключом. Проверка одной только readiness не считается rotation
   smoke.
5. Удаляйте предыдущий OTP-ключ не раньше истечения 10 минут, delivery KEK —
   только после опустошения outbox и DLQ для старого key ID, а trusted-device
   ключ — не раньше максимального срока trusted device (по умолчанию 30 дней).
   После сужения колец повторите deploy с `rotate-mfa-keys=true`, rollout и
   overlap smoke. Обычные deploy-запуски оставляют этот input выключенным и не
   требуют фиктивного изменения Secret.

Не используйте фиктивную checksum-аннотацию Pod: ExternalSecret не раскрывает
секретное содержимое Helm, поэтому источником истины служат Ready/refreshTime и
`resourceVersion`, а применение новых значений обеспечивается явным rollout.
- Healthcheck-и остаются внутри контейнеров (`127.0.0.1`), а единственная запись `extra_hosts` — `host.docker.internal`; удалите её в продакшене, если доступ к хосту не нужен.
- Prometheus-метрики выключены по умолчанию в `docker-compose.yml`. Чтобы их включить, установите `ENABLE_METRICS_ENDPOINT=true` **и** задайте собственные, стойкие значения `METRICS_BASIC_AUTH_USERNAME` и `METRICS_BASIC_AUTH_PASSWORD` (docker-compose больше не подставляет плейсхолдеры). Backend теперь падает на старте — или возвращает `503` во время запроса — если метрики включены без учётных данных, за исключением случаев, когда allowlist ограничен петлевыми адресами (`127.0.0.1`, `::1`, `localhost`).
- Для включения заголовка `Cross-Origin-Resource-Policy` установите `ENABLE_CORP=true`. Значение задаётся через `CORP_VALUE` (по умолчанию `same-site`; также поддерживаются `same-origin` и `cross-origin`).

## Миграции базы данных

- Перед первым запуском новой версии выполните `alembic upgrade head`:

  ```bash
  cd .
  # DATABASE_URL должен быть заранее передан процессу менеджером секретов.
  test -n "${DATABASE_URL:?DATABASE_URL is required}"
  alembic upgrade head
  ```

- Alembic берёт строку подключения из `alembic.ini`. Если требуется другой
  адрес, задайте его через переменную окружения `DATABASE_URL` (используйте то же
  значение, что и для приложения).
- В docker compose добавлен одноразовый сервис `migrations`, который выполняет
  `alembic upgrade head` до запуска API и воркера. При необходимости повторите
  миграции вручную:

  ```bash
  docker compose run --rm backend alembic upgrade head
  ```

- Helm выполняет тот же переход автоматически блокирующим hook Job
  `pre-install,pre-upgrade`. Secret `connections.existingSecret` должен уже
  существовать до `helm install`; при ошибке миграции rollout приложения не
  начинается. Отключайте `migrations.enabled` только если миграциями управляет
  отдельный проверенный deployment pipeline.
- Резервное копирование в Helm включается через `backup.enabled=true`: init
  container создаёт custom-format `pg_dump`, после чего `minio/mc` загружает
  файл в настроенный bucket. Нужны `backup-database-url` в connection Secret и
  `minio-access-key`/`minio-secret-key` в application Secret.

### Пул соединений базы данных

- В production средах используйте пул SQLAlchemy: задайте `DATABASE_POOL_SIZE` (основной размер пула), `DATABASE_MAX_OVERFLOW` (дополнительные соединения поверх пула), `DATABASE_POOL_TIMEOUT` (секунды ожидания свободного соединения) и `DATABASE_POOL_RECYCLE` (период принудительного закрытия соединений, секунды). Значения по умолчанию — `5`, `10`, `30` и `1800` соответственно.
- Для dev/test окружений приложение автоматически переключается на `NullPool`, чтобы каждое соединение открывалось заново; параметры пула при этом игнорируются. Это избавляет от блокировок SQLite и полезно при локальной разработке.
- Перед деплоем на PostgreSQL или другой продакшн-базе подберите значения в пределах возможностей СУБД. Например, для сервера с ограничением в 20 подключений можно выставить `DATABASE_POOL_SIZE=5` и `DATABASE_MAX_OVERFLOW=5`, оставив запас для фоновых задач и внешних инструментов.

### Особенности SQLite

- Полнотекстовый поиск по событиям использует PostgreSQL-тип `tsvector` и GIN-индекс.
  При запуске на SQLite (локальная разработка, unit-тесты) Alembic создаёт обычный
  текстовый столбец `events.search_vector`, а `crud.get_all_events` автоматически
  переключается на фильтрацию через `LIKE`. Это позволяет запускать приложение без
  дополнительной настройки, но поиск в SQLite выполняется без ранжирования по
  релевантности.

### Метрики фоновых задач

- `/metrics` теперь публикует счётчики и гистограммы для фоновых очисток:
  - `periodic_task_notifications_retention_*` — удаление старых уведомлений и доставок.
  - `periodic_task_password_reset_cleanup_*` — очистка токенов восстановления пароля.
  - `periodic_task_session_cleanup_*` — удаление протухших пользовательских сессий.
  - `periodic_task_story_cleanup_*` — очистка просроченных историй.
  - `periodic_task_mfa_challenge_cleanup_*` — удаление просроченных и потреблённых MFA-челленджей.
- Для каждой задачи доступны:
  - `*_runs_total` — количество успешных итераций.
  - `*_errors_total` — количество завершений с исключением.
  - `*_deleted_total` — суммарное число удалённых записей за всё время.
  - `*_duration_seconds{_bucket,_sum,_count}` — гистограмма продолжительности выполнения.

```bash
# пример
cd frontend
cp .env.production .env.local      # при необходимости
VITE_APP_RELEASE=$(git rev-parse --short HEAD) \
  VITE_BACKEND_ORIGIN=https://api.example.com npm run build
```

- Локализованные PWA-манифесты собираются из
  `frontend/public/manifest.source.json` (путь от корня репозитория; из каталога
  `frontend`, показанного выше, это `public/manifest.source.json`). Выполните
  `npm run generate:manifests` перед сборкой или запустите
  `npm run manifests:check`, чтобы убедиться, что сгенерированные файлы в
  `frontend/public/` не устарели.

### Офлайн-режим PWA

- Service Worker кеширует SPA-shell (`_shell.html`) и выдаёт его для любых SPA-навигаций при
  отсутствии сети; если shell недоступен, отдаётся `offline.html` из precache.
- Запросы к API для расписания, новостей и событий (`/api/schedule`, `/api/news`,
  `/api/events`) работают по стратегии stale-while-revalidate: при сбое сети
  возвращаются сохранённые ответы, а при их отсутствии — пустые офлайн-плейсхолдеры
  с заголовками `X-Offline-Fallback`/`X-Offline-Resource`.
- Эндпоинты медиа/статических файлов остаются в NetworkFirst с ограничением размера кеша
  (24 часа, до 200 записей).
- Интерактивная карта и её lazy-чанки MapLibre намеренно не входят в install-time precache:
  это удерживает манифест ниже консервативного лимита CacheStorage. Offline-shell и
  общая fallback-страница остаются доступными без сети; маршрут карты (включая
  статический список) при холодной офлайн-загрузке требует сети.
- Production-сборка завершается с ошибкой, если суммарный precache превышает 4 800 000 байт. Это
  оставляет запас для Firefox и WebKit и защищает от незаметного возврата тяжёлых lazy-чанков.
  Chromium E2E-сборка с покрытием (`E2E_COVERAGE=true` и
  `FRONTEND_BUILD_UNMINIFIED=true`) использует отдельный диагностический предел 9 000 000 байт;
  такой unminified-артефакт не предназначен для деплоя.
- Проверить офлайн-навигацию и кеширование данных можно e2e-тестом:

  ```bash
  cd frontend
  npm run test:e2e -- offline.spec.ts
  ```

### Spotify токены

- Backend шифрует Spotify access/refresh токены с помощью Fernet. Перед включением интеграции задайте `SPOTIFY_TOKEN_SECRET` — это base64-строка из `Fernet.generate_key()`.

```bash
python - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
```

- Для ротации передайте список Fernet-ключей из защищённого хранилища через переменную окружения: новый ключ укажите первым, старый оставьте вторым. Не вставляйте материал ключей в команды или документацию. После деплоя выполните скрипт ниже, чтобы перешифровать уже сохранённые значения и убрать зависимость от старого ключа, затем удалите старый ключ из хранилища и перезапустите сервисы.

```bash
python - <<'PY'
import asyncio
from sqlalchemy import text

from app.core.database import async_session
from app.utils.encryption import rotate_encrypted_string


async def main() -> None:
    async with async_session() as session:
        rows = await session.execute(
            text(
                "SELECT id, spotify_access_token, spotify_refresh_token FROM users"
            )
        )
        for row in rows.all():
            await session.execute(
                text(
                    "UPDATE users SET spotify_access_token = :access, "
                    "spotify_refresh_token = :refresh WHERE id = :user_id"
                ),
                {
                    "user_id": row.id,
                    "access": rotate_encrypted_string(row.spotify_access_token),
                    "refresh": rotate_encrypted_string(row.spotify_refresh_token),
                },
            )
        await session.commit()


asyncio.run(main())
PY
```

### Подпись аудит-логов

- `AUDIT_LOG_SECRET` используется для подписи записей журнала аудита (HMAC-SHA256) и должен отличаться от `SECRET_KEY`.
- Для ротации передайте `AUDIT_LOG_SECRET` из защищённого хранилища как список ключей через запятую: новый первым, старый вторым. После деплоя переподпишите существующие записи, затем удалите старый ключ из хранилища и перезапустите сервисы.

```bash
python - <<'PY'
import asyncio

from sqlalchemy import select

from app.core.database import async_session
from app.models.logs import DataAccessLog
from app.services.audit_service import SecureAuditService


async def main() -> None:
    service = SecureAuditService()
    async with async_session() as session:
        result = await session.execute(
            select(DataAccessLog).where(DataAccessLog.signature.isnot(None))
        )
        updated = 0
        for log in result.scalars().all():
            if service.resign_log(log):
                updated += 1
        if updated:
            await session.commit()
        print(f"Resigned {updated} audit logs.")


asyncio.run(main())
PY
```

## Docker image

- `frontend.Dockerfile` использует отдельные stages для сборки Rust/WASM, установки build/runtime-зависимостей и TanStack Start SSR. Финальный образ основан на закреплённом по digest `node:24-alpine`, запускается непривилегированным пользователем `node` и содержит только production-зависимости, WASM-пакеты, `dist/` и SSR launcher.
- `VITE_BACKEND_ORIGIN` остаётся build-time fallback для фронтенда. Node SSR сначала читает runtime-переменную `BACKEND_ORIGIN`, поэтому один immutable image можно безопасно использовать с разными Compose/Helm service names; chart и Compose уже задают внутренний адрес backend. Браузерные API-запросы остаются same-origin и идут через gateway.
- Статику и SSR отдаёт `frontend/scripts/server-prod.mjs`: хешированные файлы в `assets/` получают `Cache-Control: public, max-age=31536000, immutable`, HTML — `no-cache`/`no-store`.
- Контейнер слушает порт `3000`; Compose публикует frontend напрямую на `127.0.0.1:8081`, а Caddy/Gateway — на `127.0.0.1:8080`. Быстрая readiness/liveness-проверка доступна на `/healthz`.

```bash
# пример локальной сборки
docker compose build frontend
docker compose up frontend
```

## Edge reverse proxy

Каноническая конфигурация edge-маршрутизации находится в `services/caddy/Caddyfile`: Caddy проксирует SSR на `frontend:3000`, API на gateway/backend и WebSocket-трафик на ws-hub под одним origin. Это исключает CORS/Service Worker расхождения. Если окружение требует Nginx, он должен проксировать Node SSR, а не отдавать `dist/client` как SPA:

```nginx
server {
    listen 443 ssl;
    server_name app.example.com;

    location / {
        proxy_pass http://frontend:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        proxy_pass https://api.example.com/static/;
        proxy_set_header Host api.example.com;
        proxy_set_header X-Forwarded-Proto https;
        proxy_redirect off;
    }

    location /media/ {
        proxy_pass https://api.example.com/media/;
        proxy_set_header Host api.example.com;
        proxy_set_header X-Forwarded-Proto https;
        proxy_redirect off;
    }
}
```

> Для браузера предпочтителен same-origin edge. `BACKEND_ORIGIN` предназначен для runtime SSR, а `VITE_BACKEND_ORIGIN` — только build-time fallback; внутренние service DNS нельзя публиковать в клиентский bundle.

## Системные зависимости backend

- Для серверной проверки контента файлов используется `python-magic`, поэтому на хостах с backend нужно установить пакеты `libmagic` (например, `apt install libmagic1 libmagic-dev` для Debian/Ubuntu или `apk add file` в Alpine).
- Для антивирусной проверки загружаемых файлов поднимите сервис `clamd` (например, из пакета `clamav-daemon` или Docker-образа `clamav/clamav`).
  - Включите проверку, установив `EVENT_FILE_SCANNER_ENABLED=true`.
  - По умолчанию backend подключается к `clamd` по TCP (`EVENT_FILE_SCANNER_HOST` и `EVENT_FILE_SCANNER_PORT`, стандартно `127.0.0.1:3310`).
  - Для Unix-сокета укажите путь через `EVENT_FILE_SCANNER_SOCKET` (приоритетнее хоста/порта).
  - Таймаут подключения задаётся переменной `EVENT_FILE_SCANNER_TIMEOUT` (секунды).
  - Эндпоинт `/healthz` проверяет доступность сканера лёгкой командой `PING` без загрузки тестовых данных.
  - Он же помечает `db` как `error`, если `alembic_version` в базе не совпадает с текущим `head`, и `notification_queue` как `error`, если отсутствует таблица `notification_queue_jobs` или схема очереди не применена.
  - При недоступности сканера запросы загрузки файлов вернут HTTP 503, а при обнаружении угрозы — HTTP 422 с локализованным сообщением.
- Отправка писем (например, восстановления пароля) должна выполняться неблокирующе. Backend использует `anyio.to_thread.run_sync`, чтобы SMTP-вызовы выполнялись в отдельном потоке и не блокировали event loop; при кастомизации не вызывайте SMTP напрямую из корутин.

## Notifications worker

- Для корректной отправки push-уведомлений запустите отдельный воркер: `python -m app.workers.notifications`.
- При запуске API и воркера в разных процессах выключите встроенный планировщик в API, установив `NOTIFICATIONS_SCHEDULER_INLINE_ENABLED=false`.
- Воркер публикует здоровье и метрики Prometheus на `http://<host>:9101/healthz` и `http://<host>:9101/metrics` (порт можно изменить через `NOTIFICATIONS_WORKER_METRICS_PORT`).
- В docker-compose уже добавлен сервис `notifications-worker` с политикой перезапуска `unless-stopped`.
- Задания из dead-letter очереди автоматически удаляются по истечении 30 дней (управляется `NOTIFICATION_QUEUE_DEAD_LETTER_RETENTION_DAYS`). Периодичность проверки задаётся `NOTIFICATION_QUEUE_DEAD_LETTER_CLEANUP_INTERVAL_SECONDS` (минимум 300 секунд; значение `0` отключает планировщик).

## Очистка сессий пользователей

- API автоматически удаляет устаревшие записи из `active_sessions` при старте и затем каждые 15 минут.
- Частоту можно изменить переменной `SESSION_CLEANUP_INTERVAL_SECONDS` (минимум 30 секунд). Значение `0` выключает фоновой планировщик; при этом скрипт очистки можно запускать вручную, вызвав `python -m app.services.session_cleanup` внутри контейнера/виртуального окружения.

## Очистка MFA-челленджей

- Утилита `cleanup_stale_mfa_challenges` удаляет записи, у которых и срок действия, и отметка `consumed_at` старше `MFA_CHALLENGE_CLEANUP_GRACE_PERIOD_SECONDS`.
- Планировщик запускается каждые 10 минут по умолчанию (`MFA_CHALLENGE_CLEANUP_INTERVAL_SECONDS`, минимум 30 секунд). Значение `0` отключает фоновой цикл, но задачу можно запускать вручную через `python -m app.services.mfa_challenge_cleanup`.
- Рекомендуется выдерживать интервал 5–10 минут, чтобы база не разрасталась и не блокировала логин-формы. Следите за метриками `periodic_task_mfa_challenge_cleanup_runs_total`, `_errors_total` и `_deleted_total`, чтобы замечать аномальные пики или ошибки очистки.
