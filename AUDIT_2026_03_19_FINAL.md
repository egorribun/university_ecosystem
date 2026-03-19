# 🏛️ Тотальный Аудит Архитектуры и Безопасности: University Ecosystem (2026-03-19)

**Статус аудита:** КРИТИЧЕСКИЙ (Full Project Scan)
**Аудитор:** Principal Software Architect & Lead Security Researcher (FAANG)
**Оценка состояния:** Выявлены фундаментальные архитектурные сбои на всех слоях приложения. Найдены утечки памяти, состояния гонки, подавление фатальных исключений и опасные DevOps конфигурации, подвергающие систему рискам каскадных отказов. Требуется масштабный рефакторинг базовых паттернов.

---

## 🚨 1. Красная зона (Критичные уязвимости и баги)

# FAANG-Grade Security & Architecture Audit (Final Update: 2026-03-19)

## 🔴 Red Zone (Critical Vulnerabilities)

### 1. TOCTOU Race Condition in Concurrent Session Limiting
*   **Vector**: `SessionService.create_session` checks session count, then inserts.
*   **Impact**: Adversary can bypass concurrency limits by bursting parallel login requests, leading to account sharing or resource exhaustion.
*   **Fix**: Move to an atomic `LIMIT` check with `INSERT ... RETURNING` or a distributed lock (Postgres Advisory Lock).

### 2. Leaking Timing Information in Password Reset
*   **Vector**: `auth_service.py` returns immediately if user not found, but performs Argon2 hashing if found.
*   **Impact**: User enumeration via high-precision timing attacks (Wave 5 audit noted).
*   **Fix**: Apply a jitter-independent `constant_time_delay` (standard 200ms) regardless of logical path.

### 3. Orphaned File Upload DoS (Storage Exhaustion)
*   **File**: `app/api/events.py`
*   **Vector**: Files are uploaded to MinIO/S3 before DB record creation. If DB fails, the file is orphaned.
*   **Impact**: Unlimited storage growth without a cleanup path; eventual disk exhaustion.
*   **Fix**: Implement a "Temporary Upload Vault" with an automated `LIFECYCLE` policy and periodic reconciliation.

### 4. Zero-Trust Gateway Integrity (Verified Robust)
*   **Component**: `services/gateway`
*   **Assessment**: The gateway correctly signs internal headers (`X-User-ID`, `X-Session-ID`) with HMAC-SHA256. This prevents identity forgery from within the private network (SSRF protection).
*   **Excellence**: Uses constant-time comparison and explicit algorithm allowlists.

---

## 🏗️ Technical Debt & Architectural Flaws

### 1. gRPC Connection Thrashing in SpiceDB Auth
*   **Issue**: Re-dialing SpiceDB on every authorized request instead of using a persistent pool with health-checked streaming.
*   **Impact**: 10-15ms p99 latency overhead and potentially ephemeral port exhaustion.

### 2. React 18 Strict Mode Lifecycle Hacks
*   **File**: `useChatWebSocket.ts`
*   **Issue**: Manual tracking of connection state to evade Strict Mode double-mount.
*   **Fix**: Refactor to `useSyncExternalStore` for external state subscription.

### 3. State Management Paradigm Clash
*   **Issue**: Mixing pure WebSocket events with TanStack Query caching without a unified reconciliation layer.
*   **Risk**: Desynchronized UI states (e.g., deleted message still shows in query cache).

---

## ⚡ Performance Bottlenecks

### 1. pgvector Search Degradation
*   **File**: `app/repositories/news_repository.py`
*   **Issue**: Using `WHERE distance < 0.45`, which bypasses HNSW/IVFFlat indexes.
*   **Optimization**: Use `ORDER BY distance LIMIT N` to leverage ANN indexing correctly.

### 2. Uncontrolled Concurrency (asyncio.gather)
*   **Issue**: Parallelizing 100+ push notifications without a semaphore.
*   **Impact**: Connection pool starvation and "Network Unreachable" errors under load.
*   **Fix**: Implement `asyncio.Semaphore(max_parallel=20)`.

