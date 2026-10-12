# MVP — оперативный статус

Контрольная точка: 2026-10-12 07:55 UTC. Основания приёмки — [мастер-план](MVP_MASTER_PLAN.md), [ТЗ](University_Ecosystem_MVP.md), [ADR-047](../../adr/ADR-047-risk-based-quality-policy.md) и [audit ledger](../../audits/INDEX.md).
База проверенного checkpoint PR #1306 на egorribun: 59c161a497706ce24198d09647347c91a3cd6c4f, tree bbc0ef955c2b9f61059c9a397a0f644304c80062. Source receipt integration-source-59c161a4-root-20261012.json связывает 77 hashes; SHA-256 55BA9A6217C8F27704E7E52C36A6D7BA9F63DDEB6163E8ACA4DBFF1482F0B605. Выпуск v1.0.0 не подтверждён.

## Опубликованный source и required checks

- Strict76 snapshot для 59c, 2026-10-12 07:28:25 UTC: 74 SUCCESS, 2 FAILURE, 0 PENDING/SKIPPED/ABSENT/INVALID. Receipt ci-required76-59c161a4-final-20261012-1791790094487.json, SHA-256 E81068335D77AF7C1907B8291FD61258084673A85D4DF877013D5C49C5966435. Все четыре backend shards прошли. Блокируют Coverage & Quality Policy Gate и зависимый CI Success.
- Полный frontend coverage artifact 11730706068, run 38212994906/attempt 1: statements 19438/19440, functions 4622/4623, branches 13926/13927. Все пропуски относятся к SSR/no-window subscription в frontend/src/components/Layout.tsx:16. Artifact source — официальный PR merge 0bc56b2a6d07a2c9d1b5ffd38bf42afb0ae7f7cf с parents 6fa133b57f62c554162876d4e6d8349f8060fce9 и 59c; его tree и Layout bytes совпадают с head. Head и merge SHA различаются, source identity проверена.
- Локальный кандидат поверх 59c содержит тест этой SSR-ветки и минимальный MFA transport fix: configured Axios POST сохраняет allowlisted bypass и возвращает data/error без изменения общего retry policy. Настоящий transport test сначала подтвердил RED: generated path сбрасывал skipRateLimitQueue в false. После исправления 103 frontend tests PASS, включая transport/wrapper, Layout, queue/retry, CSRF и owned-session cleanup. Guard mfa-layout-admission-focused-green-59c161a4-working-root-20261012-7cdc772141694ce8931716d2fa5dbe0f.guard.json: source stable, exit 0, owned processes 0.
- Closed-schema Story/PWA/registration diagnostics прошли 36 focused Python tests и 12 Node admission contracts. Диагностика выводит только ограниченные категории/счётчики при failure; assertions, admission cadence, retries и quality floors сохраняются. Это локальные проверки кандидата, не runtime acceptance. Ordinary hooks и required checks следующего SHA ещё не подтверждены.
- Q1/Q4 интегрированы; разрешённые removals ограничены 14 contexts и Security Audit / Semgrep SAST. CodeQL остаётся blocking, Semgrep — в pre-commit; остальные 76 contexts и действующие coverage floors сохранены. Q2/Q3 — v1.1. Целевой PR CI wall time 15 минут пока не подтверждён.

## Core и продуктовые проверки

- На чистом 59c Core up, admin/demo seed и readiness прошли; state C:/Temp/ue-live-acceptance/run-3bdbc54b-f8d7-38ff-e476-f19c55f738a9, project ue-live-6238ecb45b6fc649. Inventory: 19 persistent running / 4 completed init containers. Ранее IPAM освободили удалением ровно четырёх пустых owned networks; data volumes и caches сохранены.
- Cohort32 на 59c, 06:50:28–07:00:58 UTC: 8 PASS / 24 FAIL, без skipped/flaky/interrupted/did-not-run. G1 — 8/4, G2 — 0/14, G3 — 0/6. Batch summary SHA-256 DB43A8E76E96D09CE2C41E46BC0738035F1F1683D626F222402FF409842B8283; guard 73213945807D3EB992B4E225225026D29A98E4B2F2CEC30C00441FA2700FC1B1 подтвердил source stable и owned processes 0. Два полных Core прогона ещё не выполнены.
- G1: Story DOM/listener totals расходятся при совпадающих per-target buckets; PWA не наблюдает смену controller. Production leak не доказан. G2: 12 registration failures без сохранённого класса причины и 2 topic-preflight failures из-за отсутствующих preferences. Новый диагностический кандидат ещё требует живого прогона.
- G3: локально исправлены fresh authenticated profile check после MFA и выбор непустого replay alert; production MFA transport regression прошла RED→GREEN. Свежая живая проверка этих исправлений pending; точный frame desktop email-OTP failure не сохранился и не заявляется.
- Read-only DB probe 07:45:57 UTC: все десять seed accounts имеют preferences; одна active synthetic-shaped live-notification-sender запись их не имеет. Receipt notification-prefix-counts-59c161a4-root-1791791156046.json, SHA-256 5B25C182A7AA7C48F653E5FC6F17486BB0FC9E6F41BFFE93EA8706B40E614D6D. Форма имени не доказывает ownership или причину остатка; данные не изменялись.
- Home12 ddbbc84d — единственный утверждённый visual пакет. News/Events/Schedule current-source captures и owner approval pending; Linux baselines не обновлялись. Предыдущий Profile Chromium responsive PASS и старые visual/hosted snapshots не являются приёмкой нового source.

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
