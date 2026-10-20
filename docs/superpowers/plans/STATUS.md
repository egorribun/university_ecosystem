# Статус выпуска MVP v1.0.0

Обновлено: 2026-10-20 (Europe/Istanbul). План — [MVP_MASTER_PLAN.md](MVP_MASTER_PLAN.md), продукт — [ТЗ MVP](University_Ecosystem_MVP.md), качество — [ADR-047](../../adr/ADR-047-risk-based-quality-policy.md).

## Текущий приоритет

Полное закрытие [октябрьского аудита](../../audits/AUDIT-2026-10.md): все 512 исходных AUD IDs. Для каждого нужны source-bound исправление с regression/runtime evidence либо обоснованный disposition. Наличие commit не заменяет приёмку. К приёмке MVP вернуться после аудита.

Подтверждённая нижняя граница — **137/512 (26,8%)**. После checkpoint 135 подтверждены уже существующие исправления AUD-144/145; полная reconciliation ещё не закончена. [Последний ledger и ограничения](../../audits/AUDIT-2026-10.md#evidence-checkpoint-137-verified-original-aud-ids). Исходные таблицы сохраняют исторические статусы.

Владелец возобновил работу после a572036d6. Работа на egorribun, в одном checkout, через существующий [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306). Root управляет Git; максимум три GPT-6 Luna Max с непересекающимися файлами. Удалённые операции — через GitHub plugin. Новые ветки/worktree, force-push, bypass, merge/deploy не выполняются.

## Последний принятый CI checkpoint

[e15027a](https://github.com/egorribun/university_ecosystem/commit/e15027afdb4793838de373463654fb9ffc31d079), [Matrix 39240974262](https://github.com/egorribun/university_ecosystem/actions/runs/39240974262), принят 2026-10-19 в 11:46 UTC: 23 terminal workflows, 21 SUCCESS / два SKIP; Matrix 86 jobs, 72 SUCCESS / 14 SKIP. Все 136 check runs сверены с 78 required context/app pairs: 77 SUCCESS / один NEUTRAL, без missing/duplicates/pending/failures.

Checkov/app57789 NEUTRAL означает «1 configuration not found» в PR comparison, а не отсутствие alerts. Отдельный Checkov IaC и пять CodeQL analyses успешны. Готовность к merge/deployment не заявляется.

Python: 16509 PASS / 174 SKIP; frontend: 9355 PASS / 772 файла; PostgreSQL: 202 PASS / 9 SKIP. Quality job 118040612402: diff-cover 4536/0/100%, universe 16683 nodes, provenance/schema/contract valid. Quality artifact 12184206100 и timing artifact 12183714114 проверены в предшествующей приёмке; подробности — в аудите и Git history.

Owned Live 39240974198: 20 browser PASS / два штатных SKIP, успешные stop/receipt/upload, artifact 12182134427; checkout имеет exact source tree e150. Это auth/role/reset smoke, не full smoke. Исторический dd17 RSS-margin risk не объявлен устранённым.

## Текущий source и проверки

Текущая проверенная партия inventory/ICS/CI и frontend исправлений основана на опубликованном 12e7a301638e2d9d76c494b26fbbaafb3072f97b (AUD-136). Её source SHA определяется commit в Git; собственные hosted checks ещё требуются. Его [Matrix 39420191979](https://github.com/egorribun/university_ecosystem/actions/runs/39420191979) ещё не принят. На предыдущем 999f source и checkout 0701692de342abaa09fd1dad96bd33adf3a0b758 подтверждён одинаковый tree 2b1e713f2a2d41346dd1bbc4da0a4e2056262833. Два полных frontend shards принимают AUD-128/132/135 в ledger; AUD-133 ещё ждёт своей приёмки; 12e7 frontend shard 4 отдельно подтвердил весь NewsHeader suite (10 PASS), включая новый News follow-up. Часть остальных 999f jobs отменена после публикации следующего source; полный GREEN не заявляется.

[Matrix 39413091195](https://github.com/egorribun/university_ecosystem/actions/runs/39413091195) выявил четыре причины отказа:

- Fast pre-commit: Ruff переформатировал одно условие verifier. Исправлено только форматирование.
- Node/WASM contracts: тест версии с переводом строки ожидал Python metadata error, хотя неизменённый SemVer gate отклоняет её раньше. Исправлено сообщение; проверка отсутствия записи всех четырёх файлов сохранена.
- Frontend shard 2: Schedule test заменял provider/router tree голым Schedule, повторно монтируя страницу. Исправлен harness, clock/month/dots assertions сохранены; production не меняется.
- Contract Tests: tests-first RED cleanup-профиля — 55 FAIL / 267 PASS. В registry добавлены ровно 27 проверенных pure path/function pairs к прежним 35. Runtime/collector/filesystem/lease cases не допускаются; cancellation и обычный GC сохраняются.

На a572 прошли security/type pre-commit, actual detect-secrets integrity scan, 234 verifier cases, frontend static/build и shards 1/3/4. Зависимые backend jobs пропущены после fast pre-commit; полный CI не принят.

Свежая локальная проверка после возобновления:

- Release-version: 39/39 PASS после точечной коррекции сообщения.
- Backend/config: 94/94 PASS — Grafana trace-to-logs, actual Helm PORT rendering, observability и cache closure.
- Frontend: 135/135 PASS, девять полных suites Schedule/mini-calendar/News edit/lesson dialogs; TypeScript проходит.
- Cleanup: 145/145 protection cases и 124/124 candidate cases PASS после RED; hosted timing ещё требуется.
- Полный локальный Contract-набор на Windows: 295 PASS / 23 platform/dependency SKIP / четыре setup ERROR. Makefile fixtures требуют POSIX; assertions и selections сохранены. Их GREEN должен подтвердить Linux CI.

Эти результаты не увеличивают ledger и не заменяют required checks нового source. Частные логи в репозиторий не добавляются.

## Следующие действия

1. Проверить hosted checks текущей партии после её обычной публикации. Его четыре frontend shards проходят: 9562 PASS / 785 файлов; checkout 9e9e95d61ad2b7179b7cebca3b278bf6261c6cc1 имеет exact source tree bbe7e20b0291e6e0180c3f90ce85fe24ab45648b. Оба pre-commit и actual baseline-integrity job успешны. Focused backend 118620594629 собрал 1052 cases, показал прежний intentional outage hold и затем достиг 300-секундного timeout; полного результата нет. На 999f тот же cohort завершился за 288,75 s. Полный backend shard 1 завершился с 3738 PASS / 38 SKIP / одним FAIL: tracked backend OpenAPI snapshot не обновлён после добавления lang; проверяется штатная регенерация этого артефакта. Backend shard 2 завершился с 5369 PASS / 43 SKIP; shard 3 — 4305 PASS / 26 SKIP / два FAIL: старое literal ожидание Helm backend origin и прежний intentional outage hold. Literal контракт синхронизирован с текущим componentName helper; actual Helm rendering остаётся проверкой. Полный CI не принят. Текущая партия переносит существующий no-Docker transport selector в Contract lane с сохранением тестов, cleanup, coverage/JUnit/provenance и всех остальных gates; увеличивать deadline или скрывать hold нельзя.
2. AUD-136 опубликован после обычных pre-commit/pre-push: единая normalized locale для detail key, SDK query, page и SSR loader; штатный экспорт OpenAPI/SDK добавляет только optional lang у GET event detail. Root: OpenAPI contract и оба backend suites — 43 PASS / два прежних PostgreSQL FTS SKIP; пять frontend suites — 187 PASS, включая actual SDK URL/signal и RU/EN cache isolation. Native TypeScript и полный scanner/verifier проходят. Hook обновил только три line_number и generated_at baseline; все 319 identities неизменны. Hosted checks ещё не приняты. AUD-131 подтверждён actual PostgreSQL 2 PASS / 0 SKIP; AUD-134 — 28 media и шесть commit-failure/shared-reference cases. AUD-133 имеет 73 локальных metrics PASS, но пока не входит в ledger.
3. NATS metadata composition завершена; текущая партия добавляет bounded project inventory reader. Root: 371 PASS (46 новых Contract cases + 224 прежних transport + 101 coordinator), обычный cleanup сохранён. Независимое ревью устранило false acceptance Compose one-off container. Runtime/coordinator/CLI/outage ещё не подключены; owner/lease и Docker authority, остальные adapters и guarded runtime acceptance остаются по [spec](../specs/2026-10-18-owned-nats-outbox-acceptance.md), [outage plan](2026-10-19-owned-nats-outage.md) и [Docker observation](2026-10-20-owned-nats-docker-observation.md). Metadata и supplied-result tests не доказывают actual inventory, daemon authenticity или restoration.
4. Следующая партия AUD-138/139/140 интегрирована локально: label/trigger associations, session-bound add и query-bound rollback receipt. Root: 137 PASS в десяти dialog/context/schedule suites, TypeScript и zero-warning ESLint проходят. Authoritative backend OpenAPI snapshot догоняет три существующих schema locations (order/400/lang): root 46 PASS / два прежних FTS SKIP. CI allocation переносит только duplicate transport invocation в Contract lane; полный четырёхшардовый universe, coverage/JUnit/provenance сохранён, root 238 PASS. Root дополнительно подтвердил AUD-146: story ID сохраняется при reorder, удаление закрывает viewer; 74 PASS в 15 suites, прежние playback reset/stale-frame controls сохранены через явное открытие replacement. Workflow image checker проверяет только реальные image arguments и поддержанные literal bindings/PowerShell arrays: все прежние static digest распознаются, 70 CI-contract PASS. Helm origin contract и actual render: 11 PASS. Полный scanner и обычные hooks применяются к финальной партии; hosted checks требуются, ledger не увеличен.
5. Закрывать оставшиеся AUD IDs с именованными доказательствами. P1 operational holds AUD-164/167/169/174 сохраняются. AUD-123 требует actual Fluent Bit evidence; source-label assertion его не заменяет.

Тематические планы: [UI lifecycle](2026-10-19-ui-lifecycle-reconciliation.md), [cleanup/timing](2026-10-20-runtime-cleanup-timing.md), [quality entrypoints](2026-10-20-quality-entrypoints.md). Подробная история — в audit supplements и Git history; STATUS содержит текущий срез.

## Неизменные границы

Baseline — 319 identities; интегрированные dispositions — 264, включая singleton, утверждённый 2026-10-20. Все 78 required context/app pairs, blocking CodeQL, hooks и finite131 migration exception до 2026-11-13 сохраняются. Прежние exact approvals не разрешают изменённые/unmatched findings или перенос категорий.

Q1/Q4 source migration действует; глобальный mutation score не повышается ради MVP. Q2/Q3 — v1.1. Новые suppressions, pragmas, broad exclusions, skips, expiry extensions и снижение floors не разрешены.

Перед тяжёлым прогоном: RAM ≤75% / free ≥8 GiB; остановка при RAM ≥85% / free <4 GiB. Отдельное исключение для одиночных Linux screenshot-прогонов: ≤80% / ≥6 GiB, container ≤1 GiB / 2 CPU. Удалять только доказанно принадлежащие работе ресурсы; чужие процессы и prune не трогать.

Manifest source_sha остаётся null. Actual RC, main/bootstrap activation, pre-merge full smoke, визуальная приёмка следующих пакетов и deployment — отдельные этапы. Home12 ранее утверждён только в своём exact scope. Merge/deploy и NATS outage не выполнены.
