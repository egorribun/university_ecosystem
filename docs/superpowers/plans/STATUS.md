# MVP — оперативный статус

Срез на 2026-09-30 09:56 UTC. [MVP_MASTER_PLAN.md](MVP_MASTER_PLAN.md)
содержит цели, решения и критерии; [University_Ecosystem_MVP.md](University_Ecosystem_MVP.md)
определяет продуктовые требования. Goal активен; MVP и релиз ещё не приняты.

## Текущее состояние

| Область | Подтверждённый факт |
| --- | --- |
| Git / PR | Текущий кодовый SHA `8af4c0367729398da2ecf21d8250a1305cb9400e`; пять кодовых коммитов впереди `origin/egorribun`=`724da93d8a73c096df493859a7b9f972df8d1894`. `origin/main`=`78b9499079442191920835eed9de93b726cf36a1` — предок ветки. PR [#1306](https://github.com/egorribun/university_ecosystem/pull/1306) ещё указывает на `724da93`; обычный push ожидает свежий preflight и интеграцию двух security patches. |
| CI | Старый Matrix run [#36693219605](https://github.com/egorribun/university_ecosystem/actions/runs/36693219605) относится к `724da93` и остаётся in progress из-за Python unit shard-2. На этом старом SHA не прошли Frontend Lint & Format и отдельный [Go Fuzz run #36693218514](https://github.com/egorribun/university_ecosystem/actions/runs/36693218514). Исправления live URL setup и Go test readiness есть локально, но новый SHA-bound CI ещё не запускался. |
| Локальные проверки | На `8af4c036`: frozen fast-preflight 9/9; JSON `artifacts/fast-preflight/mvp-block-8af4c036-20260930.json` (SHA-256 `E87CEED51EB064197D6BE103AB1FE1AF5A9E95E0C6FB1A69805A2E977054FF4A`). Ранее на той же кодовой базе прошли chat/security и live-stand contracts; эти локальные результаты не заменяют required PR checks или release evidence. После интеграции текущих security patches preflight требуется повторить. |
| Messenger | Интегрированы backend-исправление поиска пользователей и least-data projection, regression tests для API/service, реальный live-spec двух WebSocket-контекстов и согласование group-management mocks. Опциональный Chromium group-management E2E прошёл 1/1 за 29,8 с при штатном лимите памяти. Новый messenger live-spec ещё не запускался на живом стеке. |
| Backup / restore | Добавлен versioned PostgreSQL backup artifact с manifest, SHA-256 и read-back проверкой; HTTPS обязателен по умолчанию, HTTP допускается только с явным local-dev opt-in для локального/private адреса из allowlist. 26 тестов прошли. Реальные DB/S3 backup и restore, совместная точка восстановления PostgreSQL/S3 и RPO/RTO не проверялись. |
| Live-стенд | На точном SHA `8af4c036` отдельный managed worktree и Compose project прошли запуск, два idempotent seed и live Playwright: 14/14 passed, 0 skipped/flaky на desktop/mobile. Стенд остановлен owner-validated `stop`; volumes сохранены. Sanitized report: `artifacts/live-acceptance/mvp-block-8af4c036-20260930.json`. Review нашёл дополнительную проверку, связывающую Playwright URL с подписанной картой портов; patch выполняется отдельно. |
| Ruleset | Ruleset `8335285` active; после разрешённого удаления только retired `Rust Criterion Benchmarks (pyo3-sanitizer)` required-contexts стало 91 вместо 92. Ещё четыре исторических/mismatched context остаются: старые Python unit/integration, `Coverage & Quality Policy Gate`, `Incremental Mutation Tests (frontend)`. Bypass и другие изменения правил не выполнялись. |
| Credentials / архивы | 120 tracked-файлов / 3,981,581 байт. Value-free inventory нашёл девять Chromatic token-shaped упоминаний в трёх отчётах. Пользователь имеет Project Owner/Admin доступ и выполнит reset token + замену Actions secret; подтверждение успешных workflow ещё ожидается. Seeded-admin пароль подтверждён как использовавшийся только в одноразовой CI-базе; статический fallback удаляется отдельным patch. Архивы и rescue bundle остаются заблокированы до Chromatic reset/secret update и успешной проверки. Значения не выводились. 12 старых broken links находятся только внутри архивов. |
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

- Разобрать долгий Python shard-2 по последним тестам/fixture; сохранить всю тестовую популяцию и штатный timeout.
- Обычным push отправить кодовые коммиты и этот STATUS update в PR #1306, затем получить свежие terminal required checks на обновлённом head; устранить source-bound failures без ослабления контракта.
- Остаются четыре stale required contexts; старый CI run ещё ждёт Python shard-2. Chromatic token reset/secret update и проверка workflow ожидают пользователя; архивы не меняются.
- Не выполнены полный RU/EN demo matrix, backup+restore с RPO 24 ч / RTO 30 мин, BE-02 deployed DDL preflight, kind с Envoy Gateway и проверка шести GHCR digests.
- Нужны три сопоставимых полных зелёных CI-наблюдения, закрытие всех применимых coverage/mutation gates, финальная security review и проверка O1–O8.
- Визуальные комплекты и Linux baselines требуют пользовательского утверждения. Внешние production, реальные SMTP/push-провайдеры, физические устройства, CDC и field CWV остаются вне MVP.

## Ближайший порядок

1. Интегрировать два изолированных security patches, прогнать целевые контракты и повторить fast-preflight.
2. Обычным push обновить PR #1306 и получить свежие terminal required checks; старые source-bound failures классифицировать на новом head.
3. После Chromatic reset/secret update проверить обе workflow; затем завершить credential triage, перенос и link checks прежде чем решать вопрос архивов/bundle.
4. Продолжить MIG-PASS-01 и остальные acceptance-блоки по [мастер-плану](MVP_MASTER_PLAN.md), не затрагивая пользовательские volumes.

## Постоянные ограничения

- Сохранять 100% применимого coverage и viable mutation score; не добавлять необоснованные exclusions, quarantine, timeout inflation или ручные статусы мутантов.
- Разрешены обычные commits, push, PR, merge, GHCR и release. Без отдельного поручения запрещены admin bypass, изменение branch protection, force-push и переписывание Git history.
- Не удалять пользовательские volumes, `.env`, backups или данные; миграции не сжимать. Убирать только подтверждённые ресурсы текущего прогона.
- Для kind использовать Envoy Gateway + Gateway API; внешнее production-развёртывание, обязательную MFA и новые Activity-функции не добавлять.
