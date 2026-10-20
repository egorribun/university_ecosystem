# Статус выпуска MVP v1.0.0

Обновлено: 2026-10-20 (Europe/Istanbul). План — [MVP_MASTER_PLAN.md](MVP_MASTER_PLAN.md), продукт — [ТЗ MVP](University_Ecosystem_MVP.md), качество — [ADR-047](../../adr/ADR-047-risk-based-quality-policy.md).

## Текущий приоритет

Полное закрытие [октябрьского аудита](../../audits/AUDIT-2026-10.md): все 512 исходных AUD IDs. Для каждого нужны source-bound исправление с regression/runtime evidence либо обоснованный disposition. Наличие commit не заменяет приёмку. К приёмке MVP вернуться после аудита.

Подтверждённая нижняя граница — **147/512 (28,7%)**. После checkpoint 143 приняты уже существующие исправления AUD-237/238/239/240: root actual PostgreSQL 6 PASS / zero SKIP, encryption/keyring 66 PASS, circuit-breaker suites 75 PASS и attachment/image cohort 245 PASS с 100% трёх модулей; соответствующие source/test files не менялись после полностью принятого e15027a. [Последний ledger и ограничения](../../audits/AUDIT-2026-10.md#evidence-checkpoint-147-verified-original-aud-ids). Исходные таблицы сохраняют исторические статусы.

Владелец возобновил работу после a572036d6. Работа на egorribun, в одном checkout, через существующий [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306). Root управляет Git; максимум три GPT-6 Luna Max с непересекающимися файлами. Удалённые операции — через GitHub plugin. Новые ветки/worktree, force-push, bypass, merge/deploy не выполняются.

## Последний принятый CI checkpoint

[e15027a](https://github.com/egorribun/university_ecosystem/commit/e15027afdb4793838de373463654fb9ffc31d079), [Matrix 39240974262](https://github.com/egorribun/university_ecosystem/actions/runs/39240974262), принят 2026-10-19 в 11:46 UTC: 23 terminal workflows, 21 SUCCESS / два SKIP; Matrix 86 jobs, 72 SUCCESS / 14 SKIP. Все 136 check runs сверены с 78 required context/app pairs: 77 SUCCESS / один NEUTRAL, без missing/duplicates/pending/failures.

Checkov/app57789 NEUTRAL означает «1 configuration not found» в PR comparison, а не отсутствие alerts. Отдельный Checkov IaC и пять CodeQL analyses успешны. Готовность к merge/deployment не заявляется.

Python: 16509 PASS / 174 SKIP; frontend: 9355 PASS / 772 файла; PostgreSQL: 202 PASS / 9 SKIP. Quality job 118040612402: diff-cover 4536/0/100%, universe 16683 nodes, provenance/schema/contract valid. Quality artifact 12184206100 и timing artifact 12183714114 проверены в предшествующей приёмке; подробности — в аудите и Git history.

Owned Live 39240974198: 20 browser PASS / два штатных SKIP, успешные stop/receipt/upload, artifact 12182134427; checkout имеет exact source tree e150. Это auth/role/reset smoke, не full smoke. Исторический dd17 RSS-margin risk не объявлен устранённым.

## Последняя hosted проверка и новая партия

Предыдущий полностью проверенный frontend checkpoint — 299cbc0ab53e93de9c5064a8253c853a519a1f6b, [Matrix 39427747787](https://github.com/egorribun/university_ecosystem/actions/runs/39427747787). Actual checkout d8cad7677b514e32db465c817debbfc045ed7c97 имеет тот же tree bf4522f95bd7c6aa24415d95427895fb457e387b. Все четыре frontend shards и aggregate успешны: 9580 PASS / 785 файлов. Оба pre-commit, actual baseline integrity, Contract Tests, frontend lint/build и отдельные security workflows успешны.

Focused backend job 118646290769 завершился за 212,05 s: 827 PASS / один прежний intentional outage FAIL; таймаута больше нет. Полный backend shard 1: 3514 PASS / 38 SKIP; shard 2: 5967 PASS / 58 SKIP / один тот же intentional outage FAIL; shard 3: 3859 PASS / 45 SKIP. Shard 0 не доходит до полного набора после focused hold; aggregate coverage не принят. JUnit shards 1/3 проверены по digest. Matrix завершён с failure; полный CI не принят. Deadline, test universe, coverage/JUnit/provenance и required gates сохранены.

Пакет этого checkpoint (source SHA определяется содержащим commit в Git) прошёл перечисленные локальные проверки. Его собственные hosted checks ещё требуются; ledger он не увеличивает:

- AUD-148/149/150: lexical-scope/async inventory и маскирование Go comments/literals; root 124 PASS и actual duplicate scan 1021 Python / 181 Go файлов без ошибок.
- Owner/lease и runtime ports: 22 ordinary Windows PASS; отдельно 134 native Linux PASS с реальной файловой блокировкой. Supplementary Linux harness использует --noconftest и отключённую автозагрузку plugins, поэтому не заменяет штатный CI. Docker reader в handoff-тестах контролируется mock; runtime/CLI/outage не активированы.
- AUD-152/153: stale-only remount refresh и typed error fallback без записи устаревших данных как свежих; допустимая null-температура сохранена. Root 115 PASS в пяти полных weather suites.
- AUD-142/143: код погоды 97 отображается как storm; MapSidebar обновляет общий статус открытия от существующего minute clock. Root 26 PASS в трёх полных suites, включая обе границы времени и освобождение timers.
- AUD-163: ASGI custom header names нормализованы в lowercase; root 77 PASS в трёх полных exception-handler suites.
- AUD-137/147: localized metadata oracle и единое владение root/page SEO, включая actual RouterProvider SSR/hydrateRoot и отложенную Activity. Root 93 PASS в семи полных suites. Native Playwright collection выявил ESM JSON-import blocker; после добавления import attributes полный Node contract-набор проходит 241/241, actual collection — 220 full / 40 smoke в пяти выбранных файлах. Actual browser proof пока отсутствует.
- AUD-174: подготовлен prehydration/Caddy log probe с pinned ownership, deadline, bounded log/marker reads и incremental os.scandir с cap 512. Root scan-bound controls: 3 PASS. Root full run пяти полных stand/preflight/pipe/scan/identity suites: 2015 PASS / zero SKIP. Windows identity использует birthtime, POSIX сохраняет ctime; все descriptor/path comparisons сохранены. Причина прежнего Windows ctime расхождения не установлена. Успешная runtime-приёмка не заявляется.

Новый опубликованный checkpoint — 7e87d45b3d71e0c6b224697bda6faa52d55d3d6f, [Matrix 39439653743](https://github.com/egorribun/university_ecosystem/actions/runs/39439653743). Оба pre-commit и actual baseline integrity проходят. Шесть независимых expected ComposeResourceEvidence fixtures не учитывают service_mounts; inventory требует явного пояснения parent-bound intentional sleep. Обе причины локально исправлены: независимые fixtures сохраняют полную equality и новый changed-mount control, bound comment описывает реальный one-second parent timeout. Root transport/inventory/shard/allocation: 286 PASS / zero SKIP; полный inventory проходит. Producer и проверки mounts не ослабляются. Focused backend 831 PASS / один прежний outage hold, 218,50 s. Frontend shards 2/3 успешны; shards 1/4 выявили по одному устаревшему timer/SEO contract assertion. Обе причины локально исправлены тестами с точными clock/metadata assertions; root 34 PASS, production не изменён. Некоторые backend jobs ещё идут; полный CI не принят.

## Следующие действия

Текущий опубликованный source — 8c994b24505fa74ba3ae46d4e91b33457dea2af0, [Matrix 39445887682](https://github.com/egorribun/university_ecosystem/actions/runs/39445887682). Полный локальный preflight: 10/10 PASS / 88,282 s. Hosted Contract Tests, inventory, baseline integrity, frontend lint и shards 1/2 проходят; остальные jobs ещё идут. Focused backend: 831 PASS / один прежний outage hold / 229,89 s. Завершившийся старый shard 2 выявил также три alias/resolved-path assertions и два raw-header assertions; их тестовые исправления проходят 1963 ordinary stand cases, supplementary native Linux 3/3 и root 118 cases. Production guards, deadlines и skips сохранены. Actual PostgreSQL проверил пять SQL/decoder операций приватного NATS-кандидата, read-only/search_path и неизменность данных; cleanup подтверждён. Это не Core/outage acceptance; ledger остаётся 147/512.

1. Опубликовать следующий небольшой пакет Linux-reader и ASGI-header test corrections после финальных hooks/scanner. Предыдущие CI fixtures/JUnit, AUD-158/159 и Fluent Bit corrections уже опубликованы в 8c994b245; собственная hosted приёмка продолжается.
2. Принять собственные hosted checks нового source; каждый новый SHA требует своей проверки. Actual prehydration/Caddy runtime и SEO browser acceptance выполнять только после guarded admission.
3. Продолжить guarded NATS adapters и actual runtime/outage acceptance по [spec](../specs/2026-10-18-owned-nats-outbox-acceptance.md), [outage plan](2026-10-19-owned-nats-outage.md) и [Docker observation](2026-10-20-owned-nats-docker-observation.md). Metadata и supplied-result tests не доказывают daemon authenticity, actual inventory или restoration; outage остаётся выключенным.
4. Закрывать оставшиеся исходные AUD IDs с именованными доказательствами. P1 operational holds AUD-164/167/169/174 сохраняются. AUD-123: root actual Fluent Bit RED/GREEN подтверждает исправление app/component accessors; synthetic HTTP sink проверяет Loki stream labels, а не Kubernetes API enrichment или cluster rollout. Owned containers/network очищены; собственные hosted checks исправленного source ещё требуются. Actual browser/визуальную приёмку отделять от unit/contract evidence.

Тематические планы: [UI lifecycle](2026-10-19-ui-lifecycle-reconciliation.md), [cleanup/timing](2026-10-20-runtime-cleanup-timing.md), [quality entrypoints](2026-10-20-quality-entrypoints.md). История принятых исправлений, включая snapshot/Helm/CI allocation и нормализацию locale, сохранена в audit supplements и Git; STATUS содержит текущий срез.

## Неизменные границы

Baseline — 319 identities; интегрированные dispositions — 264, включая singleton, утверждённый 2026-10-20. Все 78 required context/app pairs, blocking CodeQL, hooks и finite131 migration exception до 2026-11-13 сохраняются. Прежние exact approvals не разрешают изменённые/unmatched findings или перенос категорий.

Q1/Q4 source migration действует; глобальный mutation score не повышается ради MVP. Q2/Q3 — v1.1. Новые suppressions, pragmas, broad exclusions, skips, expiry extensions и снижение floors не разрешены.

Перед тяжёлым прогоном: RAM ≤75% / free ≥8 GiB; остановка при RAM ≥85% / free <4 GiB. Отдельное исключение для одиночных Linux screenshot-прогонов: ≤80% / ≥6 GiB, container ≤1 GiB / 2 CPU. Удалять только доказанно принадлежащие работе ресурсы; чужие процессы и prune не трогать.

Manifest source_sha остаётся null. Actual RC, main/bootstrap activation, pre-merge full smoke, визуальная приёмка следующих пакетов и deployment — отдельные этапы. Home12 ранее утверждён только в своём exact scope. Merge/deploy и NATS outage не выполнены.
