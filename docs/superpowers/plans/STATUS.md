# MVP — оперативный статус

Контрольная точка на 2026-10-11, 14:17 UTC.
[Мастер-план](MVP_MASTER_PLAN.md), [ТЗ](University_Ecosystem_MVP.md) и
[ADR-047](../../adr/ADR-047-risk-based-quality-policy.md) действуют.
Работа продолжается по поручению владельца; выпуск `v1.0.0` ещё не подтверждён.

## Границы работы

- Только `egorribun`, один checkout и [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306).
  Root владеет Git/интеграцией; до трёх GPT-6 Luna Max работают в непересекающихся областях.
- Q1/Q4 migration и разрешённые 14+1 removals выполнены. Ruleset `8335285`:
  76 required context/integration pairs; остальные правила сохранены.
  CodeQL blocking, Semgrep в pre-commit; Tier 0 и нынешние floors/100% patch сохраняются.
- Q2/Q3, global mutation score, comparable CI runs, kind certification,
  RPO/RTO и deployed BE-02/MIG-PASS — v1.1. Один paired DB/S3 restore нужен для MVP.
- ADR-006 сохраняет tombstone/WS revoke до commit и conservative sibling logout
  при rollback. ГУУ — внутреннее демо; данные синтетические.

## Завершённый hosted checkpoint

Последние завершённые результаты относятся к `d133559c3b55321ffc5b5be83a38e3daa9beb9cc`,
tree `401ca2fe501954a37b7b715327d5071d018f2482`.
PR открыт, non-draft; branch/origin/PR head совпадали при проверке 2026-10-11.

