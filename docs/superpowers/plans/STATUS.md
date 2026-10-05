# MVP — оперативный статус

Срез на 2026-10-05 (Europe/Istanbul). [Мастер-план](MVP_MASTER_PLAN.md)
задаёт приёмку; [ТЗ MVP](University_Ecosystem_MVP.md) — продуктовые границы.
Работа возобновлена по поручению пользователя. Приёмка и выпуск `v1.0.0` не подтверждены.

## Контекст и источник доказательств

- Работа только на `egorribun`, один checkout и [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306).
  Опубликованный live checkpoint `605fed24029c607d2ddfdd30ab48d776d65a4a02`;
  HEAD, origin и PR head совпали; checkout чист на момент запуска приёмки.
- После контрольной точки `2e78ce97d0daccd9d9ea74606ae07974a42ab555`:
  **170 коммитов, 949 изменённых файлов** на `605fed240`. Последний проверенный `main`
  `6fa133b57f62c554162876d4e6d8349f8060fce9` входит в историю ветки.
- [AUDIT_PROMPT.md](AUDIT_PROMPT.md) включён по поручению пользователя в `cf9f5609`; шаблон не заменяет поручение.
- Root координирует три GPT-6 Luna Max: backend, frontend, CI/инфраструктура; Git выполняет root.
- Полные исторические receipts, population, ограничения и сравнения сохранены
  в [предыдущем STATUS](https://github.com/egorribun/university_ecosystem/blob/01ffea1b5d0eca52f0b76e44d83aac3cb5890b71/docs/superpowers/plans/STATUS.md).
  Старые результаты и отсутствующее локальное evidence не подтверждают новый SHA.

## Актуальная hosted-проверка опубликованного source

- `605fed240`: [Matrix 37310173142](https://github.com/egorribun/university_ecosystem/actions/runs/37310173142), attempt 1, in progress;
  partial snapshot 105 jobs: 92 success / 11 skipped / 1 failure / 1 active; aggregate открыт.
  Chromium shard 1: profile-update `getByText(newBio).toBeVisible` RED; source/attempt-bound report сохранён.
- [Matrix 37236971603](https://github.com/egorribun/university_ecosystem/actions/runs/37236971603),
  attempt 1, PR head `01ffea1b5`, producer merge `95b8ba18`: одинаковое дерево `286c57c1`.
  128/128 backend groups validated: 4 540 selected, canonical 3 770 Killed / 770 Survived;
  primary 3 684 Killed / 856 Survived отдельно. 0 proof errors; run completed/failure 03:39 UTC.
  FE 64/64 identities/hashes/source validated: 42 913 assigned, inventory gate отклонил
  4 666 Survived / 30 Timeout / 31 RuntimeError / 1 NoCoverage; exact reject `shard-026:269`.
  Central manifest/selection validated; новые локальные исправления этим run не проверены.
- [Owned live acceptance 37236971288](https://github.com/egorribun/university_ecosystem/actions/runs/37236971288)
  завершился success на том же SHA. Он подтверждает только перечисленный PR smoke;
  полную продуктовую, визуальную и disaster-recovery приёмку не заменяет.
- На `38e8c6d`: [Matrix 37263603990](https://github.com/egorribun/university_ecosystem/actions/runs/37263603990)
  completed/failure: 140 success / 26 skipped / 3 failure; один audit false positive исправлен без baseline waiver.
  На `78182847` [Matrix 37268095391](https://github.com/egorribun/university_ecosystem/actions/runs/37268095391): security/smoke GREEN, mutmut stats shard 0 RED; snapshot сохранён перед supersession.
  На `4903a0f04` [Matrix 37280637000](https://github.com/egorribun/university_ecosystem/actions/runs/37280637000): исторический partial snapshot, немутационных failures в нём нет.
  Stats 8/8 GREEN; shard-0 metadata/tree/hash проверены. 20 failed groups: 720 selected/completed,
  601 Killed / 119 Survived, без runtime statuses; это частичные proofs, не aggregate score.
- Historical `f39d5421`: [Matrix 37213691132](https://github.com/egorribun/university_ecosystem/actions/runs/37213691132)
  completed/failure: 216 success / 20 skipped / 131 failure; подробности сохранены в истории STATUS.

## Проверенные локальные checkpoints до этой сессии

- Frontend на `40bec3868800f7411d045c4468e593df63d84ab0`:
  **719 файлов / 8 642 теста**, Node 24.15.0; все четыре применимые метрики **100%**.
  Statements 19 141/19 141, branches 13 680/13 680, functions 4 561/4 561,
  lines 17 123/17 123. Shuffle seed 1306006 также прошёл 8 642/8 642;
  обе популяции совпали, 4 655 authored inputs не изменились. Это unit scope.
- Affected backend/workflow/tooling на `5edca1efafacfee272507cf407db6c4d9ee1f4be`:
  **1 646 уникальных tests / 102 файла**, полный setup/call/teardown без skips/errors/дублей.
  До `40bec3868` backend/tooling побайтно совпал; нового run нет. Это affected union,
  не полный backend suite или PostgreSQL/RLS/NATS/Elasticsearch live integration.
- Regression controls покрывают session expiry/MFA, audit HMAC wire format,
  chat replay/attachments, search, SSR/session isolation, cancellation, timers/schedule clock.
  Они не изменяют raw mutation outcomes и не являются release certification.
- Visual wrappers закреплены на Playwright 1.63.0 и official OCI digest;
  PowerShell сохраняет exit code; шесть stub-Docker passed, настоящий paint не подтверждён.
- Timing analyzer сохраняет carried-forward timestamps partial rerun и строгие
  provenance checks. Rust/WASM parity, security и coverage оцениваются по
  соответствующему source-bound run, а не по наличию изменений в Git.

## Исторические mutation-диагностики

Inventory `f39d5421` сохранён в Git; актуальнее полный run `01ffea1b5`. Populations не сравниваются вычитанием counts.

- Из 32 frontend Timeout у 22 указан hit-counter limit; у 10 reason отсутствует.
  Отсутствие reason не доказывает wall-clock timeout. Локальные native controls
  storage/circuit/schedule не дают canonical kill credit.
- [Checker diagnostic 37215003443](https://github.com/egorribun/university_ecosystem/actions/runs/37215003443)
  на `2595c0eb`, assignment 27, завершён inconclusive. Producer: 874 Killed,
  532 CompileError, 18 Survived, 4 Timeout, 32 Ignored. TS6/TS7 сверили 195 вариантов:
  191 exact code/file/span match, 4 inconclusive; 337 не проверены.
  Baselines passed; sampled RSS 9.483 GiB, headroom 5.164 GiB, duration 4:17:47.
  Canonical checker/statuses не менялись; exclusion/kill credit не выдаётся.

## Проверки текущего checkpoint

- Checkpoints `cf9f5609`–`38e8c6d` опубликованы: документ, MFA export/history,
  cache regression, Bash contract, workers=4, owned-state bridge/LF marker и live diagnostics.
- `eecaba51e`: mutmut stats inventory учитывает Git root при запуске из mutants; nested RED/GREEN, module 1098/1098, Ruff/hooks GREEN.
- MFA export/history: DTO без отношений, безопасная owner-scoped проекция; root 26 passed, полный допуск открыт.
- SSR auth/admin guards: 4 actual-route RED → 14/14 GREEN, relevant suite 60/60, types/lint и независимое review GREEN; live открыт.
- Chat scoped-reload 404 RU/EN: 2 RED → GREEN, relevant suite 100/100, Ruff/mypy и local exact-AST RED; canonical credit не выдаётся.
- Cache: root 25 passed, `shard-026:359` local RED; rateLimit: root 80/static 4/4 GREEN; focused216=212 Killed/2 Survived/2 Timeout, waiter{} Killed, local only.
- `600e18111` + bounded admin hydration protocol: root live contracts 143/143, CLI 1092/1092 + 5 domain negatives GREEN; replay открыт.
- `7b8dbbd91`: root 3 lockout/push + 2 MFA + 12 sessions tests/Ruff/hooks GREEN; 42/45 и group56:6 local RED, без canonical credit.
- `f9469d40`: root preflight 9/9, live contracts 143/143, types/lint/format/hooks GREEN; backend deletion/MFA epoch-0 modules 32/32, root new cases 3/3.
- `4903a0f04`: persisted chat/attachment/MFA locale regressions 59/59; Ruff/hooks GREEN; mypy 81→53 без новых diagnostics, старый debt открыт; root preflight 9/9.
- `f9a2d7c1c`: scoped events/stories cache transfer; core 89/89, cache isolation 59/59,
  focused V8 56/56 и четыре метрики 100% на router + двух hooks; root 26/26, preflight 9/9.
  Серверные authenticated responses private/no-store; server entrypoint 10/10. Полный live остаётся RED.
- `b92b888c5`: exact WS expiry, Argon2 dummy input, RU admin denial и MFA typing;
  root 37/37, Ruff/format/hooks GREEN; email-OTP module mypy 1→0, остальной typing debt открыт.
  Exact-AST controls локальные; новым тестам canonical kill credit не присваивается.
- `1faa3be4c` password reuse/MFA tombstone root 45/45; positive RBAC grace exact TTL root module 5/5;
  Ruff GREEN и baseline GREEN / exact generated-AST RED; canonical credit не выдаётся.
- Chat reply-preview/search: root 44/44; RLS identity 27/27; password-change 21/21, webpush 59/59 GREEN;
  baseline GREEN / exact generated-AST RED повторены root, canonical statuses не изменены.
- `41a93b056`: Docker Rolldown workers=2, RSS cap 2048/heap 1536 MiB сохранены;
  actual client/SSR build GREEN, max из 12 phase samples 1851,3 MiB, не continuous peak.
  Root build contracts 9/9, WASM Docker contracts 6/6, hooks и preflight 9/9 GREEN.
  Детальные receipts промежуточных checkpoints сохранены в
  [STATUS на 38e8c6d](https://github.com/egorribun/university_ecosystem/blob/38e8c6d0268674f0cd975ecce8aeea1525741b06/docs/superpowers/plans/STATUS.md).
- `6f96234f4`: полный live RED — 63 passed / 111 failed / 8 project-scoped skips.
  Повторный защищённый smoke после seed: 18 passed / 2 project-scoped skips, exit 0.
  `status` exit 0: bytes/population generated state до/после совпали; stop/start ещё открыт.
- `605fed240`: events restoring skeleton — root affected 42/42, types/lint/hooks/preflight 9/9 GREEN.
  RBAC exact grace boundary root 5/5; local generated-AST RED, canonical credit не выдаётся.
- Следующий batch: persisted password/session tests root 18/18 и subject-bound admin serializer 12/12 GREEN;
  Ruff/format GREEN; mypy baseline/candidate 20/20 и 13/13, новых diagnostics нет; local AST controls 10+2 RED.
- Owned live `605fed240`: up/readiness GREEN; Activity 2/2, real API/reload/geometry;
  smoke 18 passed / 2 project-scoped skips; первый cold admin 5/6, desktop React #418 открыт.
  V5 cold diagnostic: student #418 после admin redirect и retry, teacher 0; SSR body unavailable.
  V4 diagnostic содержит ошибку helper, не подтверждает поведение; оба receipts сохранены.
  Stop/start сохранил counts/ID digests users/news/events; full row/S3 integrity этим не проверена.
  Owned teardown GREEN: 175 containers/94 volumes сохранены, 0 running; всего 89 owned image tags удалены без force.

## Среда и ближайшие действия

- Windows: Node 24.21.0, uv 0.11.28, Docker CLI/Engine доступны; «Docker отсутствует»
  не переносится на эту машину. RAM/порты/ресурсы и принадлежность стенда проверяются
  перед запуском. Пользовательские `.env`, volumes, backups и evidence сохраняются.
- Live: чистый checkout, private run-owned state, source freeze после commit; тяжёлые jobs по одному.
- `71c88b8d6` News restoring: actual Dashboard/providers RED → GREEN, root 27/27;
  `c298c23e4` MFA IP buckets root 5/5; `bfa1dbb62` scoped Redis invalidation root 14/14.
- Продолжить блоки 4/5: traceability ТЗ, RU/EN, light/dark, ширины
  360/390/768/1024/1440; small visual packages и пользовательское утверждение baseline.
  Полная приёмка stack и DB/S3 данных требует отдельного evidence.
- Закрывать mutation debt по поведению, без waivers/exclusions, ручных Killed,
  timeout inflation или переноса локального verdict в canonical report.
- Подтвердить deployed PostgreSQL/Alembic upgrade/rollback и BE-02, paired S3/DB
  restore с чтением URL, RPO/RTO, WS load, Envoy Gateway/kind и failure recovery.
  Historical audit dispositions 60/2/1 не заменяют review всех 63 IDs.
- DR runner/executor review и root 16 mock tests GREEN; avatar helper 9/9, PNG decode GREEN; actual restore открыт.
  `605fed240` backend фактически использует default static storage; live S3 configuration требует исправления до paired DR.

## Открытые релизные допуски

Exact-head canonical mutation pass и все coverage/security gates; три сопоставимых
полностью зелёных CI наблюдения; полный live/visual/performance acceptance;
утверждённые baselines; WS load; paired backup/restore и RPO/RTO; BE-02 Docker/kind;
финальный независимый security review и audit ledger; resulting-main evidence;
шесть сертифицированных GHCR digests, их kind-приёмка и release `v1.0.0`.

Admin bypass, force-push, изменение защиты ветки, удаление пользовательских данных
и переписывание истории запрещены. Внешнее production, реальные SMTP/push,
физические устройства, CDC и field CWV остаются вне согласованной области MVP.
