# MVP — оперативный статус

Срез на 2026-10-09 (Europe/Istanbul).
[Мастер-план](MVP_MASTER_PLAN.md), [ТЗ](University_Ecosystem_MVP.md),
[ADR-047](../../adr/ADR-047-risk-based-quality-policy.md) действуют.
Выпуск `v1.0.0` не подтверждён. Владелец запросил безопасную паузу после
текущей контрольной точки; продолжение только по его явному поручению.

## Решения и границы

- Только `egorribun`, один checkout, [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306).
  Root владеет Git/интеграцией; до трёх GPT-6 Luna Max, раздельные файлы.
- Q1/Q4 → Core/product/visual/security/restore → frozen-RC full smoke →
  обычный merge → свежие main checks → существующий producer шести images → release.
- Q1/Q4 migration внедрена; разрешённые14+1 contexts удалены: ruleset8335285
  91→76, остальные rules сохранены. CodeQL blocking, Semgrep в pre-commit.
  Tier0 —100%; действующие floors и100% patch coverage сохраняются доQ3.
- Q2/Q3, global mutation score, три comparable CI runs, kind certification,
  RPO/RTO, deployed BE-02/MIG-PASS —v1.1. Один DB/S3 restore обязателен для MVP.
- ADR-006 сохраняет durable tombstone/WS revoke до commit и conservative
  sibling logout при rollback. ГУУ — внутреннее демо, данные синтетические.
  Без embeddings key текстовый поиск доступен, semantic-only fail-closed.

## Последний подтверждённый hosted/live checkpoint

- HEAD/origin/PR: `f14f497ee9df0ddf30ac64e19a1808633ee2a6fb`.
  Обычные hooks/commit/push PASS; baseline повторно staged, checkout был чист.
  Minimal inventory correction сохранила scanner и exact8 skip identities.
