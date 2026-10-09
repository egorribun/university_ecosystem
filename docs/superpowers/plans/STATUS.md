# MVP — оперативный статус

Срез на 2026-10-09 (Europe/Istanbul).
[Мастер-план](MVP_MASTER_PLAN.md), [ТЗ MVP](University_Ecosystem_MVP.md) и
[ADR-047](../../adr/ADR-047-risk-based-quality-policy.md) действуют.
Выпуск `v1.0.0` не подтверждён; goal этого чата ACTIVE.

## Решения и порядок

- Строго `egorribun`, один checkout, существующий
  [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306).
  Root управляет Git; до трёх GPT-6 Luna Max с раздельным ownership.
- Q1/Q4 → Core/product/visual/security/restore → frozen-RC full smoke →
  обычный merge → main checks → существующий producer шести GHCR images → release.
- Q1/Q4 обязательны: тяжёлые lanes scheduled/manual на default branch;
  живой Chromium smoke и fail-closed security/quality gates сохраняются.
  Tier 0 — 100%; прочие coverage floors сохраняются до Q3.
- Владелец разрешил исходные14 readiness-audit contexts и отдельно ровно один
  `Security Audit / Semgrep SAST`: ruleset8335285 изменён91 →76 после review/checks.
  Остальные rules/contexts сохранены; CodeQL blocking, Semgrep в pre-commit.
- Q2/Q3, полный mutation score, три сопоставимых CI runs, kind certification,
  RPO/RTO и deployed BE-02/MIG-PASS — `v1.1`. Один согласованный DB/S3 restore
  с чтением объекта production storage по DB reference обязателен для MVP.
- ADR-006: durable tombstone/WS revoke до commit; rollback может консервативно
  разлогинить siblings. Local failure paths PASS; runtime guarantee открыта.
- ГУУ — внутреннее демо; данные синтетические. Публичный бренд решается отдельно.
  Без embeddings key текстовый поиск доступен, semantic UI выключен,
  direct semantic-only API сообщает недоступность без нулевых векторов.

## Текущий checkpoint: опубликованный SHA14c2 и следующие исправления

- Опубликован `14c2f5ae179dbd2550f06d59bb77aacc742a0b7e` на `egorribun` в PR1306.
  Weather/bookmarks hydration package прошёл обычные hooks/push и preflight10/10.
- Matrix37897949258/a1 завершён за51m07s. Все76 required contexts найдены;
  исходно73 SUCCESS/3 FAILURE. Backend:14337 cases,14238 PASS/99 skips/0 failures/errors.
  После отдельно разрешённого владельцем dismissal только alerts3382/3383
  (`false positive`, audit comment) CodeQL113716129357 подтверждён SUCCESS:
  теперь74 SUCCESS/2 FAILURE — coverage policy и зависимый CI Success.
  Ruleset8335285 до/после идентичен; все76 contexts сохранены. Полного green нет.
- Frontend artifact11602690121 привязан к этому run/head:2 statements/6 branch arms
  пропущены только в AdminAuditFeature. Новый test-only case и navbar boundary tests
  прошли focused29/29; audit coverage68/68 statements,104/104 branch arms,
  17/17 functions,61/61 lines. Это диагностический scoped run, не полный hosted gate.
- Actual Linux Home-empty12/12 записан до global seed. Axe serious/critical0 относится
  только к включённым правилам: private collector отключал часть AA rules без
  согласованного исключения, поэтому полного accessibility PASS нет. Новые Home/general
  copies сохраняют WCAG A/AA и threshold0 без этих overrides; actual run ещё нужен.
  Тот же disabled-rules block удалён из tracked authenticated visual audit;
  Node syntax PASS, WCAG tags/serious-critical threshold и routes сохранены.
  Owner approval отсутствует: на768px найдено перекрытие navbar, а1440px snapshot
  снят до завершения News animation. Drawer до1024px и bounded animation settling
  подготовлены/reviewed; navbar unit checks PASS. Новый visual packet ещё нужен.
- Два existing navbar/footer live specs согласованы с drawer при1024px и tablet
  при1025px; сохранены44px, keyboard/focus/scroll-lock и geometry assertions.
  ESLint/Prettier PASS; число declarations сохранено, actual browser rerun открыт.
- Existing membership-revocation spec теперь проверяет две независимые сессии:
  initial WS delivery обеим → exact room revoke notices → отсутствие следующего
  group message до reload → reconnect/rejoin attempts/REST denial → повторная
  проверка доставки. Room eviction не объявляется transport close; notices/remaining
  delivery обязательны. ESLint/Prettier PASS, actual current-image runtime ещё открыт.
