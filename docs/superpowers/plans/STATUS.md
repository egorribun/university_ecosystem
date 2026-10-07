# MVP — оперативный статус

Срез на 2026-10-07 (Europe/Istanbul). [Мастер-план](MVP_MASTER_PLAN.md)
задаёт приёмку; [ТЗ MVP](University_Ecosystem_MVP.md) — продуктовые границы.
Пауза по запросу пользователя. Выпуск `v1.0.0` не подтверждён.

## Контрольная точка

- Работа ведётся на `egorribun` в одном checkout и [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306).
  База текущей контрольной точки — `c1b208476fbd92c21bdc0a0ccf9b5ee74977cfb1`.
  Reviewed regressions и generation reuse интегрированы; exclusions/пороги сохранены.
  Три GPT-6 Luna Max готовят приватные пакеты; root проверяет и интегрирует.
- Full-backend workflow, benchmark, WebKit/avatar/DM fixes интегрированы;
  локальные контракты не заменяют hosted/live приёмку.

## Hosted CI и мутации

- Matrix `37658682087/a1` для `c1b`: FAILED; 90 jobs SUCCESS, пять FAILED,
  24 skipped. Inventory и backend shards0/1: catalog/nightly needs;
  shard3: устаревший full-mutation command contract; CI Success — итоговый gate.
  Catalog/preflight/scheduled согласованы; retry classification остаётся review-required.
- Root cumulative auth138/138 и catalog/preflight/nightly62/62 PASS.
  Scheduled/preflight delta12/12 PASS после двух воспроизведённых stale assertions.
  Полный новый fast preflight10/10 PASS; это не release evidence.
  UV offline lock check и npm dry-run PASS; только два lock metadata leaves изменены.
  Проверены 33 Dependabot advisory против 56 locked resolutions: affected matches0;
  это не закрытие alerts default branch и не глобальная security-сертификация.
- Matrix run `37526001524/a1`: event source `4213`; producer —
  `deb33a29cc7a91b2043828fc578dc34ad037337f`. Все 128 incremental jobs FAILED.
  Root проверил API digests, ZIP/JSON, canonical evidence и exact planned join:
  4 584 terminal = 3 949 Killed / 635 Survived; selection полна.
  Timeout/no-tests/skipped/suspicious/interrupted/segfault/typecheck записей нет.
  Generated universe 54 452 не исполнялся полностью; global score не установлен.
- Manual full run `37481732603/a1`: frontend shard jobs завершились 64/64
  SUCCESS, но итоговый aggregate FAILED и aggregate artifact отсутствовал.
  Backend preflight завершился ошибкой до запуска 128 backend execution shards;
  пропущенные shards не являются результатами мутаций. Глобальный viable score
  не установлен.
- Для source7ac локальные затронутые contracts359/359 и Helm retry29/29 PASS;
  CodeQL/Chromium исправления имеют hosted proof. Для переноса тестов canonical
  lifespan + новый модуль39/39, preflight9/9 и test-file pre-commit PASS.
  Manual full run 37512795410/a1 на 7aa CANCELLED: backend planning достиг 60-minute ceiling.
  Frontend aggregate job112519043882 завершился из-за Survived, без найденного provenance failure шага.
- Historical generation54,457/344 и selection4,589/128 не являются свежим inventory.
  V8 feature flags: baseline3/3; exact resolve6/disable13 дают call failures,
  без skips/collection errors; V7 matrix22 не переносится; global score не установлен.
- Frontend preflight source7ac: 43,200 mutants / 565 files / 64 shards;
  digest `e0c3083e3defb06169c8f59897b61c3a46a4dee65c6ae66c9963168ffad66c29`.
  Root и независимый reviewer приняли полный exact planned/report join:
  Killed37,221, Survived4,672, Timeout33, RuntimeError31, NoCoverage1, Ignored1,242.
  Missing/extra/duplicate signatures0; source/input hashes проверены.
  Диагностический viable score88.7101%; обязательный gate FAILED.
  Root независимо подтвердил fresh shard30: 487/487 Killed,10 regions/6 files,
  source/run/attempt/preflight/report hashes. Это только shard-local proof.
- Интегрированы reviewed auth/chat/notification/RLS/cache/analytics regressions,
  generation reuse, planner progress и byte-safe Windows ACL subprocess calls.
  Root: frontend273/273 и crypto46/46; backend1352 PASS +5 subtests и session-policy34/34.
  PostgreSQL RLS enforcement и global mutation credit отсутствуют.
  Initial preflight7/9 сохранён; delta checks и повторный staged pre-commit PASS.
  Links433/433 в обоих режимах, Markdownlint PASS, CSpell9 files/0 issues.
  Focused useAuthApi на1ab:366 mutants =318 Killed/48 Survived,0 Timeout/RuntimeError/NoCoverage;
  86.8852%, gate FAILED. Dry-run1670 PASS; immutable local report d59264c6 сохранён.
  Historical preflight9/9, frontend delta3/3 и документационные gates PASS.
- Historical Matrix `37506190354/a1` на `6d8`: Node Dependency Audit FAILED.
  Локальный audit подтвердил GHSA-wq5f-xc86-pv6w: sharp0.35.4→0.35.5,
  librsvg2.63.2. Frozen install, SVG→PNG smoke и pinned-artifact build PASS;
  npm audit:0 advisories. Hosted Node Audit112439174423 на 7aa SUCCESS (run37512735806/a1).
