# MVP — оперативный статус

Срез на 2026-09-30 08:57 UTC. [MVP_MASTER_PLAN.md](MVP_MASTER_PLAN.md)
содержит цели, решения и критерии; [University_Ecosystem_MVP.md](University_Ecosystem_MVP.md)
определяет продуктовые требования. Goal активен; MVP и релиз ещё не приняты.

## Текущее состояние

| Область | Подтверждённый факт |
| --- | --- |
| Git / PR | Проверенный кодовый SHA — `0df28b560847b186652a86f5355180c2f2ea669b`; к нему подготовлен отдельный doc-only STATUS update. Четыре кодовых коммита впереди `origin/egorribun` (`3cdd58c90e8c7219beb930b36539f6486bfd04dd`). `origin/main`=`78b9499079442191920835eed9de93b726cf36a1` — предок ветки. PR [#1306](https://github.com/egorribun/university_ecosystem/pull/1306) пока указывает на старый head `3cdd58c`; пакет будет отправлен обычным push. |
| CI | Matrix run [#36688918511](https://github.com/egorribun/university_ecosystem/actions/runs/36688918511) относится к старому SHA `3cdd58c` и остаётся in progress: Python unit shards 0/1/3 и integration shard 0 успешны; shard 2 ещё выполнялся на последнем snapshot. Единственный required failure — Semgrep SAST из-за отсутствовавшей точной записи для безопасной Psycopg identifier-композиции в `scripts/backup_db.py`; узкая policy entry и adversarial tests добавлены в локальный коммит `18da1bcc`. В PR rollup также видны Security Policy Integrity и внешний Semgrep OSS failures, но `gh pr checks --required` их не считает required. Активный ruleset `main` по-прежнему требует retired/mismatched contexts: `Rust Criterion Benchmarks (pyo3-sanitizer)`, старые unsuffixed Python jobs, `Coverage & Quality Policy Gate` и `Incremental Mutation Tests (frontend)`. Поэтому PR остаётся BLOCKED даже после зелёных актуальных проверок; bypass и изменение правил не выполнялись. |
| Локальные проверки | На `0df28b560`: frozen fast-preflight 9/9 за 69.184 с при 6 workers; live/Compose/startup contracts: 146 passed; миграционный image-gate/workflow contracts: 58 passed; frontend TypeScript typecheck прошёл; интегрированный file-scoped pre-commit прошёл. Артефакт preflight привязан к `0df28b560847b186652a86f5355180c2f2ea669b`: `artifacts/fast-preflight/mvp-block-0df28b560-20260930.json` (SHA-256 `031E823B5025D3B4E0D41F775926B8ED2099364E0A29009BDEC043161B60EC92`). Это локальное evidence, не замена PR CI или release evidence. |
| Messenger | Интегрированы backend-исправление поиска пользователей и least-data projection, regression tests для API/service, реальный live-spec двух WebSocket-контекстов и согласование group-management mocks. Опциональный Chromium group-management E2E прошёл 1/1 за 29,8 с при штатном лимите памяти. Новый messenger live-spec ещё не запускался на живом стеке. |
| Backup / restore | Добавлен versioned PostgreSQL backup artifact с manifest, SHA-256 и read-back проверкой; HTTPS обязателен по умолчанию, HTTP допускается только с явным local-dev opt-in для локального/private адреса из allowlist. 26 тестов прошли. Реальные DB/S3 backup и restore, совместная точка восстановления PostgreSQL/S3 и RPO/RTO не проверялись. |
| Live-стенд | В `0df28b560` включена полная 15-портовая loopback remap; владелец стенда подписывает карту HMAC, `status`/`stop`/`teardown` используют её без чтения VAPID-файла, schema 2 остаётся совместимой. Перепроверены 146 контрактов и typecheck; ни один контейнер, проект или volume не запускался и не менялся. Полный Compose render в root пока не подтверждён: отсутствует локальный ignored `.env.docker.workers`; этот файл не создавался и не изменялся. Существующие Compose projects/volumes сохранены. |
| Архивы | 120 tracked-файлов / 3,981,581 байт. Уникальные полезные требования уже перенесены в master plan, workflows, ADR/runbook и индексы. В архиве остаются credential-похожие строки с неизвестным статусом; rescue bundle не создавался, архивы не удалялись до credential triage. 12 broken links находятся только внутри исторических архивных отчётов. |
| Audit ledger | Из 63 ID: 55 закрыты текущими source/test ссылками, 6 superseded принятыми решениями, открыты BE-02 и RUST-P3-03. Отдельный MIG-PASS-01 остаётся открытым; проверяется возможность exact-image CI proof без обращения к deployed secrets/DB. Эти классификации ещё не финальная SHA-bound приёмка. |

## Проверенное evidence

- Fast-preflight на `0df28b560847b186652a86f5355180c2f2ea669b` завершился 9/9 с exit 0 за 69.184 с (`--max-workers 6`, timeout 600 с). JSON: `artifacts/fast-preflight/mvp-block-0df28b560-20260930.json`; SHA-256 указан в Git/PR строке.
- На том же SHA: `tests/test_live_stand.py tests/test_docker_startup_contracts.py tests/test_s3_cutover_compose_contract.py` — 146 passed; `frontend` `npm run typecheck` — passed; интегрированный pre-commit завершился успешно.
- MIG-PASS exact-image gate добавлен в существующий DB Migration Gate. Узкие целевые backend/workflow contracts: 58 passed на кодовом снимке до live-port commit; cleanup проверяет наличие reader role и не маскирует первичный сбой при cleanup/dispose. Условия deployed MIG-PASS-01 остаются открытыми.
- Semgrep false positive разобран по точному FindingKey; policy entry scoped на `scripts/backup_db.py:612–614`, с владельцем/сроком и регрессионным тестом. Локальный SAST/pre-commit прошёл; статус старого GitHub run для этого изменения не засчитывается.
- Messenger backend: 52 целевых теста; frontend: 91 unit/contract test, `tsc --noEmit`, ESLint; Playwright group-management: 1/1 на отдельном worktree.
- Backup artifact: `tests/test_backup_db.py` — 26 passed. Markdown link checker — 548 файлов, 0 broken local links.
- Существующий compose stand и текущие volume сохранены; `status`, `stop`, `teardown` используют secret-free Compose environment, проверено 33 тестами. Live messenger workflow на текущем SHA ещё не выполнен.
- На старом CI SHA Python shard 2 всё ещё не имел терминального отчёта в последнем snapshot. Исторические coverage/mutation цифры не переобъявляются evidence для текущего SHA.
- Проверки локальных тестов и `git diff --check` не заменяют required PR checks, deployed migrations, backup/restore или проверку опубликованных образов.

## Открытые обязательные приёмки

- Разобрать долгий Python shard-2 по последним тестам/fixture; сохранить всю тестовую популяцию и штатный timeout.
- Обычным push отправить кодовые коммиты и этот STATUS update в PR #1306, затем получить свежие terminal required checks на обновлённом head; устранить source-bound failures без ослабления контракта.
- Не решены блокировка правилами из-за retired required context `Rust Criterion Benchmarks (pyo3-sanitizer)` и неизвестный статус credential-подобных архивных строк; bypass и изменение правил защиты не выполнялись.
- Не выполнены живые messenger/продуктовые сценарии на образах текущего SHA, полный RU/EN demo matrix, backup+restore с RPO 24 ч / RTO 30 мин, BE-02 deployed DDL preflight, kind с Envoy Gateway и проверка шести GHCR digests.
- Нужны три сопоставимых полных зелёных CI-наблюдения, закрытие всех применимых coverage/mutation gates, финальная security review и проверка O1–O8.
- Визуальные комплекты и Linux baselines требуют пользовательского утверждения. Внешние production, реальные SMTP/push-провайдеры, физические устройства, CDC и field CWV остаются вне MVP.

## Ближайший порядок

1. Обычным push отправить проверенные коммиты в существующий PR #1306; запускать новые SHA-bound CI checks.
2. По свежему run определить состояние Python shards и source-bound failures; не повышать timeout и не исключать тесты.
3. Подготовить изолированный live Compose project через подписанную свободную port map и проверенное владение; текущие пользовательские volumes не трогать.
4. Продолжить MIG-PASS-01 и следующие блоки мастер-плана.
5. Продолжать продуктовую, backup/restore, kind и audit-приёмку по [мастер-плану](MVP_MASTER_PLAN.md).
6. Архивы удалять и rescue bundle создавать только после credential triage и сохранения/проверки полезных материалов.

## Постоянные ограничения

- Сохранять 100% применимого coverage и viable mutation score; не добавлять необоснованные exclusions, quarantine, timeout inflation или ручные статусы мутантов.
- Разрешены обычные commits, push, PR, merge, GHCR и release. Без отдельного поручения запрещены admin bypass, изменение branch protection, force-push и переписывание Git history.
- Не удалять пользовательские volumes, `.env`, backups или данные; миграции не сжимать. Убирать только подтверждённые ресурсы текущего прогона.
- Для kind использовать Envoy Gateway + Gateway API; внешнее production-развёртывание, обязательную MFA и новые Activity-функции не добавлять.
