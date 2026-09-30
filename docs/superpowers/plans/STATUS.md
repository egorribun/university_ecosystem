# MVP — оперативный статус

Срез на 2026-09-30 08:18 UTC. [MVP_MASTER_PLAN.md](MVP_MASTER_PLAN.md)
содержит цели, решения и критерии; [University_Ecosystem_MVP.md](University_Ecosystem_MVP.md)
определяет продуктовые требования. Goal активен; MVP и релиз ещё не приняты.

## Текущее состояние

| Область | Подтверждённый факт |
| --- | --- |
| Git / PR | `egorribun` на `3ce66008`, на 8 локальных коммитов впереди `origin/egorribun` (`a012571b`); кроме текущей правки этого STATUS дерево чистое. Актуальный `origin/main` — `78b94990`, предок ветки. PR [#1306](https://github.com/egorribun/university_ecosystem/pull/1306) ещё указывает на старый SHA `a012571b`; локальные коммиты не отправлены. Diff относительно main: 185 файлов (+30,534/−19,982). |
| CI | Matrix run [#36680211704](https://github.com/egorribun/university_ecosystem/actions/runs/36680211704) на `a012571b` завершился с 85 required success, отменённым Python shard-2 и зависимой красной `CI Success`. Shard имел 2,848 тестов/2 xdist worker-а, дошёл до 98%, затем около 19 минут не показывал прогресс и был отменён лимитом job 45 минут. Причина не установлена; локальные группы-кандидаты проходят. В активном ruleset `main` остался retired required context `Rust Criterion Benchmarks (pyo3-sanitizer)`: на PR head нет такого check-run, workflow-производителя нет, а ADR-044 говорит его убрать из branch protection. Снятие blocker требует authorized ruleset-maintainer action; bypass и изменение правил не выполнялись. |
| Локальные проверки | На `3ce66008`: frozen fast preflight 9/9; `verify_harness.py`: 27/27; focused contracts: 350 passed; затронутые backend-поведения: 52 passed; backup: 26 passed; live-stand control: 33 passed; messenger frontend: 91 passed; TypeScript и ESLint прошли; проверка ссылок: 548 Markdown-файлов без dangling links. Это локальное evidence, не замена PR CI или release evidence. |
| Messenger | Интегрированы backend-исправление поиска пользователей и least-data projection, regression tests для API/service, реальный live-spec двух WebSocket-контекстов и согласование group-management mocks. Опциональный Chromium group-management E2E прошёл 1/1 за 29,8 с при штатном лимите памяти. Новый messenger live-spec ещё не запускался на живом стеке. |
| Backup / restore | Добавлен versioned PostgreSQL backup artifact с manifest, SHA-256 и read-back проверкой; HTTPS обязателен по умолчанию, HTTP допускается только с явным local-dev opt-in для локального/private адреса из allowlist. 26 тестов прошли. Реальные DB/S3 backup и restore, совместная точка восстановления PostgreSQL/S3 и RPO/RTO не проверялись. |
| Live-стенд | Read-only inventory связал активный Compose project `ue-live-1dc5f2e4c0503c50` с отдельным `mvp-live-acceptance` worktree; он занимает host ports `80/443`, `8000`, `8080`, `8081/8083`, `3000`, `7233/7243`, `9090`, `12345`, `15433`, `4040`, `8082` и `18025`. В root есть другой project `ue-live-97e64749be022c80`: контейнеры остановлены, volumes сохранены. Root-код `status` теперь проходит без чтения VAPID-файла. Новый stand пока не запускать; изолированно реализуется полная loopback port remap и preflight. Ни один существующий project/volume не менялся. |
| Архивы | 120 tracked-файлов / 3,981,581 байт. Уникальные полезные требования уже перенесены в master plan, workflows, ADR/runbook и индексы. В архиве остаются credential-похожие строки с неизвестным статусом; rescue bundle не создавался, архивы не удалялись до credential triage. 12 broken links находятся только внутри исторических архивных отчётов. |
| Audit ledger | Из 63 ID: 55 закрыты текущими source/test ссылками, 6 superseded принятыми решениями, открыты BE-02 и RUST-P3-03. Отдельный MIG-PASS-01 остаётся открытым; проверяется возможность exact-image CI proof без обращения к deployed secrets/DB. Эти классификации ещё не финальная SHA-bound приёмка. |

## Проверенное evidence

- Локальный fast-preflight запущен внутри frozen `uv` environment и прошёл 9/9. Предыдущий запуск системным Python без dev-зависимостей не является результатом проверки.
- Messenger backend: 52 целевых теста; frontend: 91 unit/contract test, `tsc --noEmit`, ESLint; Playwright group-management: 1/1 на отдельном worktree.
- Backup artifact: `tests/test_backup_db.py` — 26 passed. Markdown link checker — 548 файлов, 0 broken local links.
- Существующий compose stand и текущие volume сохранены; `status`, `stop`, `teardown` используют secret-free Compose environment, проверено 33 тестами. Live messenger workflow на текущем SHA ещё не выполнен.
- CI run на прежнем SHA не дал терминального pytest-отчёта. Никакие прежние цифры покрытия/мутаций не переобъявляются evidence для текущего SHA.
- Проверки локальных тестов и `git diff --check` не заменяют required PR checks, deployed migrations, backup/restore или проверку опубликованных образов.

## Открытые обязательные приёмки

- Разобрать долгий Python shard-2 по последним тестам/fixture; сохранить всю тестовую популяцию и штатный timeout.
- Завершить remap/preflight live-портов; выполнить file-scoped pre-commit на полном локальном diff, затем отправить проверенный SHA в PR и получить свежие terminal required checks.
- Не решены блокировка правилами из-за retired required context `Rust Criterion Benchmarks (pyo3-sanitizer)` и неизвестный статус credential-подобных архивных строк; bypass и изменение правил защиты не выполнялись.
- Не выполнены живые messenger/продуктовые сценарии на образах текущего SHA, полный RU/EN demo matrix, backup+restore с RPO 24 ч / RTO 30 мин, BE-02 deployed DDL preflight, kind с Envoy Gateway и проверка шести GHCR digests.
- Нужны три сопоставимых полных зелёных CI-наблюдения, закрытие всех применимых coverage/mutation gates, финальная security review и проверка O1–O8.
- Визуальные комплекты и Linux baselines требуют пользовательского утверждения. Внешние production, реальные SMTP/push-провайдеры, физические устройства, CDC и field CWV остаются вне MVP.

## Ближайший порядок

1. Завершить file-scoped pre-commit и документные checks для локальных коммитов; обновить status только с проверенными результатами.
2. Обычным push отправить коммиты в существующий PR #1306; запускать новые SHA-bound CI checks, не переиспользуя старый отменённый run.
3. Параллельно закончить расследование shard-2 и MIG-PASS-01; не повышать timeout и не исключать тесты.
4. Подготовить изолированный live Compose project с доказанным владением и свободными портами; не трогать текущие пользовательские volumes.
5. Продолжать продуктовую, backup/restore, kind и audit-приёмку по [мастер-плану](MVP_MASTER_PLAN.md).
6. Архивы удалять и rescue bundle создавать только после credential triage и сохранения/проверки полезных материалов.

## Постоянные ограничения

- Сохранять 100% применимого coverage и viable mutation score; не добавлять необоснованные exclusions, quarantine, timeout inflation или ручные статусы мутантов.
- Разрешены обычные commits, push, PR, merge, GHCR и release. Без отдельного поручения запрещены admin bypass, изменение branch protection, force-push и переписывание Git history.
- Не удалять пользовательские volumes, `.env`, backups или данные; миграции не сжимать. Убирать только подтверждённые ресурсы текущего прогона.
- Для kind использовать Envoy Gateway + Gateway API; внешнее production-развёртывание, обязательную MFA и новые Activity-функции не добавлять.
