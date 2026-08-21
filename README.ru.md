<div align="center">

# 🎓 Платформа Экосистемы Университета
### *Единый цифровой хаб для современного академического пространства*

<p align="center">
  <a href="README.md"><b>English 🇬🇧</b></a> • 
  <a href="README.ru.md"><b>Русский 🇷🇺</b></a>
</p>

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.14](https://img.shields.io/badge/Python-3.14-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Python Coverage Gate](https://img.shields.io/badge/Python_Coverage_Gate-100%25-brightgreen.svg?logo=pytest&logoColor=white)](TESTING.md)
[![Go Coverage Gate](https://img.shields.io/badge/Go_Coverage_Gate-100%25-brightgreen.svg?logo=go&logoColor=white)](TESTING.md)
[![Rust Coverage Gate](https://img.shields.io/badge/Rust_Coverage_Gate-100%25-brightgreen.svg?logo=rust&logoColor=white)](TESTING.md)
[![Frontend Coverage Gate](https://img.shields.io/badge/Frontend_Coverage_Gate-100%25-brightgreen.svg?logo=vitest&logoColor=white)](TESTING.md)
[![React 19](https://img.shields.io/badge/React-19-61DAFB.svg?logo=react&logoColor=black)](https://react.dev/)
[![Vite 8 / Rolldown](https://img.shields.io/badge/Vite-8_%2F_Rolldown-646CFF.svg?logo=vite&logoColor=white)](https://vitejs.dev/)
[![Go 1.26](https://img.shields.io/badge/Go-1.26-00ADD8.svg?logo=go&logoColor=white)](https://go.dev/)
[![PostgreSQL 17](https://img.shields.io/badge/PostgreSQL-17-336791.svg?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Security: Pre-commit](https://img.shields.io/badge/Security-Ruff_%7C_Semgrep_%7C_Trivy-orange.svg)](SECURITY.md)

---

**University Ecosystem** — это высокопроизводительная полиглотразностная микросервисная платформа, созданная для объединения и автоматизации всех сфер университетской жизни. От расписания в реальном времени и навигации по кемпусу до корпоративной безопасности и автоматических воркфлоу.

[Документация](docs/README.md) • [Инструкция по деплою](docs/DEPLOY.md) • [Тестирование](TESTING.md) • [Безопасность](SECURITY.md) • [Вклад в проект](docs/CONTRIBUTING.md)

</div>

## 🌟 Ключевые возможности

> [!IMPORTANT]
> Платформа спроектирована с учетом требований к высокой масштабируемости, принципам Zero-Trust безопасности и устойчивости к экстремальным нагрузкам.

- 📅 **Динамический академический движок** – Расписание пар в реальном времени с параллельным разрешением конфликтов на **Rust (PyO3)** с использованием потоков Rayon.
- 💬 **Высоконагруженный WebSocket-хаб** – Мгновенный обмен сообщениями через **Go + NATS** с поддержкой горячей перезагрузки JWKS, лимитом 60 КБ на кадр и пречеками подключений.
- 🔒 **Управление правами на основе отношений (ReBAC)** – Гранулярный доступ на базе **SpiceDB** (Zanzibar architecture) и флаги фичей **OpenFeature** + **flagd**.
- 🖼️ **Медиа-процессинг и воркфлоу** – Асинхронная обработка файлов, оптимизация изображений и проверка на вирусы через **Go file-processor**, **Temporal.io**, **MinIO** и **ClamAV**.
- ⚡ **Вероятностное кэширование XFetch L1/L2** – Защита от «лавины кэша» (Cache Stampede) и Circuit Breakers в Redis/Valkey (`volatile-lru`).
- 🗺️ **Векторный поиск и навигация** – Семантический поиск по контенту и навигация по кемпусу с использованием **pgvector** и эмбеддингов.
- 📊 **Комплексный мониторинг (Observability)** – Сквозная трассировка (**OTEL + Tempo**), метрики (**Prometheus**), профилирование (**Pyroscope**) и централизованные логи (**Grafana Loki + Fluent Bit**).

## ⚡ Производительность и Бенчмарки

Полиглотная архитектура обеспечивает максимальную пропускную способность при минимальном потреблении ресурсов:

| Подсистема / Метрика | Чистый Python / Стандарт | Полиглотное ядро (Rust / Go) | Прирост производительности |
| :--- | :---: | :---: | :---: |
| **Разрешение конфликтов расписания** (10 000 элементов) | ~45.2 мс (1 поток) | **<0.98 мс** (Rust PyO3 + Rayon) | **~46x Быстрее** 🚀 |
| **Пропускная способность WS-чата (`ws-hub`)** | ~2 500 зап/сек | **10 000+ зап/сек** (<5мс задержка) | **4x Пропускная способность** ⚡ |
| **Обновление L1 кэша (`gateway`)** | Классический TTL (Риск лавины) | **XFetch Вероятностный Refresh** | **0 Лавин кэша** 🛡️ |
| **Размер бандла фронтенда** | ~1.4 МБ (Стандартный Rollup) | **<485 КБ** (Vite 8 / Rolldown + Oxc) | **65% Легче** 📦 |

## 📂 Структура проекта

```text
university_ecosystem/
├── app/               # 🐍 Core API (Python 3.14 / FastAPI) - Бизнес-логика и GraphQL
├── frontend/          # ⚛️ Современный Web UI (React 19 + Vite 8/Rolldown + Valibot)
├── services/
│   ├── gateway/       # 🚀 API Gateway (Go) - Авторизация, L1 XFetch кэш и лимиты
│   ├── ws-hub/        # 📡 WebSocket Hub (Go/NATS) - Чат и сообщения реального времени
│   ├── file-processor/# 📁 Media Engine (Go/Temporal) - Обработка файлов и медиа
│   └── caddy/         # 🔒 Обратный прокси и TLS терминация
├── native/            # 🦀 Rust-расширения (PyO3/Rayon) - Высокоскоростные вычисления
├── k8s/               # ☸️ Манифесты Kubernetes, Kyverno-политики и Chaos Mesh
├── alembic/           # 🗄️ Миграции базы данных (SQLAlchemy 2.0 Async)
└── docs/              # 📖 Архитектура и ADR (ADR-001 — ADR-032)
```

## 🧠 Архитектурная философия

Почему полиглотный стек?
- **Python (FastAPI & Python 3.14)**: Обеспечивает высокую скорость разработки бизнес-логики, внедрение зависимостей Dishka DI и богатую экосистему.
- **Go (Golang)**: Управляет I/O-интенсивными микросервисами (`gateway`, `ws-hub`, `file-processor`), выдерживая тысячи параллельных WebSocket-соединений и gRPC-стримов с минимальным потреблением ресурсов.
- **Rust (PyO3 & Rayon)**: Интегрирован прямо в Python для горячих вычислений (расчет конфликтов расписания), где важна каждая микросекунда.
- **SpiceDB (ReBAC)**: Реализует модель Zanzibar (например: *"Студент Х имеет доступ к Курсу Y, так как состоит в Группе Z"*).
- **Vite 8 & Rolldown**: Обеспечивает молниеносную сборку фронтенда, оптимизации React Compiler и бандлы менее 500 КБ.

## 🏗️ Архитектура и Сценарии Взаимодействия

### Топология системы

```mermaid
graph TD
    Client["📱 Фронтенд (React 19 + Vite 8)"]
    Gateway["🚀 Go API Gateway (RateLimiter & XFetch L1 кэш)"]

    subgraph "Микросервисы Ядра"
        Backend["🐍 Core API (FastAPI / Python 3.14)"]
        WSHub["📡 WS Hub (Go / NATS)"]
        FileProc["📁 File Processor (Go / Temporal)"]
        Optimizer["🦀 Rust Оптимизатор (PyO3 / Rayon)"]
    end

    subgraph "Данные, Управление и Воркфлоу"
        Postgres[("🐘 PostgreSQL 17 + pgvector")]
        Valkey[("⚡ Valkey / Redis 7 (volatile-lru)")]
        Revocations[("🛡️ Revocation Valkey (AOF / noeviction)")]
        MinIO[("📦 MinIO (S3 Storage)")]
        Temporal["⏳ Temporal.io (Workflows)"]
        SpiceDB["🔐 SpiceDB (ReBAC)"]
        Flagd["🚩 OpenFeature / flagd"]
    end

    subgraph "Observability Стек (ADR-012)"
        OTEL["🔭 OpenTelemetry Collector"]
        Tempo["📈 Grafana Tempo (Трассы)"]
        Prometheus["📊 Prometheus (Метрики)"]
        Pyroscope["🔥 Pyroscope (Профилирование)"]
        Loki["📜 Grafana Loki + Fluent Bit (Логи)"]
    end

    Client --> Gateway
    Gateway --> Backend
    Gateway --> WSHub
    Gateway --> FileProc

    Backend --> Postgres
    Backend --> Valkey
    Backend --> Revocations
    Backend --> SpiceDB
    Backend --> Temporal
    Backend --> Flagd

    WSHub --> Valkey
    WSHub --> Revocations
    Gateway --> Revocations
    WSHub --> Backend
    FileProc --> MinIO
    Optimizer --- Backend

    Backend -.-> OTEL
    Gateway -.-> OTEL
    WSHub -.-> OTEL
    FileProc -.-> OTEL

    OTEL --> Tempo
    OTEL --> Prometheus
    OTEL --> Pyroscope
    Backend -.-> Loki
```

### 🔐 Сценарий Zero-Trust Аутентификации

```mermaid
sequenceDiagram
    autonumber
    actor Client as 📱 Клиент (Frontend)
    participant Gateway as 🚀 Go Gateway
    participant Backend as 🐍 FastAPI Backend
    participant Argon2 as 🔐 Argon2id / WebAuthn
    participant SpiceDB as 🛡️ SpiceDB (ReBAC)
    participant Redis as ⚡ Valkey / Redis Cache

    Client->>Gateway: POST /api/v1/auth/login (Пароль / Passkey)
    Gateway->>Gateway: Проверка Redis Circuit Breaker Rate Limit
    Gateway->>Backend: Проксирование запроса авторизации
    Backend->>Argon2: Валидация хеша пароля (Argon2id) / Челлендж WebAuthn
    Argon2-->>Backend: Успешная аутентификация
    Backend->>SpiceDB: Запрос прав и отношений пользователя
    SpiceDB-->>Backend: Ответ с ролями и разрешениями
    Backend->>Redis: Сохранение сессии и выдача тикета авторизации
    Backend-->>Gateway: HTTP 200 + Secure HTTP-Only Cookie + JWT
    Gateway-->>Client: Авторизованный ответ
```

### 📡 Сценарий Выборки и Отправки Сообщений в Чат

```mermaid
sequenceDiagram
    autonumber
    actor ClientA as 📱 Клиент A
    actor ClientB as 📱 Клиент B
    participant Gateway as 🚀 Go Gateway
    participant WSHub as 📡 Go WS-Hub
    participant NATS as 📨 NATS Broker
    participant Redis as ⚡ Redis (Кэш тикетов)

    ClientA->>Gateway: GET /ws (Запрос Upgrade + Тикет авторизации)
    Gateway->>Redis: Проверка тикета и пречек макс. клиентов (Pre-check)
    Redis-->>Gateway: Тикет валиден
    Gateway->>WSHub: Апгрейд соединения до WebSocket
    ClientA->>WSHub: Кадр сообщения чата (Защита <60 КБ)
    WSHub->>NATS: Публикация в NATS Subject (chat.room.{id})
    NATS-->>WSHub: Доставка кадра подписанным нодам WS-Hub
    WSHub-->>ClientB: Рассылка кадра соединениям получателя
```

## 🛠️ Технологический стек

| Слой | Технологии | Роль | Гейт покрытия |
| :--- | :--- | :--- | :---: |
| **Frontend** | React 19, Vite 8/Rolldown, Valibot, Framer Motion, TanStack | Matte UX, доступность (WCAG 2.2 AA), PWA | **100%** |
| **Backend API** | FastAPI, Python 3.14, Dishka DI, SQLAlchemy 2.0, GraphQL | Основная бизнес-логика, REST и GraphQL API | **100%** |
| **Микросервисы** | Go 1.26, NATS, gRPC, Temporal Go SDK | Высоконагруженный чат и обработка медиа | **100%** |
| **Производительность**| Rust, PyO3, Rayon, Maturin | Нативное вычисление расписания и HMAC | **100%** |
| **Авторизация** | Argon2id, SpiceDB, WebAuthn/Passkeys, Kyverno, CSRF nonces | Zero-Trust ReBAC, аппаратная MFA и политики | Подтверждено |
| **Данные и Кэш** | PostgreSQL 17, pgvector, кэш Valkey (`volatile-lru`), revocation Valkey (AOF, `noeviction`) | Реляционные/векторные данные, вероятностный L1/L2 кэш и изолированный отзыв сессий | Подтверждено |
| **Observability** | OTEL, Tempo, Prometheus, Pyroscope 1.19, Loki + Alloy/Fluent Bit | Полный 360° мониторинг, трассы и логи | Подтверждено |

## 🚀 Быстрый старт

### 1. Подготовка окружения
Создайте локальное окружение из включённого шаблона. Загрузчик сгенерирует
секреты только для разработки, если значения отсутствуют; `.env` нельзя коммитить.
```powershell
Copy-Item .env.example .env
```

### 2. Запуск
Запуск всей экосистемы через загрузчик PowerShell 7. Скрипт генерирует локальные секреты, настраивает постоянную инфраструктуру, собирает образы и ожидает готовности всех рантаймов и таргетов Prometheus:
```powershell
.\start-docker.ps1 -Build
```

### 🌐 Точки доступа
- **Единый цифровой хаб (Caddy edge)**: [http://localhost](http://localhost)
- **Frontend SSR debug port**: [http://localhost:8081](http://localhost:8081)
- **Документация API**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Вход Go Gateway**: [http://localhost:8080](http://localhost:8080)
- **Real-Time сигнал**: `ws://localhost:8083/ws`
- **Центр наблюдаемости**: [Grafana](http://localhost:3000) · [Prometheus](http://localhost:9090) · [Pyroscope](http://localhost:4040)

## 🛡️ Безопасность и Стандарты Качества

- **Аппаратная аутентификация**: Поддержка **WebAuthn/FIDO2** (Passkeys) и хеширование паролей **Argon2id**.
- **Строгая валидация**: Схемы **Valibot** на фронтенде и защита от Path Traversal в gRPC.
- **Антивирусная защита**: Сканирование файлов в **ClamAV** перед сохранением в MinIO S3.
- **Политики K8s**: Инспекция подов через **Kyverno** и профили `RuntimeDefault`.
- **Очистка персональных данных**: Автоматическая анонимизация PII (почты, телефоны) в логах.

## 🧪 Инструкция для разработчиков

### **Python (Core API)**
```bash
uv sync            # Синхронизация зависимостей Python 3.14
uv run pytest      # Запуск тестовой сюиты (2800+ тестов)
uv run ruff check app/      # Проверка Ruff линтером
uv run ruff format app/     # Форматирование кода
```

### **React (Frontend)**
```bash
cd frontend
npm install        # Загрузка npm-пакетов
npm run dev        # Запуск Vite 8 dev-сервера
npx tsc --noEmit   # Проверка типов TypeScript
npm run test       # Запуск Vitest тестов
```

### **Go (Микросервисы)**
```bash
cd services/gateway
go test ./...      # Запуск модульных тестов Go
make test-integration # Запуск интеграционных тестов ADR-022
```

## 🔭 Наблюдаемость и Мониторинг

Платформа включает готовую к продакшену подсистему мониторинга:
- **OpenTelemetry & Tempo**: Сквозная распределенная трассировка микросервисов Go и FastAPI.
- **Prometheus**: Метрики в реальном времени, включая процент попаданий в L1-кэш (`cache_l1_hits_total`).
- **Pyroscope**: Непрерывное профилирование ресурсов процессора и памяти (`grafana/pyroscope:1.19.1`).
- **Grafana Loki + Fluent Bit**: Централизованный логгирование с анонимизацией персональных данных (ADR-012).

---

<div align="center">
  <br />
  <h3>Сконструировано с ❤️ инженерами University Ecosystem</h3>
  © 2026 University Ecosystem Platform • Все права защищены.
</div>