- [Matrix 38138706326](https://github.com/egorribun/university_ecosystem/actions/runs/38138706326)
  SUCCESS. Rollup136:113 SUCCESS/23 SKIPPED, failures/running0.
  Exact required join:76/76 SUCCESS, missing/duplicates0; все skips вне required set.
- Backend shard3 SUCCESS: семь прежних MFA stderr failures устранены.
  Integration shard0 SUCCESS; это whole-job proof, отдельный per-node JUnit не получен.
  BE-04 также проверен локально на isolated pgvector17 + Alembic head:1/1 PASS,
  real session identity, ORM attachment, commit/rollback/pool/close и row persistence.
- Свежий timing receipt: unit-start → aggregate38m21, lint-start → aggregate41m23.
  Pytest shards19m22/17m48/15m29/15m38; max-parallel2 даёт две очереди запуска.
  Цель CI≤15min остаётся открытой; условный cap4 не принят без доказанного headroom.
- Каждый successor SHA требует собственных hosted results; d133 не заменяет их.

## Принятый пакет изменений

- Settings сохраняет один route match при смене вкладки; клавиатурный фокус
  больше не теряется из-за pending UI. Прямой Sessions deep link сохраняет prefetch.
- Post-commit profile refresh отменяет старый in-flight `users/me` и сериализует
  запросы общего QueryClient. Session/identity guards и обработка ошибок сохранены.
  Два независимых avatar/cover callers больше не отменяют refresh друг друга.
- Outbox message handler явно обновляет sender вместе с profile даже при уже
  загруженном User. Регрессионный тест воспроизводит identity-map/noload случай
  и проверяет настоящее построение имени в group notification.
- Story fixture использует управляемый Chromium и CDP attachment с `noDefaults`,
  чтобы получить настоящий hidden-tab transition. Desktop/mobile project options,
  owned-origin/session cleanup и полная проверка teardown сохранены.
  Canonical hidden/20-cycle proof на этом пакете ещё не выполнен.
- Native permission/subscription specs используют тот же полный Chromium channel,
  что delivery fixture. Совпадение режима исправлено; причинность прежних failures
  и живой результат ещё требуют проверки.
- HTTP diagnostics добавляет только конечные labels и реальные integer statuses
  OTP/MFA. UI diagnostics измеряет bounded paint/opacity/animation и footer geometry;
  selectors, текст, IDs, endpoints и response bodies в протокол не входят.
- Локально: live contracts173/173; Settings route/sessions18+4 и profile9/9 PASS.
  Profile hook:100% lines/statements/branches/functions на focused coverage.
  Parser1490/1490 и chat helpers34/34 PASS; event-handler regressions66/66 PASS.
  TypeScript, frontend lint, Ruff/Prettier и diff check PASS.
  Новые проверки не заменяют canonical live acceptance или hosted gates.

## Core и ресурсы

- Fresh d133 Core `run-66d56e70-f16d-4a12-987d-a14503eebbc3`,
  project `ue-live-bc2bf9bb0b334dcb`, signed schema11/23 services:
  up, admin-only seed до demo seed, readiness14 healthchecks/4 initializers PASS.
  Effective cookie policy:Secure=false, development=true, strictHeaders=false.
- Раздельные targeted прогоны на d133: a11y/footer3 PASS/3 FAIL из6;
  affected cohort14 PASS/28 FAIL из42; native Push4 PASS/8 FAIL из12.
  Это диагностика, не full gate; результаты не складываются в один прогон.
- Core штатно остановлен13:24 UTC:23 containers stopped,6 mounted volumes,
  env и signed owner сохранены; source stable, owned children0.
  На successor SHA нужен новый уникальный state; strict resume не обходить.
- Исправлен private process guard: PID подтверждается вместе с временем рождения
  и текущей цепочкой родителей; cleanup действует только на доказанные owned handles.
  Прежнее число77 якобы оставшихся процессов было недостоверным; по нему ничего не удалено.
  Новые quality receipts используют ownership schema3, remaining children0.
- Один heavy workload: start RAM≤75%/free≥8GiB, stop≥85%/free<4GiB.
  Serial Linux screenshots: owner exception≤80%/≥6GiB, browser1GiB/2CPU.
  Owned builder stopped, cap4GiB/no swap/2CPU; полезный cache сохранён.
  Рабочий isolated Windows browser cache сохранён; одинаковые binary hashes
  не подтверждают гипотезу повреждения глобального cache.

## Открытые критерии и следующий порядок

1. Опубликовать reviewed пакет с ordinary hooks; получить новые76 required results.
   Fresh unique Core:admin-only seed перед demo seed, readiness/cookie policy,
   затем затронутые Stories/Settings/OTP/MFA/Push/a11y/footer scenarios.
2. Устранить оставшиеся Core failures и выполнить два consecutive full runs:
   198 total,190 PASS + exact8 expected SKIP. Последний исторический full на e537
   дал117 PASS/73 FAIL/8 SKIP; он не является текущим acceptance proof.
3. В V15 strict DOM baseline716 nodes/437 listeners после первого close стал670/435
   и далее не менялся все20 cycles; docs2. Heap plateau/hidden pause пройдены,
   exact-DOM не пройден; источник одноразового уменьшения46/2 не доказан.
   Canonical прежнего bd248 отдельно падал до DOM на hidden transition.
4. Full-page axe contrast и desktop footer geometry требуют новых измерений.
   Direct native Push дошёл до subscription/message200 и persisted in-app row,
   но native notification отсутствовала; provider/outbox/SW cause не установлена.
   PWA worker update требует проверки маршрутизации настоящего worker script.
5. Visual News/Events/Schedule, LHCI21/7 routes, seed stop/start persistence,
   paired isolated DB/S3 restore и чтение объекта по восстановленной DB reference.
   Owner утвердил только Home12 `ddbbc84d`; новые bytes требуют отдельного утверждения.
6. [63 audit IDs](../../audits/INDEX.md#findings-ledger): historical60 CLOSED/2 DECLINED/1 OPEN
   не являются RC certification. SEC-03 требует backup/read-only inventory перед rotation;
   SEC-07 и RUST-P3-03 — final-source evidence. CodeQL3382/3383 уже dismissed,
   не повторять и не расширять разрешение.
7. Frozen-RC full smoke → ordinary merge → fresh main gates → шесть signed
   source-bound images/SBOM/provenance → tag/release notes `v1.0.0`.

Документационная консолидация и [canonical ownership](../../README.md#documentation-ownership)
сохранены; одноразовый prompt и superseded audits не восстанавливать.
Git history, migrations, env/data/backups, private rescue bundle и его inventory
сохраняются. Чужие процессы, Docker/WSL и глобальные caches не очищать.
