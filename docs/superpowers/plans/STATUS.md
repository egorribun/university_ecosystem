# MVP — оперативный статус

Срез на 2026-10-01 UTC, на контрольной точке паузы. [Мастер-план](MVP_MASTER_PLAN.md)
фиксирует решения и очереди, [ТЗ MVP](University_Ecosystem_MVP.md) задаёт продуктовые
требования. Долгосрочный goal приостановлен на контрольной точке; соответствие всего MVP и выпуск `v1.0.0`
ещё не подтверждены.

## Рабочее состояние

| Область | Подтверждённое состояние |
| --- | --- |
| Git / PR | Локальный checkpoint `00e3a966ccb41047e2aac5c8b22b6991da52779d` создан в основном worktree на `egorribun`. `origin/egorribun` остаётся на `f89720aa70de2bfc17dea94b01ef0c003a72ec85`; checkpoint не отправлен и существующий единственный PR [#1306](https://github.com/egorribun/university_ecosystem/pull/1306) не обновлён. Новые ветки, worktree и PR не создавались. |
| Исторические worktree | Зарегистрированы три старых detached checkout. В этой контрольной точке они не используются и не менялись; их ignored локальные данные не удалялись. |
| Последний CI | Run `36854541549` для указанной базы завершился с failure. Сырые логи с credential-shaped содержимым не публиковались. Выявлены: inventory false positives от локальной игнорируемой папки `mutants/`; strict-mypy ошибки quality checker; WASM provenance drift; Secret Keyword в статическом test hash; gofmt только в тестовом файле gateway; PostgreSQL acceptance использовал ORM новее своей схемы. Локальные исправления и проверки перечислены ниже; свежего SHA-bound CI после них пока нет. |
| Другие красные контексты | `explain-check` исправлен передачей RLS identity в тестовых сценариях; Nilaway guard и Caddy Alpine pin обновлены. `Security Policy Integrity` исполнялся trusted workflow из base `main` и упал на несовместимом аргументе `gh`; это не required context. Ruleset/bypass не менялись. |
| Секреты и данные | Значения секретов не выводились. Chromatic project token ротирован по сообщению пользователя; seeded-admin пароль и `AUDIT_LOG_SECRET` использовались только в эфемерных CI/demo-средах. `.env`, volumes, backups и остановленные Compose-проекты не изменялись. Временный PostgreSQL для проверки миграции создан без user volumes и удалён после теста. |

## Выполнено и проверено локально

- Quality inventory: генератор и anti-pattern checker проходят; checker имеет targeted mypy без ошибок; `tests/test_quality_inventory.py` + workflow contracts — 269 passed. Генератор пропускает только корневой ignored `mutants/` output; тест фиксирует правило.
- Gateway API/Helm: 25 contract tests passed, `helm lint --strict` прошёл; activation остаётся fail-closed до parity лимитов Envoy.
- Backup/restore: paired restore включает scoped prefix, версионные объекты и сохранение уже восстановленных объектов при сбое. Canonical population: 286/286 тестов прошли; statements 1068/1068 (100%), branch arcs 363/364. Единственная незакрытая дуга — `scripts/backup_db.py:1716→1717`, при этом поведенческий тест подтверждает успешный вход/выход клиента. Строгий coverage gate остаётся красным; пороги и исключения не менялись.
- Chat/RLS: related backend regression набор — 58 passed; добавлен PostgreSQL RLS integration сценарий. Реальный DB сценарий Messenger пока не запускался.
- Messenger live contracts: удаление участника проверяет повторный WS join, отказ CSRF-valid send, отсутствие новой доставки удалённому участнику и сохранение истории у остальных; contract 4/4, TypeScript/ESLint/Prettier и desktop/mobile discovery прошли. Live browser не запускался.
- WASM: pinned canonical Rust/wasm-pack/wasm-opt builder воспроизвёл и устранил package provenance drift; focused tests 12/12, artifact tests 8/8, verifier прошёл.
- MFA миграция: historical assertions сохранены на `202608250002`; перед ORM race scenario isolated DB поднимается до `head`. PostgreSQL acceptance test прошёл на одноразовом контейнере: 1 passed.
- Secrets/RBAC/UI: статический test password заменён runtime Argon2id hash, `tests/test_seed_demo_ownership.py` — 16 passed. Credential fixture в backup test генерируется во время теста. Полный `pre-commit run --all-files` прошёл, включая `detect-secrets`, hardcoded-secret scan, Bandit, mypy и Semgrep; `.secrets.baseline` явно restaged после scan. Caddy/startup contracts — 99 passed; Activity/map contracts — 2 passed.
- Документы: критерии из устаревшего `MVP_APPROVED_PLAN.md` перенесены в мастер-план и актуальные contracts; файл и ссылки удалены. Оба link-checker режима ранее прошли 429 Markdown-файлов.
- `golangci-lint run ./...` на локальном Go 1.27.1 / golangci-lint 2.14.0 — 0 issues; CI failure в 2.13.2 был только форматированием gateway test file, исправленным в текущем diff.

Все перечисленные тесты относятся к локальному изменяемому дереву, если явно не сказано обратное. Они не являются release evidence и не заменяют CI для итогового SHA.

## Пауза и продолжение

1. Локальный checkpoint сохранён; полный `pre-commit run --all-files`, commit-time hooks и `git diff --cached --check` прошли. `.secrets.baseline` restaged после последнего secret scan; tracked-изменений после commit нет.
2. После возобновления исследовать единственную недостающую backup branch arc без ослабления coverage-контракта и повторить canonical population.
3. Push и обновление PR #1306 выполнять после прохождения строгого coverage gate; release evidence для нового SHA пока отсутствует.

После возобновления: восстановить строгий coverage gate, затем отправить `egorribun` в существующий PR #1306 и разобрать SHA-bound CI; выполнить разрешённый live smoke на отдельном owned стенде, затем продолжать продуктовую, performance, mutation, backup/restore и kind-приёмку по мастер-плану.

## Release gates и постоянные ограничения

Остаются: полная live E2E-приёмка; 100% применимого coverage и viable mutation score; три сопоставимых успешных полных CI-прогона; визуальное утверждение; WS нагрузочный профиль; deployed backup/restore и rollback; Envoy Gateway/kind; финальный security review; публикация и проверка шести GHCR digests.

Не выполнять admin bypass, force-push, изменение branch protection, удаление пользовательских данных/volumes/backups, rewrite миграций или создание второго PR. Для kind сохраняется Envoy Gateway + Gateway API; внешнее production, реальные SMTP/push-провайдеры, физические устройства, CDC и field CWV остаются вне MVP.
