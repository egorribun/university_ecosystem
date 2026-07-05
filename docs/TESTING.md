# University Ecosystem — Maximum Coverage Testing Roadmap

> **Стратегия:** 6 волн, логическая последовательность без временных рамок.  
> **Философия:** Жёсткие CI-гейты — волна не закрывается, пока threshold не пройден.  
> **Цели верхнего уровня:**  
> | Фронт | Текущее | Цель |
> |-------|---------|------|
> | Python statements | ~89% | **98%+** |
> | Python branches | ~85% | **95%+** |
> | Python mutation score | ~50-60% | **85%+** |
> | Go coverage | неизвестно/умеренное | **90%+** per service |
> | Rust unit coverage | smoke only | **95%+ (llvm-cov)** |
> | Frontend statements | ~90% | **98%+** |
> | Frontend branches | ~80% | **92%+** |
> | Frontend functions | ~82% | **95%+** |
> | Playwright E2E | 18 specs, частичное | **full happy+sad path** |
> | axe-core a11y | половинчато | **0 critical/serious violations** |
> | LHCI performance | есть конфиг | **perf≥90, a11y≥95, BP=100** |
> | Fuzz (CI weekly) | неограничен | **1-2h budget, structured corpus** |

---

## Wave 0 — Инфраструктура и починка провалов

> **Цель:** Зелёный baseline. Ни одного падающего теста, конфиг без конфликтов.

### 0.1 — Унификация конфигурации pytest

**Проблема:** `pytest.ini` и `pyproject.toml [tool.pytest.ini_options]` конфликтуют. Pytest активно читает `pytest.ini` и **игнорирует** pyproject.toml с варнингом. `asyncio_mode=auto` задан в обоих, но log показывает `Mode.STRICT` — признак рассинхрона.

**Задачи:**
- [ ] Перенести всё из `pytest.ini` в `pyproject.toml [tool.pytest.ini_options]` (единый источник истины)
- [ ] Удалить `pytest.ini` полностью
- [ ] Убедиться что `asyncio_mode = "auto"` + `asyncio_default_fixture_loop_scope = "session"` применяются корректно
- [ ] Добавить `asyncio_default_test_loop_scope = "session"` (уже есть в pyproject, должно работать)
- [ ] Проверить `filterwarnings`: pyproject → `error::DeprecationWarning`, pytest.ini → `ignore` — выбрать политику
- [ ] Запустить полный suite, убедиться что нет `Mode.STRICT` в выводе

**CI-gate:** `pytest --co -q` без ошибок на конфигурацию

---

### 0.2 — Фикс fixture `client` → `async_client`

**Проблема:** `tests/test_notifications_routers_endpoints_coverage_test.py` запрашивает фикстуру `client`, которой нет в `conftest.py`. Зарегистрированы: `async_client`, `root_client`.

**Задачи:**
- [ ] Заменить `client: AsyncClient` → `async_client: AsyncClient` во всех тестах в этом файле (2 теста)
- [ ] Прогрепать весь `tests/` на использование `client` как фикстуры (`grep -rn "def.*\(client:"`) — проверить другие потенциальные жертвы
- [ ] Добавить alias `client = async_client` в `conftest.py` как `@pytest.fixture` — опционально, если паттерн повсеместный

**CI-gate:** Оба теста из файла проходят (убрать из failed set)

---

### 0.3 — Фикс `FailedOutboxEvent` в `app.workers.outbox`

**Проблема:** `tests/test_workers_outbox_booster.py` падает с `AttributeError: module 'app.workers.outbox' has no attribute 'FailedOutboxEvent'` — класс переименован/перемещён.

**Задачи:**
- [ ] Найти актуальное имя/расположение класса (`grep -rn "FailedOutboxEvent" app/`)
- [ ] Обновить импорт в тесте — либо добавить alias в `app/workers/outbox.py`
- [ ] Проверить что тест `test_process_batch_dispatch_failure_hits_dlq_at_max_retries` полностью проходит

**CI-gate:** Тест зелёный

---

### 0.4 — Фикс ratelimit Redis mock

**Проблема:** `tests/test_ratelimit_strategies.py` — 3 теста `TestRedisSlidingWindowStrategy` падают из-за проблем с Redis mock.

**Задачи:**
- [ ] Диагностировать точную причину (fakeredis vs real redis, lua script support)
- [ ] `fakeredis` поддерживает EVALSHA? Если нет — мокировать на уровне функции
- [ ] Убедиться что `clear_redis_between_tests` фикстура применяется

---

### 0.5 — Фикс middleware и schema тестов

**Проблема:** `test_middleware_content_size.py` (3 теста), `test_schema_validators.py::TestSanitizeHtmlValidator::test_xss_payload_escaped`, `test_core_di_extra.py` (2 TypeError), `test_core_security_headers_extra.py`, `test_credential_validator_branch_coverage_test.py`, `test_privacy_cleanup.py`, `test_utils_sanitization_booster.py`.

**Задачи:**
- [ ] Каждый тест диагностировать отдельно: assertion vs logic vs setup failure
- [ ] `test_schema_validators.py` — xss sanitization: проверить что rust_ext/pyo3-sanitizer даёт ожидаемый output (может быть регрессия после обновления ammonia)
- [ ] `test_core_di_extra.py` TypeError — проверить сигнатуру DI-провайдеров после рефакторинга dishka

**CI-gate:** `pytest --last-failed` → 0 failed

