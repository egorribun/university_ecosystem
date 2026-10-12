# MVP — оперативный статус

Контрольная точка: 2026-10-12 03:57 UTC. Основания приёмки — [мастер-план](MVP_MASTER_PLAN.md),
[ТЗ](University_Ecosystem_MVP.md), [ADR-047](../../adr/ADR-047-risk-based-quality-policy.md)
и [audit ledger](../../audits/INDEX.md).
Сводка отражает опубликованный source 05b и проверенные локальные результаты кандидата; выпуск v1.0.0 не подтверждён.

## Опубликованный source и проверки

- Последний опубликованный source на egorribun, PR #1306: 05b57d5cf048365124ac376ae5592ac21bfbad6c,
  tree cf3272085518f95f7877666da8e9811bb75033c0. Обычные commit/push hooks прошли.
  Source receipt фиксирует 69 уникальных входных hashes и 42 changed files.
  Рабочая ветка — egorribun; используется один checkout, Git остаётся под управлением root.
- Точный снимок 76 required checks для 05b на 03:07 UTC: 69 SUCCESS, 0 PENDING,
  4 FAILURE, 3 SKIPPED, 0 ABSENT, 0 INVALID. Две прямые первичные required failures —
  Alembic и Frontend unit shard 2/4; два failed summaries — Frontend aggregate и CI
  Success. Все три первичные причины workflow уже имели failures до этого snapshot:
  Alembic/Squawk сообщил о двух ALTER случаях, frontend shard не загрузил
  owned-session-cleanup.test.mjs из-за TypeError: The URL must be of scheme file,
  а отдельный backend integration shard 0 сообщил RuntimeError: quiet-hour wall-clock
  conversion теряет per-value TIMETZ offsets. Backend shard 0 сам не является отдельной
  строкой 76 required checks; его связанный aggregate/skip effect отражён в снимке.
  Это точный snapshot на 03:07 UTC до локальных исправлений, не результат следующего
  source SHA.

- В локальном migration candidate SQL render/Squawk 2.44 подтвердил: baseline=2,
  candidate=0, намеренно внедрённое несвязанное негативное правило=1 caught.
  Это показывает, что правило сохраняет обнаружение постороннего случая; это не hosted CI.
- Migration policy/integrity suite прошёл 27/27. Scoped PostgreSQL/asyncpg rerun
  прошёл 9/9 и подтвердил удаление ровно owned test container и временного env-file.
- owned-session-cleanup.test.mjs прошёл 24/24 Vitest tests; Prettier подтвердил
  неизменённые candidate bytes. Реальный Node contract для admission helper прошёл 11/11.
  Полный TypeScript и полный frontend ESLint (0 errors/warnings) прошли; Prettier изменённых файлов и backend Ruff
  также прошёл. Эти scoped checks не заменяют полную unit suite или свежие required checks.
- Локальный RED через HTTP и read-replica proxy подтвердил отказ audit write.
  Затем GET /users/me и GET /users переведены на writable default FromDishka dependency;
  regression прошёл 1/1, auth-cookie selection — 9/9. В этом run stderr=0, source stability
  подтверждена, children=0. Это локальная проверка, не fresh hosted check.
- Для migration остаётся обязательной проверка на новом source/Core, включая настоящий
  DND/profile HTTP 200. Scoped PostgreSQL результат проверяет codec и migration,
  но не live HTTP путь.
- Все required CodeQL rows в 05b snapshot имеют SUCCESS. Отдельный исторический f3 alert
  query относился к PR synthetic merge e5047bc8, не к main; в проверенном PR ref open
  alerts было 0. Для 05b свежий alert query не выполнялся. В историческом query у 3384
  latest instance был fixed на 07742145, но top-level state API это не возвращал;
  3382/3383 — прежние отдельно разрешённые false-positive dismissals. Нужны свежие
  обязательные checks на следующем source SHA.
