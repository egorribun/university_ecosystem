# Деплой фронтенда и медиа

_[Русская версия](DEPLOY.md) · [English version](DEPLOY.en.md)_

## Переменные окружения

- Перед сборкой фронтенда установите `VITE_BACKEND_ORIGIN` (например, через `frontend/.env.production`).
- Файл `root/.env.example` служит только шаблоном; на продакшн-средах задайте собственные секреты через `.env` или переменные окружения.
- Все переменные с префиксом `VITE_` подставляются в код на этапе `npm run build`; изменение значений после сборки эффекта не даст.
- Для включения клиентского мониторинга ошибок задайте `VITE_SENTRY_DSN` и, при необходимости, `VITE_ENVIRONMENT`. В дев-сборке SDK автоматически не активируется.
- Логгер на фронтенде (`src/app/logger.ts`) автоматически отправляет `logError`/`logWarning` в Sentry и дублирует вывод в консоль. Необработанные `Promise`/`axios` ошибки перехватываются глобальными хендлерами (`initGlobalErrorHandlers()` вызывается в `src/main.tsx`).
- Чтобы собирать Web Vitals, установите `VITE_ENABLE_WEB_VITALS=true`. При необходимости отправляйте метрики на собственный эндпоинт через `VITE_WEB_VITALS_ENDPOINT` (иначе они пишутся в консоль). Флаг игнорируется в dev/test средах, поэтому CI не упадёт даже при включённой переменной.
- Backend и фронтенд должны работать по HTTPS, иначе браузер заблокирует загрузку `/media` и `/static`.
- Для лимитирования запросов настройте backend с помощью `RATE_LIMIT_STORAGE_BACKEND` и `RATE_LIMIT_STORAGE_URI`. Значение `redis` + Redis URL (например, `redis://user:pass@host:6379/0`) включает общий сторедж для middleware и чувствительных эндпоинтов. Установите `memory` или `memory://` для простого однопроцессного режима без внешнего Redis.
- Для экспонирования Prometheus-метрик установите `ENABLE_METRICS_ENDPOINT=true` и задайте собственные, стойкие значения `METRICS_BASIC_AUTH_USERNAME` и `METRICS_BASIC_AUTH_PASSWORD` (docker-compose больше не подставляет плейсхолдеры). Backend откажется отдавать `/metrics`, если пароль равен известному плейсхолдеру вроде `changeme`.

### Пул соединений базы данных

- В production средах используйте пул SQLAlchemy: задайте `DATABASE_POOL_SIZE` (основной размер пула), `DATABASE_MAX_OVERFLOW` (дополнительные соединения поверх пула), `DATABASE_POOL_TIMEOUT` (секунды ожидания свободного соединения) и `DATABASE_POOL_RECYCLE` (период принудительного закрытия соединений, секунды). Значения по умолчанию — `5`, `10`, `30` и `1800` соответственно.
- Для dev/test окружений приложение автоматически переключается на `NullPool`, чтобы каждое соединение открывалось заново; параметры пула при этом игнорируются. Это избавляет от блокировок SQLite и полезно при локальной разработке.
- Перед деплоем на PostgreSQL или другой продакшн-базе подберите значения в пределах возможностей СУБД. Например, для сервера с ограничением в 20 подключений можно выставить `DATABASE_POOL_SIZE=5` и `DATABASE_MAX_OVERFLOW=5`, оставив запас для фоновых задач и внешних инструментов.

### Метрики фоновых задач

- `/metrics` теперь публикует счётчики и гистограммы для фоновых очисток:
  - `periodic_task_notifications_retention_*` — удаление старых уведомлений и доставок.
  - `periodic_task_password_reset_cleanup_*` — очистка токенов восстановления пароля.
  - `periodic_task_session_cleanup_*` — удаление протухших пользовательских сессий.
  - `periodic_task_story_cleanup_*` — очистка просроченных историй.
- Для каждой задачи доступны:
  - `*_runs_total` — количество успешных итераций.
  - `*_errors_total` — количество завершений с исключением.
  - `*_deleted_total` — суммарное число удалённых записей за всё время.
  - `*_duration_seconds{_bucket,_sum,_count}` — гистограмма продолжительности выполнения.

```bash
# пример
cd frontend
cp .env.production .env.local      # при необходимости
VITE_BACKEND_ORIGIN=https://api.example.com npm run build
```

- Локализованные PWA-манифесты собираются из
  `public/manifest.source.json`. Выполните `npm run generate:manifests`
  перед сборкой или запустите `npm run manifests:check`, чтобы убедиться, что
  сгенерированные файлы в `public/` не устарели.

### Spotify токены

- Backend шифрует Spotify access/refresh токены с помощью Fernet. Перед включением интеграции задайте `SPOTIFY_TOKEN_SECRET` — это base64-строка из `Fernet.generate_key()`.

```bash
python - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
```

- Для ротации используйте несколько ключей, перечисленных через запятую: новый ключ укажите первым, старый оставьте вторым (`SPOTIFY_TOKEN_SECRET="new_key,old_key"`). После деплоя выполните скрипт ниже, чтобы перешифровать уже сохранённые значения и убрать зависимость от старого ключа, затем удалите его из переменной и перезапустите сервисы.

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

## Docker image

- `root/frontend.Dockerfile` собран в два этапа: на этапе `builder` запускается `npm ci && npm run build`, а финальный образ основан на `nginx:alpine` и содержит только содержимое `dist/`.
- Значение `VITE_BACKEND_ORIGIN` передаётся через `--build-arg` (см. `docker-compose.yml`). Для локальной разработки оно уже выставлено в `http://localhost:8000`.
- Статика отдаётся Nginx'ом с кэшированием: файлы в `assets/` получают заголовок `Cache-Control: public, max-age=31536000, immutable`, а `index.html` — `Cache-Control: no-cache`.
- Контейнер слушает порт `80`. В docker-compose он проброшен на `8080`, поэтому SPA доступна на http://localhost:8080.

```bash
# пример локальной сборки
docker compose build frontend
docker compose up frontend
```

## Reverse-proxy (Nginx)

Если фронтенд и API находятся на разных хостах, проксируйте статику и медиа через тот же домен, что и SPA. Это избавит от CORS/Service Worker артефактов и позволит использовать абсолютные ссылки на API-домен.

```nginx
server {
    listen 443 ssl;
    server_name app.example.com;

    location / {
        root /var/www/app/dist; # собранный фронтенд
        try_files $uri /index.html;
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

> Альтернатива: указывайте `VITE_BACKEND_ORIGIN=https://api.example.com` и отдавайте `/media`/`/static` напрямую с API-домена (без прокси), сохраняя полное HTTPS-соединение.

## Системные зависимости backend

- Для серверной проверки контента файлов используется `python-magic`, поэтому на хостах с backend нужно установить пакеты `libmagic` (например, `apt install libmagic1 libmagic-dev` для Debian/Ubuntu или `apk add file` в Alpine).
- Для антивирусной проверки загружаемых файлов поднимите сервис `clamd` (например, из пакета `clamav-daemon` или Docker-образа `clamav/clamav`).
  - Включите проверку, установив `EVENT_FILE_SCANNER_ENABLED=true`.
  - По умолчанию backend подключается к `clamd` по TCP (`EVENT_FILE_SCANNER_HOST` и `EVENT_FILE_SCANNER_PORT`, стандартно `127.0.0.1:3310`).
  - Для Unix-сокета укажите путь через `EVENT_FILE_SCANNER_SOCKET` (приоритетнее хоста/порта).
  - Таймаут подключения задаётся переменной `EVENT_FILE_SCANNER_TIMEOUT` (секунды).
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
