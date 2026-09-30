# MVP — оперативный статус

Срез на 2026-09-30. [MVP_MASTER_PLAN.md](MVP_MASTER_PLAN.md) — решения и блоки
0–10; [University_Ecosystem_MVP.md](University_Ecosystem_MVP.md) — продуктовые
требования. Goal активен. Сейчас восстанавливаем проверяемость и live-приёмку
(блоки 0–3); release completion ещё не достигнут.

## Текущее состояние

| Область | Подтверждённый факт |
| --- | --- |
| Git и PR | Ветка `egorribun`; последний опубликованный HEAD `99fb8076fc9f4f4962f74029f0534b7884f7c7f5`. `origin/main` и merge-base: `78b9499079442191920835eed9de93b726cf36a1`. PR #1306 открыт, но пока заблокирован проверками старого SHA и stale context ruleset. Локальный рабочий набор готов к commit/push. |
| CI | Старые Actions относятся к опубликованному `99fb807`, а не к локальному diff; нужны новые checks после push. Security Policy Integrity не входит в обязательные ruleset contexts. Ruleset 8335285 требует отсутствующий `Rust Criterion Benchmarks (pyo3-sanitizer)`, удалённый по ADR-044; корректное снятие этого stale context требует отдельного изменения GitHub ruleset администратором и пока не разрешено. Не создавать фиктивную замену и не bypass. |
| Среда | GitHub CLI аутентифицирован; scope `packages` не показан, поэтому прямую публикацию в GHCR нельзя считать подтверждённой. На машине около 31.8 GiB RAM; Docker Desktop доступен. В checkout нет пользовательского `.env`; kind не установлен. |
| Live-стенд | Отдельный принадлежащий live-stand проект `ue-live-97e64749be022c80` существует; backend readiness ранее отвечал HTTP 200. Текущий read-only `status` подтвердил, что сервисы запущены, а backend/frontend/Postgres/Redis/NATS/Mailpit/S3 и health-probe контейнеры healthy. У gateway, ws-hub и Caddy нет Docker health статуса. Этот стенд ещё не обновлён на локальный diff; сохранить volumes и `.env`, lifecycle вести только через `scripts/live_stand.py`. |
| Рабочий diff | Текущая интеграционная пачка покрывает backend, frontend, Go, CI и тесты. `git diff --check` прошёл. Все изменения остаются локальными до завершения review и проверок. |
| Архивы и rescue | 120 tracked-файлов / 3,981,581 байт. Rescue bundle проверен для SHA `d0aad7c296facd79b3d41b037bc4160f5b3132be`; bundle и manifest содержат исторические credential-shaped строки. Значения не выводить и bundle не распространять. Классификация ждёт подтверждения статуса credentials; архивы пока не удалять. |
| Audit ledger | В `AUDIT_PLATFORM_FULL.md` остаются 63 ID для пересмотра на итоговом SHA. BE-02 и RUST-P3-03 требуют доказательной проверки по согласованным критериям; повторно реализовывать уже существующий base64/WASM export не нужно. |

## Проверки текущей интеграционной пачки

- `tests/test_quality_workflow_contract.py`: 187 passed.
- Auth-service branch-closure fixture failure is corrected without changing
  production behavior: the full file passed 12/12 tests. Image-proxy coverage
  passed 64 tests with 100% statements and branches; it asserts the one-day
  Redis TTL. DashboardHero accessibility/readiness closure passed 9/9 tests and
  axe checks; independent review approved the fix.
- Целевой backend/contracts набор: 145 passed; `uv lock --check` и
  orphan/anti-pattern проверка прошли. Повторённый vector-sharding набор прошёл
  118 тестов;
  `vector_sharding_service.py` имеет 100% statements и branches (247/114).
- Pinned Go 1.26.6 race + coverage: пакеты прошли; `pkg/hub` достиг 100%.
  В предыдущем aggregate `./...` было 99.7% из-за `services/ws-hub/main.go:47`;
  добавлен startup-path test, и точечный профиль подтвердил покрытие блока.
  Повторный pinned race+coverage прошёл: все четыре пакета population дали 100%;
  pinned golangci-lint v2.13.2 прошёл с 0 issues.
