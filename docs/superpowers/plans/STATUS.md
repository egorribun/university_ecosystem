# MVP — оперативный статус

Контрольная точка: 2026-10-11 22:19 UTC (2026-10-12 по местному времени). Основания приёмки — [мастер-план](MVP_MASTER_PLAN.md),
[ТЗ](University_Ecosystem_MVP.md), [ADR-047](../../adr/ADR-047-risk-based-quality-policy.md)
и [audit ledger](../../audits/INDEX.md). Выпуск `v1.0.0` пока не подтверждён.

## Source и проверки

- Работа остаётся на `egorribun`, в одном checkout и [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306); Root управляет Git.
- Проверенный опубликованный base: `e9a6bd18cfa9d8f722f7a3818496820e96994729`,
  tree `afc940057a33b7d57b6af9d43ad655351e27b719`. Hosted exact check дал 76/76
  SUCCESS по ruleset `8335285` 2026-10-11 в 20:38 UTC;
  [Matrix CI Success](https://github.com/egorribun/university_ecosystem/actions/runs/38169847107/job/114568316530).
  CodeQL alert 3384 исправлен на этом base.
- После base Root интегрировал 23 файла: Auth V5, Story V2, PWA/parser V3,
  Layout V1 и visual V7.1. Локально PASS: 237 Node contracts, 31 Vitest test,
  полный TypeScript и frontend lint с 0 warnings, Prettier, Ruff и `git diff --check`.
  Для этих 23 точных пар файлов AST comparison подтвердил сохранение семантики
  после форматирования; compiler/bundler directives отдельно сверены.
  Scoped parser selection ранее дал 169/169; это не полный backend suite.
  Commit/hooks, новый hosted CI и live acceptance для delta ещё предстоят;
  предыдущие 76 hosted checks относятся только к опубликованному base.
- Q1/Q4 и только ранее разрешённые 14+1 context removals сохранены; прочие правила
  и required contexts остаются. CodeQL blocking, Semgrep — в pre-commit; quality floors
  и Tier 0 100% не снижались.

## Core и визуальная диагностика

- Core на base e9 использовал state `C:\Temp\ue-live-acceptance\run-aab8247c-7d28-4403-a533-d6b5842455ea`,
  project `ue-live-d31e8615676cc711`, signed schema 11 / 23 services. Up, admin-only seed,
  demo seed, readiness и cookie policy прошли. Штатно остановлен в 21:43Z:
  23 containers, 0 running, данные сохранены; owned browser и network удалены.
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
   review и ADR-006 ordering. Перейти к frozen RC только после acceptance выше.

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