---

### 0.6 — Унификация Makefile coverage threshold

**Проблема:** `Makefile` backend-test: `--cov-fail-under=88`, `pyproject.toml [tool.coverage.report]`: `fail_under = 89`.

**Задачи:**
- [ ] Синхронизировать на `89` везде
- [ ] Добавить в `pyproject.toml` единый source of truth для threshold и убрать дублирование из Makefile (читать через `coverage report --fail-under=$(python -c "import tomllib; ...")` или проще — захардкодить в одном месте)

---

## Wave 1 — Python Backend: Unit Coverage к 98%+

> **Цель:** `fail_under = 95` в CI (с рачетом на 98%+ реальных измерений). Покрыть все непокрытые ветки.

### 1.1 — Coverage gap analysis

**Задачи:**
- [ ] Запустить `pytest --cov=app --cov-report=json` и распарсить `coverage.json`
- [ ] Написать скрипт `scripts/coverage_gaps.py` который выводит топ-50 модулей по наименьшему `percent_covered` с количеством `missing_lines` и `missing_branches`
- [ ] Приоритизировать по: (1) highest business criticality, (2) most missing lines

**Ожидаемые проблемные зоны (из coverage.json):**

| Модуль | Statements | Branches |
|--------|-----------|----------|
| `app/api/auth/login.py` | 74% | **36%** |
| `app/api/auth/mfa.py` | 77% | 50% |
| `app/api/deps/auth.py` | 81% | 70% |
| `app/api/chat.py` | 82% | 100% (отсутствуют веткиendering) |

---

### 1.2 — Auth API: login.py ветки (приоритет 1)

**Что не покрыто:**
- `login_passkey_verify` — 18% statements, 0% branches (строки 133-170)
- `login`, `login_json` — 25% statements, 0% branches (строки 195-232)
- `verify_mfa_challenge` — 50% branches пропущено
- `request_step_up` — 29% statements, 0% branches

**Задачи:**
- [ ] Тест: `test_login_passkey_verify_*` — WebAuthn passkey verification flow (success + error paths)
- [ ] Тест: `test_login_form_submit_*` — legacy form login (credentials, lockout, 2FA redirect)
- [ ] Тест: `test_login_json_*` — JSON login endpoint (happy path + invalid credentials + MFA)
- [ ] Тест: `test_verify_mfa_challenge_*` — все ветки: valid code, expired code, wrong code, lockout
- [ ] Тест: `test_request_step_up_*` — step-up auth flow с разными методами MFA

**CI-gate:** `login.py` ≥ 90% statements, ≥ 85% branches

---

### 1.3 — Auth API: mfa.py ветки (приоритет 1)

**Что не покрыто:**
- `generate_recovery_codes_endpoint` — 0% (строки 409-421)
- `request_step_up` — 29%
- `confirm_totp_enrollment` — 58%, branch 50%
- `delete_webauthn_credential` — 44%, branches 0%

**Задачи:**
- [ ] Тест: `test_generate_recovery_codes_*` — success + already_exists + rate_limit
- [ ] Тест: `test_delete_webauthn_credential_*` — не-существующий credential, чужой credential, success
- [ ] Тест: `test_confirm_totp_enrollment_*` — invalid code, expired enrollment, success + recovery

**CI-gate:** `mfa.py` ≥ 88% statements, ≥ 80% branches

---

### 1.4 — Chat API: непокрытые endpoints

**Что не покрыто (0% coverage):**
- `edit_message` (244, 247)
- `delete_message` (264, 267)  
- `add_reaction` (288, 291)
- `remove_reaction` (324, 327)
- `get_reactors` (352)
- `typing_indicator` (380, 381)

**Задачи:**
- [ ] Тест: `test_edit_message_*` — успех, не своё сообщение (403), слишком старое (400)
- [ ] Тест: `test_delete_message_*` — soft-delete + hard-delete, permissions
- [ ] Тест: `test_reactions_*` — add, remove, get reactors, duplicate add, limit
- [ ] Тест: `test_typing_indicator_*` — broadcast + debounce

---

### 1.5 — Deps/auth.py: непокрытые ветки

**Что не покрыто (29 missing lines):**
- Строки 81-113: JWT validation edge cases (expired, invalid sig, wrong audience)
- Строки 130-170: session validation branches
- Строки 199, 221, 274, 307: conditional auth paths

**Задачи:**
- [ ] Тест: `test_jwt_validation_edge_cases_*` — expired/not_yet_valid/wrong_alg/tampered
- [ ] Тест: `test_session_validation_*` — revoked session, concurrent sessions, device fingerprint mismatch
- [ ] Тест: `test_step_up_requirement_*` — required vs optional step-up по эндпоинтам

---

### 1.6 — Workers: полное покрытие

**Задачи:**
- [ ] `app/workers/outbox.py` — все ветки `process_batch`: retry exhausted → DLQ, partial failure, empty batch, concurrency
- [ ] `app/workers/notifications.py` — push fail, email fail, template error, rate limit
- [ ] `app/workers/dlq.py` — requeue, dead letter → archive, inspect

**CI-gate (per module):** ≥ 95% statements, ≥ 90% branches

---

### 1.7 — Services: gap sweep

