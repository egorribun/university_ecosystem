# MVP — оперативный статус

Срез на 2026-10-09 (Europe/Istanbul).
[Мастер-план](MVP_MASTER_PLAN.md) — действующий план;
[ТЗ MVP](University_Ecosystem_MVP.md) задаёт продуктовые границы,
[ADR-047](../../adr/ADR-047-risk-based-quality-policy.md) — переход качества.
Выпуск `v1.0.0` пока не подтверждён; goal этого чата ACTIVE.

## Решения и порядок

- Строго `egorribun`, один checkout,
  [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306).
  Root управляет Git; до трёх GPT-6 Luna Max с раздельным ownership.
- Q1/Q4 → Core/product/visual/security/restore → frozen-RC full smoke →
  обычный merge → main checks → существующий producer шести GHCR images → release.
- Q1/Q4 обязательны: тяжёлые lanes scheduled/manual на default branch;
  Chromium smoke, security и остальные fail-closed gates сохраняются.
  Tier 0 — 100%; прочие действующие coverage floors сохраняются до Q3.
- Владелец разрешил ровно 14 contexts и отдельно `Security Audit / Semgrep SAST`:
  ruleset8335285 обновлён 91 → 76 после review/checks; свежий GET подтвердил
  остальные contexts и правила. CodeQL blocking, Semgrep в pre-commit.
- Q2/Q3, полный mutation score, три сопоставимых CI runs, kind certification,
  RPO/RTO и deployed BE-02/MIG-PASS — `v1.1`. Один согласованный DB/S3
  restore с проверкой объекта через DB reference обязателен уже для MVP.
- ADR-006: durable tombstone/WS revoke до commit; rollback может консервативно
  разлогинить siblings. Local failure paths PASS, runtime guarantee ещё открыта.
- ГУУ — внутреннее демо; данные синтетические. Публичный бренд решается отдельно.
  Без embeddings key текстовый поиск доступен, semantic UI выключен,
  direct semantic-only API сообщает недоступность без нулевых векторов.

## Текущий source и проверки

- Опубликованный checkpoint `de3e10c20b169d7439cbcd9ea72fd15ea9998c98` проверен
  в PR1306; следующий package требует отдельного свежего hosted CI.
  На de3 исправлена mypy-аннотация `TypeAdapter[str]` без изменения runtime;
  hosted Backend Type Check и Pre-commit PASS. Обязательные commit/pre-push hooks
  предыдущего push PASS, `.secrets.baseline` повторно staged.
- Принятые 00b/12f восстановили шесть nullable Schedule PATCH inputs: обязательные
  storage поля получают только ненулевые updates, optional clear сохраняется.
  Focused24/OpenAPI18/MSW3 PASS; semantic schema diff ровно на этих шести полях.
- Frozen-RC uv/npm caching отключено, включая setup-node automatic caching.
  На de3 все пять CodeQL language analyses PASS, но required GHAS
  check113654781071 FAIL по HIGH alerts3382/3383 на PR merge dae6c37e.
  Read-only triage подтвердил cache-mode query-model gap; отдельное разрешение
  владельца на запись решения по этим двум alerts ожидается. Gate открыт.
  Job-level cache-mode:none и workflow/security contracts14/14 PASS.
  Actionlint временно pinned на reviewed upstream PR745 commit5dc52e8, архив проверен
  по SHA-256; pre-commit/CI одинаковый source, Go1.26.9, actual repo lint PASS.
  Upstream parser/cmd и прочие helpers PASS; один unchanged HTTP helper test FAIL.
  Pin unmerged, не released provenance; suppressions/dismissal не добавлялись.
- Go CI/builders1.26.9, fuzz1.27.2, x/net0.60.0 и нужные x/text0.42.0 overrides.
  Language floor1.26.4/runtime images сохранены; независимый review CLEAR.
  Windows scan всех9 modules exit0, imported/reachable vulnerabilities0;
  unimported OpenPGP GO-2026-5932 есть в трёх graphs, fixed version отсутствует.
  Linux hosted проверка остаётся отдельным gate.
- Integration preflight10/10 PASS, включая337 contracts: peak52,3%/free15,17 GiB.
  Focused Node154/cleanup54 PASS; полный WASM555 PASS/1 planned skip/0 FAIL.
  Auth collectors отзывают только принадлежащие им sessions, проверяют401,
  сохраняют primary/cleanup failures; recovery/multiple contexts peer review CLEAR.
- Existing live CLI получил quiesce только для current-SHA in-place Core:
  writers остановлены, healthy PostgreSQL/MinIO и marker/volumes сохраняются.
  Owner/source/daemon/projection/container identity проверяются до/после.
  External writers требуют отдельной операторской проверки.
  Focused19 и полный seven-module CLI1265/1265 PASS; peak47,7%/free16,62 GiB.
  Исторические v4/v5 fixtures исправлены; current-MINIO fail-closed сохранён.
  [Runbook](../../runbooks/database-backup-restore.md) описывает quiesce/resume.
- Финальный preflight Caddy/cache package10/10 PASS; peak54,0%/free14,65 GiB.
  Obsolete services.command lint exception удалён, прочие правила сохранены.
- Terminal Matrix37879139844/a1 на de3: required76 —69 success/4 failure/3 skipped,
  pending0/absent0; длительность45m42s, цель15 минут не достигнута.
  Failures: Python shards2/3, GHAS CodeQL и CI Success; downstream coverage,
  integration и unit aggregators skipped. Shard2:3971 PASS/43 skips/1 stale S3
  assertion; shard3:4152 PASS/12 skips/1 stale helper-checkpoint assertion.
  Оба failures локально воспроизведены. Последующий package сохраняет exact live
  loopback S3 binding и retarget всех provenance полей к reviewed immutable00b
  с Go1.26.9; два полных contract-модуля21/21 PASS, root review CLEAR.
  Свежий hosted gate для этого package ещё требуется.
