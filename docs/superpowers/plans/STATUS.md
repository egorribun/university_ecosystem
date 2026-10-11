# MVP — оперативный статус

Контрольная точка на 2026-10-11, 16:11 UTC.
[Мастер-план](MVP_MASTER_PLAN.md), [ТЗ](University_Ecosystem_MVP.md) и
[ADR-047](../../adr/ADR-047-risk-based-quality-policy.md) действуют.
Работа продолжается; выпуск `v1.0.0` ещё не подтверждён.

## Границы работы

- Только `egorribun`, один checkout и [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306).
  Root владеет Git/интеграцией; до трёх GPT-6 Luna Max работают в непересекающихся областях.
- Q1/Q4 migration и разрешённые 14+1 removals выполнены. Ruleset `8335285`:
  76 required context/integration pairs; остальные правила сохранены.
  CodeQL blocking, Semgrep в pre-commit; Tier 0, нынешние floors и 100% patch сохраняются.
- Q2/Q3, global mutation score, comparable CI runs, kind certification,
  RPO/RTO и deployed BE-02/MIG-PASS — v1.1. Один paired DB/S3 restore нужен для MVP.
- ADR-006 сохраняет tombstone/WS revoke до commit и conservative sibling logout
  при rollback. ГУУ — внутреннее демо; данные синтетические.

## Hosted CI

Последний проверенный published SHA:
`7167b218791ebb64cd93393255aa9c74a6e122e5`,
tree `bdce879fe9d6848e3e2ce85e460173efab3729e0`.
Branch/origin/PR head совпадают; PR открыт, non-draft.

