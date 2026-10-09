# MVP — оперативный статус

Срез на 2026-10-09, 21:08 UTC.
[Мастер-план](MVP_MASTER_PLAN.md), [ТЗ](University_Ecosystem_MVP.md),
[ADR-047](../../adr/ADR-047-risk-based-quality-policy.md) действуют.
Выпуск `v1.0.0` не подтверждён. Goal active; владелец возобновил автономную работу.

## Работа и разрешённые границы

- Только `egorribun`, один checkout,
  [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306).
  Root владеет Git, интеграцией и canonical docs; до трёх GPT-6 Luna Max.
- Порядок: Q1/Q4 → Core/product/visual/security/restore → frozen-RC full smoke →
  ordinary merge → свежие main checks → существующий producer ровно шести images → release.
- Q1/Q4 migration и разрешённые14+1 removals DONE: ruleset8335285 имеет76
  required contexts. Остальные rules сохранены; CodeQL blocking, Semgrep в pre-commit.
  Tier0 и нынешние coverage floors/100% patch coverage сохраняются доQ3.
- Q2/Q3, global mutation score, три comparable CI runs, kind certification,
  RPO/RTO, deployed BE-02/MIG-PASS —v1.1. Один DB/S3 restore обязателен для MVP.
- ADR-006: durable tombstone/WS revoke до commit, conservative sibling logout
  при rollback. Данные синтетические, ГУУ — внутреннее демо.
  Без embeddings key текстовый поиск доступен, semantic-only fail-closed.

## Проверенный опубликованный checkpoint

Последний независимо проверенный published checkpoint перед этим обновлением:
`cce5e6eb5be85bbe22493d5a0f6f25ebccb4091d`, tree
`acb4ba868c5dfb3cff7a7a68cf81b49d6dfe2187`; HEAD/origin/PR совпадали.
Successor SHA и новый hosted CI сверять по Git/PR, не выводить из текста документа.

