# Деплой фронтенда и медиа

## Переменные окружения

- Перед сборкой фронтенда установите `VITE_BACKEND_ORIGIN` (например, через `frontend/.env.production`).
- Все переменные с префиксом `VITE_` подставляются в код на этапе `npm run build`; изменение значений после сборки эффекта не даст.
- Backend и фронтенд должны работать по HTTPS, иначе браузер заблокирует загрузку `/media` и `/static`.

```bash
# пример
cd frontend
cp .env.production .env.local      # при необходимости
VITE_BACKEND_ORIGIN=https://api.example.com npm run build
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