- [Matrix 38146996494](https://github.com/egorribun/university_ecosystem/actions/runs/38146996494)
  завершён FAILURE:86 jobs, failures в Frontend Unit shards1/3, их aggregate и CI Success.
  Девять unit failures воспроизведены: три старых QueryClient mocks не содержали
  нового `cancelQueries`. Исправлены именно эти fixtures; assertions сохранены.
- Backend и integration jobs этого Matrix прошли. Failed frontend steps не дали
  полного coverage artifact; их coverage не заявляется.
- Исторический `d133559c`:76/76 required SUCCESS. Он не заменяет проверки successor SHA.
  Измеренный CI budget38m21 unit-start → aggregate и41m23 lint-start → aggregate;
  цель≤15min открыта, max-parallel2 сохранён без недоказанного повышения нагрузки.
- Следующий reviewed пакет требует обычного commit/push и собственных76 required results.

## Подготовленный и локально проверенный пакет

- BrandBootLoader: контраст status foreground исправлен; уходящий status скрыт
  семантически и визуально. Существующие fade/reduced-motion и сроки удаления сохранены.
- Service Worker сообщает terminal bootstrap status; ready испускается после установки
  постоянных queue listeners. Story memory baseline ждёт эту границу перед прежним
  warm-up и всеми20 cycles. Exact DOM/heap/focus/hidden assertions не ослаблены.
- PWA update использует настоящий HTTP proxy для worker script. GET/HEAD, cookie/
  Origin/CSRF forwarding, POST405, замена script bytes/валидаторов и отмена stalled
  запроса проверены реальным локальным transport test:3/3 PASS. Browser update ещё не принят.
- OTP retry выполняет требуемое явное подтверждение после stale-code error;
  MFA проверяет свежий API profile после verify. Password/TOTP/OTP и DND scenarios
  ждут идентичность своего синтетического аккаунта в UI. Production guard defect
  этими изменениями не доказан; API/UI acceptance assertions сохранены.
- Notification preferences использует тот же full Chromium native profile,
  что остальные Push specs. Full demo seed идемпотентно добавляет недостающие topic
  preferences только точному roster; admin-only seed не меняется, чужие accounts/
  existing preferences сохраняются.
- Footer geometry сравнивает usable client viewport с учётом stable scrollbar gutter
  и дополнительно запрещает горизонтальный overflow; hit targets/overlap checks сохранены.
- DM/group Push failure observation ограничена временем и числом записей, печатает
  только finite enums/boolean/count fields до owned-profile cleanup; delivery gate сохранён.
- Локально:113/113 focused units; пять изменённых production files имеют100%
  statements/branches/functions/lines (191/97/46/172), точный состав JSON проверен.
  Это focused evidence, не глобальный coverage proof.
- Full TypeScript, frontend lint, live contracts181/181, Ruff/Prettier и diff check PASS.
  Parser1521/1521 и seed14/14 PASS. Quality guards: source stable,
  ownership schema3, remaining recorded owned children0. Hosted/live gates ещё нужны.

Предыдущие исправления Settings route/focus, сериализованного post-commit profile
refresh и outbox sender identity уже находятся в published source; повторно не выполнять.
BE-04 isolated PostgreSQL attachment/transaction/persistence proof выполнен ранее.

## Core и ресурсы

- Fresh7167 Core `run-d257cb1c-5c74-4515-b3a2-d259e054c02a`,
  project `ue-live-07f326d6b3da293d`, signed schema11/23 services:
  up → admin-only seed → demo seed → readiness14 healthchecks/4 initializers PASS.
  Effective cookie policy:Secure=false, development=true, strictHeaders=false.
- Targeted7167 результаты раздельны: Stories/Settings8 PASS/2 FAIL из10;
  a11y/footer3 PASS/3 FAIL из6; Auth/Notifications0 PASS/14 FAIL;
  native Push7 PASS/5 FAIL из12. Это диагностика, не full gate.
- V15 на7167 выполнил20 cycles: baseline659 nodes/2 documents/434 listeners;
  каждый close659/2/435. Heap plateau, focus, hidden pause7001ms, reduced motion
  и scroll PASS; exact listener gate FAIL. Structural DOM идентичен, bootloader отсутствует.
  Runtime показал document visibilitychange4→5; source registration добавляет
  постоянную visibility/online пару. Runtime owner window online прямо не установлен.
- Footer diagnostic: innerWidth390, clientWidth/scrollWidth/visualViewport/nav375;
  причина15px — stable scrollbar gutter. Контраст bootloader3.09 требовал исправления.
  Native Push дошёл до persisted in-app rows; provider/outbox/SW cause ещё не установлена.
- Core штатно остановлен15:26 UTC:23 containers stopped,6 volumes, env и signed owner
  сохранены. На successor SHA нужен новый уникальный state; strict resume не обходить.
- Один heavy workload: start RAM≤75%/free≥8GiB, stop≥85%/free<4GiB.
  Serial Linux screenshots: owner exception≤80%/≥6GiB, browser1GiB/2CPU.
  Owned builder stopped, cap4GiB/no swap/2CPU; полезные caches сохранены.
  Cleanup только по подтверждённым PID+birth+parent handles; чужие процессы/
  Docker/WSL и глобальные caches не очищать.

## Открытые критерии и следующий порядок

1. Ordinary hooks/commit/push reviewed пакета; fresh76 required results.
   Fresh unique Core:admin-only seed перед demo seed, readiness/cookie policy,
   затем затронутые Stories/UI/Auth/PWA/Push/Notifications scenarios.
2. Устранить оставшиеся failures; два consecutive full Core runs на неизменном source:
   198 total,190 PASS + exact8 expected SKIP. Исторический full e537:
   117 PASS/73 FAIL/8 SKIP, текущим acceptance proof не является.
3. Visual News/Events/Schedule, LHCI21/7 routes, seed stop/start persistence,
   paired isolated DB/S3 restore и чтение объекта по восстановленной DB reference.
   Owner утвердил только Home12 `ddbbc84d`; новые pixels требуют отдельного утверждения.
4. [63 audit IDs](../../audits/INDEX.md#findings-ledger): historical60 CLOSED/2 DECLINED/1 OPEN
   не являются RC certification. SEC-03:backup/read-only inventory перед rotation;
   SEC-07 и RUST-P3-03:final-source evidence. CodeQL3382/3383 уже dismissed,
   не повторять и не расширять разрешение.
5. Frozen-RC full smoke → ordinary merge → fresh main gates → шесть signed
   source-bound images/SBOM/provenance → tag/release notes `v1.0.0`.

[Canonical documentation ownership](../../README.md#documentation-ownership)
и audit retention сохранены; одноразовый prompt и superseded audits не восстанавливать.
Git history, migrations, env/data/backups, private rescue bundle и его inventory сохраняются.
