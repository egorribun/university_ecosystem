# Статус выпуска MVP v1.0.0

Обновлено: 2026-10-14 UTC. Действующий порядок и критерии — [MVP_MASTER_PLAN.md](MVP_MASTER_PLAN.md), продукт — [ТЗ MVP](University_Ecosystem_MVP.md), качество — [ADR-047](../../adr/ADR-047-risk-based-quality-policy.md).

## Источник и hosted CI

- PR #1306 остаётся на ветке `egorribun`. Текущий HEAD задают Git и PR; последний проверенный hosted source — `c1a0d1b0`, tree `6b32c866`.
- Hosted run `38520159099`: все 4 backend shards, backend aggregate, integration, migrations, Python security и CodeQL прошли. Все 4 frontend shards и WASM contract завершились неуспешно; coverage gate пропущен (SKIPPED), не считается PASS. Это не зелёный PR.
- Наблюдаемый промежуток выполнения backend shards при `max-parallel=2` — 38:44 (06:19:59–06:58:43 UTC); самый длинный shard — 19:50. Это отдельные измерения, а не вычисленный critical path всего pipeline. Целевой PR-бюджет 15 минут не достигнут.
- Сохраняются 78 required contexts и blocking CodeQL `code_scanning`; Semgrep остаётся в pre-commit. Новый source требует собственных актуальных required-check результатов.

## Локально проверенные результаты

- Q4 cleanup ограничен 35 точными чистыми parser functions. Повторные 228 cases сократились с 24,795 до 1,685 s; lifecycle/isolation — 95 PASS / 2 прежних subprocess-only skips. Session preparation, task scan/cancel/await, четыре shard, `max-parallel=2`, assertions и resource gates сохранены. Это ускорение не закрывает 15-минутный бюджет.
- На C1 native CSP/Worker проверка дала 20 PASS после ограниченного ожидания paint timestamps. AUD174 с обычным Enter отправил 1 native POST; query и canary — 0, проверки прошли. Причина перехвата мышиного клика остаётся неустановленной, UX этим результатом не подтверждён.
- Focused8 дал 24 PASS / 10 FAIL / 6 утверждённых skips и не является приёмкой.
- Рабочий frontend пакет: 8966/8966 PASS, без skips; все шесть изменённых production-файлов имеют 100% lines/statements/branches/functions. Полные TypeScript, ESLint и форматирование PASS. Исправлены преждевременная публикация профиля, remount дерева, три concurrency-регрессии и утечка языкового маркера между тестами; реальный known-owner refetch проверен через QueryClient/MSW. Это локальные результаты, свежие hosted checks и browser acceptance ещё нужны.
- Для anonymous `null→null` без ротации nonce ограниченный статический разбор текущего потока не выявил достижимой поздней положительной записи профиля. Это не заменяет final-RC auth/browser security review.

## Политика и сохранность

- Действуют ровно 135 owner-approved exact secret dispositions; baseline остаётся на 319 identities. Не добавлять identities, baseline entries, pragmas или broad exclusions.
- Finite131 привязан к 131 неизменённому migration blob из base `ac74e915` до 2026-11-13. Все touched/new/unmatched migrations и остальные Tier 0 сохраняют 100%; app и patch floors не снижены. Quality contract tests: 423 PASS / 1 прежний Windows skip.
- SeaweedFS 4.47 TUS V7 прошёл scoped component probe: ownership denials, create/complete/cancel, deleted-resource check, offset и payload readback. Реальные app multipart/S3 upload и readback всё ещё требуются на свежем Core.
- Core C1 остановлен: сохранены 23 контейнера и 6 volumes; активных Docker stands нет. Ранее остановленные Core 532 и failed Core 81, их state/backups и 12 named volumes остаются сохранены. Full E2E source 532 был диагностическим и не считается приёмкой.

## Оставшиеся gates

1. Завершить обычные hooks и tracked-secrets scan, затем commit/push текущего проверенного пакета. На опубликованном SHA дождаться свежих 78 contexts, CodeQL и hosted coverage.
2. На новом UUID Core с опубликованным source выполнить native CSP/Worker и focused product checks, затем два последовательных полных запуска 59 live specs. После первого запуска создать avatar canary и row baseline, сделать paired DB/S3 snapshot, остановить и поднять тот же Core, сравнить persistence и прочитать исходный объект до reseed. Восстановить данные в отдельные DB/bucket/prefix и проверить объект через восстановленную DB reference до второго запуска.
3. Выполнить risk/a11y/reduced-motion checks; снять News/Events/Schedule — 36 Linux captures RU/EN, light/dark, 390/768/1440 и risk 360/1024. Единственное утверждённое визуальное решение Home12 — `ddbbc84d`. Новые baselines разрешены только после решения владельца; затем serial Lighthouse 7 routes × 3.
4. Перед final RC повторно проверить все 63 platform IDs, [October audit](../../audits/AUDIT-2026-10.md) и [dependency report](../../audits/dependency-updates-2026-10/README.md), отсутствие P0/P1, frozen-RC full smoke, ordinary merge и resulting-main checks, шесть GHCR images существующим producer, tag/release v1.0.0.

## Ресурсы и scope

Root владеет Git и runtime; максимум три GPT-6 Luna Max работают в непересекающихся областях. Тяжёлый локальный процесс один. Admission RAM ≤75% / free ≥8 GiB, stop ≥85% / free <4 GiB; serial Linux screenshots допускают ≤80% / ≥6 GiB при cap 1 GiB / 2 CPU. Lighthouse сохраняет 75% / 8 GiB и cap 2 GiB / 2 CPU. Чужие процессы, env, volumes, история Git/миграций и private rescue bundle сохраняются. Q2/Q3, global mutation, kind certification, три comparable CI и RPO/RTO остаются в v1.1.