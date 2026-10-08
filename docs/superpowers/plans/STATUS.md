# MVP — оперативный статус

Срез на 2026-10-08 (Europe/Istanbul). [Мастер-план](MVP_MASTER_PLAN.md) — единственный
действующий план; [ТЗ MVP](University_Ecosystem_MVP.md) задаёт продуктовые границы,
[ADR-047](../../adr/ADR-047-risk-based-quality-policy.md) — переход качества.
Работа приостановлена по просьбе пользователя после подготовки плана и harness.
Выпуск `v1.0.0` пока не подтверждён.

## Решения владельца и ближайший результат

- При следующем разрешении на продолжение исполнение возобновляется.
  Работа строго на `egorribun`, один checkout и
  [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306).
  Root интегрирует; максимум три GPT-6 Luna Max владеют раздельными областями.
- Кратчайший путь: Q1/Q4 → Core/product/visual/security/restore → full smoke →
  обычный merge → main checks → готовый producer шести GHCR images → release.
  Независимые исправления продукта идут параллельно с CI; агенту 30 минут до
  контрольной точки, длительные процессы контролируются отдельно.
- Q1 и весь Q4 обязательны до MVP: мутации, Schemathesis, DAST, chaos,
  cross-browser и kind переходят из blocking PR lane в scheduled/manual.
  Live Chromium smoke, security и fail-closed оставшиеся checks сохраняются.
  Эти изменения ещё не внедрены; старые CI dependencies пока действуют.
- Tier 0 — 100%; остальные действующие coverage floors также сохраняются до Q3.
  Если они блокируют MVP, перенос Q3 согласуется отдельно. Q2/Q3 — `v1.1`.
- Полный mutation score, три сопоставимых полных CI-прогона, kind certification,
  RPO/RTO и deployed BE-02/MIG-PASS — `v1.1`; готовую оснастку сохраняем.
  Один согласованный изолированный DB/S3 restore обязателен для MVP.
- ГУУ остаётся брендом внутреннего демо; данные синтетические. Публичное
  использование решается отдельно. Помещения/вместимость — после MVP.
- Без embeddings key текстовый поиск работает; UI semantic mode выключен,
  direct semantic-only API сообщает о недоступности без нулевых векторов.

## Подтверждённая контрольная точка до изменения политики

- Source checkpoint: `7ddc114b72f346ff27bd6dd6d83e191eb7f89412`, отправлен в remote.
  Новый policy commit: `60a886529c6e89176e2d53395268ca6279805cb4`.
  Старые результаты ниже подтверждают свои SHA, а не текущий release candidate.
- Planner cost cache: RED 24 conversions вместо 4 → GREEN; root317 PASS и
  5 subtests. Synthetic512/128 планы идентичны; global score не получен.
- Browser cache override: validated private pinned Playwright browser работает;
  live CLI1164 tests PASS. Workflow snapshot contracts26/26 PASS после исправления.
  Preflight10/10, staged hooks и push прошли на checkpoint.
- Hosted Live `37767058529/a1` на `460501`: SUCCESS, 18 passed/2 planned skips,
  flaky нет. Uploaded artifact отсутствует; evidence — API/job/redacted stdout.
- Matrix `37767059576/a1` на `460501`: backend shard1 FAILED на трёх stale
  workflow assertions, 4189 passed/18 skipped. Локальное исправление принято;
  новый hosted результат и обязательный зелёный набор ещё нужно подтвердить.
- Profile Core acceptance на `15ad90aac`: 4/4 PASS, validation/save/reload.
  Исторический stop/start smoke на `444ed`: 18 PASS/2 planned skips,
  hashes/secret files/volumes совпали. Полная продуктовая traceability открыта.
- Core на `460501` поднялся, E2E не начат из-за RAM85,4%/free4,63 GiB.
  Stop/teardown PASS; проверенные owned containers/volumes/networks/image tags0.
  Shared base images/build cache сохранены; global prune не применялся.
- Private checkpoint receipt:
  `C:/Temp/ue-quality-session-dm-root-20261008-82730e4856e54ecbb944e5fa90cc3110/checkpoint-7ddc114b-v1.json`.

## Сохранённые начатые направления

- Подготовка harness: verifier изолирован от real gate state; shared loader/lock,
  atomic write и per-file latest map сохраняют failures; malformed JSON и timeout
  fail closed. Все Go modules обнаруживаются, max2 workers/shared95s budget.
  Profiles согласованы с одним checkout/root Git/30-minute checkpoint.