Прогнать coverage_gaps.py, закрыть все модули <90%:
- [ ] `app/services/auth/` — все ветки login service, session cleanup, device trust
- [ ] `app/services/notifications/` — quiet hours, channel routing, template fallback
- [ ] `app/services/chat/` — message encryption, media attachment, group permissions
- [ ] `app/services/events/` — time constraints, recurrence, cancellation cascade
- [ ] `app/services/files/` — MIME validation edge cases, size limits, quarantine
- [ ] `app/services/search/` — ElasticSearch error path, fallback to DB
- [ ] `app/services/vector/` — pgvector similarity threshold, empty results

---

### 1.8 — Property-based tests (Hypothesis)

**Текущее:** `tests/test_property_based.py` (8KB) — начало положено.

**Новые стратегии:**
- [ ] Стратегия: `UserCredentials` — любая комбинация email/password → валидация не падает
- [ ] Стратегия: `PaginationParams` — offset/limit → всегда возвращает list, никогда 500
- [ ] Стратегия: `ChatMessage` — любой text (unicode, emoji, RTL, XSS) → всегда sanitized
- [ ] Стратегия: `DateTimeRange` — overlap detection, timezone conversion
- [ ] Стратегия: `UUID7` — monotonicity, sortability properties
- [ ] Стратегия: `RateLimitKey` — prefix collisions, namespacing invariants
- [ ] Стратегия: `JWTPayload` — claims roundtrip (encode→decode→encode идемпотентно)

**Инструмент:** `hypothesis.strategies.from_type()` + `@given` + `@settings(max_examples=500)`

---

### 1.9 — Mutation testing: к 85%

**Текущее:** `mutmut run` настроен, `paths_to_mutate = ["app/"]`.

**Задачи:**
- [ ] Запустить `mutmut run` на приоритетных модулях: `app/auth/`, `app/services/`, `app/utils/`
- [ ] Найти выживших мутантов (`mutmut results --only-survived`)
- [ ] Для каждого выжившего мутанта написать тест, убивающий его
- [ ] Добавить в CI job: `mutmut export-results` + threshold check скрипт
- [ ] Создать `scripts/mutmut_ci_gate.py` — читает `mutmut.log`, выдаёт exit 1 если kill rate < 85%

**CI-gate:** `mutmut_ci_gate.py` → exit 0 (kill rate ≥ 85%)

---

### 1.10 — Atheris/fuzz расширение

**Текущее:** `tests/fuzz/run_atheris.py` (единственный файл).

**Задачи:**
- [ ] Новый target: `fuzz_sanitize_html()` — подавать мусорный html, проверять что нет crash/exception
- [ ] Новый target: `fuzz_jwt_decode()` — случайные bytes как JWT
- [ ] Новый target: `fuzz_redis_key_build()` — случайные строки как ключи Redis
- [ ] Новый target: `fuzz_email_validation()` — случайные unicode как email
- [ ] Новый target: `fuzz_pagination_params()` — случайные int как offset/limit
- [ ] Настроить corpus seed dir: `tests/fuzz/corpus/` с минимальными valid inputs
- [ ] Добавить в CI: weekly job с `--timeout 90min`, results в artifacts

---

### 1.11 — CI-gate эскалация Python

**После Wave 1:**
- [ ] Поднять `fail_under = 95` в `pyproject.toml [tool.coverage.report]`
- [ ] Синхронизировать Makefile: `--cov-fail-under=95`
- [ ] В `reusable-backend-tests.yml` добавить branch coverage gate: `--cov-branch`


---

## Wave 2 — Go Services: 90%+ Coverage с Race Detector

> **Цель:** ≥90% coverage per service в CI с `go test -race`.

### 2.1 — Измерить текущее покрытие Go

**Задачи:**
- [x] `go test -coverprofile=coverage.out ./... -coverpkg=./...` в каждом сервисе
- [x] `go tool cover -func=coverage.out | tail -1` — итоговый %
- [x] Создать `scripts/go-coverage-report.sh` — агрегирует все три сервиса в единую таблицу
- [x] Установить baseline в `reusable-go-tests.yml`: текущий % + 0 regression

---

### 2.2 — Gateway middleware: исчерпывающее покрытие

**Текущее:** 15 test files в `middleware/` — хорошая база.

**Незакрытые зоны (анализ файлов):**
- [x] `auth.go` — token rotation paths, concurrent JWKS refresh race
- [x] `ratelimit.go` — Lua script error paths, Redis timeout, sliding window overflow
- [x] `errors.go` — все error types

**Новые тесты:**
- [x] `auth_concurrent_refresh_test.go` — 100 goroutines → одновременное обновление JWKS
- [x] `ratelimit_lua_error_test.go` — симулировать EVALSHA miss → EVAL fallback
- [x] `auth_token_expiry_test.go` — expired access token, refresh path, revoked token
- [x] `auth_role_hierarchy_test.go` — admin > teacher > student permission matrix
- [x] Fuzz test расширение: `auth_fuzz_test.go` добавить corpus для JWT header variants

---

### 2.3 — Gateway handlers: internal/handlers/

**Задачи:**
- [x] Листинг всех handler файлов в `internal/handlers/`
- [x] Написать `handlers_test.go` для каждого handler: health check, proxy, metrics endpoints
- [x] Мок upstream: httptest.NewServer для backend
- [x] Тест: circuit breaker activation (upstream down → 503)
- [x] Тест: request timeout propagation
- [x] Тест: response header passthrough

---

### 2.4 — Gateway: config validation

**Задачи:**
- [x] `internal/config/config_test.go` — все env vars: missing required, invalid format, defaults
- [x] Тест: TLS config (cert file missing, expired cert detection)
- [x] Тест: JWKS URL reachability check on startup

