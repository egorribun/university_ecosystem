# MVP — оперативный статус

Срез на 2026-09-30. [MVP_MASTER_PLAN.md](MVP_MASTER_PLAN.md) — решения и блоки
0–10; [University_Ecosystem_MVP.md](University_Ecosystem_MVP.md) — продуктовые
требования. Goal активен. Сейчас восстанавливаем проверяемость и live-приёмку
(блоки 0–3); release completion ещё не достигнут.

## Текущее состояние

| Область | Подтверждённый факт |
| --- | --- |
| Git и PR | Ветка `egorribun`, локальный проверенный кодовый SHA `66a62d1333407571e563faf5a5268fae89e09e37`; шесть функциональных коммитов продолжают PR #1306. На момент среза опубликованная вершина PR была `6b93913adfa893d89033f7598dab37bd87b82e30`; перед merge сверить актуальные checks и ancestry с GitHub. `origin/main`/merge-base: `78b9499079442191920835eed9de93b726cf36a1`. |
| CI | На старом SHA `6b93913` integration job упал из-за устаревшего `testcontainers.redis` при `-W error`; импорт исправлен и целевой Docker-тест проходит. Security Policy Integrity не входит в обязательные contexts и использовал workflow base SHA. Ruleset 8335285 всё ещё требует снятый по ADR-044 `Rust Criterion Benchmarks (pyo3-sanitizer)`; его администраторское изменение отдельно не разрешено. Не создавать фиктивный check и не обходить правила. |
| Среда | GitHub CLI аутентифицирован; scope `packages` не показан, поэтому прямую публикацию в GHCR нельзя считать подтверждённой. На машине около 31.8 GiB RAM; Docker Desktop доступен. В checkout нет пользовательского `.env`; kind не установлен. |
| Live-стенд | `ue-live-1dc5f2e4c0503c50` запущен на SHA `6b93913`; сервисы и readiness были healthy. Первый полный live lane дал 5 passed / 7 failed: три role logins и desktop reset упёрлись в общий лимит 5/min; два admin assertions — в responsive duplicate locator; mobile reset был перезагружен первой передачей контроля service worker. Все три причины исправлены локально, live повтор ещё не выполнен. Seed повторно не запускать до отдельной проверки; volumes сохранять, lifecycle вести только через `scripts/live_stand.py`. |
| Рабочее дерево | Шесть обычных коммитов собраны на `egorribun`; `git diff --check` и targeted hooks прошли. Не force-push; перед отправкой сверить чистое состояние. |
| Архивы и rescue | 120 tracked-файлов / 3,981,581 байт. Rescue bundle проверен для SHA `d0aad7c296facd79b3d41b037bc4160f5b3132be`; bundle и manifest содержат исторические credential-shaped строки. Значения не выводить и bundle не распространять. Классификация ждёт подтверждения статуса credentials; архивы пока не удалять. |
| Audit ledger | В `AUDIT_PLATFORM_FULL.md` остаются 63 ID для пересмотра на итоговом SHA. BE-02 и RUST-P3-03 требуют доказательной проверки по согласованным критериям; повторно реализовывать уже существующий base64/WASM export не нужно. |

## Ранее подтверждённые широкие проверки

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

## Текущие исправления и evidence

- На кодовом SHA `66a62d1` `scripts/fast_preflight.py --max-workers 3` прошёл
  9/9; changed-files pre-commit, `git diff --check` и harness прошли. Повторный
  all-files pre-commit не завершился на repo-wide Semgrep и не засчитывается.
- Login form/JSON теперь используют отдельный `rate_limit_auth_login`; полный
  rate-limit + middleware набор прошёл 51/51. Admin audit seed повторно создаёт
  0 новых записей: regression test 1/1. Redis Testcontainers integration test
  прошёл 1/1 с `DeprecationWarning` как ошибкой.
- PWA register-SW и forgot-password unit/component набор прошёл 31/31; frontend
  typecheck, ESLint и Prettier прошли. Live Playwright config собрал 12 сценариев;
  live retest на новом image/SHA ещё не выполнен.
- Локальные результаты не заменяют SHA-bound CI, полную live-приёмку или release
  evidence. В частности, RU/EN seed, owner gate и полный demo content matrix
  остаются открытыми.

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