- Q1/Q4 уже интегрированы. Ранее разрешены ровно 14 removals и отдельно
  Security Audit / Semgrep SAST; все остальные правила и contexts сохранены.
  CodeQL остаётся blocking, Semgrep — в pre-commit. Q2/Q3 и mutation/nightly policy
  gates не продвигаются из v1.1. Quality floors и Tier 0 100% не снижались.
## Core и продуктовые проверки

- Core на 05b прошёл up: state C:\Temp\ue-live-acceptance\run-87a0640e-ac37-41a7-91e5-4b1fac6ae46b,
  project ue-live-ae71e7cc6d3304fa. В этой сессии не выполнялись новые seed/readiness/cookie
  probes. В 02:37 UTC штатный stop подтвердил 23 остановленных контейнера и сохранение
  шести volumes; receipt core-stop-before-ci-fixes-05b-root-v3-dfb9a69325a1495cb3e1cb23724a53d5.guard.json.
- На 05b нет нового полного targeted cohort. Последний cohort 32 относится к f3:
  G1 8 PASS / 4 FAIL, G2 0 PASS / 14 FAIL, G3 0 PASS / 6 FAIL; без skips, flakes,
  interruption или source drift. Это диагностика, не продуктовая приёмка.
- Фокусированный Story run на f3 дошёл до строгого cycle-0 DOM сравнения и упал в обоих
  проектах. Listener totals warm→cycle 0: desktop 445→452, mobile 456→457. Buckets показали
  document visibilitychange +1, keydown +1 и window other +4; documentTree без изменения.
  Это наблюдение, не attribution конкретным callback. Readiness change остаётся
  непроверенным live на 05b; exact DOM/heap/20-cycle/hidden-tab assertions не менялись.
- Исторический News V7 capture завершился capture_validation exit 9, cleanup не подтверждён.
  12 diagnostic sidecars содержали layout geometry; opacity=0, PNG=0. Четыре aborted avatar
  requests были на 1440px. News не принят и baseline не обновлён; для нового source требуется
  новый capture и отдельное owner approval.
- Четыре native permission cases на прежнем source прошли; это не подтверждает subscription
  или delivery.
- Traceability inventory: Home12 ddbbc84d уже утверждён владельцем для layout; это
  одобрение сохраняется, а оставшиеся News/Events/Schedule visuals требуют новых
  current-source captures и отдельного owner approval. Existing Events keyboard/ARIA
  coverage проверяет поведение; ожидаемый Events12 visual должен также дать reviewable
  evidence вертикального центрирования активного tab.
  Profile в ТЗ §7 требует адаптивную сетку. Отдельный mocked browser scenario
  frontend/tests/e2e/profile-responsive.spec.ts (SHA-256
  47ba87360324808b302c08810bf5b4a10f2e64c052e7f1665bab5fd5b269b2d3) прошёл Chromium
  1/1 на 390/768/1440px; guard profile-responsive-split-mocked-working6-05b-root-v3-85c3a850bd7c4b4684aa61a07266dc27.guard.json
  SHA-256 82b057e3a7b1f6e17e064df8d3b038b3c5f31058aaa4b8a07f8a20e9a4f3194e подтвердил
  source stability, 0 children, stderr=0, peak RAM 57.88% и 13.40GiB free. Firefox/WebKit
  projects остаются pending final matrix.
  Отдельный существующий Profile screenshot run на Windows завершился 14% diff до новых
  geometry assertions; причина не установлена. Screenshot spec восстановлен к parent
  версии, baseline не обновлялся, Profile visual acceptance не заявлена.
  Source inventory охватывает все 63 audit IDs; per-ID RC dispositions остаются pending,
  owner acceptance не заявлена. В ограниченном frontend inventory не найден WebAuthn/passkey flow; это
  соответствует явному требованию ТЗ §1 убрать аппаратные security keys.