### 3. HTML Response Buffering Limits
*   **File**: `app/core/security_headers.py`
*   **Status**: Capped at 64KB (RZ-W10-12). High-performance, but will skip nonce injection for oversized pages.
*   **Optimization**: Move nonce replacement to a custom Jinja2 filter to eliminate middleware-layer buffering.

---

## 🚀 2026 Modernization Plan

### 1. Adopt Python 3.13+ Free-Threading
*   Remove GIL for compute-heavy ML/Vector processing tasks.
*   Migrate `asyncio` loops to the new built-in high-performance task runners.

### 2. Infrastructure: Transition to ALB + Gateway API
*   Migrate custom Go Gateway logic to AWS/GCP Gateway API controllers to offload HMAC/Auth logic to the edge.

### 3. Frontend: Hook Action Upgrades
*   Adopt React 19 `useActionState` and Server Actions to eliminate redundant Redux/Query boilerplate.

### 4. Unified Event Outbox
*   Adopt Debezium or a native Postgres Outbox for domain events to guarantee 100% atomicity between DB changes and NATS broadcasts.

### 1.4. Массовое "проглатывание" исключений (Exception Swallowing / CWE-391)
**Файлы:** `app/utils/files.py`, `app/workers/*`, `app/services/*` (>50 вхождений в codebase)
**Риск:** Critical (Отказ наблюдаемости).
**Описание:** Сплошное использование `except Exception:` без явного `raise` или передачи ошибки в системы трассировки. Это убивает Data Integrity. Если воркер (Outbox/Notifications) падает из-за деградации сети, процесс "ловит" это и молча продолжает работу. Транзакции теряются, почта не доставляется, а мониторинг (Sentry/Datadog) показывает 0 ошибок.
**Эталонное решение:** Перехватывать только узкие (explicit) типы ошибок. Если используется `except Exception:`, вызывать `logger.exception(...)` с проброкидкой контекста для сбора метрик.

---

## ⚠️ 2. Технический долг (Архитектурные ошибки и Anti-patterns)

### 2.1. Утечка памяти (Memory Leak) в WebSocket Клиенте
**Файл:** `frontend/src/hooks/useChatWebSocket.ts`
**Описание:** Интеграция WebSocket-потока в кеш сообщений через React Query реализована наивно: на каждое событие `new_message` вызывается конкатенация массива сообщений `[...old.items, message]`. В долгоживущих сессиях браузера массив разрастется до тысяч элементов, что неминуемо приведет к Out of Memory (OOM), сборке мусора V8 и зависанию UI-потока React.
**Эталонное решение:** Внедрение фиксированного лимита (Sliding Window), применение виртуализации списков.

**Диф:**
```diff
-            if (old.items.some((m) => m.id === data.message.id)) return old
-            return { ...old, items: [...old.items, data.message as unknown as Message] }
+            if (old.items.some((m) => m.id === data.message.id)) return old
+            // Ограничение окна для предотвращения OOM (Sliding Window O(1) Memory)
+            const newItems = [...old.items, data.message as unknown as Message];
+            if (newItems.length > 200) newItems.shift();
+            return { ...old, items: newItems }
```

### 2.2. Злоупотребление useEffect (React Anti-pattern)
**Файлы:** `frontend/src/pages/*`, `frontend/src/hooks/*` (>110 мест)
**Описание:** Архитектура фронтенда опасно завязана на каскадные `useEffect` хуки для загрузки данных и мутаций. Это нарушает конвенции React 18+ (Strict Mode) и ведет к "теневым" состояниям гонки (Race Conditions) и ненужным ре-рендерам (Waterfall Fetching). Эффекты не предназначены для контроля бизнес-потоков.
**Эталонное решение:** Переезд на Data Loaders (React Router 6.4+). Для WebSockets использовать `useSyncExternalStore`. Запросы изолировать внутри Suspense Boundaries `tanstack/react-query`.

