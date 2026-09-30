# MVP — оперативный статус

Срез на 2026-09-30 07:01 UTC. [MVP_MASTER_PLAN.md](MVP_MASTER_PLAN.md)
содержит цели, решения и критерии; [University_Ecosystem_MVP.md](University_Ecosystem_MVP.md)
определяет продуктовые требования. Goal активен; MVP и релиз ещё не приняты.

## Текущее состояние

| Область | Подтверждённый факт |
| --- | --- |
| Git / PR | Ветка egorribun и origin/egorribun чистые на a012571bf3e8dc3b6d56536f842e3d424c7fd6de. origin/main и merge-base: 78b9499079442191920835eed9de93b726cf36a1. PR [#1306](https://github.com/egorribun/university_ecosystem/pull/1306) открыт, BLOCKED; GitHub показывает 167 файлов (+28,786/−19,838) относительно main. Не менять правила защиты и не обходить их. |
| CI | Matrix Expansion #36680211704 на a012571: последний снимок 41 SUCCESS, 10 IN_PROGRESS, 19 QUEUED, 0 failures. Source/Test Inventory SUCCESS (job 109774910668). Required Security Audit тоже SUCCESS. Отдельный не-required PR-target Security Policy Integrity упал, потому что workflow из base main использует неподдерживаемый gh api --fail-with-body. Остальные required checks ещё выполняются. |
| Локальные проверки | На актуальной ветке fast preflight 9/9, harness 27/27, применимые pre-commit hooks и git diff --check прошли. PostgreSQL row-lock regression прошёл 1/1 на Testcontainers PostgreSQL; SQLite lane корректно пропускает тест. После detect-secrets .secrets.baseline перепроверен и staged без содержательных изменений. |
| Live-стенд | Отдельный manager worktree; Compose project ue-live-1dc5f2e4c0503c50 healthy, volumes сохранены. Runtime собран на ea5f341717b332bf5670c4cf4bc63e1ee7cef5a3; последующий a012571 меняет только комментарий к test inventory. Demo seed запускался дважды без дублирования. Существующие desktop/mobile live specs прошли 12/12 на runtime ea5f341. |
| Live ограничения | Локальный Docker Caddy profile отключает auto-HTTPS и принимает HTTP; TLS остаётся проверкой kind. Полный продуктовый live workflow и полный RU/EN demo matrix ещё не выполнены. |
| Messenger | Live UI проверка выявила дефект поиска: frontend посылает search, backend применяет только full_name. Независимая проверка подтвердила, что узкое отображение search в full_name сохранит текущий безопасный escaped name filter и приоритет явного full_name. Исправление и тест доставки по настоящему WS разрабатываются в отдельном worktree; не интегрировано. |
| Backup / restore | Read-only аудит не нашёл проверяемого manifest/checksum/read-back/restore workflow или RPO/RTO evidence. Изолированная реализация versioned backup artifact и безопасного restore начата отдельным агентом; данные и внешние backups не затрагиваются. |
| Архивы | 120 tracked-файлов / 3,981,581 байт. Исторические token/password-подобные записи имеют неизвестный статус. Значения не выводить и не проверять запросами; архивы и rescue bundle не удалять/распространять до разрешения credential triage и переноса уникальных требований. |
| Audit ledger | AUDIT_PLATFORM_FULL.md содержит 63 ID для итоговой сверки. BE-02 требует проверки на deployed Docker/kind БД; RUST-P3-03 — доказательства существующего base64 path и canonical WASM parity, без повторной реализации. |

## Проверенное evidence

- scripts/fast_preflight.py --max-workers 3: 9/9; verify_harness.py --repo-only: 27/27.
- Regression tests/integration/test_user_repository_for_update_postgres.py: 1 passed при USE_TESTCONTAINERS_POSTGRES=1; default SQLite run пропущен ожидаемо.
- Полный существующий live Playwright набор: 12/12 desktop/mobile; seed повторён без изменений/дублирования.
- PostgreSQL row-lock и auth/repository/reset набор: 25/25; backend/contracts набор: 145 passed.
- Ранее завершённые frontend, Go, Rust и coverage результаты остаются историческим evidence; они не заменяют проверку нового SHA и release-source evidence.
- Локальные результаты не подменяют завершённый CI, обязательные PR checks, полную live приёмку или SHA-bound release evidence.

## Открытые обязательные приёмки

- Получить терминальный результат текущего CI и исправлять только актуальные failures без исключений и ослабления контрактов.
- Интегрировать messenger search regression, два browser contexts и реальную WS доставку; затем повторить live suite на итоговом image.
- Завершить идемпотентный RU/EN demo seed и полный сценарный workflow из ТЗ.
- Не решены блокировка ruleset снятым Rust Criterion Benchmarks (pyo3-sanitizer) и credential triage старых архивных записей.
- Не выполнены backup/restore с RPO 24 ч / RTO 30 мин, BE-02 deployed DDL preflight, kind с Envoy Gateway, полный аудит 63 ID, три сопоставимых полных CI-прогона и проверка шести опубликованных GHCR digests.
- Визуальные комплекты и Linux baselines требуют пользовательского утверждения. Внешние production, реальные SMTP/push-провайдеры, физические устройства, CDC и field CWV остаются вне MVP.

## Ближайший порядок

1. Дождаться терминального результата текущей Matrix Expansion; inventory исправление на a012571 уже подтверждено.
2. Независимо проверить messenger patch и backup/restore patch в их worktrees; интегрировать только после тестов и review.
3. Обновить этот status на интегрированном SHA, выполнить релевантные проверки, commit и normal push в PR #1306.
4. Не merge до разрешения существующего правила GitHub с точным retired check; не использовать bypass.
5. Продолжать продуктовую и инфраструктурную приёмку по блокам [мастер-плана](MVP_MASTER_PLAN.md).
6. Архивы очищать только после переноса требований и решения credential triage.

## Постоянные ограничения

- Сохранять 100% применимого coverage и viable mutation score; не добавлять необоснованные exclusions, quarantine, timeout inflation или ручные статусы мутантов.
- Разрешены обычные commits, push, PR, merge, GHCR и release. Запрещены без отдельного поручения admin bypass, изменение branch protection, force-push и переписывание Git history.
- Не удалять пользовательские volumes, .env, backups или данные; миграции не сжимать. Очищать только подтверждённые ресурсы текущего прогона.
- Использовать Envoy Gateway + Gateway API для kind; внешнее production-развёртывание, обязательную MFA и новые Activity-функции не добавлять.
