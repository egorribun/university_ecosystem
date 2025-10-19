# Деплой фронтенда и медиа

## Переменные окружения

- Перед сборкой фронтенда установите `VITE_BACKEND_ORIGIN` (например, через `frontend/.env.production`).
- Все переменные с префиксом `VITE_` подставляются в код на этапе `npm run build`; изменение значений после сборки эффекта не даст.
- Backend и фронтенд должны работать по HTTPS, иначе браузер заблокирует загрузку `/media` и `/static`.
- Для лимитирования запросов настройте backend с помощью `RATE_LIMIT_STORAGE_BACKEND` и `RATE_LIMIT_STORAGE_URI`. Значение `redis` + Redis URL (например, `redis://user:pass@host:6379/0`) включает общий сторедж для middleware и чувствительных эндпоинтов. Установите `memory` или `memory://` для простого однопроцессного режима без внешнего Redis.

```bash
# пример
cd frontend
cp .env.production .env.local      # при необходимости
VITE_BACKEND_ORIGIN=https://api.example.com npm run build
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

## Notifications worker

- Для корректной отправки push-уведомлений запустите отдельный воркер: `python -m app.workers.notifications`.
- При запуске API и воркера в разных процессах выключите встроенный планировщик в API, установив `NOTIFICATIONS_SCHEDULER_INLINE_ENABLED=false`.
- Воркер публикует здоровье и метрики Prometheus на `http://<host>:9101/healthz` и `http://<host>:9101/metrics` (порт можно изменить через `NOTIFICATIONS_WORKER_METRICS_PORT`).
- В docker-compose уже добавлен сервис `notifications-worker` с политикой перезапуска `unless-stopped`.