- [Matrix37972688405/a1](https://github.com/egorribun/university_ecosystem/actions/runs/37972688405)
  SUCCESS. Exact-head/ruleset join19:14 UTC:76/76 SUCCESS, pending/missing/failed0;
  140 unique check runs, CodeQL SUCCESS. Matrix72 successful/14 skipped jobs.
  Required Matrix43,37min: цель15min остаётся открытой; backend cap2 сохранён.
- [Owned Live37972687964/a1](https://github.com/egorribun/university_ecosystem/actions/runs/37972687964)
  SUCCESS в advisory Core-smoke границе. Frozen-RC full-stack шаги SKIPPED;
  это не full-stack PASS. Четыре full Chromium shards/LHCI остаются scheduled/manual.
- Browser-free fixture isolation внедрена наcce5: root Node158/158 PASS без
  установленного Chromium; production owned cleanup сохранён. Старый c06 advisory
  contract FAIL до Docker остаётся историческим FAIL.

## Core cce5: setup и диагностические результаты

- Fresh signed Core up18:27–18:29 PASS:23 services,19 running/4 initializer exit0,
  14 health checks; owner/source/daemon/Compose/ports и функциональные probes PASS.
- Admin-only seed PASS до Home; canonical demo seed PASS. Последний demo refresh
  19:37–19:38 PASS; readiness/cookie proofs обновлены19:38–19:39.
- SEC-03 persisted API/PG canonical-v2/signature/logout→sameBearer401 PASS
  в узкой границе. Key rotation и native Rust signing не сертифицированы.
- Targeted News/Events/Schedule:8 PASS/7 FAIL/1 expected project skip,3m13s.
  Полный Corecce5 не запускался.
  Events проходят; News и Schedule причины проверены живыми bounded diagnostics.
  Owned logout429/Retry-After33 не поместился в оставшиеся26,463s; лимиты,
  deadline и assertions сохранены. Это FAIL, не скрытый retry PASS.
- Canonical teardown19:52–19:56 PASS: source stable, owned children0, guardfalse.
  Независимый Docker readback после teardown: containers/networks/volumes0/0/0.
  State `run-66842753-1521-4c10-a5e0-ac5e1fbcb8a6` и private evidence сохранены.
  Не запускать этот state снова: следующий clean SHA требует нового unique run.

## Интегрированный пакет News/Schedule

Root применил три frozen reviewed patch наcce5;19 файлов. Обычные hooks/commit/push
для successor проверить по actual Git/PR. Current-source browser acceptance ещё открыта.

- News: категории выводятся из непустых English полей с fallback по каждому полю.
  RU/EN mixed-keyword fixture получает одну категорию в фильтре, badge, detail
  и related feed. Порядок category rules не изменён; displayed/search text сохранён.
- News scroll: тест создаёт фактический положительный scroll и ждёт settled route
  content. Strict exact Back/Forward scroll/viewport restoration сохранён.
- Schedule: API реально отдавал28 lessons, group assigned; на странице два valid
  grids (Schedule/MiniCalendar). Тесты выбирают точный named Schedule grid/tablist;
  production grid и seed не удалены. NULL-group defect не доказан.
- Integrated Vitest7 files/70 tests PASS20:04,0 failed/pending.
  Static typecheck/lint/format/i18n4/4 PASS20:06,50,53s.
  Live Node contracts158/158 PASS20:07,0 skips, без установленного browser.
  Guards: exact19-path working snapshot stable, owned children0, resource stopfalse.
  Coverage review статический; это не measured full-suite coverage PASS.
- Дополнительный полный frontend coverage run20:23–20:28 отменён root для
  продолжения публикации и обязательного hosted coverage. Итог CANCELLED, не PASS;
  source/21-path working snapshot stable, owned children0. Coverage floors сохранены.
- Root интегрировал reviewed logout-header V3 ещё в5 файлов. Legacy пяти-польный
  retry protocol сохранён; отдельный stdout protocol выводит только bounded
  числовые limit/remaining либо `invalid`. Retry/deadline/caps/logout→401 сохранены.
  Root live Node contracts160/160 PASS20:45; весь `tests/test_live_stand.py`
  1292/1292 PASS20:49,147,24s; Ruff check/format PASS. Integrated static4/4
  PASS20:50,49,47s. Guards:26-path snapshot stable, owned children0, stopfalse.
- Canonical visual collector теперь поддерживает required remote Chromium:
  loopback endpoint, exposure только owned localhost origin и bounded30s News
  readiness перед снимком. Root+peer review и root integrated visual/auth/admin
  Node contracts59/59 PASS21:08,0 skips; scoped ESLint/Prettier PASS.
  Guard:28-path snapshot stable/owned children0. Linux capture ещё NOT RUN;
  его ownership/proofs и owner visual approval этим не подтверждены.
- Предыдущие Python1286/1286, Events41/41 scoped100%, Node158/158 и static
  проверки сохранены как evidence соответствующего source. Unchanged backend
  повторно не запускался. Assertions/caps/coverage floors не ослаблены.

## Home и визуальная приёмка

- Владелец утвердил Home12 на`ddbbc84d`: RU/EN ×light/dark ×390/768/1440.
  Gap RU/light/1440 карта кампуса→Messenger исправлен; approved12 PNG и curated
  provenance сохранены byte-for-byte в `frontend/visual-baselines/live/home-empty/`.
- Fresh cce5 Home12 technical PASS, axe serious/critical0, exact-session cleanup.
  Динамические greetings/weather/time и gradient дают иной RGBA; approval новых
  bytes из этого не следует. Первоначальный вывод о navbar regression был ошибочен
  и исправлен после actual crop comparison: новых navbar fixes не требуется.
- Остальные product/admin/auth пакеты, owner review и LHCI открыты.
  Windows mock screenshots не заменяют Linux approval; Chromatic billing не включать.

## Native Stories, Push, security и данные

- Native V10 actual: one warmup+20 measured cycles, hidden7000,7ms,
  heap delta254461,6≤524288 bytes, focus/scroll/reduce/zero writes/auth cleanup PASS.
  Browser/process/profile/container cleanup PASS. Итог INCOMPLETE: baseline
  DOM2/760/437 → все20 post-close2/714/435, strict exact-DOM gate FAIL.
  Причина изменения не доказана; отсутствие роста не заменяет strict equality.
- Native V11 prepared/root+independent static review CLEAR, runtime NOT RUN.
  Добавлен bounded wait для settled/not-pending/not-refetching Dashboard/Story
  markers до единственного warmup; успешные data queries этим не доказаны.
  Exact20/DOM/heap/pause/focus/scroll/reduce/write/auth/cleanup gates сохранены.
- Push V4/V5 actual FAIL до browser на Docker Mounts representation.
  Оба дополнительных контейнера удалены exact-owned cleanup; V6 root/peer CLEAR,
  добавляет bounded in-container tmpfs mountinfo verification, runtime NOT RUN.
  Historical education0/12 permission denied остаётся; real all-five-topic Push открыт.
- LHCI V12 private candidate-v2 static CLEAR, runtime NOT RUN:
  fresh seed/readiness/cookie/source/state,21 reports/7 routes×3 и cleanup gates.
- Paired S3 V6 ACL fix/read-probe V3 root+peer static CLEAR; avatar fixture V3
  reviewed. Actual snapshot/isolated restore/read by restored DB reference NOT RUN.
  Не удалять source/backups/partial targets и не заявлять RPO/RTO.
- 63 audit IDs исторически60 CLOSED/2 DECLINED/1 OPEN(BE-02); source/test review
  21 P0/P1 без нового дефекта не заменяет full runtime certification.
  Exact CodeQL3382/3383 dismissal уже выполнен; не повторять/не расширять.

## Следующие обязательные проверки

1. Проверить ordinary hooks/restage `.secrets.baseline`/commit/push successor,
   новый hosted CI и создать новый signed unique Core на clean SHA.
2. Readiness/admin-only seed/Home comparison/SEC-03/demo seed; affected targeted
   News/Events/Schedule, затем два consecutive full Core runs.
   Каждый full:190 PASS+exact8 source/project expected skips, failures/flaky/
   interrupted/did-not-run0. Unexpected skip —FAIL.
3. Оставшиеся real auth/MFA/WS/Push, Native Stories, visual approvals/LHCI/JS<500KB,
   stop/start seed persistence, security/data и один paired DB/S3 restore.
4. Frozen-RC full smoke, ordinary merge PR1306, свежие main checks, шесть signed
   source-bound image digests/SBOM/provenance/tag/release notes. Это ещё не выполнено.

Исторические Full89:76 PASS/114 FAIL/8 skips и resource-aborted14c2 с cleanup
UNCONFIRMED сохраняются; session leak не доказан причиной всех114 failures.
Superseded Core14c2/df/89/dd/f14/cce5 удалены canonical teardown; history/receipts
сохранены в Git/private storage, не добавляются в текущие documentation indexes.

## Ресурсы

- Один heavy workload: startup RAM≤75%/free≥8GiB; stop≥85%/free<4GiB.
  Только serial Linux screenshots: owner exception≤80%/≥6GiB, browser1GiB/2CPU.
- После teardown RAM44,98%/free17,50GiB; integrated static peak52,11%/
  minimum free15,23GiB. Builder stopped, cap4GiB/no swap/2CPU, useful cache сохранён.
- После отмены дополнительного coverage: RAM35,93%/free20,38GiB.
- Повторный integrated static: peak42,82%/minimum free18,19GiB.
- Последний account refresh:20% weekly consumed/80% remaining, ordinary usage allowed.
  Не удалять чужие процессы, shared Docker/WSL/caches/env/data/private rescue bundle.
