# MVP — оперативный статус

Срез на 2026-10-06 (Europe/Istanbul). [Мастер-план](MVP_MASTER_PLAN.md)
задаёт приёмку; [ТЗ MVP](University_Ecosystem_MVP.md) — продуктовые границы.
Goal активен. Выпуск `v1.0.0` не подтверждён.

## Контрольная точка

- Работа только на `egorribun`, один checkout и [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306).
  Проверяемый runtime/CI source: `97a8415959bfebd3cc6ccfc565a3f50051ef6e22`.
  Checkpoint отправлен обычным push; preflight9/9, focused contracts370/370,
  normal pre-commit PASS. Root — единственный tracked writer и владелец runtime.
  Три GPT-6 Luna Max готовят приватные пакеты с отдельной проверкой root.
- Source включает full mutation contracts, immutable benchmark activation,
  WebKit focus fix, строгую avatar resource identity и DM reconnect/replay oracle.
  Unit/contracts не заменяют живую приёмку.
- `source-map-js` 1.2.2 закрывает GHSA-68fv-2mgg-jv7q; frozen install/audit/build
  проверены на предыдущем checkpoint. На lock97a audit findings0;
  четыре transitive npm deprecation warnings остаются открыты.

## Hosted CI и мутации

- [Matrix37469190278](https://github.com/egorribun/university_ecosystem/actions/runs/37469190278)
  source97a, PR merge `ce2122c8f329a2fd36ec201b119db35d2d640e79`.
  Backend shard1: 3797 passed,26 skipped,1 failed — Helm retry consumer contract
  для nightly, делегирующего reusable producer. Требуется проверка всей цепочки.
  Chromium authenticated a11y subcommand: webServer exit1, tests не собраны;
  предыдущие Chromium subcommands прошли. Vite RSS2071.3MiB превысил watchdog2048;
  reviewed fix ограничивает Rolldown двумя workers, сохраняя heap1536 и timeout.
  Root Windows URL_STATE coverage build PASS20.676s; tracked frontend неизменен;
  это не замена Linux hosted CI proof.
- CodeQL check112288877701: шесть high cache-poisoning alerts в двух reusable
  workflows. Guards уже сверяют source/event/workflow SHA; reviewed fix выбирает
  checkout напрямую по trusted event SHA. Hosted подтверждение ещё отсутствует.
- [Paired benchmarks37469189921/a1](https://github.com/egorribun/university_ecosystem/actions/runs/37469189921):
  оба обязательных gate success. BASE `6fa133b57f62c554162876d4e6d8349f8060fce9`,
  candidate — merge `ce2122…`, source97a. Root проверил archive/API digests,
  merge parents, helper/harness Git pins и повторил immutable BASE comparator:
  по12 пар,33 Go и4 Rust metrics, результаты полностью совпали с CI.
  Threshold1.10 сохранён; это microbenchmarks, не WS load/release certification.
- Исторический quality manifest source76cd valid: applicable coverage100%.
  Это не подтверждение coverage текущего source97a.
- Frontend generation:43193 mutants/565 files/64 shards; partial artifacts
  не устанавливают global score. Свежий shard30 на6a:487 Killed/10 files,
  Survived/NoCoverage0; aggregate полного execution отсутствует.
- Backend generation:54457 mutants/344 files/mutmut3.8.0; incremental selection
  4589 в128 groups, universe digest
  `d15e06c97f7e8d286081277b9137efdbbd6948596c5a19004503d57619a6c351`.
  Root проверил свежие groups1/6/8 на6a:108 selected,94 Killed,14 Survived.
  Неполный execution не устанавливает viable score.
- Интегрированные auth/events/push/audit/NATS/presence/WS-ticket regressions
  имеют локальные baseline/exact-mutant controls; новый canonical producer
  требуется для mutation credit. Unsupported метрики трактуются по контракту.
- Интегрированы reviewed regressions: localized empty-chat403 (EN/RU), concurrent
  idempotency409 detail, internal MessageEdited metadata. Root exact controls
  baseline PASS/expected mutant FAIL; affected private modules40/40,12/12,11/11.
  Canonical affected modules и workflow contracts359/359 PASS, Helm retry29/29;
  actionlint трёх изменённых workflows PASS. Global mutation credit ещё отсутствует.
- PG UserRepository.get mutant9: historical generation source76cd отдельно
  от execution97a. Root проверил ten fixture pins на97a/6a/76cd и семь input
  hashes плюс historical receipt; inner38 tests PASS, outer Windows32 PASS/2
  platform skips и WSL34/34 PASS. V5 native execution удержан: Windows timeout
  не доказывает завершение owned WSL scope; новый cancellation contract в работе.
  Regular mutation selector исключает integration; supplemental credit не
  добавляется автоматически к regular/global score.
- Full-backend reusable workflow подготовлен для полного source-bound execution;
  default incremental/manual и main-only nightly сохранены. Hosted full run,
  canonical global score100 и три сопоставимых зелёных CI ещё открыты.

## Live-приёмка

- Ordinary full Compose source97a, project `ue-live-5b58d4ebdfc22c50`:
  signed owner/daemon/Compose fingerprint проверены,29 services ready,
  шесть init jobs exit0, frontend/Mailpit HTTP200, seed committed.
  Focused avatar + messenger run:2 passed/10 failed, desktop/mobile.
  Это diagnostic-only subset, не полный сертификат live-приёмки.
- Mobile avatar failure на waitForResponse POST; mobile DM — sender chat-log
  prerequisite до receiver WS join/send. Group cases также падали на API outcome,
  visibility, reaction/history и cleanup assertions. Sanitized receipt не
  содержит фактических status/body/locator values; RCA нельзя предполагать.
  Prepared passive diagnostics сохраняют исходные assertions и закрытый output.
- Ordinary stand безопасно stopped после terminal failure; env/data/evidence
  сохранены. State:
  `C:/Temp/ue-live-acceptance/run-ordinary-97a-avatar-dm-20261006-54a6e8136ba948bb8671abfc3534f4a2`.
- Historical diagnostic image6a avatar desktop/mobile PASS не подтверждает
  ordinary97a. Original cold auth-role error source76cd остаётся открытым;
  warm denial4/4 не заменяет cold proof. Private diagnostics Python809/Node16
  проверены, integration/live execution ещё отсутствуют.
- Блоки4/5: остаются полная traceability ТЗ, RU/EN, light/dark, responsive,
  SSR/PWA, accessibility/performance и пользовательское visual approval.
  Group notification context отсутствует в live assertions; draft отложен
  до разбора существующих messenger prerequisites.

## Backup/restore и рабочая среда

- DR source76cd: paired snapshot создан, executor failed на source_snapshot_gate,
  restore не начат, clock не сбрасывался. Read-only probe: BackupArtifactError,
  outer manifest_s3_read; внутренний RCA открыт. RPO/RTO не подтверждены.
- Исторические DR/diagnostic и ordinary97a stands stopped; env, volumes,
  backups, evidence сохранены. Новый heavy workload: RAM≤75%,free≥8GiB,
  один heavy job. Last root snapshot: running Docker0, free17GiB/RAM46.6%.
- Docker address pools exhausted при новом up. Root/peer проверили signed owner,
  daemon, полный resource fingerprint и emptiness трёх старых d484 networks;
  удалены только exact IDs. Container/volume inventory до/после совпал.
  Повторный ordinary startup успешен; global prune не применялся.
- Root ignored pytest cache перенесён целиком в проверенный private quarantine
  без удаления содержимого. Исходный cache guard finding пока не воспроизведён
  в isolated fixtures; code patch не принят, исключения не расширены.
- Только основной worktree. Не удалять retained данные без проверки уникальности.
  Private evidence: `C:/Temp/ue-orchestrator-1f5a42b2c5ec49c4bc020ea0752bd157`.
  Отклонённые cleanup requests не обходились; rescue bundle остаётся private.

## Следующие результаты

- Закрыть CodeQL checkout findings, Helm delegated consumer contract и Chromium
  RSS build: проверить reviewed fixes → preflight/hooks → обычный commit/push;
  закрытие hosted findings подтверждает только новый SHA-bound CI.
- Сначала проверить PG owned cancellation/deadline, затем native control; разобрать
  ordinary avatar/DM/group failures с bounded diagnostics, без threshold waiver.
- Интегрировать reviewed behavioral regressions; получить новый canonical
  mutation inventory/execution и закрывать survivors по фактическому evidence.
- Открыты migrations/rollback/BE-02, app restore, SpiceDB graph/search parity,
  WS load, Envoy Gateway/kind,63 audit IDs, шесть certified GHCR digests,
  resulting-main evidence и выпуск `v1.0.0`.

Сохранять env, volumes, backups и Git history. Не применять admin bypass,
force-push или менять branch protection. Внешний production, реальные SMTP/push,
физические устройства, CDC и field CWV вне MVP.