- Ранние Core00b/12f не прошли build/resource guard; все их owned resources удалены.
  Caddy CA pin20260909-r0 проверен реальной установкой и contract test;
  COMPOSE_PARALLEL_LIMIT=1 не ограничивает Bake solver. Для de3 создан
  отдельный owned builder: parallelism1, CPU2, RAM4 GiB,
  swap0; реальные cgroup limits проверены. Default builder/shared cache сохранены.
- Core на de3 успешно поднят: up exit0, guardfalse, peak82,5%/free5,56 GiB.
  Owner schema11/source/daemon/projection и все23 container identities проверены;
  четыре one-shot exit0, все14 running healthchecks healthy, 10/10 actual loopback
  bindings совпадают с подписанными значениями. Edge /healthz, backend readiness,
  DB/migrations/cache/storage/SpiceDB health и Mailpit search PASS; SMTP delivery,
  persisted audit, logout/revocation и product E2E этим не доказаны.
- На этом fresh Core existing admin-only seed PASS: admin/roster/authorization
  готовы, news/stories/events/schedules/chats остались пустыми. Home screenshots
  ещё не сняты. Перед изменением source owner-checked stop exit0, running0;
  teardown exit0, postcheck containers0/volumes0/networks0. Private receipts
  сохранены; owned builder остановлен, его cache пока нужен следующему build.
- SEC-03 native dispatch на de3 PASS: настоящий extension/builtin verifier,
  ровно один positive canonical_v2 вызов; owner/health/inventory до/после неизменны.
  Первый private probe FAIL из-за не-UTF-8 disposable key; исправлен только
  оператор, immutable failure receipt сохранён. API/DB calls0, persistent rows0;
  это не proof persisted audit, native signing или key rotation.
- Два P1 GraphQL/Python WS DB fallback при mandatory revocation outage
  воспроизведены20 RED cases; fix и actual GraphQL context проверены121/121 PASS.
  Оба production-модуля100% line/branch coverage; root и независимый review CLEAR.
  Public WS идёт через Go ws-hub; Python handler mounted.
  Current-SHA runtime и независимый финальный review ещё требуются.
- LHCI requested/final origin/path policy исправлена: protected→login не считается
  выполненным маршрутом; только root→dashboard alias разрешён. RED/GREEN18 cases,
  adjacent48/48 PASS. Existing collector/auth hook сохранены, реальные scores NOT RUN.
- Полный live Chromium набор собран:198 cases/59 specs,99 desktop+99 mobile;
  collection PASS не является browser execution. Visual collectors готовы,
  screenshots/owner approval/Linux baselines и DB/S3 restore ещё не выполнены.
  Пустой Home снимать до global-feed seed; shared feeds не очищать.

## Проверенные предыдущие checkpoints

- Принятые nullable PATCH/cache/Go/ShellCheck/WASM fixes сохранены; старый Core0fc
  после resource guard полностью очищен. Старые auth/reset smokes18 PASS/2 skips
  относятся только к своим SHA и не закрывают current-SHA Core traceability.
- R02 inventory/hooks165, planner317, auth74, SEC-03 focused98/adjacent221 PASS;
  profile15ad90aac4/4, stop/start444ed сохранил hashes/secrets/volumes.
  Эти source/historical checks не заменяют текущую runtime acceptance.
- Harness28/runtime44/preflight10 PASS; gate-state hash сохранён. Windows taskkill
  не гарантирует cleanup orphan после parent exit; Job Object — backlog.
  Antigravity lifecycle explicit, native Codex hooks не зарегистрированы.
- Kind/global mutation closure — v1.1; прежний DR не дошёл до restore, receipts сохранены.
- Six-image main-only producer реализован; actual release/signing/SBOM/provenance
  и WASM parity ещё требуется подтвердить.

## Открытые этапы и ближайший checkpoint

- Завершить auth fail-closed и текущие contract fixes, обычные hooks/push; проверить свежие76
  required contexts, critical-path15 минут и default-branch scheduled/manual activation.
- На clean frozen SHA поднять один fresh Core; Home-empty до canonical seed;
  ТЗ2–13: auth/MFA, messenger/group delivery/topics push, profile/settings/admin,
  SSR/PWA/i18n/RU-EN/a11y. Два последовательных Core passes плюс stop/start/seed persistence.
- Реальный visual packet light/dark/RU-EN/390/768/1440 и targeted360/1024;
  owner approval, затем approved Linux baselines; bundle/Lighthouse,
  stories20 cycles/reduced motion. Синтаксис collector не является capture PASS.
- Независимый auth/session/data review, ADR-006 guarantees/limits и все63 audit IDs;
  P0/P1 нельзя переносить. Один coordinated DB/S3 snapshot/isolated restore,
  чтение восстановленного объекта production storage по DB reference.
- Frozen-RC full smoke → обычный merge/main checks → ровно шесть source-bound images
  с verified run/SHA/attempt/manifest/digests/signing/SBOM/provenance → accurate release notes.

## Ресурсы и сохранность

- Один heavy workload; admission RAM≤75%/free≥8 GiB, runtime guard85%/4 GiB.
  Свежая resource check перед следующим запуском; owned process tree только.
- Удалять лишь доказанно принадлежащие работе ненужные synthetic resources;
  чужие env/data/volumes/backups/processes, shared Docker/WSL/caches сохранять.
- Git history/migrations/private rescue bundle сохранить; session logs и старые
  snapshots не возвращать в indexes. Worktree/branch не создавать.