- Frontend suite после readiness, auth import и DashboardHero изменений: 712 файлов / 8,210 тестов passed.
  TypeScript, ESLint и
  Prettier тоже прошли; два UI-тестовых ожидания приведены к новому readiness
  контракту и CSSOM-нормализации.
- Финальные локальные проверки dirty worktree: `verify_harness.py` 27/27,
  `scripts/fast_preflight.py --max-workers 3` 9/9, all-files pre-commit — pass,
  `uv lock --check`, link checker, `git diff --check` и cached diff check — pass.
  Preflight включает frontend typecheck/lint/format/i18n, backend typecheck/lint,
  message contract, harness и выбранные backend/CI contracts; отчёт
  `artifacts/fast-preflight/fast-preflight.json` помечен SHA `99fb807` при dirty
  worktree и не является SHA-bound release evidence.
- Документационные/CI контракты: 236 passed; Markdown link checker проверил
  547 файлов без broken local links. `STATUS.md` остаётся в лимите 150 строк.
- `npm run build` и `node scripts/check-bundle-budget.mjs` прошли после устранения
  трёх ineffective dynamic-import warnings: main 205.67 KiB raw, initial JS
  365.83 KiB gzip, CSS 39.33 KiB gzip, largest general lazy 274.2 KiB gzip,
  password dictionary 591.17 KiB gzip. Три tracked Windows WASM/provenance outputs,
  изменённые сборкой, восстановлены к исходному чистому состоянию; canonical
  Linux parity этим прогоном не подтверждена.
- Независимые reviews не нашли actionable-дефектов в vector и текущих Go/backend
  изменениях. Проверены SET EX/SETEX, Redis transport exceptions, legacy и
  uninspectable clients, WS Hub locking/auth/cache invalidation и Gateway POST
  recovery routes. Content-level сверка архива завершена: уникальные требования
  перенесены, а O2/O3/O5/O7 остатки описаны без ложного статуса завершения.
- Эти результаты относятся к локальному dirty workspace; они не заменяют CI или
  release evidence, привязанные к итоговому SHA.

## Известные незакрытые приёмки

- Не выполнен полный live product workflow и сквозная приёмка требований ТЗ.
- Не замерены WS 1000 подключений / 500 пар / 100 сообщений/с / 30 минут,
  slow-reader поведение и восстановление per-replica invalidation consumer.
- Не завершены backup/restore и RPO/RTO evidence, BE-02 на deployed Docker/kind
  БД, kind-приёмка с Envoy Gateway, полный audit-ledger review и три сравнимых
  полных CI-прогона.
- Визуальные комплекты и Linux baselines требуют пользовательского утверждения.
  Внешние production, реальные SMTP/push-провайдеры, физические устройства,
  CDC и field CWV остаются вне согласованной области MVP.

## Ближайший порядок

1. Повторить all-files pre-commit на стабильном дереве и fast preflight;
   подтвердить baseline, links и diff checks.
2. Обычным commit/push обновить PR #1306 и разобрать новые checks; исправлять
   актуальные failures без bypass.
3. Обновить live stand на проверенный commit без удаления данных; проверить
   readiness, повторяемый demo seed и существующие live specs.
4. Продолжить блоки мастер-плана по свежим CI и live evidence.
5. Удалять архивы и распространять bundle только после triage credential-shaped
   строк и проверки восстановления полезного содержимого.

## Постоянные границы

- Не ослаблять 100% применимые coverage и viable mutation score; не вводить
  необоснованные exclusions, quarantine, timeout inflation или ручной статус.
- Разрешён обычный commit/push/PR/merge/GHCR/release. Нет admin bypass,
  force-push, branch-protection изменений и переписывания Git history.
- Не удалять пользовательские volumes, `.env`, backups или данные; миграции не
  сжимать. Удалять только проверенные ресурсы, принадлежащие текущему прогону.
- Kubernetes MVP использует Envoy Gateway + Gateway API. Внешний production
  остаётся вне MVP; обязательная MFA и новые Activity-функции не добавляются.
