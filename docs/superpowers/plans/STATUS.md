# MVP — оперативный статус

Срез на 2026-10-06 (Europe/Istanbul). [Мастер-план](MVP_MASTER_PLAN.md)
задаёт приёмку; [ТЗ MVP](University_Ecosystem_MVP.md) — продуктовые границы.
Goal активен. Выпуск `v1.0.0` не подтверждён.

## Контрольная точка

- Работа ведётся на `egorribun` в одном checkout и [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306).
  Исходный checkpoint — `c421c0e5128339f9ab519846086c0a56138304b7`.
  В `6d8` перенесены RuntimeFeatureOverrides, в `7be1` — auth/audit/session
  regressions; `107845` обновил sharp/libvips; `1ab` — RLS; `c421` — cache/session.
  Сейчас — MFA/profile/get regressions и эквивалентное UTF-8 упрощение; exclusions/пороги сохранены.
  три GPT-6 Luna Max готовят приватные пакеты для независимой проверки.
- В checkpoint вошли full-backend mutation workflow, immutable benchmark
  activation, WebKit focus fix, строгая avatar resource identity и DM
  reconnect/replay regressions. Локальные контракты не заменяют hosted/live
  приёмку.
- Source-map-js 1.2.2 закрывает GHSA-68fv-2mgg-jv7q; frozen install/audit/build
  прошли на предыдущем checkpoint. Четыре transitive npm deprecation warnings
  остаются открыты.

## Hosted CI и мутации

- CodeQL check `112329936293` и CodeQL Advanced run `37481003467` для `7ac`
  завершились SUCCESS. Check сообщал: “No new alerts in code changed by PR”.
- Matrix run `37481003822/a1`: event source `7ac`; artifact producer —
  PR merge `a43b6b471b6d964093b994eb9c08b436be6015ad`.
  Проверенные backend groups 1/2 дали соответственно 29 Killed / 7 Survived и 32 Killed /
  4 Survived. Это реальные survivors, а не runner failure; остальные группы
  и полный inventory ещё не закрыты. Полный viable score не установлен.
- Manual full run `37481732603/a1`: frontend shard jobs завершились 64/64
  SUCCESS, но итоговый aggregate FAILED и aggregate artifact отсутствовал.
  Backend preflight завершился ошибкой до запуска 128 backend execution shards;
  пропущенные shards не являются результатами мутаций. Глобальный viable score
  не установлен.
- Для source7ac локальные затронутые contracts359/359 и Helm retry29/29 PASS;
  CodeQL/Chromium исправления имеют hosted proof. Для переноса тестов canonical
  lifespan + новый модуль39/39, preflight9/9 и test-file pre-commit PASS.
  Manual full run 37512795410/a1 на 7aa выполняется; полный hosted proof ещё требуется.
- Historical backend generation54,457/344 и incremental selection4,589/128
  не подменяют свежий inventory. Принятый перенос сохраняет None/default,
  явные True/False, disable из True и None, reset и неизвестные флаги.
  Root повторил V8 baseline3/3 и exact resolve6/disable13 controls:
  2 PASS/1 call failure и 1 PASS/2 call failures, без skips/collection errors.
  V7 matrix22 не перенесён на изменённый V8; global score не установлен.
- Frontend preflight source7ac: 43,200 mutants / 565 files / 64 shards;
  digest `e0c3083e3defb06169c8f59897b61c3a46a4dee65c6ae66c9963168ffad66c29`.
  Root и независимый reviewer приняли полный exact planned/report join:
  Killed37,221, Survived4,672, Timeout33, RuntimeError31, NoCoverage1, Ignored1,242.
  Missing/extra/duplicate signatures0; source/input hashes проверены.
  Диагностический viable score88.7101%; обязательный gate FAILED.
  Root независимо подтвердил fresh shard30: 487/487 Killed,10 regions/6 files,
  source/run/attempt/preflight/report hashes. Это только shard-local proof.
