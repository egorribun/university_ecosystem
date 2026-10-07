# MVP — оперативный статус

Срез на 2026-10-08 (Europe/Istanbul). [Мастер-план](MVP_MASTER_PLAN.md)
задаёт приёмку; [ТЗ MVP](University_Ecosystem_MVP.md) — продуктовые границы.
Работа безопасно приостановлена по просьбе пользователя. Выпуск `v1.0.0` не подтверждён.

## Контрольная точка

- Работа ведётся на `egorribun` в одном checkout и [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306).
  База изменений — `27e0fbfc5`; закрытый demo и full mutation run — на `a3f339514`.
  Reviewed regressions и generation reuse интегрированы; exclusions/пороги сохранены.
  Три GPT-6 Luna Max остановлены; owned workloads отсутствуют, root проверил интеграцию.
- Full-backend workflow, benchmark, WebKit/avatar/DM fixes интегрированы;
  локальные контракты не заменяют hosted/live приёмку.

## Hosted CI и мутации

- Matrix `37668629672/a1` на `a3f`: CANCELLED; backend unit shard1 FAILED.
  Причина: stale urllib3 floor assertion; corrected focused backend5/5 PASS.
  Full mutation `37670438144/a1` запущен с `backend_scope=full`; stats shard2/8 FAILED.
  Backend aggregate FAILED; stats RCA: stale urllib3 assertion, исправлен в `a028`.
  Это не итоговый score. PR checks нового source проверяются отдельно.
- Root auth82/82, event contracts40/40, live contracts145/145 PASS;
  fast preflight10/10 PASS. PR live `37684359401/a1` FAILED до Docker:
  stale seed signature regex исправлен; требуется новый hosted run.
  Focused366: initial AuthContext failure, outcomes отсутствуют; baseline94/94 PASS.
  Related dry-run GREEN после policy staging; exact case collection не доказана, RCA открыт.
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
- Historical UserRepository.get9 Survived: run37403597748/a1, source76cd.
  Root get9: baseline2 PASS/exact1 PASS+1 assertion FAIL; canonical get9/9 PASS.
  PostgreSQL SQL compile-only, не live DB proof. MFA230/profile126 также дали exact RED/GREEN;
  Spotify default UTF-8 эквивалентен: canonical55/55 PASS, без Killed credit.
- Cert-manager/local CA: independent review clear, offline kind204/204 PASS.
  Kind teardown11/11 PASS; binary/checksum проверены. Runtime kind/TLS ещё не запускался.

## Live-приёмка

- Hosted Live Acceptance `37668628464/a1` на `a3f`: SUCCESS.
  Полная продуктовая приёмка этим smoke не закрыта.
- Demo завершён: project `ue-live-8c2a21f71d21a9a6`.
  State: `C:/Temp/ue-live-acceptance/run-a3f339514-20261007-9e5093bd`.
  Attempt1: исчерпаны Docker подсети; attempt2: up111s PASS, peak RAM76%.
  Canonical seed PASS; БД: active student, пароль fixture, profile/group проверены;
  news10, stories15, schedule28, chats2, events10 +2 будущих demo events.
  Student login — в `frontend/tests/e2e-live/fixtures.ts`; secret values здесь нет.
  Browser UI не проверен: CUA policy check unavailable; обход не выполнялся.
  По разрешению пользователя выполнены stop и teardown: 35 containers,
  14 volumes, 3 networks удалены; тестовые данные не сохранялись.
  Старый desktop avatar R3: invalid counts/exit1; mobile NOT RUN, без acceptance credit.
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
  Пользователь разрешил удалить все аналогичные ue-live стенды и тестовые данные.
  После проверки Compose ownership, daemon и references удалены ещё 386 stopped
  containers, 188 volumes (включая 16 доказанных anonymous mounts), 26 networks.
  Удалены 142 локальных ue-live image tags. Fresh verification: containers0,
  ue-live volumes0/networks0/image tags0; shared base images не удалялись.
  Global prune не применялся; filesystem archives не доказывают backup/restore.
- Private evidence: `C:/Temp/ue-orchestrator-1f5a42b2c5ec49c4bc020ea0752bd157`.
  Чужие env/data/volumes/backups сохраняются; временный state-dir deletion
  отклонён automatic review, обход не выполняется.
  Rescue bundle остаётся private; Git history сохраняется.

## Следующие проверки и ограничения

- Следующие очереди: news schema14 Survived (shard50), Outbox process_batch31;
  затем получить complete same-run backend/frontend aggregates с source/run/
  attempt-bound artifacts до заявления о mutation score.
  Full dispatch API принят; не создавать повторный run без причины. MFA263/307:
  baseline81/81, каждый exact mutant даёт одну assertion failure. Mapper16 controls:
  #117 pins исправлены; root backend/seed45/45 и auth635/635, typecheck/lint PASS;
  flaky config static8/8 и root fast preflight10/10 PASS; global mutation gate открыт.
- Получить root-reviewed live diagnostics для desktop/mobile без ослабления
  исходных assertions; доказать auth, API/DB/S3 equality и пользовательские
  сценарии, а не только health/readiness.
- DR RCA: immutable helper/receipts; RPO/RTO не подтверждены до проверки target app.
- Открыты migrations/rollback/BE-02, app restore, SpiceDB graph/search parity,
  WS load, Envoy Gateway/kind, 63 audit IDs, шесть certified GHCR digests,
  resulting-main evidence и выпуск `v1.0.0`.
  Три полных зелёных CI ещё требуются; следующий live-стенд привязывать к новому committed SHA.

Сохранять чужие env, volumes, backups, private evidence и Git history. Не применять admin bypass,
force-push или менять branch protection. Внешний production, реальные SMTP/push,
физические устройства, CDC и field CWV вне MVP.
