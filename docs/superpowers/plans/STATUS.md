# MVP — оперативный статус

Срез на 2026-10-08 (Europe/Istanbul). [Мастер-план](MVP_MASTER_PLAN.md)
задаёт приёмку; [ТЗ MVP](University_Ecosystem_MVP.md) — продуктовые границы.
Работа возобновлена по просьбе пользователя. Выпуск `v1.0.0` не подтверждён.

## Контрольная точка

- Работа ведётся на `egorribun` в одном checkout и [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306).
  Три GPT-6 Luna Max работают в раздельных областях; root проверяет интеграцию и ресурсы.
- Full-backend workflow, benchmark, WebKit/avatar/DM fixes интегрированы; локальные контракты не заменяют hosted/live приёмку.

## Hosted CI и мутации

- PR@`444ed`: live FAILED до Docker (stale alert contract исправлен/root150 PASS); WS-Hub HandleRegister ns/op ratio1,146, gate1,10, RCA открыт.
- Full `37699104150/a1`@`ec69`: generation transport3483 files PASS; universe54 450, stats8/8 PASS.
  Run CANCELLED; planner59m20s, planning без end marker; plan отсутствует, backend execution0/128, global score открыт.
  Full `37670438144/a1`: execution0/128, stats7/8; shard2 stale urllib3 исправлен в `a028`, score отсутствует.
  Frontend artifacts64/64; aggregate FAILED на Survived27:108, global gate открыт.
- Root outbox9/9, news14/14 +UI23/23, ranked27/27, SSR/cache88/88 PASS;
  preflight10/10, kind243/243, ranked28/28, compliance9/9 и auth83/83 PASS; local exact275 и lockout2/4/9/10 RED.
  Root chat63/63, gateway middleware/config и Linux race PASS; pinned Go lint0 issues после complexity fix.
  Helm wiring13/13 +275 contracts и doc delta PASS; planner reuse37 +5 subtests/150 contracts PASS.
  CRD helper прошёл K3 prerequisites; приложение в kind ещё не развёрнуто.
  Local exact259/314/123/278/56/140/44/45/121 RED; global gate открыт. PR live `37684359401/a1` FAILED до Docker:
  stale seed signature regex исправлен; требуется новый hosted run.
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
- Manual full run 37512795410/a1 на 7aa CANCELLED: backend planning достиг 60-minute ceiling.
  Frontend aggregate job112519043882 завершился из-за Survived, без найденного provenance failure шага.
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
- Historical UserRepository.get9 Survived: run37403597748/a1, source76cd; root canonical get9/9 PASS.
  MFA export5 эквивалентен COUNT(*): код упрощён, без Killed credit.
  PostgreSQL SQL compile-only, не live DB proof. MFA230/profile126 также дали exact RED/GREEN;
  Spotify default UTF-8 эквивалентен: canonical55/55 PASS, без Killed credit.
- K3/e874a81e778d helper@`727eecab`: create/prepare/repeat/preflight/smoke/CA/teardown PASS.
  Inventory20/Helm revisions1 неизменны; app routes заблокированы parity; `C:/Temp/ue-kind-acceptance-k3-e874a81e778d/receipts`.

## Live-приёмка

- Hosted Live Acceptance `37668628464/a1` на `a3f`: SUCCESS; это только smoke.
- Core@`0229`: up1, readiness23/24; Mailpit читался через неверную переменную порта; seed/E2E не запускались.
  Mailpit/common-Git owner-key fixes@`f281`: root PS57 PASS/1 POSIX skip; hosted live37716509827/a1 SUCCESS.
- Core@`f281`: up0, status0 без изменения state; profile desktop/mobile2 PASS/2 FAIL на error alert.
  Backend PUT500: nested education dict присваивается ORM relation; profile_detail не сохраняется.
  RED→GREEN: root49 PASS, logic/mapper line+branch100%; DTO/schema54 и UI28 PASS, OpenAPI synced; preflight10/10 PASS.
  Peak RAM70%,free≥9,533GiB; stop0/teardown0, owned containers/volumes/networks/image tags0.
  Evidence: `C:/Temp/ue-core-review-f2818079c-e2e-v1/root-cleanup-f281.v1.json`; полный live gate открыт.