- Fresh source14c2 Core:23 containers/4 one-shot exit0/14 healthy/10 signed loopback
  bindings; up/readiness PASS. Canonical full runner уже выполнил global demo seed.
  Этот superseded Core затем удалён canonical owner-checked teardown: exit0,
  containers/networks/volumes0, private failure evidence/state directory сохранены,
  guardfalse (peak56,6%/free13,83 GiB). Следующий source требует нового Core state.
- Full live pass1 остановлен resource guard при RAM87,3%/free4,05 GiB.
  Итог198 cases отсутствует; cleanup receipt остаётся unconfirmed, несмотря на
  отсутствие записанного PID/его descendants в последующем read-only снимке.
  Private artifacts содержат56 error contexts, включая25 retry folders.
  Повторяющийся React418 и oversized attachment500 разобраны и исправлены ниже;
  подтверждение исправлений на свежем image ещё требуется.
  Все эти ошибки нельзя объявлять доказанным resource cascade. Два full PASS открыты.
- Последующий real SSR→hydrate RED подтвердил timezone15:00/18:00 mismatch и
  различный состав списка около полуночи. DateBullet/EventsCard используют общий
  принцип UTC server snapshot → browser-local post-hydration; final focused28/28 PASS,
  scoped coverage89/89 statements,57/57 branches,37/37 functions,83/83 lines.
  Непрерывный guard: peak57,4%/free13,54 GiB. Это ещё не current-image live PASS.
- Upload RED подтвердил, что TaskGroup оборачивал ожидаемый HTTP413 в ExceptionGroup.
  Исправление восстанавливает только homogeneous HTTP errors, сохраняет mixed/internal
  groups и cleanup. API413/no persisted message, timeout, nested-group/slot и partial
  cleanup проверены27/27 под непрерывным guard (peak57,3%/free13,57 GiB).
- Lockout/email-verification и две PWA ошибки разобраны как defects live specs:
  form-scoped alert, раскрытие email accordion до ожидания ответа, localized title
  и JS marker после reload. Real API/Mailpit/MFA/cache assertions и timeouts сохраняются;
  actual browser rerun ещё нужен. Stories hidden/visible transition на headless shell
  не достигнут;20 cycles/memory plateau и реальная pause/resume остаются открытыми.
- Два credentialless Windows probes дали0/3 реальных visibility transitions на
  default headless shell. Full Chromium channel не запустился (`spawn UNKNOWN`),
  причина OS не доказана. Network requests0; browser configuration не менялась.
  Linux no-network capability probe full Chromium headless и headed/Xvfb завершён:
  каждый20 cycles,0/40 expected visibility pairs, requests0, оба browser/context закрыты,
  exact owned container удалён. Реальная причина ещё исследуется; product PASS нет.
- SEC-03 на текущем Core: persisted production probe PASS (canonical_v2/configured
  key/UTC fields/one PostgreSQL row/logout401); native verifier dispatch PASS.
  Rotation и native signing этими probes не проверялись. SMTP hosted real PG17+
  Mailpit integration job113714252292:1/1 PASS; deadline/cancellation unit tests PASS.
- Current Rust-P3-03 PR-head parity подтверждена: producer113713539701,
  artifact11601332318, все6 Rust inputs совпадают с14c2. Финальные release images,
  signatures/SBOM/provenance и performance claims этим не подтверждаются.
- JUnit14337 cases дают проверенный duration refresh без удаления истории.
  Updater merge-mode ошибочно учитывал bookkeeping полностью skipped файлов;
  RED воспроизведён, minimal fix GREEN17/17. Current cap2 и quality floors сохранены;
  target15m остаётся открытым — одно обновление весов не доказывает этот бюджет.
- Final local fast preflight всего29-file package:10/10 PASS за81,966s; process exit0,
  все35 source/config inputs стабильны, оставшихся recorded owned processes0.
  Непрерывный guard: peak58,9%/free13,07 GiB. Это не hosted coverage/live acceptance.

## Сохранённые CI и package проверки предыдущих checkpoint

- MFA checkpoint `fcdda2a0b33332ace6f5a1f54747ec023f41f94d` опубликован в PR1306;
  обычные commit/pre-push hooks PASS, `.secrets.baseline` повторно staged.
  Matrix37893211061/a1 ещё не подтверждён как полный PASS. Hosted live Core
  run37893210706/a1 FAIL: auth-roles, desktop, React hydration418 при dashboard navigation.
- Weather sessionStorage давал server skeleton/client badge; bookmarks localStorage —
  server0/client1. Real renderToString/hydrateRoot воспроизвёл оба RED; fixes сохраняют
  cache после hydration. Weather120/120 в семи модулях (10,76s), bookmarks55/55
  в шести (10,08s), guardfalse; root/peer review CLEAR. Final package preflight10/10 PASS
  после static probes correction; guardfalse, peak66,7%/free10,58 GiB. Hosted smoke открыт.
