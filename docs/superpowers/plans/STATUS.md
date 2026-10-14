# Статус выпуска MVP v1.0.0

Обновлено: 2026-10-14 UTC. Действующий порядок и критерии — [MVP_MASTER_PLAN.md](MVP_MASTER_PLAN.md), продукт — [ТЗ MVP](University_Ecosystem_MVP.md), качество — [ADR-047](../../adr/ADR-047-risk-based-quality-policy.md).

## Source и CI

- Один checkout, ветка `egorribun`, существующий [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306). Текущий HEAD задают Git и PR; последний проверенный hosted snapshot — 81b40d7b.
- Snapshot 81: 106 SUCCESS, 26 SKIPPED, 4 FAILURE. Failed backend shards 1/3, зависимый CI Success и advisory Owned Live Acceptance; quality aggregate SKIPPED. CodeQL и остальные security checks прошли. Advisory smoke остановился на PWA glob до браузера и не является продуктовой приёмкой.
- Действуют 78 required contexts и blocking CodeQL `code_scanning`. Q1/Q4 source migration внедрена; Semgrep остаётся в pre-commit. Каждый новый source требует собственных required-check results.
- Бюджет PR 15 минут остаётся OPEN: backend pytest steps snapshot 81 дали critical path 35:10 при max-parallel 2. Локальное ускорение не закрывает этот критерий.

## Локально проверенный пакет

- Три backend CI fixture regressions: 51 PASS. Finite131 и production validators не ослаблены; historical-reference negative controls сохранены.
- PWA glob сохраняет прежние восемь расширений и включает WOFF2; существующий Node live-contract suite — 211 PASS.
- Q4 cleanup ограничена 35 точными чистыми parser functions. Следующие одинаковые 228 cases: 24,795 → 1,685 s; lifecycle/isolation — 95 PASS / 2 прежних subprocess-only skips. Session preparation, task scan/cancel/await, shards, max-parallel, assertions и resource gates сохранены.
- Auth: функциональный React updater выполняет только преобразование данных; committed state управляет query/cache ownership и записью профиля. Исправлены rebase-публикация и потеря очистки storage при coalesced local/remote logout. Авторитетный локальный logout очищает storage до broadcast; remote persist:false не пишет storage.
- Auth regression suite: 749/749 PASS. У трёх изменённых production-файлов 100% line/statement/branch/function coverage. Полные frontend lint, TypeScript и форматирование текущего пакета PASS; обычные hooks и проверки опубликованного source ещё нужны.
- RED/GREEN подтвердил и исправил запаздывающую запись при смене shared generation: async persistence теперь проверяет captured session epoch. Случай anonymous null→null без смены nonce остаётся OPEN; новая проверка его не закрывает. Результат локальных auth tests не означает завершение независимой final-RC security/browser acceptance.

## Политика и сохранность

- Ровно 135 owner-approved exact secret dispositions; baseline 319 неизменна. Новые identities, baseline entries, pragmas и broad exclusions не разрешены.
- Finite131: source-bound no-decrease baseline ровно для 131 неизменённых migration blobs base ac74e915 до 2026-11-13. Все touched/new/unmatched migrations и остальные Tier 0 сохраняют 100%. Канонический quality suite — 423 PASS / 1 прежний Windows skip.
- SeaweedFS 4.47 TUS component probe V7 прошёл: ownership denials, create/complete/cancel, deleted-resource check, offset и payload readback. Это scoped component evidence; реальный app multipart/S3 upload и readback ещё нужны на свежем Core.
- Удалены только подтверждённые owned ресурсы: 46 остановленных контейнеров и 6 сетей двух старых Core проектов, а также временные SeaweedFS probe resources. Сохранены 12 named volumes, state, bind data, backups, Core 532 и failed Core 81.
- Full E2E source 532 был прерван как диагностика; это не acceptance. Для следующего Core нужен новый UUID и чистый опубликованный source.

## Оставшиеся gates

1. Завершить текущий ограниченный auth пакет, ordinary hooks и tracked-secrets scan; commit/push и свежие 78 contexts, CodeQL и hosted coverage.
2. На новом Core: native CSP/Worker и focused product checks, затем два последовательных полных прогона 59 live specs. Между ними создать avatar canary, снять row baseline, выполнить paired DB/S3 snapshot, stop/up того же Core, persistence comparison и source-object readback до reseed; восстановить в отдельные DB/bucket/prefix и прочитать объект по восстановленной DB reference до второго полного прогона.
3. Risk/a11y/reduced-motion checks; News/Events/Schedule — 36 Linux captures RU/EN, light/dark, 390/768/1440 и risk 360/1024. Утверждён только Home12 ddbbc84d. Новые baselines — после визуального решения владельца; затем serial Lighthouse 7 routes × 3.
4. Final-RC revalidation всех 63 platform IDs, [October audit](../../audits/AUDIT-2026-10.md) и [dependency report](../../audits/dependency-updates-2026-10/README.md); отсутствие открытых P0/P1, frozen-RC full smoke, ordinary merge, resulting-main checks, шесть GHCR images существующим producer, tag/release v1.0.0.

## Ресурсы

Root владеет Git и runtime; максимум три GPT-6 Luna Max работают в непересекающихся областях. Тяжёлый локальный процесс один. Admission RAM ≤75% / free ≥8 GiB, stop ≥85% / free <4 GiB; только serial Linux screenshots допускают ≤80% / ≥6 GiB при cap 1 GiB / 2 CPU. Lighthouse сохраняет 75% / 8 GiB и cap 2 GiB / 2 CPU. Чужие процессы, env, volumes, история Git/миграций и private rescue bundle сохраняются. Q2/Q3, global mutation, kind certification, три comparable CI и RPO/RTO — v1.1.