---

### 2.5 — ws-hub: pkg/hub/ исчерпывающее покрытие

**Текущее:** 12 test files — хорошая база. Анализ `pkg/hub/`:

**Незакрытые зоны:**
- [ ] Presence: join/leave events across rooms

**Новые тесты:**
- [ ] `hub_graceful_shutdown_test.go` — shutdown с активными клиентами
- [ ] `hub_nats_redelivery_test.go` — NATS ack timeout → redelivery
- [ ] `client_reconnect_test.go` — expired ticket, new ticket, room rejoin
- [ ] `presence_test.go` — online/offline events, typing indicators

---

### 2.6 — ws-hub: internal/contract/

**Задачи:**
- [ ] `cache_invalidation_provider_test.go` — расширить: все event types, partial failure
- [ ] `telemetry/` — тесты для span creation, metric recording

---

### 2.7 — ws-hub: main.go startup

**Текущее:** `main_test.go` (5.7KB), `main_startup_test.go` (3KB), `main_coverage_test.go` (1.4KB).

**Задачи:**
- [ ] Тест: invalid NATS URL → startup fails gracefully
- [ ] Тест: Redis unavailable → startup с fallback
- [ ] Тест: signal handling (SIGTERM → graceful shutdown)
- [ ] Тест: metrics server binding failure

---

### 2.8 — file-processor: coverage от 3 → 20+ тестов

**Текущее:** Только 3 test files. Явный gap.

**Задачи:**
- [ ] `internal/service/file_service_test.go` — upload, scan, transform, delete
- [ ] `internal/service/scan_service_test.go` — ClamAV response mocking (clean/infected/error)
- [ ] `internal/graphql/resolver_test.go` — все Query/Mutation resolvers
- [ ] `internal/workflow/workflow_test.go` — workflow steps: download → scan → resize → store
- [ ] `internal/middleware/auth_middleware_test.go` — gRPC auth interceptor
- [ ] `internal/config/config_test.go` — validation
- [ ] Тест: файл > size limit → 413
- [ ] Тест: MIME mismatch → 415
- [ ] Тест: ClamAV timeout → 504 + quarantine
- [ ] Тест: MinIO write failure → rollback

---

### 2.9 — uni-cli: расширение

**Текущее:** 1 `main_test.go` (10KB).

**Задачи:**
- [ ] Проверить coverage `main_test.go` — что покрыто, что нет
- [ ] Тест каждой CLI команды (subcommands)
- [ ] Тест: invalid flags → usage error
- [ ] Тест: migrate → rollback → migrate (idempotency)

---

### 2.10 — Go CI gate

**Задачи:**
- [ ] В `reusable-go-tests.yml` добавить threshold:
  ```yaml
  - name: Check Go coverage
    run: |
      COVERAGE=$(go tool cover -func=coverage.out | tail -1 | awk '{print $3}' | tr -d '%')
      if (( $(echo "$COVERAGE < 90" | bc -l) )); then
        echo "Coverage $COVERAGE% < 90% threshold"; exit 1
      fi
  ```
- [ ] Race detector: `go test -race ./...` должен быть в CI без -race исключений
- [ ] Добавить `go vet ./...` + `staticcheck ./...` в pre-test

---

### 2.11 — Go Integration Tests: расширение

**Текущее:** `reusable-go-integration-tests.yml` — вероятно минимальный.

**Задачи:**
- [ ] `tests/integration/test_gateway_revocation.py` — добавить Go-side variant: токен отзывается → gateway даёт 401 в течение <1s
- [ ] Go integration test: gateway → backend через реальный HTTP (testcontainers-go)
- [ ] ws-hub integration: реальный NATS server (testcontainers-go), publish → receive

---

## Wave 3 — Rust: 95%+ Unit Coverage + Hardened Fuzzing

> **Цель:** Критический security-код должен иметь максимальное покрытие. llvm-cov ≥ 95%.

### 3.1 — rust_ext: unit тесты в lib.rs

**Текущее:** `native/rust_ext/src/lib.rs` (18.5KB) содержит `#[cfg(test)]` блок.

**Задачи:**
- [x] Запустить `cargo test --no-default-features --lib` — посмотреть текущий coverage
- [x] Установить `cargo llvm-cov`:
  ```toml
  # в native/rust_ext/Cargo.toml
  [dev-dependencies]
  cargo-llvm-cov = "*"
  ```
- [x] Запустить: `cargo llvm-cov --no-default-features --lib --lcov --output-path lcov.info`
- [x] Найти все непокрытые функции/ветки

**Типичные функции в rust_ext (18KB) — вероятно содержат:**
- UUID v7 generation → тест: monotonicity, clock regression, uniqueness
- HMAC signing → тест: all key lengths, unicode input, empty input, known vectors
- Partitioning logic → тест: all partition strategies, edge sizes
- Audit functions → тест: all audit event types

**Новые тесты:**
- [x] `test_uuid7_monotonic()` — 1000 UUID v7 → строго возрастающий порядок
- [x] `test_hmac_known_vector()` — RFC 2202 test vectors для HMAC-SHA256
- [x] `test_hmac_empty_input()` — пустой payload, пустой ключ
- [x] `test_hmac_unicode_key()` — ключ с non-ASCII символами
- [x] `test_partition_boundary()` — offset=0, offset=max, wrap-around
- [x] `test_partition_consistency()` — одинаковый input → одинаковый partition
- [x] `test_audit_all_event_types()` — каждый enum variant
- [x] `test_audit_invalid_payload()` — malformed data не паникует

