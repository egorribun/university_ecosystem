# MVP — оперативный статус

Контрольная точка: 2026-10-12 02:04 UTC (2026-10-12 по местному времени). Основания приёмки — [мастер-план](MVP_MASTER_PLAN.md),
[ТЗ](University_Ecosystem_MVP.md), [ADR-047](../../adr/ADR-047-risk-based-quality-policy.md)
и [audit ledger](../../audits/INDEX.md). Выпуск `v1.0.0` пока не подтверждён.
Сводка зафиксирована перед публикацией следующего пакета исправлений.

## Source и проверки

- Работа остаётся на `egorribun`, в одном checkout и [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306); Root управляет Git.
- Последний source, к которому относятся hosted-результаты: `f3f99a991e800edcc2881bdfe8b76f5512e38656`,
  tree `a3d71663452845d6d653bfa60121f92574ab2768`. Точный join 76 пар
  context/integration_id по active ruleset `8335285`: 71 SUCCESS, 2 FAILURE,
  3 SKIPPED, 0 pending/absent. В [backend shard 3](https://github.com/egorribun/university_ecosystem/actions/runs/38184697747/job/114609206805)
  3224 PASS / 1 FAIL / 42 SKIP: WebSocket test double не имел `app`.
  Второй failure — зависимый `CI Success`; это одна установленная причина,
  исправление которой ещё требует свежего CI. Старые 76/76 SUCCESS не заменяют новый source.
- На f3 обычные commit/push hooks прошли. Интегрированы проверка актуального `is_active`
  под User row lock до INSERT/commit/JWT/Redis и отдельный Dishka REQUEST scope
  с per-frame SpiceDB-проверкой privileged `get_online`; отказ/недоступность закрывает доступ.
  Focused auth/session selection: 127 PASS. SQLite committed-state regression
  не доказывает PostgreSQL lock scheduling; это не полный backend suite.
- Следующий пакет от f3 содержит 41 code/test/config файл и этот STATUS.
  Исправлены WebSocket test double, DND wall-clock contract и forward migration,
  ожидание существующего PWA controller activation и Story overlay readiness.
  Registration admission сериализует реальные UI submits в пределах действующего
  production rate limit и прежних test deadlines; лимиты, retries и assertions не снижены.
  Contract child project воспроизводит ESM package boundary реального frontend.
- Локально для соответствующих неизменных файлов пакета PASS: полный TypeScript;
  202 Node contracts (0 FAIL/SKIP/cancelled/todo); 18 overlay Vitest tests;
  полный frontend lint (0 errors/warnings); Prettier; Ruff check/format и `git diff --check`.
  Backend focused selection: 33 PASS. Более широкий policy/live-stand selection дал
  1691 PASS / 2 FAIL; обе ошибки новых Story parser fixtures исправлены, затем
  соответствующий focused selection дал 9 PASS. Это не повторный полный 1693-test run.
  Scoped mypy двух DND source files: 0 errors, с предупреждениями о неиспользованных
  config sections; полный zero-warning mypy этим не подтверждён.
  После финального форматирования helper AST/comments и JSON content совпали.
  Для пакета нужны ordinary commit/push hooks, новые required checks и live acceptance.
- На f3 quiet-hours `PUT /users/me` вернул HTTP 500 в обоих проектах.
  Trace подтвердил `NoneType.utcoffset` в asyncpg TIMETZ codec.
  Исправление хранит naive local wall-clock отдельно от IANA timezone и сохраняет
  local clock, microseconds и NULL при forward migration; offset-aware DTO отвергается.
  Реальная изолированная PostgreSQL/asyncpg regression: 9 PASS, 0 FAIL/SKIP, pytest exit 0.
  Общий первый test guard не подтвердил cleanup из-за ошибки оператора;
  отдельная reconciliation PASS удалила только его остановленный test container
  и связанный env-file. Эти два evidence не подменяют свежий HTTP 200 через profile API.
- CodeQL на f3 SUCCESS: пять analyses относятся к PR synthetic merge `e5047bc8`,
  не к main. Новых alerts не обнаружено; в проверенном PR ref open alerts: 0.
  У 3384 latest instance fixed на `07742145`, но top-level state API не возвращает;
  3382/3383 — прежние отдельно разрешённые false-positive dismissals.
- Q1/Q4 и только ранее разрешённые 14+1 context removals сохранены; прочие правила
  и required contexts остаются. CodeQL blocking, Semgrep — в pre-commit; quality floors
  и Tier 0 100% не снижались.

## Core и визуальная диагностика

- Core f3: state `C:\Temp\ue-live-acceptance\run-8cc6cab1-9ae6-4c15-ab96-5592853be822`,
  project `ue-live-813b128d3326b281`, signed schema 11 / 23 services.
  Up, seed и readiness/cookie probes прошли. В 00:58Z штатно остановлены все 23
  containers, 0 running; шесть data volumes сохранены, owned builder остановлен.
- Targeted cohort 32 на f3: G1 8 PASS / 4 FAIL, G2 0 PASS / 14 FAIL,
  G3 0 PASS / 6 FAIL; без skips, flakes, interruption или source drift.
  Это диагностика, не продуктовая приёмка. Отдельные native permission cases:
  4 PASS; subscription и delivery этим не подтверждены.
- С принадлежащим работе browser cache два Story tests дошли до strict cycle-0
  DOM comparison и упали. Lazy global overlay effects — проверяемая гипотеза,
  ещё не доказанная live-прогоном текущего readiness fix. Все 20 cycles, точное
  DOM equality, heap floor и hidden-tab assertions сохранены.
- News V7 на прежнем source: 12 гидратированных вариантов, DOM=10, paint=0,
  PNG=0, layout/opacity=0; четыре aborted avatar requests на 1440px.
  Новый Layout fix ещё требует fresh-source screenshots. Пакет News не утверждён.

## Следующие критерии MVP

1. Пройти ordinary commit/push hooks и свежие 76 required checks; поднять новый Core
   на опубликованном чистом source. Пройти targeted cohort 32, проверить DND HTTP 200,
   Story/PWA, первый paint News и оставшиеся реальные сбои. PASS между SHA не переносить.
2. На неизменном source пройти два последовательных full Core runs: каждый 198 tests,
   190 PASS и ровно 8 ожидаемых SKIP. Завершить seed persistence через stop/start.
   Каждое применимое требование ТЗ 2–13 связать со сценарием/результатом/SHA либо
   обоснованной ручной проверкой; пройти mocked Firefox/WebKit/mobile-WebKit lane.
3. Завершить visual acceptance News, Events и Schedule: 36 изображений (12 на раздел),
   RU/EN, light/dark, 390/768/1440. Утверждён только Home пакет `ddbbc84d`;
   новые pixels требуют отдельного owner approval до обновления Linux baselines.
   Проверить 360/1024 risk cases, accessibility/reduced motion/axe.
   Main JS budget <500 KB и key-route Lighthouse pass — отдельные gates;
   authenticated LHCI остаётся 21 sample (7 routes × 3).
4. Провести один согласованный paired DB/S3 backup/restore в изолированные цели;
   прочитать объект по restored DB reference, проверить bytes/hashes и сохранность исходной среды.
5. Закрыть final-source SEC-07 и RUST-P3-03 evidence, независимый auth/session/data
   review и ADR-006 ordering: tombstone/WebSocket revocation до commit,
   rollback sibling logout. Переклассифицировать все 63 audit IDs на RC,
   не оставлять P0/P1 security открытыми. Исторические 60 CLOSED / 2 DECLINED /
   1 OPEN не являются RC dispositions. Bounded SEC-07 review на `829a1e78`
   не выявил конкретного дефекта; это не runtime/final-source приёмка.
6. Заморозить code/dependencies/config/docs и пройти финальные Core scenarios,
   backup/restore и full smoke на RC. Новое поведение после freeze требует
   нового кандидата и повторения затронутой приёмки.

SEC-03 historical source review CLOSED: владелец подтвердил только ephemeral CI/demo use;
это само по себе не указывает на необходимость production rotation. Перед любой migration
сохраняемых подписанных записей нужны protected consistent backup и read-only inventory;
учесть оба DataAccessLog legacy verifiers и hash-linked/nullable StoredEvent rows, выполнять
migration атомарно и fail closed. См. [audit ledger](../../audits/INDEX.md#findings-ledger).

После frozen RC: ordinary merge и свежие resulting-main push checks согласно
`quality/release-required-checks.json`. Готовый producer должен опубликовать ровно
шесть images (backend/frontend/gateway/ws-hub/file-processor/caddy) с Trivy,
signatures, SBOM/provenance и WASM parity. Проверить actual published digests
и связь с source/run/attempt manifest; затем tag/release notes `v1.0.0`.
Kind certification, три comparable CI runs, RPO/RTO, Q2/Q3 и global mutation score остаются
в v1.1, но разовый paired restore обязателен для MVP. Бренд ГУУ — только внутреннее
синтетическое демо до отдельного решения о публичном использовании.

Ограничения ресурсов: перед одним heavy workload RAM≤75% и free≥8GiB; остановка при
RAM≥85% или free<4GiB. Исключение только для serial Linux screenshots: старт≤80%/≥6GiB,
browser≤1GiB/2CPU; guard остановки неизменен. Owned builder≤4GiB/2CPU/no swap.
Сохранять Core data и полезные caches; не очищать чужие процессы, Docker/WSL или global caches.
Git history, migrations и environment/data state сохранять; приватный rescue bundle держать отдельно.
Не восстанавливать superseded audits или одноразовые session prompts.
