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

## Последний опубликованный package и CI

- Coverage checkpoint `9d44f2b3e52190dadf1171e0fee1a08a2f3797b9` опубликован в PR1306;
  обычные commit/pre-push hooks PASS, `.secrets.baseline` повторно staged.
  Matrix37891315450/a1 выполняется; последующий MFA acceptance package проверен локально.
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
  Это diagnostic; новый hosted gate ещё не запущен, исходный100% floor сохранён.
- Цель blocking CI15 минут открыта: backend cap2 даёт два этапа; terminal shard
  занимает19m54s сам по себе. Полный green JUnit нужен до duration reweighting;
  cap2 сохранён, retries/фиктивные PASS не добавлялись.
- На679 все пять CodeQL analyses PASS. GHAS check113676546272 FAIL только по HIGH
  alerts3382/3383; missing-configuration diagnosis не актуален. Read-only triage
  подтвердил cache-mode query-model gap; отдельное разрешение на запись решения
  по двум alerts ожидается. Suppressions/dismissal не добавлялись.
- Frozen-RC uv/npm/setup-node caching отключено; contracts14/14 PASS.
  Actionlint pinned на reviewed upstream PR745 commit5dc52e8 с проверенным SHA-256;
  unmerged provenance явно сохранён. Repo lint PASS, один unchanged HTTP helper FAIL.
- Go CI/builders1.26.9, fuzz1.27.2, x/net0.60.0 и нужные x/text0.42.0 overrides.
  Windows scan9 modules exit0/reachable vulnerabilities0; unimported OpenPGP
  GO-2026-5932 остаётся в трёх graphs без fixed version. Linux hosted gate отдельный.
- Package679 preflight9/10:337 contracts и остальные gates PASS; единственный
  Prettier failure исправлен и полный format:check отдельно PASS. Все10 повторно
  не запускались. Ранние10/10 receipts относятся к своим прежним packages.
  Local Node154/cleanup54 и WASM555 PASS/1 planned skip/0 FAIL — локальные receipts,
  не свежая hosted acceptance на679.
- Package9d44: full preflight10/10 PASS (81,22s), scoped Ruff/check format PASS;
  root/peer review и обычные hooks PASS. Новый hosted coverage gate ещё открыт.
- MFA package сохраняет198 cases/59 specs: real sibling ticket/Go WS остаётся OPEN
  до OTP verify, затем ожидается4401/Session revoked, siblingREST401/current session retained.
  Typecheck/lint/format/3 contracts/198 collection PASS; root/peer review CLEAR, runtime NOT RUN.

## Core и фактические runtime доказательства

- Core679 поднят и затем возобновлён в том же owned state; resume exit0/guardfalse,
  peak80,3%/free6,27 GiB. Source/owner schema11/daemon/projection проверены;
  23 containers, четыре one-shot exit0, все14 healthchecks healthy,10/10 loopback
  bindings совпадают с подписанными. Edge/backend readiness/Mailpit search PASS.
- Existing admin-only seed выполнен один раз. После stop/start read-only transaction
  подтвердила точный roster10 users/1 admin/2 teachers; news/stories/events/schedules/
  chats пусты. Stop сохранил данные; после нового SHA superseded synthetic Core
  удалён canonical owner-checked teardown: exit0, containers/volumes/networks0.
  Receipts сохранены; cross-SHA rebind запрещён, следующий Core будет свежим.
- Actual frontend image679: main JS168786 bytes/164,83 KiB при existing raw budget
  500 KiB; Linux Node24.19.0, asset/image hashes сохранены приватно. Это только main
  raw chunk; transfer budgets/Lighthouse scores этим не доказаны.
- SEC-03 native dispatch679 PASS: genuine extension/builtin verifier, один positive
  canonical_v2 вызов; owner/health/inventory до/после неизменны, stderr пуст.
  API/DB calls0/persistent rows0; persisted audit/signing/rotation остаются открыты.
- Official Playwright1.63.0 Linux image/digest и Chromium revision1243 проверены.
  Credentialless host-network probe достиг подписанного Caddy. Chromium не запускался;
  idle server удалён после доказательства ownership, image сохранён.
  Home/push/general collectors и minimal auth/admin invocation прошли review;
  LHCI private adapter подготовлен, пропущенный build найден review и исправляется.
- Live Chromium collection перечислила198 cases/59 specs,99 desktop+99 mobile;
  browser execution NOT RUN. Screenshots/owner approval/Linux baselines, SMTP/MFA,
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

- Опубликовать reviewed MFA package обычными hooks/push; заморозить source.
  Свежие76 contexts и честное измерение critical path; ожидаемый4401 не считать PASS до runtime.
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
  Запрошено, но ещё не разрешено исключение только для serial Linux screenshots
  startup≤80%/free≥6 GiB с1 GiB/2 CPU browser cap; остальные thresholds сохраняются.
- Свежая resource check перед запуском; удалять лишь доказанно owned временные
  ресурсы. Чужие процессы/env/data, shared Docker/WSL/caches и backups сохранять.
  Weekly Codex usage83%/remaining17%; free reset1 доступен, не использован.
- Git history/migrations/private rescue bundle сохранить; session logs и superseded
  snapshots не возвращать в indexes. Новые branch/worktree не создавать.