---

### 3.2 — rust_ext: pyo3 binding тесты (Python side)

**Текущее:** `tests/test_smoke_pyo3_ext.py`, `test_smoke_rust_audit.py`, `test_smoke_rust_partitions.py`.

**Задачи:**
- [x] Расширить smoke → full: каждая PyO3-функция имеет тест на Python side
- [x] Тест: неправильный тип → `TypeError` (не `panic`)
- [x] Тест: None как аргумент → graceful error, не segfault
- [x] Тест: concurrent calls (threading.Thread) → thread safety
- [x] Тест: GIL interaction — pyO3 `allow_threads` корректно

---

### 3.3 — pyo3-sanitizer: unit тесты

**Текущее:** `crates/pyo3-sanitizer/src/lib.rs` (10.6KB) — нет `#[cfg(test)]` модуля (вероятно).

**Задачи:**
- [x] Добавить `#[cfg(test)]` модуль в `lib.rs`
- [x] Тест: XSS payload → stripped (известные векторы из OWASP XSS CheatSheet)
- [x] Тест: легитимный HTML → сохранён (разрешённые теги)
- [x] Тест: пустая строка → пустая строка
- [x] Тест: очень длинная строка (1MB) → не OOM, не timeout
- [x] Тест: вложенные теги > 100 уровней → не stack overflow
- [x] Тест: utf-8 non-BMP chars (emoji, CJK) → сохранены
- [x] Сравнение с pyo3-sanitizer вывод = wasm-sanitizer вывод (изоморфность)

---

### 3.4 — WASM sanitizer (frontend/wasm-sanitizer)

**Задачи:**
- [x] Проверить наличие Rust unit тестов в `frontend/wasm-sanitizer/src/`
- [x] Если нет — добавить аналогичные тесты из п.3.3
- [x] `wasm-pack test --node` — запустить тесты в Node.js окружении
- [x] Добавить в CI: `wasm-pack test --node frontend/wasm-sanitizer`
- [x] Добавить в CI: сравнительный тест "pyo3 output == wasm output" для identical inputs

---

### 3.5 — Fuzzing: расширение corpus и бюджета

**Текущее:** `native/rust_ext/fuzz/fuzz_targets/` — cargo-fuzz targets существуют.

**Задачи:**
- [x] Посмотреть существующие fuzz targets (`ls fuzz/fuzz_targets/`)
- [x] Новый target: `fuzz_sanitize` — подавать произвольный HTML pyo3-sanitizer
- [x] Новый target: `fuzz_uuid7_roundtrip` — случайный timestamp → UUID v7 → parse → timestamp
- [x] Новый target: `fuzz_hmac_verify` — произвольные payload/sig/key → не panic
- [x] Corpus структура:
  ```
  fuzz/corpus/
  ├── fuzz_sanitize/     # seed inputs: known XSS payloads
  ├── fuzz_uuid7/        # seed inputs: timestamps
  └── fuzz_hmac/         # seed inputs: valid HMAC tuples
  ```
- [x] CI budget: `timeout 90m cargo fuzz run {target} -- -max_total_time=5400`
- [x] В `rust-fuzz.yml`: добавить все новые targets, artifacts upload при crash
- [x] Настроить OSS-Fuzz integration (опционально, если проект open source)

---

### 3.6 — Rust CI gate

**Задачи:**
- [x] В CI добавить:
  ```yaml
  - name: Rust unit coverage
    run: |
      cargo llvm-cov --no-default-features --lib --fail-under-lines 95
  ```
- [x] Добавить `cargo clippy --all-targets -- -D warnings` как gate
- [x] Добавить `cargo audit` для dependency CVE check

---

## Wave 4 — Frontend: 98% Statements, 92% Branches, 95% Functions

> **Цель:** Vitest coverage ≥ 98/92/95, Playwright E2E полный happy+sad path.

### 4.1 — Vitest coverage gap analysis

**Текущее:** statements 90%, branches 80%, functions 82%.

**Исключения которые нужно пересмотреть (`vitest.config.ts`):**
```ts
// Сейчас исключены — возможно часть можно покрыть:
"**/routes/**/*"      // роуты — можно тестировать loader/action
"**/pages/**/*"       // страницы — renderToSnapshot + interaction
"**/api/events.ts"    // API функции — unit mockable
"**/api/stories.ts"
"**/api/news.ts"
```

**Задачи:**
- [x] Запустить `npm run test:ci` → получить `coverage/coverage-summary.json`
- [x] Скрипт: `scripts/fe-coverage-gaps.mjs` — топ-30 файлов по missing branches

---

### 4.2 — Hooks: покрытие до 95%+

**Текущее gap (из vitest.config.ts комментариев):**
- `useChatWebSocket` — 32% → 78.9% (был поднят до 78%, нужно довести)
- `useProfileSync` — cached-restore paths (возможно unreachable)
- `api/client` — 429-retry loop