- Root повторил auth signing-key #62: baseline65/65, exact mutant64 PASS/
  1 call failure; HMAC missing-IP #48: baseline PASS/exact call failure.
  Session ownership #417: baseline18/18, exact mutant17 PASS/1 call failure.
  Replay #723/#735/#827: baseline40/40, каждый exact mutant39 PASS/1 call failure.
  RLS reload #255: root baseline PASS/exact call-phase ValueError; typed fixture,
  canonical chat80/80 и strict targeted mypy PASS, без реальной PostgreSQL.
  Canonical suites: frontend123/123, session/WS/persistence81/81, MFA/profile260/260 и audit67/67 PASS.
  Root подтвердил exact WS4, session382/390 и persistence1037 RED/GREEN; global credit отсутствует.
  Focused useAuthApi на1ab:366 mutants =318 Killed/48 Survived,0 Timeout/RuntimeError/NoCoverage;
  86.8852%, gate FAILED. Dry-run1670 PASS; immutable local report d59264c6 сохранён.
  Preflight9/9 и последующие frontend delta checks3/3, pre-commit,
  links в обоих режимах, Markdownlint и configured CSpell PASS.
- Historical Matrix `37506190354/a1` на `6d8`: Node Dependency Audit FAILED.
  Локальный audit подтвердил GHSA-wq5f-xc86-pv6w: sharp0.35.4→0.35.5,
  librsvg2.63.2. Frozen install, SVG→PNG smoke и pinned-artifact build PASS;
  npm audit:0 advisories. Hosted Node Audit112439174423 на 7aa SUCCESS (run37512735806/a1).
- Historical UserRepository.get9 Survived: run37403597748/a1, source76cd.
  Root get9: baseline2 PASS/exact1 PASS+1 assertion FAIL; canonical get9/9 PASS.
  PostgreSQL SQL compile-only, не live DB proof. MFA230/profile126 также дали exact RED/GREEN;
  Spotify default UTF-8 эквивалентен: canonical55/55 PASS, без Killed credit.
- Paired benchmark workflow сохранил immutable BASE comparator, threshold 1.10,
  33 Go и 4 Rust metrics по 12 парам. Root проверял BASE/candidate archive и
  сравнение на предыдущем source97a; это не нагрузочная или release
  certification для `7ac`.

## Live-приёмка

- Обычный Compose stand `7ac` был поднят с 29 healthy services, seed прошёл.
  Stand штатно остановлен; данные и evidence сохранены.
- Desktop avatar diagnostic R3 завершился без принятых маркеров: counts
  invalid, child exit 1, cleanup verified. Mobile run — NOT RUN / HOLD. Это
  диагностический результат, не pass/fail продукта и не полная live-приёмка.
  Причина неизвестна: child output не сохранён в outer log. До нового runtime
  закрыть descendant lineage и ограниченную классификацию child output.
- Ранний desktop до seed не учитывается: synthetic admin credential отсутствовал. Demo seed затем PASS; это
  устранило только prerequisite, но не закрыло R3.
- Полная traceability требований, RU/EN, light/dark, responsive, SSR/PWA,
  accessibility/performance и пользовательское visual approval остаются
  открытыми.
- Historical ordinary97a subset:2 passed/10 failed, desktop/mobile;
  diagnostic-image avatar PASS не подтверждает ordinary source.
  Original cold auth-role failure source76cd остаётся открытым.

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
  Последний root snapshot: running Docker0, RAM38.5%; основной worktree один.
  Удалены только три доказанно пустые retired networks; global prune не применялся.
- Только основной worktree. Не удалять уникальные env/data/volumes/backups.
  Private evidence: `C:/Temp/ue-orchestrator-1f5a42b2c5ec49c4bc020ea0752bd157`.
  Rescue bundle остаётся private; Git history сохраняется.

## Следующие проверки и ограничения

- Получить exact same-run survivors и новый full-run preflight после переноса;
  затем получить complete same-run backend/frontend aggregates с source/run/
  attempt-bound artifacts до заявления о mutation score.
- Получить root-reviewed live diagnostics для desktop/mobile без ослабления
  исходных assertions; доказать auth, API/DB/S3 equality и пользовательские
  сценарии, а не только health/readiness.
- Продолжить DR RCA через отдельные immutable версии helper/receipts. Исторические
  receipts и их failure status не перезаписывать; не объявлять восстановление
  или RPO/RTO до успешной проверки target app.
- Открыты migrations/rollback/BE-02, app restore, SpiceDB graph/search parity,
  WS load, Envoy Gateway/kind, 63 audit IDs, шесть certified GHCR digests,
  resulting-main evidence и выпуск `v1.0.0`.
  Три полных зелёных CI ещё требуются; GitHub PR/webhook incident задерживает PR HEAD обновление.

Сохранять env, volumes, backups и Git history. Не применять admin bypass,
force-push или менять branch protection. Внешний production, реальные SMTP/push,
физические устройства, CDC и field CWV вне MVP.
