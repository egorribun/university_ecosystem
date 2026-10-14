# Статус выпуска MVP v1.0.0

Обновлено: 2026-10-14 (UTC / Europe/Istanbul). Действующий план —
[MVP_MASTER_PLAN.md](MVP_MASTER_PLAN.md), редакция 8; продукт —
[ТЗ MVP](University_Ecosystem_MVP.md), качество —
[ADR-047](../../adr/ADR-047-risk-based-quality-policy.md).

## Source и CI

- Один checkout, ветка egorribun, существующий
  [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306).
  Текущий head задают Git и PR; последний завершённый hosted snapshot —
  532ea7d1, main — ac74e915.
- Этот snapshot: 111 SUCCESS, 23 SKIPPED, 2 FAILURE. Не прошли
  Coverage & Quality Policy Gate и зависимый CI Success; CodeQL и advisory
  Owned live acceptance прошли. Общая coverage остановилась на пороге 100%.
  Advisory smoke не заменяет полные 59 live specs.
- Действуют 78 required contexts и blocking CodeQL code_scanning.
  Q1/Q4 source migration внедрена; Semgrep остаётся в pre-commit.
  Новый source требует собственных hosted checks. Бюджет PR 15 минут открыт.

## Проверенные локальные исправления

- Backend application: 241 PASS и отдельные 61 PASS. Диагностические прогоны
  выполнили все 54 ранее недостававшие строки и 33 branch arcs приложения.
  Это targeted evidence; свежий обязательный aggregate остаётся необходимым.
- Миграции: required-table preflight db31 отклоняет неполную схему до DDL.
  Реальный PostgreSQL RED воспроизвёл прежний сбой на отсутствующей users;
  GREEN — 77 unit и 6 исторических PostgreSQL checks. Добавленные empty/zero
  sequence cases проверяют порядок запросов и setval; весь guard suite — 38 PASS.
  У всех девяти затронутых миграций 100% line/branch в диагностическом union.
  Перед повторным измерением двух изменённых файлов старые данные удалены.
- CI migration producer дополняет прежний round-trip тремя unit и тремя
  PostgreSQL suites до записи provenance. Обвязка pytest использует SQLite
  в памяти; реальные PG suites сохраняют собственные capped containers.
  Все шесть suites одним процессом — 81 PASS; workflow contracts — 181 PASS.
  Hosted producer и aggregate нового source ещё нужны.
- Frontend: 67 Vitest, 21 Node checks, TypeScript, ESLint и production build PASS.
  RootShell, htmlText и MapLibre loader имеют 100% измеренных метрик.
  Main entrypoint проверен поведением и исключён прежней coverage policy.
  Precache: 195 файлов / 4 269 211 bytes; все 9 CSS-referenced WOFF2 включены.
  CSP/Trusted Types, Worker, SSR и offline fixes требуют свежего native Core.
- Q4 cleanup ограничена 13 точными чистыми parser functions.
  Те же 576 cases: 63,24 → 2,23 s; следующие 256: 26,24 → 1,50 s.
  Task scan/cancel/await и session preparation сохраняются.
  Lifecycle/isolation плюс прежние 576 cases: 603 PASS / 2 штатных
  subprocess-only skip. Shards/max-parallel, assertions и resource gates сохранены;
  Для следующих девяти функций те же 291 cases: 30,05 → 1,64 s;
  lifecycle/isolation — 45 PASS / 2 штатных subprocess-only skip.
  Точные populations сверены; независимое ревью PASS. Локальное ускорение
  не закрывает hosted critical-path budget.
- Принятые auth/session, media ownership, outbox, timezone/schedule, proxy,
  Gateway/WS, Go race/lint/coverage, WASM и dependency fixes сохраняются.
  Local checks прежних пакетов не подменяют final-source acceptance.

## Политика качества

- Активны ровно 135 owner-approved secret dispositions; baseline319 неизменна.
  Новые identities, baseline entries, inline pragmas и broad exclusions
  без отдельного решения не разрешены.
- Владелец 2026-10-14 UTC утвердил finite131: no-decrease baseline ровно
  для 131 неизменённого migration blob base ac74e915 до 2026-11-13.
  Точный пакет V8 применён; все четыре canonical quality modules —
  423 PASS / 1 штатный Windows skip. Затронутые/new/unmatched migrations
  и остальные Tier 0 сохраняют 100%; Q3 остаётся v1.1.
- Отдельно утверждены и применены ровно 17 public-integrity identities:
  15 в coverage contract и 2 в validator, reviewed_on 2026-10-14,
  expiry 2027-01-10. Прежние 118 records сохранены без изменений.
  Полный tracked scan PASS: 409 findings, 110 exact approved matches,
  baseline319 неизменна. Обычные hooks и hosted checks нового source ещё нужны.

## Core, audit и зависимости

- Full E2E 532 прерван как диагностический после каскада ошибок; он не acceptance.
  Core остановлен, данные сохранены. Новому source нужен новый run UUID.
  Unsafe-eval и исходный ambiguous registration request требуют browser evidence;
  тихий drain и rate-limit/deadline guards не ослаблены.
- [October audit](../../audits/AUDIT-2026-10.md) и
  [dependency report](../../audits/dependency-updates-2026-10/README.md) остаются в scope.
  Все 63 platform IDs требуют final-RC классификации; blanket CLOSED запрещён.
  AUD-497 updater side effects проверяются отдельно приватно, исправление не принято.
  Уже согласованные P2 dispositions AUD-100/134/236 сохраняются в audit index.
- Caddy 2.11.7, Redis 7.4.11, Imgproxy 4.0.17 и другие принятые обновления
  имеют scoped checks; runtime/app-endpoint proof ещё нужен.
  SeaweedFS TUS metadata/source discrepancy остаётся открытым.

## Ближайшие шаги

1. Завершить полный скан и обычные hooks, затем commit/push текущего пакета.
   Проверить 78 contexts и CodeQL нового head.
2. На чистом опубликованном source поднять один Core с новым UUID; проверить
   focused browser failures, затем два полных прогона 59 live specs.
   Между ними: seed, paired DB/S3 snapshot/restore с avatar canary, stop/start
   того же frozen Core, persistence comparison до reseed и чтение restored object
   по DB reference. Old Core data не перезаписывать.
3. Risk/a11y/reduced-motion checks; News/Events/Schedule — 36 captures
   RU/EN, light/dark, 390/768/1440; 360/1024 risk. Утверждён только Home12 ddbbc84d.
   Новые visual baselines сохранять после приёмки; Lighthouse — 7 routes × 3.
4. Final-source security/data review, 63 audit IDs и remaining dependencies;
   frozen RC, full smoke, ordinary merge, resulting-main checks,
   producer ровно шести images, tag/release v1.0.0.

## Ресурсы и сохранность

Root владеет Git; три GPT-6 Luna Max ведут disjoint private tasks/review.
Тяжёлый локальный процесс один. Admission RAM ≤75% / free ≥8 GiB;
runtime stop ≥85% / <4 GiB. Только serial Linux screenshots: ≤80% / ≥6 GiB,
browser ≤1 GiB / 2 CPU. Удалять только доказанно owned resources;
Core data, backups, чужие env/volumes, Git/migration history и rescue bundle сохраняются.
Q2/Q3, global mutation, kind certification, три comparable CI и RPO/RTO — v1.1.