**Задачи:**
- [x] `useChatWebSocket` — ping/reconnect-cap 30s timer paths (fake timer mocking)
- [x] `useProfileSync` — initFn cached-restore (если source bug — зафиксировать pragma: no cover + issue)
- [x] `api/client.ts` — 429 retry: `vi.useFakeTimers()` + `vi.advanceTimersByTime()`
- [x] `useAuthApi` — все error states (network error, 401, 403, 500)
- [x] `useLoginFlow` — MFA challenge paths
- [x] `useSessionCrypto` — key derivation, storage
- [x] `usePushPreferences` — subscription/unsubscription, permission denied

---

### 4.3 — Components: render + interaction

**Задачи:**
- [x] Все компоненты в `src/components/` — `@testing-library/react` render тесты
- [x] Проверка: каждый компонент рендерится без исключений (smoke render)
- [x] Interaction: click, keyboard nav, form submit
- [x] Error boundaries: проверить что компонент показывает fallback при throw

**Приоритет по покрытию:**
- [x] `MessengerButton.tsx` — сейчас исключён, добавить
- [x] `MainLayout.tsx` — сейчас исключён, добавить
- [x] `FocusListener.tsx` — исключён, добавить
- [x] Features: `EventsFeature`, `MapFeature`, `MessengerFeature`

---

### 4.4 — API interceptors и client

**Задачи:**
- [x] `src/api/client.ts` — все paths: success, 4xx, 5xx, network timeout, retry
- [x] `src/api/events.ts`, `src/api/stories.ts`, `src/api/news.ts` — убрать из exclusion или явно обосновать
- [x] MSW handlers: убедиться что все API эндпоинты замокированы
- [x] ETag cache: hit/miss/invalidation

---

### 4.5 — i18n: полное покрытие

**Текущее:** `translationParity.test.ts`, `authTranslations.test.tsx`, `pageTranslations.test.tsx`, `navigationTranslations.test.tsx`, `i18n.test.tsx`.

**Задачи:**
- [x] Убедиться что все ключи i18n покрыты `translationParity.test.ts`
- [x] Тест: переключение языка mid-session
- [x] Тест: RTL locale (если поддерживается)
- [x] Тест: missing key → fallback, не пустая строка

---

### 4.6 — Service Worker тесты

**Текущее:** `src/tests/sw.test.ts` (22KB) — хорошая база.

**Задачи:**
- [x] Покрыть все workbox стратегии: NetworkFirst, CacheFirst, StaleWhileRevalidate
- [x] Тест: offline → cache hit
- [x] Тест: push notification receive → display
- [x] Тест: background sync (failed request → retry on reconnect)

---

### 4.7 — Storybook/Chromatic: snapshot гейт

**Текущее:** Chromatic настроен, `storybook-static/` есть.

**Задачи:**
- [x] Убедиться что каждый UI компонент имеет Story
- [x] Добавить Story для edge cases: empty state, error state, loading state
- [x] Chromatic threshold: accept ≤ 0.1% pixel diff
- [x] В `chromatic.yml`: `--exit-zero-on-changes false` (блокировать при изменениях без review)

---

### 4.8 — Playwright E2E: полный happy+sad path

**Текущее:** 18 spec файлов. Анализ пробелов:

**Happy paths (добавить):**
- [x] `registration_flow.spec.ts` — регистрация → email verify → login → dashboard
- [x] `profile_complete.spec.ts` — обновление профиля, аватар upload, timezone
- [x] `events_lifecycle.spec.ts` — create event → publish → register → attend → review
- [x] `news_authoring.spec.ts` — create → draft → publish → edit → delete
- [x] `schedule_management.spec.ts` — view schedule, export iCal, add to calendar

**Sad paths (добавить):**
- [x] `auth_lockout.spec.ts` — 5 wrong passwords → lockout → unlock
- [x] `mfa_recovery.spec.ts` — lost MFA device → recovery codes
- [x] `upload_rejection.spec.ts` — virus file upload → rejection message
- [x] `network_offline.spec.ts` — уже есть `offline.spec.ts`, расширить
- [x] `permission_denied.spec.ts` — student trying admin actions → 403 UI

**Задачи:**
- [x] Для каждого spec: Page Object Model pattern
- [x] Fixtures: `fixtures/auth.ts`, `fixtures/data-factory.ts`
- [x] Параллелизация: `playwright.config.ts` → `workers: 4`

---

### 4.9 — axe-core: 0 violations CI gate

**Задачи:**
- [x] Установить: `@axe-core/playwright` (уже в devDependencies)
- [x] В каждый E2E spec добавить:
  ```ts
  const results = await checkA11y(page);
  expect(results.violations.filter(v => v.impact === 'critical' || v.impact === 'serious')).toHaveLength(0);
  ```
- [x] Создать `a11y-assertions.ts` helper
- [x] Запустить на: login page, dashboard, chat, notifications, events, profile
- [x] CI gate: 0 critical/serious violations → fail build

---

### 4.10 — LHCI: жёсткие thresholds

**Текущее:** `.lighthouserc.js` и `.lighthouserc.js.backend` существуют.

**Задачи:**
- [x] Обновить `.lighthouserc.js`:
  ```js
  assertions: {
    'categories:performance': ['error', { minScore: 0.9 }],
    'categories:accessibility': ['error', { minScore: 0.95 }],
    'categories:best-practices': ['error', { minScore: 1.0 }],
    'categories:seo': ['warn', { minScore: 0.9 }],
  }
  ```
- [x] Добавить в CI: `lhci autorun` как блокирующий step (не warn)
- [x] Измерить baseline на current build, зафиксировать в `budget.json`

---

### 4.11 — Frontend Vitest CI gate эскалация

