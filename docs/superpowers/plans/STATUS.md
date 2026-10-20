# Статус выпуска MVP v1.0.0

Обновлено: 2026-10-20 (Europe/Istanbul). План — [MVP_MASTER_PLAN.md](MVP_MASTER_PLAN.md), продукт — [ТЗ MVP](University_Ecosystem_MVP.md), качество — [ADR-047](../../adr/ADR-047-risk-based-quality-policy.md).

## Текущий приоритет

Полное закрытие [октябрьского аудита](../../audits/AUDIT-2026-10.md): все 512 исходных AUD IDs. Для каждого нужны source-bound исправление с regression/runtime evidence либо обоснованный disposition. Наличие commit не заменяет приёмку. К приёмке MVP вернуться после аудита.

Подтверждённая нижняя граница — **120/512 (23,4%)**. Это сверка до 7735f048c; полная reconciliation ещё не закончена. [Последний ledger и ограничения](../../audits/AUDIT-2026-10.md#2026-10-20-1100-utc--verified-120-id-checkpoint-and-bounded-corrections). Исходные таблицы сохраняют исторические статусы.

Владелец возобновил работу после a572036d6. Работа на egorribun, в одном checkout, через существующий [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306). Root управляет Git; максимум три GPT-6 Luna Max с непересекающимися файлами. Удалённые операции — через GitHub plugin. Новые ветки/worktree, force-push, bypass, merge/deploy не выполняются.

## Последний принятый CI checkpoint

[e15027a](https://github.com/egorribun/university_ecosystem/commit/e15027afdb4793838de373463654fb9ffc31d079), [Matrix 39240974262](https://github.com/egorribun/university_ecosystem/actions/runs/39240974262), принят 2026-10-19 в 11:46 UTC: 23 terminal workflows, 21 SUCCESS / два SKIP; Matrix 86 jobs, 72 SUCCESS / 14 SKIP. Все 136 check runs сверены с 78 required context/app pairs: 77 SUCCESS / один NEUTRAL, без missing/duplicates/pending/failures.

Checkov/app57789 NEUTRAL означает «1 configuration not found» в PR comparison, а не отсутствие alerts. Отдельный Checkov IaC и пять CodeQL analyses успешны. Готовность к merge/deployment не заявляется.

Python: 16509 PASS / 174 SKIP; frontend: 9355 PASS / 772 файла; PostgreSQL: 202 PASS / 9 SKIP. Quality job 118040612402: diff-cover 4536/0/100%, universe 16683 nodes, provenance/schema/contract valid. Quality artifact 12184206100 и timing artifact 12183714114 проверены в предшествующей приёмке; подробности — в аудите и Git history.

Owned Live 39240974198: 20 browser PASS / два штатных SKIP, успешные stop/receipt/upload, artifact 12182134427; checkout имеет exact source tree e150. Это auth/role/reset smoke, не full smoke. Исторический dd17 RSS-margin risk не объявлен устранённым.

## Текущий source и проверки

Опубликованная контрольная точка — a572036d61a2452bb093b740e9ab264960f6aa51. Она сохраняет семь подготовленных исправлений AUD-119/120/121/122/124/125/126 и exact singleton disposition; GREEN при публикации ещё не был установлен.

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

1. Проверить и опубликовать согласованный пакет исправлений CI, finite cleanup-профиля и audit corrections; получить собственные hosted checks. Сохранить selections, 300-секундный focused budget и quality/security gates.
2. Продолжить tests-first AUD-127/129/130: keyboard radio group, имя/pressed state like, escaping ORG vCard. AUD-128/132 — отдельные задачи. AUD-131 сначала сверить с уже существующим wall-clock schema/model/migration contract.
3. Завершить NATS metadata composition, затем bounded transport/coordinator и guarded runtime acceptance по [spec](../specs/2026-10-18-owned-nats-outbox-acceptance.md), [outage plan](2026-10-19-owned-nats-outage.md) и [Docker observation](2026-10-20-owned-nats-docker-observation.md). Runtime/outage отключены; pure metadata match не доказывает daemon authenticity, inventory или restoration.
4. Закрывать оставшиеся AUD IDs с именованными доказательствами. P1 operational holds AUD-164/167/169/174 сохраняются. AUD-123 требует actual Fluent Bit evidence; source-label assertion его не заменяет.

Тематические планы: [UI lifecycle](2026-10-19-ui-lifecycle-reconciliation.md), [cleanup/timing](2026-10-20-runtime-cleanup-timing.md), [quality entrypoints](2026-10-20-quality-entrypoints.md). Подробная история — в audit supplements и Git history; STATUS содержит текущий срез.

## Неизменные границы

Baseline — 319 identities; интегрированные dispositions — 264, включая singleton, утверждённый 2026-10-20. Все 78 required context/app pairs, blocking CodeQL, hooks и finite131 migration exception до 2026-11-13 сохраняются. Прежние exact approvals не разрешают изменённые/unmatched findings или перенос категорий.

Q1/Q4 source migration действует; глобальный mutation score не повышается ради MVP. Q2/Q3 — v1.1. Новые suppressions, pragmas, broad exclusions, skips, expiry extensions и снижение floors не разрешены.

Перед тяжёлым прогоном: RAM ≤75% / free ≥8 GiB; остановка при RAM ≥85% / free <4 GiB. Отдельное исключение для одиночных Linux screenshot-прогонов: ≤80% / ≥6 GiB, container ≤1 GiB / 2 CPU. Удалять только доказанно принадлежащие работе ресурсы; чужие процессы и prune не трогать.

Manifest source_sha остаётся null. Actual RC, main/bootstrap activation, pre-merge full smoke, визуальная приёмка следующих пакетов и deployment — отдельные этапы. Home12 ранее утверждён только в своём exact scope. Merge/deploy и NATS outage не выполнены.
