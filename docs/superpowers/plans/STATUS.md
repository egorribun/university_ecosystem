# MVP — оперативный статус

Срез на 2026-10-06 (Europe/Istanbul). [Мастер-план](MVP_MASTER_PLAN.md)
задаёт приёмку; [ТЗ MVP](University_Ecosystem_MVP.md) — продуктовые границы.
Goal активен. Выпуск `v1.0.0` не подтверждён.

## Контрольная точка

- Работа только на `egorribun`, один checkout и [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306).
  Последний проверенный source: `76cd4026dbe241f9a57b7f98488f54856f6b37d9`;
  tree `17e06f9eb374ffe90950830540e8240155158b96`.
  Следующий checkpoint добавляет шесть test-only regressions; новое CI ещё нужно.
- Root — единственный tracked writer, владелец Git и runtime. Три GPT-6 Luna Max
  готовят приватные пакеты; root проверяет код, происхождение и результаты.
- В source интегрированы SmartImage fallback, audit/news event regressions,
  CAS rejection, MFA export-order и persisted ranked-news tie/cursor regression.
  Ranked-модуль 24/24; exact mutant114 — call-phase AssertionError.
  SQLite ranking UDF не подтверждает PostgreSQL ranking.
- `source-map-js` обновлён 1.2.1 → 1.2.2 для GHSA-68fv-2mgg-jv7q;
  frozen install/audit/build пройдены. Четыре npm deprecation warnings открыты.
  Текущий checkpoint: preflight 9/9, harness в его составе, pre-commit PASS;
  оба режима link checker, Markdownlint и CSpell reviewed docs 9/9 пройдены.

## Hosted CI и мутации

