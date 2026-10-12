# MVP — оперативный статус

Контрольная точка: 2026-10-12 06:29:17 UTC. Основания приёмки — [мастер-план](MVP_MASTER_PLAN.md), [ТЗ](University_Ecosystem_MVP.md), [ADR-047](../../adr/ADR-047-risk-based-quality-policy.md) и [audit ledger](../../audits/INDEX.md).
Опубликованный source snapshot и база текущего пакета PR #1306 на egorribun: 04fdd84c23bf7e021dc16af5ab0a48101d6aabc2, tree 89eb1fd49cb8dadf9b5f82547ddd9055c2e38941. Source receipt связывает 75 входных hashes и 9 changed files; ordinary hooks прошли. Выпуск v1.0.0 не подтверждён.

## Опубликованный source и required checks

- Проверенный snapshot 76 required checks, 2026-10-12 05:19:01 UTC: 71 SUCCESS, 2 FAILURE, 3 SKIPPED, 0 PENDING, 0 ABSENT, 0 INVALID. Receipt ci-required76-04fdd84c-resume-20261012-1791782331289.json, SHA-256 3F1EDAE7398679AC58A50CD36C712734F10AA5041F6A5D52B1DCEEE7DC243A58; source SHA — 04fdd84c. Единственные failure rows — backend shard 0 и агрегат CI Success; все остальные backend shards прошли. Ранее блокировавшие Alembic и Frontend shard теперь SUCCESS.
- В Run pytest shard 0 summary: 2 failed, 4479 passed, 30 skipped. tests/test_auth_cookie_flow.py::test_profile_audit_writes_use_default_session_when_read_component_is_read_only падает в setup: get_password_hash сообщает Password must include: symbols; secrets.token_urlsafe(24) не гарантирует все обязательные password classes.
- tests/test_route_dependency_inventory.py::test_repository_route_dependency_inventory_is_current_and_has_no_mixed_owner падает на assert violations == [] из-за двух изменённых строк: app.api.users:get_users:GET: и app.api.users:me:GET:/me. В 04fdd обе DB зависимости переключены на default writable FromDishka; checked-in inventory устарел.
- Текущий локальный working packet содержит 6 файлов поверх опубликованного 04fdd: auth-cookie fixture с гарантированными password classes, обновление двух route inventory rows, password-change rollback regression и frontend deadline-clock fix. Combined focused suite — 31/31 PASS в 06:29:17 UTC под guard backend-focused-security-working7-04fdd84c-root-v4-e1cb156cc18e4bc5bf2d3f3c9b46b814.guard.json (source stable, exit 0, stderr 0, owned processes 0); Ruff для 2 Python-файлов PASS, форматирование без изменений; Frontend ESLint — 0 warnings в 06:14:40 UTC. Node contract 12/12 PASS в 06:02:14 UTC, Playwright clock probe v2 GREEN в 06:04:31 UTC под guard actual-playwright-clock-probe-v2-working5-04fdd84c-root-v2-2f1c89f68ccc4f2090ddc10c4e938737.guard.json. Первый ordinary commit attempt остановил detect-secrets на generated-password false positive. После UUID-backed генерации detector проходит без waivers или baseline исключений; остальные ordinary hooks ожидаются. Пакет локальный, ещё не опубликован; strict76 остаётся историческим snapshot 04fdd, hosted CI/runtime acceptance не заявляются, PASS между SHA не переносится.
- Предыдущие scoped local доказательства остаются привязаны к своим SHA: migration render/Squawk 2.44 дал baseline 2 -> candidate 0, а внесённое отрицательное правило было поймано; migration suite 27/27, PostgreSQL 9/9, owned-session cleanup 24/24 и Node admission contract 11/11. Это не заменяет текущие required checks и не переносится между SHA.
- Q1/Q4 интегрированы; разрешённые removals ограничены 14 contexts и Security Audit / Semgrep SAST. CodeQL остаётся blocking, Semgrep — в pre-commit. Quality floors и Tier 0 100% сохранены; Q2/Q3 остаются в v1.1.

## Core и продуктовые проверки

- Попытка Core на 04fdd собрала образы, но docker compose up не запустил runtime: Docker IPAM сообщил, что все predefined address pools полностью заняты subnet-ами. Failed state run-10a4… содержит 0 контейнеров. 2026-10-12 05:44:45 UTC завершена очистка ровно 4 пустых owned networks: inventory 32→28; containers, volumes, images и markers не изменились, child processes 0. Runtime acceptance на 04fdd не пройдена; PASS со старых SHA не переносится.
- Предыдущий Core state C:/Temp/ue-live-acceptance/run-87a0640e-ac37-41a7-91e5-4b1fac6ae46b относился к 05b; штатный stop сохранил шесть volumes и подтвердил остановку 23 контейнеров. На паузе root в 04:54 UTC Docker показывал 0 running; отдельный снимок RAM в 04:54 показывал 44.59% и 17.62 GiB free. При resume в 05:16 RAM составляла 35%, free — 20.7 GiB; это моментальные снимки, не постоянное состояние.
- Отдельная advisory password-reset lane показала 2 failures до регистрации; причина остаётся в расследовании. Deadline-clock prerequisite исправлен в локальном кандидате и прошёл локальные проверки, но свежий hosted rerun pending; lane не считается закрытой и не входит в strict76.
- Текущего полного Core или targeted cohort на 04fdd нет. Последний cohort 32 относится к f3: G1 8 PASS / 4 FAIL, G2 0 / 14, G3 0 / 6; это диагностика, не продуктовая приёмка.
- Старый News V7 capture завершился capture_validation exit 9, cleanup не подтверждён; baseline не обновлялся. Исторический Profile screenshot дал 14% diff с неизвестной причиной; baseline не утверждён. Home12 ddbbc84d остаётся единственным утверждённым visual пакетом; News, Events и Schedule требуют новых current-source captures и owner approval.
- Mocked Profile responsive scenario прошёл Chromium 1/1 на 390/768/1440px на прежнем SHA; Firefox/WebKit проекты остаются pending. Все 63 audit IDs покрыты inventory, но per-ID RC dispositions и owner acceptance pending.

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