- Verifier28/28, hook runtime/Stop44/44, relevant full preflight10/10,
  live contracts154/154 PASS; real gate state hash неизменен после проверок.
  Старый OwnedLive `37839467416/a1` на `a01e572b5` упал до Docker на двух
  stale plan-wording assertions; они исправлены. Новый hosted результат требуется.
- Known P2: Windows timeout cleanup через `taskkill /T` не гарантирует завершение
  descendant, если родитель уже вышел и оставил inherited pipes. В этом случае
  cleanup failure явный, PASS нет; полную Job Object containment отнести в backlog.
  Нативная Codex registration отсутствует; Antigravity hooks вызываются явно.

- Mutation diagnostic: frontend inventory43200, viable88,7101%; backend
  universe54450, complete global score отсутствует. Это debt/baseline,
  не MVP допуск. Полные очереди ради 100% теперь не запускаются.
- Kind K3 helper на `727eecab`: controllers/CA/create/prepare/repeat/preflight/
  smoke/teardown PASS, inventory20 и Helm revisions1 неизменны.
  Приложение не развёрнуто; chart/routes parity и полная приёмка — `v1.1`.
- DR на `76cd4026dbe241f9a57b7f98488f54856f6b37d9`: paired snapshot создан,
  executor остановился на `source_snapshot_gate`; target restore НЕ НАЧИНАЛСЯ.
  Logical restore, DB/S3 связность, RPO/RTO не подтверждены. Неудачные
  immutable diagnostics/receipts сохраняются без заднего изменения outcome.
- Manifest-aware backup/restore CLI/runbook и BE-02 preflight/tests реализованы;
  наличие кода не подтверждает deployed restore/upgrade/rollback.
- Six-image main-only producer и source-bound release consumer реализованы;
  signing/SBOM/provenance/WASM parity сохраняются. Публикация текущего релиза
  и проверка его main SHA/run/attempt/manifest/digests ещё предстоят.

## Открытая MVP-приёмка

- Q1/Q4 implementation ещё не начат. Schedule regression draft сохранён
  приватным patch `C:/Temp/ue-quality-session-dm-root-20261008-82730e4856e54ecbb944e5fa90cc3110/schedule-update-checkpoint.patch`;
  production code не менялся, RED/GREEN не получен. Search fix только спроектирован.
- Schedule update conflict; проверка потребителей unused event analytics;
  поведение semantic search без ключа и согласованный UI.
- ТЗ2–13: актуальные Core auth/MFA, messenger/group delivery, push,
  profile/settings, admin permissions, SSR/PWA/i18n, RU/EN и a11y.
- Visual approval: light/dark, 390/768/1440 px, targeted360/1024;
  Linux baselines, bundle budget, Lighthouse, stories20 cycles/reduced motion.
- Независимый auth/session/data review и ADR-006 tombstone-first ordering;
  все63 audit ID классифицировать; P0/P1 security нельзя переносить молча.
- Один backup/restore в отдельные DB/S3 targets с чтением восстановленного
  объекта через DB reference. Затем frozen RC и один full release smoke.
- Q1/Q4 должны обновить triggers/dependencies/results/assertions/catalog/
  release requirements/contracts вместе. Целевой PR бюджет15 минут ещё не измерен.
  Scheduled/manual lanes требуют default-branch activation; наличие workflow
  в `egorribun` не доказывает их работоспособность на `main`.

## Ресурсы и сохранность

- Один heavy workload: перед стартом RAM≤75%, free≥8 GiB;
  runtime guard85%/4 GiB. Следующий запуск требует свежего измерения.
- Удалять только доказанно принадлежащие нам ненужные Docker ресурсы;
  пользователь разрешил удаление synthetic ue-live данных. Чужие env/data/
  volumes/backups/processes сохраняются. Worktree не создавать.
- Git history/migrations/private rescue bundle сохраняются. Исторические
  session logs и superseded snapshots не возвращать в текущие индексы.
- Codex goal сохраняет прежнюю расширенную формулировку и сейчас `paused`;
  инструмент не предоставляет изменения objective/resume. Последнее поручение —
  безопасно приостановиться; выпуск MVP не закрывает сертификацию `v1.1`.