**После Wave 4:**
- [x] Поднять в `vitest.config.ts`:
  ```ts
  thresholds: {
    statements: 92,
    branches: 81,
    functions: 84,
    lines: 92,
  }
  ```

---

## Wave 5 — Integration, Contract, Performance, Chaos

> **Цель:** Все межсервисные границы верифицированы. k6 P99 thresholds в CI. Chaos resilience.

### 5.1 — Pact contract tests: расширение

**Текущее:** 8 контрактных тестов в `tests/contracts/`.

**Задачи:**
- [ ] `test_file_processor_contract.py` — добавить: upload > 100MB, ClamAV infected response
- [ ] `test_ws_hub_contract.py` — добавить: broadcast to 1000 clients, heartbeat timeout
- [ ] `test_gateway_rest_contract.py` — добавить: all error codes (401, 403, 429, 503)
- [ ] `test_redis_key_contracts.py` — расширить: все ключи из `contracts/redis-keys.md`
- [ ] Новый: `test_nats_message_contract.py` — формат NATS-сообщений между backend и ws-hub
- [ ] Новый: `test_grpc_contract.py` — все gRPC методы file-processor → backend
- [ ] Настроить Pact Broker (или PactFlow): хранить pacts centrally
- [ ] В CI: provider verification step после consumer tests

---

### 5.2 — Integration tests: расширение

**Текущее:** 6 файлов в `tests/integration/`.

**Задачи:**
- [ ] `test_redis_contract.py` — расширить: Lua scripts, pub/sub, streams, keyspace notifications
- [ ] `test_rls_messages.py` — PostgreSQL Row Level Security: проверить все роли
- [ ] `test_trace_driven.py` — расширить: traces для chat, notifications, events flows
- [ ] Новый: `test_full_stack_auth.py` — gateway → backend → DB → Redis (testcontainers)
- [ ] Новый: `test_nats_delivery.py` — publish → ws-hub → client receive (testcontainers)
- [ ] Новый: `test_elasticsearch_search.py` — indexing → search → pagination (testcontainers)

---

### 5.3 — k6 Performance: CI integration

**Текущее:** `tests/performance/load_test.js`, `ws_hub_load_test.js` — скрипты есть, но нет CI запуска.

**Задачи:**
- [ ] В `docker-compose.ci-loadtest.yml` — добавить k6 service
- [ ] SLO определить:
  ```
  HTTP P50 < 50ms, P95 < 200ms, P99 < 500ms
  WebSocket connect < 100ms
  Error rate < 0.1%
  ```
- [ ] Расширить `load_test.js`:
  - Scenario: login flow (10 users, 5min)
  - Scenario: chat burst (100 messages/s, 30s)
  - Scenario: file upload (10 concurrent, 10MB files)
- [ ] Расширить `ws_hub_load_test.js`:
  - 500 concurrent connections
  - Message fanout: 1 → 100 subscribers
- [ ] Добавить `tests/performance/db_perf_test.js` — критические SQL queries
- [ ] CI: weekly k6 run + result comparison с baseline
- [ ] Threshold failure → CI fail + alert

---

### 5.4 — Chaos Engineering

**Текущее:** `tests/chaos/test_resilience.py` (1 файл).

**Задачи:**
- [ ] `test_redis_failure.py` — Redis падает mid-request → 503 + retry
- [ ] `test_postgres_failover.py` — primary → replica failover → eventual consistency
- [ ] `test_nats_partition.py` — NATS network partition → message deduplication
- [ ] `test_s3_timeout.py` — MinIO timeout → upload retry + cleanup
- [ ] `test_elasticsearch_down.py` — ES недоступен → fallback к DB search
- [ ] `test_rate_limit_storm.py` — 10000 requests/s → limiter holds, no crash
- [ ] `test_concurrent_logins.py` — 1000 concurrent logins → no race in session creation

---

### 5.5 — Database: migration и schema тесты

**Задачи:**
- [ ] `tests/integration/test_migration_data.py` — расширить: data seeding, constraint violations, index creation
- [ ] `db-perf-gate.yml` — анализ: что именно гейтится, добавить EXPLAIN ANALYZE тесты
- [ ] Тест: все alembic миграции идемпотентны (up → down → up даёт одинаковую схему)
- [ ] Тест: RLS policies для всех ролей (student, teacher, admin, service)

---

### 5.6 — Security: расширение

**Задачи:**
- [ ] DAST: `dast.yml` — ZAP сканирование всех аутентифицированных эндпоинтов
- [ ] `tests/security/test_mfa_race.py` — расширить: все race conditions в auth
- [ ] `tests/test_ssrf_blocklist.py` — расширить: cloud metadata endpoints, internal IPs
- [ ] Добавить: `tests/security/test_timing_attacks.py` — constant-time comparison checks
- [ ] Semgrep custom rules в `.semgrep-custom/`: SQL injection, path traversal, unsafe deserialization

---

## Wave 6 — Observability, Documentation, Final CI Gate

> **Цель:** Полное observability тестирование. Roadmap задокументирован. CI gates финализированы.

### 6.1 — OpenTelemetry тесты

**Задачи:**
- [ ] `tests/test_otel_v2.py` — расширить: spans для каждого DB query, NATS publish, Redis op
- [ ] Тест: baggage propagation через services
- [ ] Тест: sampling rate (не 100% traces в prod)
- [ ] Тест: span attributes — все required semantic conventions присутствуют

---

