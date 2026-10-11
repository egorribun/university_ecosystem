# MVP — оперативный статус

Контрольная точка: 2026-10-11 23:30 UTC (2026-10-12 по местному времени). Основания приёмки — [мастер-план](MVP_MASTER_PLAN.md),
[ТЗ](University_Ecosystem_MVP.md), [ADR-047](../../adr/ADR-047-risk-based-quality-policy.md)
и [audit ledger](../../audits/INDEX.md). Выпуск `v1.0.0` пока не подтверждён.

## Source и проверки

- Работа остаётся на `egorribun`, в одном checkout и [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306); Root управляет Git.
- Текущий опубликованный source: `829a1e78c75c3e0d472bf641d46da44d5d3423d9`,
  tree `40fab7f14608f33f00060ef0bb6cf6d4fbc3455a`. Точный join 76 пар
  context/integration_id по active ruleset `8335285`: 71 SUCCESS, 3 SKIPPED,
  2 FAILURE, 0 pending/absent. Единственный упавший test — Knip asset contract
  в [backend shard-1](https://github.com/egorribun/university_ecosystem/actions/runs/38180087575/job/114591525500)
  (3597 PASS / 1 FAIL / 12 SKIP); итоговый CI Success также failed.
  Предыдущие 76/76 SUCCESS на `e9a6bd18` не заменяют проверки нового source.
- На опубликованном source обычные commit/push hooks прошли. Интегрированы Auth V5, Story V2, PWA/parser V3,
  Layout V1 и visual V7.1. Локально PASS: 237 Node contracts, 31 Vitest test,
  полный TypeScript и frontend lint с 0 warnings, Prettier, Ruff и `git diff --check`.
  Для этих 23 точных пар файлов AST comparison подтвердил сохранение семантики
  после форматирования; compiler/bundler directives отдельно сверены.
  Scoped parser selection ранее дал 169/169; это не полный backend suite.
  Live acceptance этих изменений ещё предстоит.
- Следующая delta содержит десять code/test файлов: контракт распознаёт также точную
  `path.join`-форму того же локального axe-core asset; `get_online` проверяет
  SpiceDB через отдельный Dishka REQUEST scope на каждый privileged frame и
  fail closed при отказе/недоступности. Ping/read не требуют разрешения admin.
  Создание сессии под той же User row lock проверяет актуальную `is_active`
  наряду с `mfa_epoch`: отсутствующий/неактивный пользователь получает 401
  `credentials_invalid` до INSERT, commit, JWT и Redis. Это закрывает выпуск
  новой сессии из stale active DTO после деактивации/удаления.
  Регрессия дала ожидаемый RED до исправления и GREEN после; она проверяет
  committed state в SQLite, не PostgreSQL lock scheduling. Root focused pytest:
  127 PASS; Ruff: PASS. Независимая AST-сверка подтвердила сохранение семантики
  всех десяти файлов после форматирования. Для delta
  ещё нужны ordinary commit/push hooks и свежие 76 required checks.
- CodeQL check на source `829a1e78` SUCCESS; анализ привязан к PR synthetic merge
  `8f343a22`, не к main. В текущем PR ref open CodeQL alerts: 0. У 3384 latest
  instance fixed на `07742145`, но top-level state API не возвращает; 3382/3383
  остаются ранее разрешёнными false-positive dismissals.
- Q1/Q4 и только ранее разрешённые 14+1 context removals сохранены; прочие правила
  и required contexts остаются. CodeQL blocking, Semgrep — в pre-commit; quality floors
  и Tier 0 100% не снижались.

## Core и визуальная диагностика

- Core на `829a1e78` использовал state `C:\Temp\ue-live-acceptance\run-6633fbea-426f-4a85-b5c8-37867610a1f5`,
  project `ue-live-3069515eef291fe7`, signed schema 11 / 23 services. Up прошёл;
  backend healthy, без OOM/restarts. Перед новой source delta штатно остановлен
  в 22:54Z: 23 containers, 0 running, данные сохранены, owned builder остановлен.
  Seed, readiness/cookie probes и приёмка на этом source не запускались.
- Targeted cohort 32 на e9: 6 PASS / 26 FAIL; это диагностический результат,
  не продуктовая приёмка. News V7 получил 12 гидратированных вариантов; отчёт: layout/opacity=0,
  DOM=10, paint=0, PNG=0 и четыре aborted avatar requests на 1440px. Пакет не утверждён.

## Следующие критерии MVP

1. Пройти обычные commit/push hooks, получить свежие required checks и новый Core
   для опубликованного source. Повторить targeted cohort 32 и News12, проверить
   первый paint и диагностировать оставшиеся реальные сбои. Не переносить PASS между SHA.
2. На неизменном source пройти два последовательных full Core runs: каждый 198 тестов,
   190 PASS и ровно 8 ожидаемых SKIP. Завершить seed persistence через stop/start.
3. Завершить visual acceptance News, Events и Schedule: 36 изображений (12 на раздел),
   RU/EN, light/dark, 390/768/1440. Утверждён только Home пакет `ddbbc84d`;
   любые новые pixels требуют отдельного owner approval до обновления baselines.
   LHCI остаётся 21 sample (7 routes × 3).
4. Провести один согласованный paired DB/S3 backup/restore в изолированные цели;
   проверить чтение объекта через restored DB reference и сохранность исходной среды.
5. Закрыть final-source SEC-07 и RUST-P3-03 evidence, независимый auth/session/data
   review и ADR-006 ordering. Bounded SEC-07 source review на `829a1e78` не выявил
   конкретного дефекта; это не runtime/final-source приёмка. Перейти к frozen RC
   только после acceptance выше.

SEC-03 historical source review CLOSED: владелец подтвердил только ephemeral CI/demo use;
это само по себе не указывает на необходимость production rotation. Перед любой migration
сохраняемых подписанных записей нужны protected consistent backup и read-only inventory;
учесть оба DataAccessLog legacy verifiers и hash-linked/nullable StoredEvent rows, выполнять
migration атомарно и fail closed. См. [audit ledger](../../audits/INDEX.md#findings-ledger).

После frozen RC: ordinary merge, свежие main checks и ровно шесть source-bound images
с Trivy, signatures, SBOM/provenance и WASM parity; затем tag/release notes `v1.0.0`.
Kind certification, три comparable CI runs, RPO/RTO, Q2/Q3 и global mutation score остаются
в v1.1, но разовый paired restore обязателен для MVP.

Ограничения ресурсов: перед одним heavy workload RAM≤75% и free≥8GiB; остановка при
RAM≥85% или free<4GiB. Исключение только для serial Linux screenshots: старт≤80%/≥6GiB,
browser≤1GiB/2CPU; guard остановки неизменен. Owned builder≤4GiB/2CPU/no swap.
Сохранять Core data и полезные caches; не очищать чужие процессы, Docker/WSL или global caches.
Git history сохранять; приватный rescue bundle держать отдельно от рабочей области.
Не восстанавливать superseded audits или одноразовые session prompts.