- Historical UserRepository.get9 Survived: run37403597748/a1, source76cd.
  Root get9: baseline2 PASS/exact1 PASS+1 assertion FAIL; canonical get9/9 PASS.
  PostgreSQL SQL compile-only, не live DB proof. MFA230/profile126 также дали exact RED/GREEN;
  Spotify default UTF-8 эквивалентен: canonical55/55 PASS, без Killed credit.
- Paired benchmark: immutable BASE, threshold1.10, 33 Go/4 Rust metrics по 12 парам.
  Root BASE/candidate proof на source97a не является load/release certification для `7ac`.

## Live-приёмка

- Hosted Live Acceptance `37658678595/a1`: SUCCESS, 18 PASS/2 project skips;
  auth-roles/password-reset desktop/mobile, checkout merge `153ec752` (`c1b` + main `6fa133`).
  Полная продуктовая приёмка этим smoke не закрыта.
- Локальный run `c1b208476-20261007-82671e94`: up144s, 29 running, peak RAM83%.
  Seed/E2E не запускались: startup budget75%/8GiB не выдержан после up.
  Canonical stop PASS: owned running0, 14 томов сохранены; следующий run — на новом SHA.
- Desktop avatar diagnostic R3 завершился без принятых маркеров: counts
  invalid, child exit 1, cleanup verified. Mobile run — NOT RUN / HOLD. Это
  диагностический результат, не pass/fail продукта и не полная live-приёмка.
  Причина неизвестна: child output не сохранён в outer log. До нового runtime
  закрыть descendant lineage и ограниченную классификацию child output.
- Ранний desktop без synthetic admin не учитывается; seed PASS не закрывает R3.
- Полная traceability требований, RU/EN, light/dark, responsive, SSR/PWA,
  accessibility/performance и пользовательское visual approval остаются
  открытыми.
- Historical97a subset:2 PASS/10 FAIL, desktop/mobile; diagnostic avatar не подтверждает ordinary source.
  Cold auth-role failure source76cd остаётся открытым.

## Backup/restore и диагностика

- DR RunId `8b804d4b67a24f2481099d50349ab7d1`, historical source
  `76cd4026dbe241f9a57b7f98488f54856f6b37d9`: paired snapshot был создан,
  но основной executor завершился на `source_snapshot_gate`; target restore
  НЕ НАЧИНАЛСЯ. RTO clock не сбрасывался; logical restore, RPO и RTO не
  подтверждены.
- Отдельная read-only V7 диагностика не стартовала probe из-за template
  проверки image metadata. V8 создал диагностический контейнер, но отклонил
  его до старта на identity validation. Сохранённый V8 receipt остаётся
  `cleanup_complete=false` / `identity_unverified`; менять его задним числом
  нельзя.
  Concrete mismatch: Docker shorthand SecurityOpt и ещё пустой endpoint
  NetworkID в created state. До старта проверять exact HostConfig network
  binding, после старта — endpoint. Probe не запускался.
- Позже точные name и nonce selectors оба вернули отсутствие контейнера
  (Docker exit 0); root сообщил, что start/rm не выполнял. Ограниченная
  Docker-events проверка не дала событий из-за команды с exit 64. Причина
  исчезновения не установлена; acceptance/RCA credit отсутствует. Не было
  backup/restore retry, source snapshot retry или clock reset.
- Root-reviewed V9/controllerV4 прошли39/39 и23/23 offline tests. Один V4
  runtime проверил probe identity, но inner cleanup остался неподтверждённым;
  outer source cleanup PASS, running Docker0. Exact probe ID затем отсутствовал.
  Receipt сохраняет failure; причина отсутствия ещё не установлена.

## Рабочая среда

- Один heavy workload; перед запуском RAM≤75%,free≥8GiB, runtime guard85%/4GiB.
  Последний root snapshot: owned running0, RAM54.3%, free14.55GiB; worktree один.
  Под canonical lifecycle lock удалены 35 exact owned stopped CIDs и три сети.
  Перед удалением V10 verify-existing подтвердил 35 archives/96 resource records;
  11 083 100 160 bytes filesystem archives, без volume/restore/RPO/RTO credit.
  16 volumes/29 images сохранены; remaining target containers/networks0.
  Старый total351/27 предшествует новому stand; global prune не применялся.
- Сохранять env/data/volumes/backups; private evidence: `C:/Temp/ue-orchestrator-1f5a42b2c5ec49c4bc020ea0752bd157`.
  Rescue bundle остаётся private; Git history сохраняется.

## Следующие проверки и ограничения

- Получить exact same-run survivors и новый full-run preflight после переноса;
  затем получить complete same-run backend/frontend aggregates с source/run/
  attempt-bound artifacts до заявления о mutation score.
  Manual full dispatch на `egorribun` ещё не выполнен; проверить acceptance новых inputs API.
  Приватный MFA lifecycle V4 — unrun; mapper V1 требует строковый achievements до controls.
- Получить root-reviewed live diagnostics для desktop/mobile без ослабления
  исходных assertions; доказать auth, API/DB/S3 equality и пользовательские
  сценарии, а не только health/readiness.
- DR RCA: immutable helper/receipts; RPO/RTO не подтверждены до проверки target app.
- Открыты migrations/rollback/BE-02, app restore, SpiceDB graph/search parity,
  WS load, Envoy Gateway/kind, 63 audit IDs, шесть certified GHCR digests,
  resulting-main evidence и выпуск `v1.0.0`.
  Три полных зелёных CI ещё требуются; следующий live-стенд привязывать к новому committed SHA.

Сохранять env, volumes, backups и Git history. Не применять admin bypass,
force-push или менять branch protection. Внешний production, реальные SMTP/push,
физические устройства, CDC и field CWV вне MVP.