- Открытые traceability/visual confirmations остаются частью закрытия ТЗ 2–13; не считать их
  выполненными только по наличию компонента или отдельного unit test.

## Следующие критерии MVP

1. Пройти ordinary commit/push hooks и свежие 76 required checks; поднять новый Core
   на опубликованном чистом source. Пройти targeted cohort 32, проверить DND HTTP 200,
   Story/PWA, первый paint News и оставшиеся реальные сбои. PASS между SHA не переносить.
2. На неизменном source пройти два последовательных full Core runs: каждый 198 tests,
   190 PASS и ровно 8 ожидаемых SKIP. Завершить seed persistence через stop/start.
   Каждое применимое требование ТЗ 2–13 связать со сценарием/результатом/SHA либо
   обоснованной ручной проверкой; пройти mocked Firefox/WebKit/mobile-WebKit lane.
3. Завершить visual acceptance News, Events и Schedule: 36 изображений (12 на раздел),
   RU/EN, light/dark, 390/768/1440. Утверждён только Home пакет `ddbbc84d`;
   новые pixels требуют отдельного owner approval до обновления Linux baselines.
   Проверить 360/1024 risk cases, accessibility/reduced motion/axe.
   Main JS budget <500 KB и key-route Lighthouse pass — отдельные gates;
   authenticated LHCI остаётся 21 sample (7 routes × 3).
4. Провести один согласованный paired DB/S3 backup/restore в изолированные цели;
   прочитать объект по restored DB reference, проверить bytes/hashes и сохранность исходной среды.
5. Закрыть final-source SEC-07 и RUST-P3-03 evidence, независимый auth/session/data
   review и ADR-006 ordering: tombstone/WebSocket revocation до commit,
   rollback sibling logout. Переклассифицировать все 63 audit IDs на RC,
   не оставлять P0/P1 security открытыми. Исторические 60 CLOSED / 2 DECLINED /
   1 OPEN не являются RC dispositions. Bounded SEC-07 review на `829a1e78`
   не выявил конкретного дефекта; это не runtime/final-source приёмка.
6. Заморозить code/dependencies/config/docs и пройти финальные Core scenarios,
   backup/restore и full smoke на RC. Новое поведение после freeze требует
   нового кандидата и повторения затронутой приёмки.

SEC-03 historical source review CLOSED: владелец подтвердил только ephemeral CI/demo use;
это само по себе не указывает на необходимость production rotation. Перед любой migration
сохраняемых подписанных записей нужны protected consistent backup и read-only inventory;
учесть оба DataAccessLog legacy verifiers и hash-linked/nullable StoredEvent rows, выполнять
migration атомарно и fail closed. См. [audit ledger](../../audits/INDEX.md#findings-ledger).

После frozen RC: ordinary merge и свежие resulting-main push checks согласно
`quality/release-required-checks.json`. Готовый producer должен опубликовать ровно
шесть images (backend/frontend/gateway/ws-hub/file-processor/caddy) с Trivy,
signatures, SBOM/provenance и WASM parity. Проверить actual published digests
и связь с source/run/attempt manifest; затем tag/release notes `v1.0.0`.
Kind certification, три comparable CI runs, RPO/RTO, Q2/Q3 и global mutation score остаются
в v1.1, но разовый paired restore обязателен для MVP. Бренд ГУУ — только внутреннее
синтетическое демо до отдельного решения о публичном использовании.

Ограничения ресурсов: перед одним heavy workload RAM≤75% и free≥8GiB; остановка при
RAM≥85% или free<4GiB. Исключение только для serial Linux screenshots: старт≤80%/≥6GiB,
browser≤1GiB/2CPU; guard остановки неизменен. Owned builder≤4GiB/2CPU/no swap.
Сохранять Core data и полезные caches; не очищать чужие процессы, Docker/WSL или global caches.
Git history, migrations и environment/data state сохранять; приватный rescue bundle держать отдельно.
Не восстанавливать superseded audits или одноразовые session prompts.
