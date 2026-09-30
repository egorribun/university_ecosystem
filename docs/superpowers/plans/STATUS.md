# MVP — оперативный статус

Срез на 2026-09-30. [MVP_MASTER_PLAN.md](MVP_MASTER_PLAN.md) — решения и блоки
0–10; [University_Ecosystem_MVP.md](University_Ecosystem_MVP.md) — продуктовые
требования. Goal активен. Сейчас восстанавливаем проверяемость и live-приёмку
(блоки 0–3); release completion ещё не достигнут.

## Текущее состояние

| Область | Подтверждённый факт |
| --- | --- |
| Git и PR | Последний push в PR #1306: `d0cb778fedbe77f9e8b275ef2bd274411af2dea1`; локальный HEAD `57a095d5c` содержит после него admin API E2E correction `a1d62e975`, PostgreSQL row-lock fix `3f84a6cfc` и scope regression `57a095d5c`. Эти три коммита ещё не запушены. `origin/main`/merge-base: `78b9499079442191920835eed9de93b726cf36a1`; ancestry и diff сверить перед merge. |
| CI | На опубликованном PR SHA `d0cb778` `gh pr checks` показал 133 pass, 2 in progress и один failure в необязательном `Security Policy Integrity` (ошибка флага из base workflow); монитор required checks не сообщил обязательных failures. Новые коммиты ещё не запускались в CI. Ruleset 8335285 всё ещё требует снятый по ADR-044 `Rust Criterion Benchmarks (pyo3-sanitizer)`; не создавать фиктивный check и не обходить правила. |
| Среда | Проверены: uv 0.11.28 с Python 3.14.7, Node 24.21.0, Go 1.27.1, Rust 1.98.1; `uv lock --check` проходит. GitHub CLI аутентифицирован (`repo`, `workflow`), scope `packages` не показан. Docker 29.8.1 доступен с effective limits 23.5 GiB RAM / 16 CPU; host ранее измерялся около 31.8 GiB RAM. В checkout нет пользовательского `.env`; наличие kind перепроверить перед Block 9. |
| Live-стенд | `ue-live-1dc5f2e4c0503c50` healthy на `3f84a6cfc`, backend readiness — HTTP 200. На этом SHA password-reset и исправленный admin API denial прошли desktop/mobile по 2/2 каждый. Предыдущий полный прогон на `d0cb` выявил reset HTTP 500 и неверный admin URL; оба дефекта имеют regression proof. Seed не запускался; volumes сохранены. |
| Рабочее дерево | Коммиты `a1d62e975`, `3f84a6cfc` и `57a095d5c` прошли применимые hooks; PostgreSQL row-lock regression со scope check прошёл 1/1, auth/repository/reset набор — 25/25; harness — 27/27; fast preflight — 9/9 на HEAD `57a095d5c` при незакоммиченных docs (отчёт `artifacts/fast-preflight/fast-preflight.json`). Только master-plan и STATUS остаются незакоммиченными; link checker проверил 547 файлов без broken local links. Перед push сверить diff и чистое состояние. |
| Архивы и rescue | 120 tracked-файлов / 3,981,581 байт. Pinned detect-secrets и Gitleaks дали 0 находок в архивных файлах, однако ручная классификация нашла исторические ссылки на project token (W121/W123/W201) и тестовый пароль seeded-admin (W171:118); актуальная валидность/отзыв неизвестны. Не выводить значения, не проверять их запросами и не распространять bundle. Удаление архивов приостановлено до разрешения вопроса credentials и переноса требований. |
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
- W208–W211 сверены с ТЗ и текущим кодом: live-группы, reply, forwarding,
  персональный unread и group-notification context включены в Block 4; прежние
  live-результаты не засчитываются для текущего SHA. «Seen by N» уже реализован,
  но не входит в MVP gate; автоудаление группы ниже трёх участников и отдельные
  roster frames тоже не добавлять. W210/W211 перенести как rationale и считать
  историческими без текущей роли; live API/WS доказательства остаются открытыми.
- В audit archive известны 12 исторических broken links. Автоматический secrets
  scan дал 0 находок, но ручная проверка выявила потенциально операционные
  исторические credentials с неизвестным статусом; архивы и rescue bundle не
  удалять/распространять до решения по credential triage.
- Независимые reviews не нашли actionable-дефектов в vector и текущих Go/backend
  изменениях. Проверены SET EX/SETEX, Redis transport exceptions, legacy и
  uninspectable clients, WS Hub locking/auth/cache invalidation и Gateway POST
  recovery routes. O2/O3/O5/O7 остатки описаны без ложного статуса завершения.
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
- PostgreSQL integration regression воспроизвёл ошибку bare `FOR UPDATE` на
  nullable joined relationship (RED), затем подтвердил `FOR UPDATE OF users`,
  успешное обновление профиля из конкурирующей сессии и сериализацию блокировки
  пользователя (GREEN 1/1). Auth/repository/reset unit набор прошёл 25/25;
  password-reset и admin live specs прошли по 2/2 на desktop/mobile.
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