- Два P1 GraphQL/Python WS DB fallback при mandatory revocation outage
  воспроизведены20 RED cases; fix и actual GraphQL context проверены121/121 PASS.
  Оба production-модуля100% line/branch; root/независимый P1 review CLEAR.
  Current-SHA runtime и release-level auth/session/data review остаются открыты.
- Stale S3 loopback/provenance assertions исправлены без ослабления guards;
  два полных contract-модуля21/21 PASS. LHCI requested/final origin/path policy
  закрывает protected→login false completeness; только root→dashboard alias.
  RED/GREEN18, adjacent48/48 PASS; actual Lighthouse scores NOT RUN.
- Hosted Matrix37886084026/a1 на679 завершён за45m36s: required76/76,
  73 SUCCESS/3 FAILURE. Все четыре Python shard и их unit/integration aggregators PASS.
  Coverage gate FAIL; отдельный CodeQL FAIL; CI Success FAIL как следствие.
- Все четыре coverage artifacts прошли provenance/hash checks; tested merge
  `e3005c6d9716ccf8407a6b47f2861baecc91c94b` имеет parent679 и byte-identical
  affected source. Diagnostic combine:99,957301%, восемь statements/branch paths
  не покрыты в schedule schema, audit service и embedding event handlers.
  Regression bundle167/167 PASS. Все app/quality/pyproject byte-identical tested merge;
  combine четырёх shards и свежего local coverage даёт100%,0 missing/partial.
  Это diagnostic; свежий hosted full gate ещё не подтверждён, исходный100% floor сохранён.
- Цель blocking CI15 минут открыта: backend cap2 даёт два этапа; terminal shard
  занимает19m54s сам по себе. Полный green JUnit нужен до duration reweighting;
  cap2 сохранён, retries/фиктивные PASS не добавлялись.
- Наfcdda все пять CodeQL analyses PASS. GHAS check113698844614 FAIL только по HIGH
  alerts3382/3383; missing-configuration diagnosis не актуален. Read-only triage
  подтвердил cache-mode query-model gap; отдельное разрешение на запись решения
  по двум alerts на том checkpoint ожидалось. Последующее разрешение и exact dismissal
  выполнены только для3382/3383; текущий результат описан выше.
- Frozen-RC uv/npm/setup-node caching отключено; contracts14/14 PASS.
  Actionlint pinned на reviewed upstream PR745 commit5dc52e8 с проверенным SHA-256;
  unmerged provenance сохранён; repo lint PASS, один unchanged HTTP helper FAIL.
- Go CI/builders1.26.9, fuzz1.27.2, x/net0.60.0 и нужные x/text0.42.0 overrides.
  Windows scan9 modules exit0/reachable vulnerabilities0; unimported OpenPGP
  GO-2026-5932 остаётся в трёх graphs без fixed version. Linux hosted gate отдельный.
- Исторический package679 preflight9/10:337 contracts PASS; Prettier исправлен,
  полный format:check отдельно PASS, повторного10/10 не было. Local Node154/
  cleanup54/WASM555 PASS/1 planned skip/0 FAIL не являются hosted acceptance.
- Package9d44: full preflight10/10 PASS (81,22s), scoped Ruff/check format PASS;
  root/peer review и обычные hooks PASS. Новый hosted coverage gate ещё открыт.
- MFA package сохраняет198 cases/59 specs: real sibling ticket/Go WS остаётся OPEN
  до OTP verify, затем ожидается4401/Session revoked, siblingREST401/current session retained.
  Typecheck/lint/format/3 contracts/198 collection PASS; root/peer review CLEAR.
  Последующий full198 attempt остановлен guard; отдельный runtime outcome остаётся unresolved.

## Сохранённые Core и runtime доказательства предыдущих checkpoint

- Fresh Corefcdda: up exit0/guardfalse, peak74,8%/free8,01 GiB. Schema11/source/
  daemon/projection/readiness PASS;23 containers/4 one-shot exit0/14 healthy/
  10 signed loopback bindings. Admin-only seed выполнен один раз; feeds/schedule/chats пусты.
  Core штатно stopped с сохранением данных на время weather fix; cross-SHA rebind запрещён.
- Исторический SEC-03 persisted probe дошёл до SQL parsing, но итог FAIL: boolean `::text`
  возвращал true/false при parser t/f. Private one-line correction reviewed, ещё не выполнена;
  тогда persisted acceptance оставалась открыта. Этот parser failure superseded последующим
  current14c2 persisted PASS выше; старые native receipts отдельно не заменяли её.
- Исторический Core679 resume exit0/guardfalse, peak80,3%/free6,27 GiB;
  source/schema11/daemon/projection/23 containers/4 one-shot exit0/14 healthy/
  10 signed bindings и edge/backend readiness/Mailpit search PASS.
