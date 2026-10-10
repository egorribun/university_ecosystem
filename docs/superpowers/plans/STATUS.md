# MVP — оперативный статус

Срез на 2026-10-10, 00:33 UTC.
[Мастер-план](MVP_MASTER_PLAN.md), [ТЗ](University_Ecosystem_MVP.md) и
[ADR-047](../../adr/ADR-047-risk-based-quality-policy.md) действуют.
Выпуск `v1.0.0` ещё не подтверждён; автономная работа продолжается.

## Границы работы

- Только `egorribun`, один checkout и [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306).
  Root владеет Git/интеграцией; до трёх GPT-6 Luna Max работают в непересекающихся областях.
- Q1/Q4 migration и разрешённые 14+1 removals выполнены; ruleset `8335285`
  содержит 76 required contexts. Точный разрешённый список сохранён в ADR-047.
  Readback 00:31 UTC подтвердил неизменность всех 76 context/integration pairs.
  CodeQL blocking, Semgrep в pre-commit; Tier 0 и текущие coverage floors/100% patch сохраняются.
- Q2/Q3, global mutation score, три comparable CI runs, kind certification,
  RPO/RTO и deployed BE-02/MIG-PASS остаются v1.1. Один paired DB/S3 restore нужен для MVP.
- ADR-006 сохраняет tombstone/WS revoke до commit и conservative sibling logout
  при rollback. ГУУ — внутреннее демо; данные синтетические.

## Опубликованный checkpoint и CI

Опубликован `2b53ed12748c5483161e8ea5ea4a55b5d8cad613`,
tree `d6dbdb7dae2256f26afde720838700096fb977cf`; PR открыт, base `main`.
Документационная консолидация и предыдущие News/mock/license fixes опубликованы
с ordinary hooks. Новые локальные исправления ниже требуют successor commit/push
и свежих hosted results.

- Exact-head hosted snapshot: 138 checks, 112 SUCCESS/23 SKIPPED/3 FAILURE,
  чужих SHA0, незавершённых0. Required join: 73 SUCCESS/3 FAILURE,
  missing/skipped/in-progress0; все 23 skips вне required set.
