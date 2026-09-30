# MVP — оперативный статус

Срез на 2026-09-30 10:15 UTC. [MVP_MASTER_PLAN.md](MVP_MASTER_PLAN.md)
содержит цели, решения и критерии; [University_Ecosystem_MVP.md](University_Ecosystem_MVP.md)
определяет продуктовые требования. Goal поставлен на паузу по просьбе пользователя
для перезапуска приложения; MVP и релиз ещё не приняты.

## Текущее состояние

| Область | Подтверждённый факт |
| --- | --- |
| Git / PR | Проверенный docs checkpoint `98c9145c2` содержит root HEAD `1671973e7` и зафиксирован до этой pause-status записи; в том snapshot ветка `egorribun` была ahead на семь коммитов (пять code, два docs/status) относительно `origin/egorribun`=`724da93d8a73c096df493859a7b9f972df8d1894`. `origin/main`=`78b9499079442191920835eed9de93b726cf36a1` — предок. PR [#1306](https://github.com/egorribun/university_ecosystem/pull/1306) всё ещё на `724da93`; обновления не push-ились. |
| Worktrees | Read-only инвентарь Git показывает 15 локальных worktrees; четыре привязаны к текущим Codex artifacts. Неизвестные/старые worktrees не изменялись; аудит владельца и необходимости завершить после текущих агентов. |
| CI | Старый Matrix run [#36693219605](https://github.com/egorribun/university_ecosystem/actions/runs/36693219605) относится к `724da93`; по последней проверке 10:10Z Python unit shard-2 всё ещё in progress, хотя прошёл штатный 45-минутный job timeout; terminal результата нет. Frontend static gates упали на `knip` из-за eager-чтения LIVE URL, исправленного в локальном `a24a85098`; отдельный [Go Fuzz run #36693218514](https://github.com/egorribun/university_ecosystem/actions/runs/36693218514) упал в `TestDisconnectUser_MultipleSessionsForUser` при ожидании готовности hub, исправление уже есть в `398db9841`. Все относятся к старому SHA; свежего SHA-bound CI пока нет. |
| Локальные проверки | На `8af4c036`: frozen fast-preflight 9/9; JSON `artifacts/fast-preflight/mvp-block-8af4c036-20260930.json` (SHA-256 `E87CEED51EB064197D6BE103AB1FE1AF5A9E95E0C6FB1A69805A2E977054FF4A`). Ранее на той же кодовой базе прошли chat/security и live-stand contracts; эти локальные результаты не заменяют required PR checks или release evidence. После интеграции текущих security patches preflight требуется повторить. |
| Messenger | Интегрированы backend-исправление поиска пользователей и least-data projection, regression tests для API/service, реальный live-spec двух WebSocket-контекстов и согласование group-management mocks. Опциональный Chromium group-management E2E прошёл 1/1 за 29,8 с при штатном лимите памяти. Новый messenger live-spec ещё не запускался на живом стеке. |
| Backup / restore | Добавлен versioned PostgreSQL backup artifact с manifest, SHA-256 и read-back проверкой; HTTPS обязателен по умолчанию, HTTP допускается только с явным local-dev opt-in для локального/private адреса из allowlist. 26 тестов прошли. Реальные DB/S3 backup и restore, совместная точка восстановления PostgreSQL/S3 и RPO/RTO не проверялись. |
| Live-стенд | На точном SHA `8af4c036` отдельный managed worktree и Compose project прошли запуск, два idempotent seed и live Playwright: 14/14 passed, 0 skipped/flaky на desktop/mobile; остановлен owner-validated `stop`, volumes сохранены. Report: `artifacts/live-acceptance/mvp-block-8af4c036-20260930.json`. Reviewed owner-port patch commit `85bce3c3` отдельно: 49 Python + 23 Node tests и lint/pre-commit/harness прошли, но cherry-pick не выполнен. Follow-up `--no-sync` test change остался незакоммиченным в том worktree; требует retest. |
| Ruleset | Ruleset `8335285` active; после разрешённого удаления только retired `Rust Criterion Benchmarks (pyo3-sanitizer)` required-contexts стало 91 вместо 92. Ещё четыре исторических/mismatched context остаются: старые Python unit/integration, `Coverage & Quality Policy Gate`, `Incremental Mutation Tests (frontend)`. Bypass и другие изменения правил не выполнялись. |
| Credentials / архивы | 120 tracked-файлов / 3,981,581 байт. Value-free inventory: девять Chromatic token-shaped упоминаний в трёх отчётах. Пользователь подтвердил reset; GitHub metadata показывает `CHROMATIC_PROJECT_TOKEN` `updatedAt=2026-09-30T10:08:36Z`; значение не читалось. Workflow закрыт billing gates/`skip: true`, платный запуск не выполнять. Seeded-admin пароль использовался только в одноразовой CI-базе; hardening patch остался незавершённым в отдельном worktree. Архивы и bundle не изменялись. 12 старых broken links только внутри архивов. |
| Audit ledger | Из 63 ID: 55 закрыты текущими source/test ссылками, 6 superseded принятыми решениями, открыты BE-02 и RUST-P3-03. Отдельный MIG-PASS-01 остаётся открытым; проверяется возможность exact-image CI proof без обращения к deployed secrets/DB. Эти классификации ещё не финальная SHA-bound приёмка. |

## Проверенное evidence

- Fast-preflight на `0df28b560847b186652a86f5355180c2f2ea669b` завершился 9/9 с exit 0 за 69.184 с (`--max-workers 6`, timeout 600 с). JSON: `artifacts/fast-preflight/mvp-block-0df28b560-20260930.json`; SHA-256 указан в Git/PR строке.
- На том же SHA: `tests/test_live_stand.py tests/test_docker_startup_contracts.py tests/test_s3_cutover_compose_contract.py` — 146 passed; `frontend` `npm run typecheck` — passed; интегрированный pre-commit завершился успешно.
- MIG-PASS exact-image gate добавлен в существующий DB Migration Gate. Узкие целевые backend/workflow contracts: 58 passed на кодовом снимке до live-port commit; cleanup проверяет наличие reader role и не маскирует первичный сбой при cleanup/dispose. Условия deployed MIG-PASS-01 остаются открытыми.
- Semgrep false positive разобран по точному FindingKey; policy entry scoped на `scripts/backup_db.py:612–614`, с владельцем/сроком и регрессионным тестом. Локальный SAST/pre-commit прошёл; статус старого GitHub run для этого изменения не засчитывается.
- Messenger backend: 52 целевых теста; frontend: 91 unit/contract test, `tsc --noEmit`, ESLint; Playwright group-management: 1/1 на отдельном worktree.
- Backup artifact: `tests/test_backup_db.py` — 26 passed. Markdown link checker — 548 файлов, 0 broken local links.
- Изолированный live Compose stand прошёл запуск и live lane; остановлен без удаления данных. Полный RU/EN продуктовый matrix и остальные acceptance-сценарии ещё не выполнены.
- На старом CI SHA Python shard 2 всё ещё не имел терминального отчёта в последнем snapshot. Исторические coverage/mutation цифры не переобъявляются evidence для текущего SHA.
- Проверки локальных тестов и `git diff --check` не заменяют required PR checks, deployed migrations, backup/restore или проверку опубликованных образов.

## Открытые обязательные приёмки

- Дождаться терминального статуса старого Python shard-2; новый SHA проверять отдельным run, сохраняя полную тестовую популяцию и штатный timeout.
- Обычным push отправить кодовые коммиты и этот STATUS update в PR #1306, затем получить свежие terminal required checks на обновлённом head; устранить source-bound failures без ослабления контракта.
- Остаются четыре stale required contexts; старый CI run всё ещё не имеет терминального результата. Chromatic reset и secret update подтверждены пользовательским сообщением и GitHub metadata; платный workflow не запускать. Архивная миграция/bundle ещё не завершены.
- Не выполнены полный RU/EN demo matrix, backup+restore с RPO 24 ч / RTO 30 мин, BE-02 deployed DDL preflight, kind с Envoy Gateway и проверка шести GHCR digests.
- Нужны три сопоставимых полных зелёных CI-наблюдения, закрытие всех применимых coverage/mutation gates, финальная security review и проверка O1–O8.
- Визуальные комплекты и Linux baselines требуют пользовательского утверждения. Внешние production, реальные SMTP/push-провайдеры, физические устройства, CDC и field CWV остаются вне MVP.

## Ближайший порядок

1. Интегрировать два изолированных security patches, прогнать целевые контракты и повторить fast-preflight.
2. Обычным push обновить PR #1306 и получить свежие terminal required checks; старые source-bound failures классифицировать на новом head.
3. Продолжить credential triage, перенос и link checks; подготовить rescue bundle с проверкой восстановления до решения вопроса об отдельных удалениях.
4. Продолжить MIG-PASS-01 и остальные acceptance-блоки по [мастер-плану](MVP_MASTER_PLAN.md), не затрагивая пользовательские volumes.

## Checkpoint перед паузой

- Основной checkout: ветка `egorribun`; plan/status checkpoint сохранён локальным
  commit `98c9145c2`, не push-ен. Pause-status запись находится в следующем local-only
  commit.
- Owner-port patch `85bce3c3` reviewed без blocker, но не cherry-picked. В worktree
  `live-owner-port-guard` осталась незакоммиченная правка `--no-sync` и тест; отдельно
  проверить/зафиксировать перед интеграцией.
- Admin-smoke hardening остаётся незакоммиченным в worktree
  `admin-smoke-credential-hardening`; изменены workflow, smoke script/test и seed
  script/test. Продолжить его targeted tests/review перед cherry-pick.
- Архивы и rescue bundle не удалялись/не создавались. Продолжить mapping уникальных
  требований, затем bundle verification и только после этого отдельные удаления.
- Старый GitHub run не использовать как evidence для текущего SHA; следующий шаг
  после возобновления — закончить патчи, review, preflight, затем обычный push PR #1306.

## Постоянные ограничения

- Сохранять 100% применимого coverage и viable mutation score; не добавлять необоснованные exclusions, quarantine, timeout inflation или ручные статусы мутантов.
- Разрешены обычные commits, push, PR, merge, GHCR и release. Без отдельного поручения запрещены admin bypass, изменение branch protection, force-push и переписывание Git history.
- Не удалять пользовательские volumes, `.env`, backups или данные; миграции не сжимать. Убирать только подтверждённые ресурсы текущего прогона.
- Для kind использовать Envoy Gateway + Gateway API; внешнее production-развёртывание, обязательную MFA и новые Activity-функции не добавлять.