- Existing admin-only seed выполнен один раз. После stop/start read-only transaction
  подтвердила точный roster10 users/1 admin/2 teachers; news/stories/events/schedules/
  chats пусты. Stop сохранил данные; superseded synthetic Core удалён canonical
  owner-checked teardown: exit0, containers/volumes/networks0; receipts сохранены.
- Image679 main JS168786 bytes/164,83 KiB при raw budget500 KiB; Linux Node24.19.0,
  hashes сохранены. Только raw chunk: transfer budgets/Lighthouse этим не доказаны.
- SEC-03 native679 PASS: genuine extension/builtin verifier, один positive canonical_v2;
  owner/health/inventory неизменны, stderr пуст; API/DB calls0/persistent rows0.
- Official Playwright1.63.0 Linux image/digest и Chromium revision1243 проверены.
  Current container→Caddy probe PASS; Windows→host-network WS refused до credentials/
  browser/captures. Exact idle server удалён, failure receipts сохранены. Internal bridge/
  loopback/native exact-origin exposeNetwork adapter подготовлен; runtime ещё открыт.
  Auth/admin ACL и LHCI build-before-collect исправлены/reviewed; actual runs открыты.
  Последующий bridge/Home14c2 PASS описан выше; expired owned browser server retired.
- Live Chromium collection перечислила198 cases/59 specs,99 desktop+99 mobile;
  на том checkpoint полный run NOT RUN; позднее14c2 attempt был guard-aborted, итог открыт.
  Screenshots/owner approval/Linux baselines, SMTP/MFA,
  logout/revocation/product E2E и coordinated DB/S3 restore ещё открыты.
  Home-empty снимать до global-feed seed; shared feeds не очищать.
- Owned bounded builder: Bake parallelism1/CPU2/RAM4 GiB/swap0, реальные limits
  проверены; сейчас остановлен. Только его11 reclaimable exec.cachemount удалены;
  build layers/cache volume сохранены. Старые de3 images удалены после no-ref proof.
  Default builder/shared caches сохранены.

## Сохранённые предыдущие проверки

- Nullable Schedule PATCH: focused24/OpenAPI18/MSW3 PASS; шесть required storage
  полей игнорируют explicit null, optional clear сохранён. TypeAdapter[str] mypy fix принят.
- Existing live CLI quiesce: focused19 и seven-module1265/1265 PASS; writers stopped,
  healthy PostgreSQL/MinIO/marker/volumes сохранены; external writer check отдельный.
  [Runbook](../../runbooks/database-backup-restore.md) описывает quiesce/resume.
- R02 inventory/hooks165, planner317, auth74, SEC-03 focused98/adjacent221 PASS;
  старые auth/reset18 PASS/2 skips относятся к своим SHA. Harness28/runtime44/preflight10
  PASS. Known P2 taskkill после parent exit не гарантирует orphan containment;
  cleanup-unconfirmed даёт failure; Antigravity не является native Codex hook registration.

## Следующий checkpoint

- Опубликовать проверенный navbar/audit/duration/upload/timezone/spec package
  обычными hooks/push, заморозить source.
  Свежие76 contexts и честное измерение critical path; ожидаемый4401 не считать PASS до runtime.
- Продолжить Linux browser visibility диагностику: реальный переход hidden/visible
  обязателен до проверки story pause/resume; credentialless capability probe не заменяет
  20 actual story viewer cycles.
- Owner-checked Core на clean SHA: Home12 до canonical seed; persisted SEC-03 до
  full E2E из-за bounded audit inventory; два полных последовательных198 passes,
  stop/start/seed persistence, реальные all-topic push/SMTP/MFA/WS scenarios.
- Утвердить actual RU/EN/light/dark/Linux visual packets, затем tracked baselines;
  stories20/reduced motion/a11y и ключевые Lighthouse routes, прочие bundle ratchets.
- Закрыть независимый auth/session/data review, все63 audit IDs и coordinated restore;
  P0/P1 нельзя переносить. Frozen-RC full smoke → ordinary merge/main checks → ровно
  шесть source-bound images/signing/SBOM/provenance/WASM parity → accurate release notes.

## Ресурсы и сохранность

- Один heavy workload: startup RAM≤75%/free≥8 GiB, runtime guard85%/4 GiB.
  Владелец отдельно разрешил исключение только для serial Linux screenshots:
  startup≤80%/free≥6 GiB с1 GiB/2 CPU browser cap; остальные thresholds сохраняются.
- Свежая resource check перед запуском; удалять лишь доказанно owned временные
  ресурсы. Чужие процессы/env/data, shared Docker/WSL/caches и backups сохранять.
  Weekly Codex usage92%/remaining8%; free reset1 доступен, не использован.
- Git history/migrations/private rescue bundle сохранить; session logs и superseded
  snapshots не возвращать в indexes. Новые branch/worktree не создавать.