- [Matrix37946889584/a1](https://github.com/egorribun/university_ecosystem/actions/runs/37946889584)
  SUCCESS; exact-head/ruleset join16:35 UTC:76/76 required SUCCESS,
  missing/duplicate/bad/wrong-head/integration-mismatch0. Это proof дляf14,
  не для последующих изменений. Все jobs44m53s, required Matrix43m33s;
  target15m открыт, backend cap2 сохранён. Shard shuffle не решает lower bound.
- [Advisory Owned Live37946889184/a1](https://github.com/egorribun/university_ecosystem/actions/runs/37946889184)
  FAIL:15 PASS/3 FAIL/2 expected skips. Logout429→200 и reset-replay429
  зафиксированы; Retry-After в прежних diagnostics отсутствовал.
  Auth cap/лимит5/min не меняются, advisory context не повышен до required.
- Fresh Coref14 up/readiness PASS:23 services/4 initializer exit0/
  14 healthy checks/10 signed loopback ports; функциональные Mailpit/Redis probes.
  Admin-only seed до Home, затем canonical demo seed PASS.
- SEC-03 узкий persisted API/PG canonical-v2/signature/logout→sameBearer401 PASS.
  Key rotation/native Rust signing этим не сертифицированы.
- Coref14 canonical owner-checked teardown16:42–16:45 UTC PASS:
  containers/networks/volumes0/0/0, source stable, owned children0,
  RAM/time guard не сработал. Private state/env/evidence сохранены.
  Следующий clean SHA требует нового уникального state, без cross-SHA rebind.

## Home и остальная визуальная приёмка

- Владелец явно утвердил новый Home12 на`ddbbc84d`: RU/EN ×light/dark ×
  390/768/1440. Замечание RU/light/1440 карта кампуса→Messenger закрыто.
  Loaded cards visible/settled, axe serious/critical0, exact-session cleanup.
- Одобренные12 PNG и curated provenance сохранены byte-for-byte в
  `frontend/visual-baselines/live/home-empty/`; это manual comparison baseline.
  Freshf14 capture12/12 технически PASS, не новое owner approval чужих байтов.
- Navbar29/29 и UserMenu/DesktopNav100% четырёх metrics; visual contracts19 PASS.
  Остальные согласованные product/admin/auth пакеты, owner review и LHCI открыты.
  Chromatic billing не включать; Windows mocked snapshots не заменяют Linux.

## Исправления послеf14 и проверка

- Targeted six live specs наf14:1 PASS/14 FAIL/1 expected skip за3m28s,
  source stable/guardfalse/owned children0. Полныйf14 Core run не запускался.
- Source-proven: News title/count ожидания устарели; graduation fixture была
  future-only, archive row отсутствовал; active Events tab оставлял default
  `tab=active`. Пакет исправляет heading/path expectations, добавляет9 прошлых
  inactive localized owner-keyed archive events и удаляет default tab из URL.
  Foreign collisions/reseed/boundary guard сохранены и проверены.
- Events production regression RED→GREEN41/41, scoped coverage100%:
  statements106/106, branches82/82, functions23/23, lines102/102.
  Seed ownership14/14, archive guard19/19 lines и8/8 edges в private review.
- Schedule production defect пока не доказан. Добавлены только pathname
  diagnostics; loading/data/hydration/locator причины требуют живой проверки.
- Reviewed RetryV3 допускает ровно один429 retry при строгом Retry-After1..60,
  только если реальный Playwright deadline оставляет запрос и cleanup reserve.
  Invalid/nonfitting header остаётся FAIL; test timeout/assertions не ослаблены.
  Reset replay проверяется в исходном body; DELETE уникального synthetic account
  передан существующему owned cleanup slot. Logout200→sameBearer401 обязателен.
  Finite redacted retry protocol source/project bounded; V2 deadline bug отвергнут.
- Root integrated Python1286/1286 PASS,0 failures/errors/skips за146s.
  Vitest64/64 PASS после исправления package pin test через static JSON imports;
  Node158/158 PASS,0 skips после source-bound обновления11 existing contracts;
  initial148/158 FAIL сохранён. Assertions/role delegation/replay400 сохранены.
  Preflight первоначально8/10; после исправлений frontend types/lint/format3/3
  PASS. Остальные восемь проверок PASS, Ruff check/format4 Python paths и
  437 Markdown link checks PASS; финальные contract lint/format PASS.
  Current-source browser acceptance и новый hosted CI ещё не подтверждены.

## Native Stories, Push и data review

- Native capability V3: credentialless full Chromium153/direct-CDP3/3 настоящих
  hidden/visible transitions PASS. Focus emulation не заменяет native visibility.
- Actual Stories V7 наf14: warmup1+20 measured cycles, hidden7002ms,
  heap early8063252/late8327144 bytes (delta263892≤524288), focus PASS,
  story writes0, logout401/весь cleanup PASS. Итог INCOMPLETE:
  DOM counters unstable; reduced-motion open probe ожидал progress>0,
  хотя production при reduce оставляет0. Aggregate scroll/reduce не доказаны.
  V8 исправляет predicate и добавляет bounded numeric20-cycle DOM series;
  exact DOM gate сохраняется. Новый run только на свежих bound proofs.
- V4/V5/V6 native attempts INCOMPLETE сохранены; V6 имел no-space markers.
  V7 tmp256MiB устранил эти markers в данном run, без утверждения полной причины.
- Push educationf14:0/12 eligible, permission denied при доступных APIs/SW.
  No permission override/mock subscription. Private credentialless normal/OTR
  comparison подготовлен; all-five-topic real Web Push остаётся открытым.
-63 audit IDs классифицированы исторически60 CLOSED/2 DECLINED/1 OPEN(BE-02).
  Source/test review21 P0/P1 не нашёл нового дефекта; это не fresh runtime
  certification всех строк. Exact CodeQL3382/3383 dismissal уже выполнен.
- Native V9 статически reviewed/hash/ACL checked, unrun. LHCI V12 driver
  остаётся unapproved: старый proof-root и seed-guard freshness требуют правок.
  Paired snapshot V5 и Push parent — приватные unrun drafts; Push parent
  AST/Ruff/явная file ACL ещё не проверены. Не запускать их без review.
- Paired DB/S3 snapshot/restore/read-object operators сохранены приватно;
  actual isolated restore и чтение объекта по восстановленной DB reference открыты.

## История и следующий checkpoint

- Full Core89:76 PASS/114 FAIL/8 skips30m29s, source stable/no resource stop.
  Session leak исправлен, причина всех114 ошибок этим не доказана.
  Full14c2 resource-aborted с cleanup UNCONFIRMED остаётся незавершённым.
  Superseded14c2/df/89/dd/f14 Core удалены canonical teardown; не повторять.
  Полные исторические снимки сохранены в Git и private receipts, не в indexes.
- Checked package послеf14 сохраняется обычным commit/push; actual SHA
  сверять по Git/PR. На паузе новые Core/runtime прогоны не запускались.
- После явного возобновления: fresh Core/readiness/admin-only seed/
  Home comparison/SEC-03/demo seed →
  targeted affected specs. Успешный full требует190 PASS +exact8 expected
  project-axis identities, failures/flaky/interrupted/did-not-run0; нужны два подряд.
- Затем stop/start persistence, оставшиеся real auth/MFA/WS/Push, native Stories,
  visual approvals/LHCI, security/data/restore, frozen-RC full smoke.
- Ordinary merge/main proof/шесть signed source-bound image digests/SBOM/
  provenance/tag/release notes ещё не выполнены. Release PASS не заявляется.

## Ресурсы и сохранность

- Один heavy workload: startup RAM≤75%/free≥8GiB, runtime stop≥85%/free<4GiB.
  Только serial Linux screenshots: owner exception≤80%/≥6GiB, browser1GiB/2CPU.
- Root check17:27 UTC:RAM59,1%/free13,02GiB; новые local guards без abort,
  source stable/owned children0. Owned builder stopped, Core0/0/0 подтверждены.
  Usage16:44 UTC:11% weekly consumed,89% remaining, ordinary usage allowed.
- Удалять только доказанно owned ресурсы; shared Docker/WSL/caches,
  чужие процессы/env/data/backups, Git/migrations/private rescue bundle сохранять.