### 6.2 — Prometheus metrics тесты

**Текущее:** `tests/test_metrics_endpoint.py`, `tests/test_business_metrics.py`.

**Задачи:**
- [ ] Тест: все кастомные метрики increment при соответствующих действиях
- [ ] Тест: labels корректны (user_role, service, endpoint)
- [ ] Тест: gauge/counter/histogram правильно используются
- [ ] Тест: metrics не leak между тестами (reset между изолированными тестами)

---

### 6.3 — TESTING.md документация

**Задачи:**
- [ ] Создать `TESTING.md` в корне репозитория:
  ```markdown
  # Testing Guide
  ## Architecture
  ## Running tests locally
  ## Coverage thresholds
  ## Wave progress tracker
  ## Adding new tests
  ## CI pipeline explained
  ```
- [ ] Создать `docs/testing/` с разделами по фронтам
- [ ] Добавить coverage badges в README.md

---

### 6.4 — Финальный CI gate sweep

**Задачи:**
- [ ] Python: `fail_under = 98`, branch coverage enforced
- [ ] Go: 90% per service, race detector
- [ ] Rust: llvm-cov 95%
- [ ] Frontend: statements 97%, branches 90%, functions 94%
- [ ] Mutation: 85% kill rate
- [ ] Fuzz: weekly CI job с budget
- [ ] Pact: provider verification blocking
- [ ] k6: P99 SLO blocking
- [ ] LHCI: perf≥90, a11y≥95, BP=100
- [ ] axe-core: 0 critical/serious violations

---

## Приложения

### A. Coverage Progress Tracker

| Фронт | Wave 0 | Wave 1 | Wave 2 | Wave 3 | Wave 4 | Wave 5 | Wave 6 |
|-------|--------|--------|--------|--------|--------|--------|--------|
| Python statements | baseline | 95% | — | — | — | — | 98%+ |
| Python branches | baseline | 88%+ | — | — | — | — | 95%+ |
| Python mutation | baseline | 75% | — | — | — | — | 85%+ |
| Go gateway | baseline | — | 85% | — | — | — | 90%+ |
| Go ws-hub | baseline | — | 85% | — | — | — | 90%+ |
| Go file-proc | baseline | — | 80% | — | — | — | 90%+ |
| Rust unit | baseline | — | — | 90% | — | — | 95%+ |
| FE statements | 90% | — | — | — | 95% | — | 98%+ |
| FE branches | 80% | — | — | — | 88% | — | 92%+ |
| E2E scenarios | 18 specs | — | — | — | 30+ specs | — | full |

---

### B. Ключевые команды

```powershell
# Python coverage
pytest --cov=app --cov-report=json --cov-branch

# Python mutation
uv run mutmut run

# Go coverage
go test -coverprofile=coverage.out -coverpkg=./... ./...
go tool cover -func=coverage.out

# Rust coverage  
cargo llvm-cov --no-default-features --lib --fail-under-lines 95

# Frontend coverage
npm run test:ci --prefix frontend

# E2E
npm run test:e2e --prefix frontend

# k6 load test
k6 run tests/performance/load_test.js

# Fuzz (Rust)
cargo fuzz run fuzz_sanitize -- -max_total_time=7200

# Fuzz (Python)
python -m atheris tests/fuzz/run_atheris.py
```

---

### C. Инструменты которые уже есть и их роль

| Инструмент | Роль | Волна |
|-----------|------|-------|
| pytest + pytest-asyncio | Unit/integration Python | 0, 1, 5 |
| pytest-cov + Coverage.py | Python branch coverage | 0, 1 |
| pytest-xdist | Параллельный запуск | 1 |
| Hypothesis | Property-based tests | 1 |
| Schemathesis | OpenAPI conformance | 1 |
| mutmut | Python mutation testing | 1 |
| Atheris | Python fuzzing (Linux) | 1 |
| pact-python | Contract tests | 5 |
| testcontainers | Live service integration | 5 |
| go test -race | Go unit + race | 2 |
| golangci-lint | Go static analysis | 2 |
| cargo test | Rust unit | 3 |
| cargo-fuzz | Rust fuzzing | 3 |
| cargo llvm-cov | Rust coverage | 3 |
| Vitest + v8 | Frontend unit | 4 |
| Playwright | E2E | 4, 5 |
| @axe-core/playwright | A11y E2E assertions | 4 |
| LHCI | Performance/a11y | 4 |
| Chromatic | Visual regression | 4 |
| k6 | Load testing | 5 |
| ZAP DAST | Dynamic security | 5 |
| Semgrep | Static security | 5 |
| bandit + pip-audit | Python security | 5 |
| Trivy + grype | Container security | 6 |
| OpenTelemetry | Observability testing | 6 |

---

### D. Anti-patterns которых избегаем

1. **No "coverage cheats"** — `# pragma: no cover` только для genuinely untestable code (entrypoints, platform-specific)
2. **No trivial assertions** — `assert True`, `assert mock.called` без content check — убиваются mutation тестами
3. **No fixture explosion** — новые фикстуры только если действительно shared (>3 tests)
4. **No `time.sleep()` в тестах** — только `anyio.sleep(0)`, fake timers, event-based waiting
5. **No test isolation violations** — каждый тест должен быть F.I.R.S.T (Fast, Independent, Repeatable, Self-Validating, Timely)
6. **No broad mocking** — mock только external I/O (Redis, DB, HTTP), не internal logic