- Core@`444ed09e0`: up0; profile2 PASS/2 FAIL: scoped alert проходит, следующий отказ на списке mutation paths; persistence/reload ещё не подтверждены.
  Smoke18 PASS/2 planned skips до и после stop/start; read-only baseline16 users/10 news/10 events, hashes/4 secret files/6 volumes совпали.
  Stop0/teardown0, owned containers/volumes/networks/image tags0; teardown2147 subprocess calls; Core/full acceptance остаётся открытой.
  Evidence: `C:/Temp/ue-core-review-444ed09e0-e2e-v1/root-smoke-restart-summary.v1.json` и `root-cleanup-444ed09e0.v1.json`; first-smoke scope исправлен sidecar.
  Full mutation37723031168/a1@`520850`: stats0/8 и5/8 FAILED, aggregate incomplete; frontend выполняется, RCA stats открыт; schema100% только локально.
- Demo `ue-live-8c2a21f71d21a9a6` завершён; state: `C:/Temp/ue-live-acceptance/run-a3f339514-20261007-9e5093bd`.
  Attempt1: исчерпаны Docker подсети; attempt2: up111s PASS, peak RAM76%.
  Canonical seed PASS; БД: active student, пароль fixture, profile/group проверены;
  news10, stories15, schedule28, chats2, events10 +2 будущих demo events.
  Browser UI не проверен: CUA policy check unavailable; обход не выполнялся. По разрешению
  пользователя stop/teardown удалили35 containers/14 volumes/3 networks и тестовые данные.
  Старый desktop avatar R3: invalid counts/exit1; mobile NOT RUN, без acceptance credit.
- Полная traceability, RU/EN, light/dark, responsive, SSR/PWA, accessibility/performance и visual approval открыты.
- Historical97a subset:2 PASS/10 FAIL, desktop/mobile; diagnostic avatar не подтверждает ordinary source.
  Cold auth-role failure source76cd остаётся открытым.

## Backup/restore и диагностика

- DR RunId `8b804d4b67a24f2481099d50349ab7d1`@`76cd4026dbe241f9a57b7f98488f54856f6b37d9`: paired snapshot создан,
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
  Пользователь разрешил удалить все аналогичные ue-live стенды и тестовые данные.
  После проверки Compose ownership, daemon и references удалены ещё 386 stopped
  containers, 188 volumes (включая 16 доказанных anonymous mounts), 26 networks.
  Удалены 142 локальных ue-live image tags; containers/volumes/networks/image tags0, shared base images сохранены.
  Global prune не применялся; filesystem archives не доказывают backup/restore.
- Private evidence: `C:/Temp/ue-orchestrator-1f5a42b2c5ec49c4bc020ea0752bd157`.
  Чужие env/data/volumes/backups сохраняются; временный state-dir deletion
  отклонён automatic review, обход не выполняется.
  Rescue bundle остаётся private; Git history сохраняется.

## Следующие проверки и ограничения

- Profile contract/collector исправлены: root150/150 и preflight10/10 PASS; bounds root114/schema100%, runner1127/Node11; следующий live, затем chart parity;
  затем получить complete same-run backend/frontend aggregates с source/run/
  attempt-bound artifacts до заявления о mutation score.
  Historical MFA263/307 exact RED; global mutation gate открыт.
- Owned Docker inspect: batches≤64/full IDs/exact join с прежними guards; CLI probe23/23, root1134/1134 и preflight10/10 PASS.
  Дальше committed-SHA profile/live и API/DB/S3 equality; затем измерить teardown.
  Runtime savings и полная продуктовая приёмка пока не заявлены.
- DR RCA: immutable helper/receipts; RPO/RTO не подтверждены до проверки target app.
- Открыты migrations/rollback/BE-02, app restore, SpiceDB graph/search parity,
  WS load, Envoy Gateway/kind, 63 audit IDs, шесть certified GHCR digests,
  resulting-main evidence и выпуск `v1.0.0`.
  Три полных зелёных CI ещё требуются; следующий live-стенд привязывать к новому committed SHA.

Сохранять чужие env, volumes, backups, private evidence и Git history. Не применять admin bypass,
force-push или менять branch protection. Внешний production, реальные SMTP/push,
физические устройства, CDC и field CWV вне MVP.
