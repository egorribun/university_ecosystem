# MVP — оперативный статус

Контрольная точка: 2026-10-12 10:36 UTC. Основания приёмки — [мастер-план](MVP_MASTER_PLAN.md), [ТЗ](University_Ecosystem_MVP.md), [ADR-047](../../adr/ADR-047-risk-based-quality-policy.md) и [audit ledger](../../audits/INDEX.md).
Опубликованный PR #1306 на `egorribun`: `8295b807d8448ef9d4490f4d8c9bfccddaab9ca1`, tree `62730ed4c2cf956570a0c71ec72e1cf181ce0480`. Source receipt `integration-source-8295b807-root-20261012.json` связывает 80 hashes; SHA-256 `403027ADE425E8DA555DEDD6A0B5221D4E5B539D996B11CE016CFC4CCC1ECBDB`. Следующий локальный кандидат описан ниже; его live acceptance и required checks ещё не подтверждены. Выпуск v1.0.0 не подтверждён.

## Опубликованный source и required checks

- Ordinary commit/push hooks опубликованного source прошли. MFA transport использует configured Axios POST с типизированным `ApiRequestConfig`, сохраняет allowlisted bypass и data/error; общий retry policy не менялся. Локальный transport RED→GREEN, focused frontend/AST/contracts и полный TypeScript check прошли. Это локальное доказательство, не live acceptance.
- Strict76 snapshot для `8295b807`, 2026-10-12 10:28 UTC: 65 SUCCESS, 7 PENDING, 4 ABSENT, 0 FAILURE/NEUTRAL/SKIPPED/INVALID. Receipt `ci-required76-8295b807-progress-20261012-1791800891741.json`, SHA-256 `B9C751DED3F57813F84B679200C50A428ADBDE193415279F7CDC1FFF1C92FFAB`. Все 76 результатов ещё не получены; coverage gate и CI Success pending.
- Четыре frontend shards прошли. Artifact `11736106552` shard 2 подтверждает SSR/no-window ветку `Layout.tsx:16`: statements 3/3, functions 1/1, branches 2/2. Официальный PR merge `8f891a674af260666a57425865afc5acef0cbe31` имеет parents `6fa133b57f62c554162876d4e6d8349f8060fce9` и текущий head; tree и Layout bytes совпадают. Это не подтверждение полного merged coverage gate.
- Q1/Q4 интегрированы; разрешённые removals ограничены 14 contexts и `Security Audit / Semgrep SAST`. CodeQL остаётся blocking, Semgrep — в pre-commit; остальные 76 contexts и действующие coverage floors сохранены. Q2/Q3 — v1.1. Целевой PR CI wall time 15 минут пока не подтверждён.

## Core и продуктовые проверки

- На чистом `8295b807` Core up, admin/demo seed и readiness прошли; state `C:/Temp/ue-live-acceptance/run-5bb1e30d-14bc-4995-b4d3-4412cc520727`, project `ue-live-cf7f10902821fada`. Inventory: 19 persistent / 4 init containers. Windows browser cache launch/close проверен без загрузок; это не Linux visual proof.
- Cohort32, 09:29:16–09:40:38 UTC: 10 PASS / 22 FAIL, без skipped/flaky/interrupted/did-not-run. G1 — 9/3, G2 — 0/14, G3 — 1/5. Batch summary SHA-256 `6D729111F73A4AD0282D7EBF635BC9129D95FFD3C8BA97D0076698186AFD0526`; guard SHA-256 `CC7C221CF83DD45A6B4636C55B7D5784731F2AC2AD8CBB83B5C39220AA9A8DD0`: source stable, stopReason null, owned processes 0, peak RAM 72.64%, free ≥8.70 GiB. Full double run не допущен.
- G1: PWA diagnostics показывают controller change и загруженный изменённый bundle; локальный кандидат ожидает production reload перед assertions. Story mobile PASS; desktop DOM totals уменьшаются после первого hidden/visible цикла, per-target listener buckets совпадают. Production leak не доказан. Warm-up приведён к измеряемому lifecycle, 20 циклов и строгие assertions сохранены; новая живая проверка pending.
- G2: click-only registration callback заканчивается до наблюдения matching request; следующий fail-closed quiet drain не помещается в прежний deadline. Нулевой счётчик не доказывает отсутствие HTTP. Локальный кандидат ожидает реальный ответ до выхода из шести callbacks в пяти specs; лимиты, deadlines и fail-closed сохранены.
- G3: mobile TOTP PASS. Email MFA обоих проектов получает enablement HTTP 200, затем не видит `email_mfa_enabled_at` в свежем профиле. Найдена потеря поля в приватном `UserOut` mapper: regression test воспроизвёл RED; после копирования поля 10 schema/mapper tests PASS. Публичный `UserPublicOut` поле не раскрывает. Живая проверка исправления pending.
- Email verification mobile получает stale-code HTTP 429; общий per-IP verify budget 5/600s — возможная причина, но статус сам её не доказывает. Кандидат G3 различает submit-click/response-wait, фиксирует фактический TOTP login status и ограниченный numeric Retry-After для stale-code 429 без повторов или ожидания; production quotas, assertions и case deadlines сохранены.
- G1/G2 прошли 25 Node contracts, полный TypeScript check, ESLint/Prettier и Ruff без ошибок. Guard contracts SHA-256 `527D2D4D2DD283481A595D35E10D9E80F485E149E20CDC65B3F1849FE381E236`, lint/types `4A7889553D2FB9E1EDBCD122A404F5217F9CF2638085A943816BF95AACE2781A`, mapper GREEN `44AEDDD93D82623AB728C8E62461BE449933079C6B51051EF7CA51B1D131F865`. Результаты локальные; ordinary hooks нового пакета и live acceptance pending.
- G3 прошёл 29 Node contracts, 66 focused Python parser tests, полный TypeScript check, ESLint/Prettier и Ruff без ошибок. Guard SHA-256 `1558FF8F58E4D3ED46CA5F08721BD520E6166E93A43E2D13C029DDF441C73BD6`: source stable, exit 0, owned processes 0. Это локальная проверка кандидата; причины оставшихся runtime failures ещё не подтверждены.
- Core штатно остановлен 09:51:41 UTC; stop guard SHA-256 `8CA43AEEFE07954E2A6ABAC7D9F679965DEF8851D8BD500288DC72FC7404E907`: PASS, source stable, owned processes 0. Затем после signed-owner и zero-endpoint проверки удалены ровно три пустые сети этого стенда; число сетей 31→28, все 23 контейнера, тома, образы и owner/key bytes сохранены. Cleanup guard SHA-256 `187166FBF7EE262E98BCEA7C453B5109906E02B48F4D55891B71CDB1A8A6C6F0`. Остановленный стенд с удалёнными сетями не использовать для нового прогона.
- Home12 `ddbbc84d` — единственный утверждённый visual пакет. News/Events/Schedule current-source captures и owner approval pending; Linux baselines не обновлялись. Старые visual/hosted snapshots не являются приёмкой нового source.

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
