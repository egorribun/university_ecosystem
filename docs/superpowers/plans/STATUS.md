# MVP — оперативный статус

Контрольная точка: 2026-10-11, 19:50 UTC. Основания приёмки —
[мастер-план](MVP_MASTER_PLAN.md), [ТЗ](University_Ecosystem_MVP.md) и
[ADR-047](../../adr/ADR-047-risk-based-quality-policy.md). Выпуск `v1.0.0` не подтверждён.

## Границы и hosted CI

- Только `egorribun`, один checkout и [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306).
  Root управляет Git и интеграцией; до трёх GPT-6 Luna Max работают в непересекающихся областях.
- Последний проверенный hosted source — `147bc20a99dbe7942ad543dfb5fb8edb139062a3`,
  tree `c2df255a2678d57aff4adf7e9bf99593546df625`.
  [Matrix 38154776186](https://github.com/egorribun/university_ecosystem/actions/runs/38154776186) SUCCESS;
  точная сверка ruleset `8335285` дала 75/76 required context/integration pairs SUCCESS.
  Blocking CodeQL gate сообщает новый alert 3384 в PWA proxy. Анализ CodeQL завершён;
  исправление должно получить подтверждение на следующем опубликованном SHA.
- Q1/Q4 migration и разрешённые ровно 14+1 удаления contexts выполнены.
  Остальные contexts и правила сохраняются; CodeQL blocking, Semgrep в pre-commit.
  Tier 0, действующие coverage floors и 100% patch floor не снижены.
  Целевой CI budget ≤15 минут ещё не подтверждён; max-parallel 2 сохранён.
- Q2/Q3, global mutation score, comparable CI runs, kind certification,
  RPO/RTO и deployed BE-02/MIG-PASS — v1.1. Один согласованный paired DB/S3 restore нужен для MVP.

## Проверенный локальный пакет поверх этого source

- API привязывает запрос к session epoch/generation до CSRF и ожидания очереди,
  повторно проверяет владельца перед отправкой и вокруг 429 retry.
  Устаревшей вкладке доступны только точные same-origin bootstrap routes и ограниченное
  восстановление auth после неудачной записи generation. Абсолютные, foreign и неоднозначные
  recovery aliases запрещены; обход через triple-slash URL устранён с учётом семантики Axios.
- Profile DTO сохраняет email verification timestamp. PWA proxy использует постоянный
  loopback destination и изменяет revision настоящего quoted precache entry.
  Footer учитывает usable viewport/scrollbar gutter; a11y ждёт завершения fade.
  Story/Auth/Push diagnostics ограничены закрытыми полями и не ослабляют acceptance assertions.
- 13-file API/session selection: 169/169 PASS; оба production-модуля имеют 100%
  statements/branches/functions/lines (294/213/38/270 суммарно), JSON проверен.
  Focused backend selection: 224/224 PASS, включая WebPush full-service 62/62;
  mapper/WebPush — 100% line/statement/branch coverage. Это scoped evidence, не общий coverage proof.
- Full TypeScript, frontend lint без warnings, live contracts 189/189, Ruff/format и diff check PASS.
  Quality guards подтвердили неизменность исходников и отсутствие оставшихся owned children.
  Пакет требует обычных hooks/commit/push, собственных 76 required results и свежей live-проверки.
- Предыдущие Settings/profile/outbox fixes и BE-04 isolated PostgreSQL proof сохраняются;
  повторно выполнять уже принятые исправления не требуется.

## Core и следующая приёмка

- Source 147 Core `run-706d182c-ed12-42b1-b8df-4330dd1e0486`,
  project `ue-live-015bb1ed087e7018`, signed schema 11/23 services:
  up → admin-only seed → demo seed → readiness/cookie policy PASS.
  Стенд штатно остановлен, данные и volumes сохранены.
- Его targeted diagnostics остаются диагностикой: UI/PWA/Story selection 20 PASS/6 FAIL,
  Auth/Notifications 0 PASS/14 FAIL, native Push 8 PASS/4 FAIL.
  Новый пакет не объявляется live-fixed до свежего source-bound запуска.
- После commit/push нужен уникальный Core state: admin-only seed перед demo seed,
  readiness/cookie policy, затронутые UI/Story/PWA/Auth/Notifications/Push/OTP scenarios.
  Затем два последовательных full Core runs на неизменном source:
  каждый 198 total, 190 PASS + ровно 8 ожидаемых SKIP.
- Следующая visual acceptance — News12, затем Events12 и Schedule12: RU/EN,
  light/dark, 390/768/1440. Owner утвердил только Home12 `ddbbc84d`;
  новые pixels требуют отдельного утверждения перед baselines. LHCI: 7 routes × 3 = 21 sample.

## Открытые release критерии

1. Свежие 76 required results и подтверждённый fix CodeQL 3384 на итоговом source.
2. Seed/preferences stop/start persistence; app-compatible paired DB/S3 restore
   в изолированную DB/bucket с quiescence и чтением объекта через restored DB reference.
   Canary/source/snapshot и partial target при неуспехе сохранять.
3. [63 audit IDs](../../audits/INDEX.md#findings-ledger): historical 60 CLOSED/2 DECLINED/1 OPEN
   не являются RC certification. SEC-03: backup/read-only inventory перед rotation;
   SEC-07 и RUST-P3-03: final-source evidence. Разрешённые CodeQL 3382/3383 уже dismissed.
4. ADR-006 сохраняет tombstone/WS revoke до commit и conservative sibling logout
   при rollback; завершить независимый auth/session/data review.
5. Frozen-RC full smoke → ordinary merge → свежие main gates → шесть source-bound
   signed images/SBOM/provenance → tag/release notes `v1.0.0`.
   Admin bypass, force-push и дополнительные context removals запрещены.

Один heavy workload: старт RAM≤75%/free≥8GiB, остановка RAM≥85%/free<4GiB.
Serial Linux screenshots: разрешённое исключение ≤80%/≥6GiB, browser≤1GiB/2CPU.
Owned builder≤4GiB/2CPU/no swap. Сохранять полезные caches и Core data;
останавливать только доказанно owned процессы по PID/birth/parent identity.
Чужие процессы, Docker/WSL и global caches не очищать.

[Canonical documentation ownership](../../README.md#documentation-ownership) и audit retention сохранены.
Git history, migrations, environment/data/backups, credential-shaped history и private rescue bundle
сохраняются по действующей политике; приватные материалы не помещать в рабочее дерево или PR.
Одноразовый prompt и superseded audits не восстанавливать.
