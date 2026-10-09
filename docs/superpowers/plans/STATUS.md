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

- Code checkpoint `12f72031eeab3bd09f13aac4fa45fa4457f3bf5a` отправлен обычным push;
  HEAD=origin/egorribun=PR1306 head на этом checkpoint; checkout после push чистый.
  Обязательные commit/pre-push hooks PASS, `.secrets.baseline` повторно staged.
- Этот follow-up восстановил шесть nullable Schedule PATCH inputs: обязательные
  storage поля получают только ненулевые updates, optional clear сохраняется.
  Focused24/OpenAPI18/MSW3 PASS; semantic schema diff ровно на этих шести полях.
- Frozen-RC uv/npm caching отключено, включая setup-node automatic caching.
  CodeQL `37876450427/a1` завершил все пять language analyses успешно,
  но required GHAS check113646340681 оставляет два HIGH alerts3382/3383.
  Current instances относятся к PR merge94a6a6b; cache-mode:none уже действует.
  Query-model gap проверяется отдельно; gate остаётся открытым.
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
- Свежий Matrix37876450739/a1 на12f: snapshot76 —61 success/6 pending/2 failure/7 absent.
  MD047 в STATUS исправлен, local markdownlint PASS; свежий hosted gate ещё ожидается.
  Предыдущий shard1:3908 PASS/17 skips/2 stale assertions; retarget13/13 PASS,
  независимый review CLEAR. Fresh hosted gate и бюджет15 минут ещё не подтверждены.
- Core00b с COMPOSE_PARALLEL_LIMIT=1 завершился build exit1, guard не сработал:
  peak60,1%, free12,68 GiB. Caddy требует ca-certificates20260611-r0,
  Alpine3.24 предоставляет20260909-r0; hosted OwnedLive37873409126/a1 подтвердил.
  E2E/seed не запускались. Owner-checked stop/teardown exit0;
  postcheck подписанного project: containers0/volumes0/networks0.
  CA pin20260909-r0: focused contract и install в том же builder image PASS;
  Git pin/digests сохранены, четыре owned image tags удалены, shared cache сохранён.
- Core12f остановлен guard при87,3%/free4,03 GiB во время параллельной Bake build.
  Caddy apk errors нет; COMPOSE_PARALLEL_LIMIT=1 не ограничил Bake solver.
  Owner stop/teardown exit0; containers0/volumes0/networks0, четыре owned tags удалены.
  Ограниченный временный builder готовится; E2E/seed/restore ещё не запускались.
- Private SEC-03 probe проверен независимо CLEAR, native dispatch snippet подготовлен;
  runtime/key rotation не доказаны. Visual collectors подготовлены, screenshots ещё нет.
  Пустой Home требует fresh Core до global-feed seed; admin-only existing seeder
  использует roster-only synthetic prerequisites; private three-run operation peer CLEAR.
  Shared feeds не очищать, новый stand ради screenshot не создавать.

## Проверенные предыдущие checkpoints

- На0fc7af03 hosted CI обнаружил nullable PATCH, shared caches, Go security,
  ShellCheck и два stale WASM contract blockers; исправления включены в00b.
  Core0fc достиг readiness, но up guard остановил при85,4%/free4,64 GiB.
  E2E/seed не запускались; owner stop/teardown и zero-resource postcheck PASS.
- Refresh851c4763: OwnedLive37848497910/a1 SUCCESS18 PASS/2 planned skips,
  artifacts0 — только auth/reset smoke. Matrix37848498285/a1 отменён root
  после сохранения snapshot; Handlebars4.7.10 policy/audit/graph локально PASS.
- R02 inventory/hooks/fixtures review CLEAR165 PASS; planner317 PASS/5 subtests;
  auth fail-closed74 PASS, SEC-03 focused98/adjacent221, metadata112/UI7 PASS.
  Source tests не заменяют runtime acceptance.
- Старые OwnedLive37843216072/a1 и37767058529/a1:18 PASS/2 planned skips,
  artifacts0, только их SHA. Profile15ad90aac:4/4; stop/start444ed сохранил
  hashes/secrets/volumes. Полная current-SHA Core traceability остаётся открытой.
- Harness verifier28/runtime44/preflight10 PASS; real gate-state hash неизменен.
  Windows taskkill не гарантирует orphan descendant после parent exit: явный
  cleanup failure без PASS; Job Object containment — backlog.
  Antigravity hooks вызываются явно, native Codex registration отсутствует.
- Kind helper727eecab smoke/teardown PASS без app deployment; certification v1.1.
  DR76cd4026 остановлен на source_snapshot_gate: target restore не начинался.
  Immutable failure receipts сохранены; code/runbook не доказывают restore.
- Mutation inventory43200/backend54450, global score отсутствует; diagnostic debt.
  Six-image main-only producer/source-bound consumer реализованы;
  actual release/signing/SBOM/provenance/WASM parity ещё требуется подтвердить.

## Открытые этапы и ближайший checkpoint

- Завершить Caddy/cache fixes, focused checks, обычные hooks/push; проверить свежие76
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