- [Matrix 38005762675/a1](https://github.com/egorribun/university_ecosystem/actions/runs/38005762675)
  завершилась с двумя прямыми ошибками: устаревшие policy literals в
  `verify_harness.py` и MD047/final LF в `AUDIT_PROMPT.md`.
  Третья ошибка — производный `CI Success`. Оба исправления reviewed и интегрированы.
- [Dependency Review 38005762392/a1](https://github.com/egorribun/university_ecosystem/actions/runs/38005762392)
  PASS; frontend shard2/MSW drift, все четыре backend unit shards, Go integrations
  и Linux Python3.14 integration shard0 PASS.
- Actual Linux shard3 JUnit подтверждает MFA deadline1/1 и cancellation7/7,
  без skip/failure/error. Linux integration job подтвердил реальный PG/Mailpit
  outbox test и fail-closed JUnit1/0/0/0; XML не скачан, upload failure-only.
- Ранее подтверждённые Docker Hub/registry transport failures не переносятся
  на этот snapshot. Цель PR critical path ≤15min остаётся открытой.

## Последний Core и рабочая интеграция

- Fresh signed Core `run-d71b6d00-33ee-4230-b6fc-15dedc149cef` на 2b53:
  up, admin-only seed, readiness и cookie policy PASS. Admin-only seed выполнен
  до demo seed; synthetic notification safety сохранена.
- Targeted News: 3 PASS/1 FAIL. Responsive axes и mobile history PASS;
  desktop history упал на exact scrollY после первого Science filter click.
  Full Core на этом SHA не запускался.
- Ограниченный geometry diagnostic V6 не воспроизвёл failure; обнаружены
  незавершённые загрузка/анимации перед click baseline. Reviewed test preconditions
  теперь ждут seeded article, видимый Science filter в viewport и stable position.
  Exact scrollY/URL/aria/history assertions, deadlines и skips сохранены;
  product code не менялся. Новый browser acceptance ещё не выполнен.
- Canonical teardown 00:22–00:25 PASS; независимый readback 00:26 UTC:
  owned containers/networks/volumes0/0/0. State и private evidence сохранены.
  Retired states d71b6d00/a0b646d8/6684 повторно не запускать.
- После текущей интеграции root harness28/28 PASS и canonical live Node
  contracts160/160 PASS 00:32. Source/branch stable, owned children0, resource stopfalse.
  Предыдущий focused mock Vitest23/23 PASS 22:40.
- Documentation checks: Markdown tests9/9, dashboard/generator tests6/6,
  actual generated dashboard byte-identical; оба режима link checker PASS.
  Root AST comparison подтвердил неизменность executable logic после правок
  комментариев/docstrings в auth/Watch/Redis и Markdown test module.
- Для successor подготовлены readiness/cookie helpers под unique state
  `run-1faec800-7fcf-47a0-8cc2-1222b0f07e16`; state ещё не создан,
  helpers static reviewed, runtime привязывается к clean successor SHA.

## Визуал, security и данные

- Владелец утвердил Home12 на `ddbbc84d`; approved PNG/provenance сохранены
  byte-for-byte в `frontend/visual-baselines/live/home-empty/`. Technical capture
  на другом SHA не означает одобрения новых bytes. Остальные visual packages/owner review открыты.
- Native V10 выполнил 20 cycles и прочие измерения, но strict exact-DOM gate FAIL;
  V11 static reviewed, runtime NOT RUN. LHCI V12 candidate-v2 static reviewed,
  runtime NOT RUN; требуются 21 reports, 7 routes ×3. Текущие V11 source pins совпадают.
- Независимый source review изменённых auth/session/data путей не нашёл нового
  подтверждённого P0/P1 в проверенной области; это не полная runtime certification.
  Real all-five-topic Push/auth/MFA/WS acceptance открыта; использовать существующие
  full Core scenarios, не создавать дублирующий Push operator.
- Paired S3 V6/read-probe V3/avatar V4/invocation map V2 static reviewed.
  ACL трёх pinned private dependencies исправлены без изменения bytes.
  Actual snapshot/isolated DB+S3 restore/read by restored DB reference NOT RUN.
  Source data, backups и partial targets сохранять; RPO/RTO не заявлять.
- [Реестр всех 63 audit IDs](../../audits/INDEX.md#findings-ledger) сохраняет aliases,
  rationale и source references. Historical 60 CLOSED/2 DECLINED/1 OPEN не являются
  текущей RC certification; revalidation открыта. Exact CodeQL3382/3383 dismissal
  уже выполнен; не повторять и не расширять.
- Read-only release preflight: remote tags/releases отсутствуют; default
  semantic-release first version — `1.0.0`, tag `v1.0.0`. Producer/consumer сохраняют
  source/run/attempt binding шести images. Full smoke и paired restore — отдельные
  root prerequisites до dispatch; публикация ещё не выполнялась.

## Документация и ближайшие действия

По поручению владельца завершена общая сверка 82 проектных Markdown-документов
с кодом и ADR; сторонний каталог skills сохранён.
Удалены superseded audits и одноразовый session prompt после переноса уникальных
требований; Git history, rescue bundle и его inventory сохранены. Canonical ownership
описано в [docs index](../../README.md#documentation-ownership).

1. Опубликовать reviewed News/harness/Markdown fixes с ordinary hooks:
   restage `.secrets.baseline`, commit/push и проверить новые hosted checks.
2. Создать fresh signed unique Core на clean successor SHA, выполнить admin-only
   seed перед demo seed, readiness/cookie policy и targeted News. Затем два consecutive
   full Core runs: каждый 190 PASS +
   exact8 source/project expected skips; failures/flaky/interrupted/did-not-run0.
3. Завершить Native/Push/auth/MFA/WS, visual approvals/LHCI/JS<500KB, seed persistence,
   security/data и один paired DB/S3 restore.
4. Frozen-RC full smoke, ordinary merge PR1306, свежие main checks, существующий
   producer шести signed source-bound image digests/SBOM/provenance, tag/release notes.

## Ресурсы

Один heavy workload: startup RAM≤75%/free≥8GiB, stop≥85%/free<4GiB.
Для serial Linux screenshots действует owner exception≤80%/≥6GiB, browser1GiB/2CPU.
Последний guard 00:32 UTC: peakRAM47,05%/minimum free16,84GiB;
диск C readback00:08 — свободно195,31GiB.
Owned builder stopped, cap4GiB/no swap/2CPU; полезный cache сохранён.
Последний account refresh00:03 UTC:29% weekly consumed/71% remaining,
ordinary usage allowed.
Чужие процессы, Docker/WSL, env/data/backups и приватный rescue bundle сохраняются.