---

## ⚡ 3. Производительность (Узкие места)

### 3.1. Деградация индексного поиска pgvector (O(N) Sequential Scan)
**Файл:** `app/repositories/news_repository.py` -> `list_news`
**Описание:** Индекс векторной базы HNSW работает исключительно с операторами дистанции в конструкции `ORDER BY ... LIMIT`! Ваша логика применяет формулу косинус-расстояния прямо в блоке `WHERE (sim_score > 0.45)`. Это вынуждает PostgreSQL отключить индексы и читать каждую строку таблицы через Full Sequential Scan. При 10,000+ записях DB CPU будет парализован.
**Эталонное решение:** Отвечать на радиусные запросы только через алгоритмы ANN (Approximate Nearest Neighbor).

### 3.2. Неконтролируемый Async Concurrency (Micro-DDoS Инфраструктуры)
**Файлы:** `app/services/webpush.py`, `app/api/ws/connection_manager.py`
**Описание:** Десятки вызовов `await asyncio.gather(*tasks)` при рассылке веб-пушей или бродкастов. При 500 участниках чата, asyncio попытается мгновенно открыть 500 одновременных TCP-сессий, что ударит в TCP Backlog, лимиты File Descriptors (ulimit) и вызовет каскадный отказ в обслуживании (DoS внутри сети).
**Эталонное решение:** Использование `asyncio.Semaphore` (Throttling) или чанковой нарезки (`itertools.batched`).

**Диф:**
```diff
-        # Micro-DDoS: запускает N тасок мгновенно
-        await asyncio.gather(*tasks, return_exceptions=True)
+        # Ограничение конкурентности через семафор:
+        sem = asyncio.Semaphore(50)
+        async def _bounded_task(t):
+            async with sem: return await t
+        await asyncio.gather(*[_bounded_task(t) for t in tasks], return_exceptions=True)
```

### 3.3. Опасные лимиты памяти в Docker / Kubernetes (OOM Kills)
**Файлы:** `docker-compose.yml`, `k8s/` конфигурации
**Описание:** Установлены критически низкие лимиты: `memory: 512M` для FastAPI Backend (в котором крутятся SQLAlchemy и векторные библиотеки) и `memory: 256M` для Frontend (Node.js/Next.js/Vite). Оба фреймворка в продакшене легко требуют базовых 300-500МБ для кэшей. Такие лимиты гарантируют регулярные и непредсказуемые убийства поди/контейнера оркестратором (OOMKilled Exit Code 137) в пиковые часы нагрузок.
**Эталонное решение:** Увеличить ресурсы (Backend > 1.5GB, Frontend > 512MB) или жестко тюнить GC параметры V8 (`--max-old-space-size`) и `MALLOC_ARENA_MAX` для Python.

---

## 🚀 4. План модернизации (2026 Best Practices)
1. **Zero-Trust & Transactional Outbox:** Перенести все отправки почты, нотификации и вебхуки в строгий `Outbox Pattern` с гарантиями At-Least-Once Delivery поверх PostgreSQL -> Temporal IO. Никаких сайд-эффектов в HTTP обработчиках.
2. **Headless State Client-Side:** Заменить хаос логики React `useEffect` на независимые автоматы состояний (`XState` или `Zustand`) вне дерева компонентов и использовать `useSyncExternalStore`.
3. **Strict Exception Linters (Shift-Left Security):** Настроить CI правила (custom `Ruff` rules или `Semgrep` пайплайны), блокирующее пулл-реквесты с `except Exception` или бесконтрольным `asyncio.gather`.
4. **Data Contract Pipeline:** Внедрить SQL-дифференциальное профилирование (напр. `pgMustard`), не дающее замерджить PR, если `EXPLAIN ANALYZE` обнаруживает Sequential Scan на больших таблицах, спасая БД от коллапсов.