- [Matrix 37403597748](https://github.com/egorribun/university_ecosystem/actions/runs/37403597748),
  attempt1: source `76cd…`, PR producer `40b5a90e312d0bfc318665078ca833b704c03290`.
  Родители и совпадение tree проверены root. Coverage Policy, Node audit
  и Performance Gate — success. Снимок 08:05 UTC: 312 jobs,
  62/64 frontend mutation jobs success, два active, queued нет;
  127 failures относятся к backend mutmut, немутационных failures нет.
  Это исторический неполный снимок, полного зелёного Matrix нет.
- Root проверил quality manifest: valid, missing/errors отсутствуют;
  все применимые метрики 100%. Frontend statements 19228/19228,
  branches 13785/13785, functions 4583/4583, lines 17190/17190;
  Python lines/statements 29822/29822, branches 7376/7376.
  Python function metric unsupported по контракту; Go/Rust applicable — 100%.
- Frontend preflight: 43193 mutants, 565 files, 64 shards; provenance/population
  проверены. Первые 11 disjoint artifacts: 676 Killed, без открытых результатов.
  Неполный набор не устанавливает global score.
- Backend universe: 54457 mutants, 344 files, mutmut3.8.0; artifacts validated.
  Текущий execution plan — incremental 4589 selected в 128 groups.
  Selection digest `2aa5ddd40da6245b1f0865a344f549a53524eeb83ff339b41bf2eb57f88d6581`;
  universe digest `d15e06c97f7e8d286081277b9137efdbbd6948596c5a19004503d57619a6c351`.
  Root validated 55 groups: 1972 selected, 1697 Killed, 275 Survived;
  no-tests/skips/timeouts/runtime faults — 0. Stats не являются execution evidence.
- Интегрированы шесть проверенных регрессий: Spotify identity100, durable chat
  event37, pinned Web Push88, legacy audit fallback58, NATS strict publish26,
  remaining-member presence invalidation69. Root baseline PASS и exact mutant
  RED подтверждены. Canonical affected modules: 168/168 PASS, Ruff PASS.
  Независимое review потребовало сохранить прежний transport-None сценарий
  отдельно от DNS-pinning regression; он восстановлен, Web Push module 60/60 PASS.
  До нового canonical producer mutation credit не присваивается.
- PG `UserRepository.get` mutant9 — shard37. Regular mutation selector исключает
  integration. Private supplemental Linux PG lane V4: root offline29/29,
  actual installed SQLAlchemy/asyncpg translation и JUnit boundary проверены.
  PostgreSQL/native runtime ещё не выполнен; regular/global score не изменены.
- Private reusable full-backend workflow готовится для source-bound полного
  execution. Default incremental manual mode и main-only nightly сохраняются.

## Live-приёмка

- Owned full stand на `76cd…`: readiness/seed PASS. Cold smoke: 17 passed,
  один non-admin page-exception failure, два intentional cross-project skips.
  Root warm denial student/teacher × desktop/mobile: 4/4, workers1/retries0,
  page errors0. Исходная cold ошибка остаётся открытой.
- Avatar diagnostics опровергли naturalWidth oracle: density-corrected 1×1
  может иметь natural dimensions0 при успешном IMG.decode(). Negative control
  проверен. Resource oracle строгий: origin/path/hash/query сохраняются,
  разрешено различие только cache-version `_v`; cross-mount сравнения исправлены.
- V7r2 desktop: 1/1 PASS, retries0; upload/reload, реальный415 rollback и
  rejected-upload reload проверены. Mobile failed до первого POST; RCA открыт.
- V8 mobile вновь failed до POST: chooser/setFiles/native change наблюдались,
  input оставался connected, выбран один PNG within limit, button enabled,
  avatarPostCount0. Это не доказывает вызов React handler или auth-ref readiness.
  Private V9 actual handler/guard instrumentation готовится без изменения поведения.
- State: `C:/Temp/ue-live-acceptance/run-orchestrator-76cd4026d-20261006-e27723ac7de24e31a02870ffc409506c`.
  Project `ue-live-2bec0462a275fd36`; env, seed и evidence сохраняются.

## Backup/restore и рабочая среда

- DR run `8b804d4b67a24f2481099d50349ab7d1` связан с `76cd…`.
  Pinned runner, private assets/key, PS7 preflight и absence guard проверены.
  Root V6 adapter/dispatcher offline31/31 и независимое review пройдены.
- One-shot clock начат, owned source quiescence PASS. Standalone source-env CLI
  failed из-за import-path; явная reconciliation через тот же pinned signed
  context PASS. Первое failure сохранено; clock не сбрасывался.
- Paired snapshot создан. Executor failed на `source_snapshot_gate`,
  `runner_step_failed`; restore_started_at_utc отсутствует, target restore
  не начат. Read-only gate diagnostic: `source_snapshot_gate_failed`;
  точная причина ещё устанавливается. Ledger помечен failed, RPO/RTO не подтверждены.
- Исходные 27 остановленных containers возобновлены; три health-probe потребовали
  отдельного запуска после namespace dependencies. Protected receipts сохраняют
  частичную ошибку и reconciliation. Root health: 29 running, health PASS,
  frontend HTTP200. PG/S3/env не пересозданы, данные не удалены.
- Только основной worktree. 80b stand очищен по владельцу; остальные retained
  data/volumes и private backups сохраняются до проверки уникальности.
  Global prune, чужие stop/delete и распространение rescue bundle запрещены.
- Private scratch artifacts: `C:/Temp/ue-orchestrator-1f5a42b2c5ec49c4bc020ea0752bd157`.
  Удаление dependency scratch и PG V4 `__pycache__` отклонено автоматической
  проверкой; оба сохранены, bypass не выполнялся.

## Следующие результаты

- Проверить и отправить текущие test-only regressions; получить новый canonical
  evidence. Завершить source snapshot gate RCA и пересмотреть DR chain.
- Завершить mobile no-POST диагностику, native PG mutation lane и полный backend
  execution route. Блоки4/5: live traceability ТЗ, RU/EN, light/dark, responsive,
  SSR/PWA, performance и пользовательское visual approval остаются открыты.
- Открыты 100% viable score, три полных зелёных CI, migrations/rollback/BE-02,
  app restore, SpiceDB graph/search parity, WS load, Envoy Gateway/kind,
  63 audit IDs, шесть certified GHCR digests и выпуск `v1.0.0`.

Сохранять env, volumes, backups и Git history. Не применять admin bypass,
force-push или менять branch protection. Внешний production, реальные SMTP/push,
физические устройства, CDC и field CWV вне MVP.
