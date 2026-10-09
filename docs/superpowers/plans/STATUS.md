# MVP — оперативный статус

Срез на 2026-10-09, 23:42 UTC.
[Мастер-план](MVP_MASTER_PLAN.md), [ТЗ](University_Ecosystem_MVP.md) и
[ADR-047](../../adr/ADR-047-risk-based-quality-policy.md) действуют.
Выпуск `v1.0.0` ещё не подтверждён; автономная работа продолжается.

## Границы работы

- Только `egorribun`, один checkout и [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306).
  Root владеет Git/интеграцией; до трёх GPT-6 Luna Max работают в непересекающихся областях.
- Q1/Q4 migration и разрешённые 14+1 removals выполнены; ruleset `8335285`
  содержит 76 required contexts. Точный разрешённый список сохранён в ADR-047.
  CodeQL blocking, Semgrep в pre-commit; Tier 0 и текущие coverage floors/100% patch сохраняются.
- Q2/Q3, global mutation score, три comparable CI runs, kind certification,
  RPO/RTO и deployed BE-02/MIG-PASS остаются v1.1. Один paired DB/S3 restore нужен для MVP.
- ADR-006 сохраняет tombstone/WS revoke до commit и conservative sibling logout
  при rollback. ГУУ — внутреннее демо; данные синтетические.

## Опубликованный checkpoint и CI

Последняя опубликованная база (readback 23:26 UTC):
`5da3a6dea2d807373a4252e7f9f7d5b96b77483a`,
tree `4e735d0f8fe7c41a1302f1ed28fbdc99da7b62e9`; PR открыт, base `main`.
Локальный source checkpoint `791e81a2fdb2f796590ca9964027efd805ca4baa`
прошёл ordinary commit hooks. Он и документационная интеграция ещё не опубликованы
и не имеют нового hosted PASS.

- На 5da3 hosted snapshot: 136 checks, 80 SUCCESS/29 FAILURE/27 SKIPPED.
  [Matrix 37992269520/a1](https://github.com/egorribun/university_ecosystem/actions/runs/37992269520)
  выявила шесть ошибок partial mock в frontend shard 2; исправление интегрировано,
  focused Vitest 23/23 PASS. [Dependency Review 37992269210/a1](https://github.com/egorribun/university_ecosystem/actions/runs/37992269210)
  ожидает свежей проверки exact-version license clarification.
- Часть hosted jobs останавливается до тестов/scans на Docker Hub rate limit,
  registry/server/token errors или Helm transport. В двух benchmark artifacts
  [37992269093/a1](https://github.com/egorribun/university_ecosystem/actions/runs/37992269093)
  root подтвердил `TOOMANYREQUESTS`, ZIP digest и source binding; numeric HTTP429
  присутствует только в Rust log. Benchmark acceptance не получена.
- Эти сбои не являются PASS и не доказывают одинаковую причину всех failures.
  Для successor нужны новые required checks. Цель PR critical path ≤15min открыта.

## Последний Core и рабочая интеграция

- Core 5da3: signed up/readiness/admin-only seed/demo seed PASS; Home12 technical
  PASS, axe serious/critical0. SEC-03 API/PG canonical-v2/signature/logout→401 PASS
  в узкой границе; key rotation/native Rust signing не сертифицированы.
- Targeted News/Events/Schedule: 13 PASS/2 FAIL/1 expected project skip.
  Full Core на 5da3 не запускался. News history diagnostics подтвердили motion
  во время измерений; responsive diagnostic прошёл геометрию, не заменяя acceptance.
- Root интегрировал reviewed News settling: existing layout waits после ready/filter
  и ожидание завершения positional animations со стабильной геометрией для history.
  Exact assertions, viewport sizes, deadlines и expected skips сохранены.
  Новый browser acceptance ещё не выполнен.
- Canonical teardown 22:29–22:32 PASS; независимый Docker readback: owned
  containers/networks/volumes 0/0/0. State `run-a0b646d8-b43a-4e23-af66-d36a78ad03d9`
  и private evidence сохранены; повторно этот state не запускать.
- Root live Node contracts 160/160 PASS 23:39 после всех News waits;
  focused mock Vitest 23/23 PASS 22:40.
  Guards: source/working snapshot stable, owned children0, resource stopfalse.
- Documentation checks: Markdown tests9/9, dashboard/generator tests6/6,
  actual generated dashboard byte-identical; оба режима link checker PASS.
  Root AST comparison подтвердил неизменность executable logic после правок
  комментариев/docstrings в auth/Watch/Redis и Markdown test module.

## Визуал, security и данные

- Владелец утвердил Home12 на `ddbbc84d`; approved PNG/provenance сохранены
  byte-for-byte в `frontend/visual-baselines/live/home-empty/`. Technical capture
  на другом SHA не означает одобрения новых bytes. Остальные visual packages/owner review открыты.
- Native V10 выполнил 20 cycles и прочие измерения, но strict exact-DOM gate FAIL;
  V11 static reviewed, runtime NOT RUN. LHCI V12 candidate-v2 static reviewed,
  runtime NOT RUN; требуются 21 reports, 7 routes ×3.
- Real all-five-topic Push/auth/MFA/WS acceptance открыта. Дополнительный Push V6
  diagnostic не выбран: AST parse PASS, Ruff 16 findings/format FAIL; это не waiver.
- Paired S3 V6/read-probe V3/avatar V4/invocation map V2 static reviewed.
  Actual snapshot/isolated DB+S3 restore/read by restored DB reference NOT RUN.
  Source data, backups и partial targets сохранять; RPO/RTO не заявлять.
- [Реестр всех 63 audit IDs](../../audits/INDEX.md#findings-ledger) сохраняет aliases,
  rationale и source references. Historical 60 CLOSED/2 DECLINED/1 OPEN не являются
  текущей RC certification; revalidation открыта. Exact CodeQL3382/3383 dismissal
  уже выполнен; не повторять и не расширять.

## Документация и ближайшие действия

По поручению владельца завершена общая сверка 82 проектных Markdown-документов
с кодом и ADR; сторонний каталог skills сохранён.
Удалены superseded audits и одноразовый session prompt после переноса уникальных
требований; Git history, rescue bundle и его inventory сохранены. Canonical ownership
описано в [docs index](../../README.md#documentation-ownership).

1. Завершить ordinary hooks и публикацию reviewed документационной интеграции:
   restage `.secrets.baseline`, commit/push и проверить новые hosted checks.
2. Создать fresh signed unique Core на clean successor SHA. После readiness/admin-only
   seed — targeted News, затем два consecutive full Core runs: каждый 190 PASS +
   exact8 source/project expected skips; failures/flaky/interrupted/did-not-run0.
3. Завершить Native/Push/auth/MFA/WS, visual approvals/LHCI/JS<500KB, seed persistence,
   security/data и один paired DB/S3 restore.
4. Frozen-RC full smoke, ordinary merge PR1306, свежие main checks, существующий
   producer шести signed source-bound image digests/SBOM/provenance, tag/release notes.

## Ресурсы

Один heavy workload: startup RAM≤75%/free≥8GiB, stop≥85%/free<4GiB.
Для serial Linux screenshots действует owner exception≤80%/≥6GiB, browser1GiB/2CPU.
Последний readback 23:41 UTC: RAM50,93%/free15,61GiB; диск C свободно195,75GiB.
Owned builder stopped, cap4GiB/no swap/2CPU; полезный cache сохранён.
Последний account refresh 23:38 UTC:29% weekly consumed/71% remaining,
ordinary usage allowed.
Чужие процессы, Docker/WSL, env/data/backups и приватный rescue bundle сохраняются.
