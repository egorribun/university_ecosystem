# MVP — оперативный статус

Срез на 2026-10-05 (Europe/Istanbul). [Мастер-план](MVP_MASTER_PLAN.md)
задаёт приёмку; [ТЗ MVP](University_Ecosystem_MVP.md) — продуктовые границы.
Работа возобновлена по поручению пользователя. Приёмка и выпуск `v1.0.0` не подтверждены.

## Контекст и источник доказательств

- Работа только на `egorribun`, один checkout и [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306).
  Опубликованный checkpoint — `38e8c6d0268674f0cd975ecce8aeea1525741b06`;
  16 checkpoints отправлены обычным push после сохранения terminal CI evidence; новые тесты локальные.
- После контрольной точки `2e78ce97d0daccd9d9ea74606ae07974a42ab555`:
  **139 коммитов, 915 изменённых файлов** на `38e8c6d`. Актуальный `main`
  `6fa133b57f62c554162876d4e6d8349f8060fce9` входит в историю ветки.
- Пользователь подтвердил включение [AUDIT_PROMPT.md](AUDIT_PROMPT.md) в Git.
  Исходные bytes сохранены в `cf9f5609`; инструкции шаблона не заменяют поручение пользователя.
  Tracked tree до этой сессии был чист.
- Root координирует три GPT-6 Luna Max: backend, frontend, CI/инфраструктура.
  Владельцы пишут в непересекающиеся файлы; Git-операции выполняет root.
- Полные исторические receipts, population, ограничения и сравнения сохранены
  в [предыдущем STATUS](https://github.com/egorribun/university_ecosystem/blob/01ffea1b5d0eca52f0b76e44d83aac3cb5890b71/docs/superpowers/plans/STATUS.md).
  Старые результаты и отсутствующее локальное evidence не подтверждают новый SHA.

## Актуальная hosted-проверка опубликованного source

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
  completed/failure: 140 success / 26 skipped / 3 failure; audit checklist false positive воспроизведён UTF-8 hook, исправлен локально.
  [Live smoke 37263603695](https://github.com/egorribun/university_ecosystem/actions/runs/37263603695) completed/success; scope только PR smoke.
- На предыдущем `f39d5421341d84dd5e316fe9e88e2b4399758d0e`
  [matrix 37213691132](https://github.com/egorribun/university_ecosystem/actions/runs/37213691132)
  завершён: **367 checks, 216 success / 20 skipped / 131 failure**.
  Обычные unit/coverage, types, security, browser/live и performance prerequisites
  прошли; failures — 128 backend mutation groups и три aggregate/required contexts.
  Тестируемый merge `d1ae8fba7311fc196b555823e94d93dc7dc53740` имел то же дерево.

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

## Последний полный исторический mutation inventory

Кампания `f39d5421`, run 37213691132 / attempt 1, завершена 2026-10-04 UTC.

| Область | Полнота | Raw outcomes и предел доказательства |
| --- | --- | --- |
| Frontend | 64/64 reports; 42 913 identities, без пропусков/дублей | 36 938 Killed; 4 669 Survived; 1 NoCoverage; 32 Timeout; 31 RuntimeError; 0 CompileError; 1 242 Ignored |
| Backend | 128/128 complete proofs; 4 540 selected IDs; 138 archives | 3 764 Killed; 776 подтверждённых Survived; остальные native statuses 0 |
| Backend generation | 54 418 identities | 49 878 unselected не имеют execution evidence; им не присваивается статус |

Frontend aggregate отклонил `shard-026:269`; validated artifact отсутствует.
Backend full-map confirmation убила ещё 104 из 880 primary survivors.
Это полный inventory выбранной кампании, **не 100% viable mutation score**.
Предыдущие b6/2595 populations и mixed producer attempts сохранены по Git-ссылке;
разные populations нельзя сравнивать простым вычитанием counts.

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
- Scanner RED сохранён; UUID fix без suppressions; hooks GREEN, bridge `ba8a236b5`.
- Исправлен экспорт MFA: public DTO не содержит отношения; отдельная проекция
  возвращает сохранённый count и безопасные enrollment metadata с изоляцией владельца.
  Root: 26 целевых backend tests passed; это не полный coverage/mutation допуск.
- Cache: root 25 passed, `shard-026:359` local RED; rateLimit: root 80/static 4/4 GREEN; focused216=212 Killed/2 Survived/2 Timeout, waiter{} Killed, local only.
- `600e18111` + bounded admin hydration protocol: root live contracts 143/143, CLI 1092/1092 + 5 domain negatives GREEN; replay открыт.
- `7b8dbbd91`: root 3 lockout/push + 2 MFA + 12 sessions tests/Ruff/hooks GREEN; 42/45 и group56:6 local RED, без canonical credit.
- `38e8c6d`: root preflight 9/9, hooks/pre-push GREEN; live CLI 1 020 pytest + 8 Node GREEN.
- `1faa3be4c` test-only password reuse/MFA tombstone: root 45/45 в двух модулях, Ruff/hooks GREEN;
  baseline GREEN / exact generated-AST RED проверены отдельно, canonical credit не выдаётся.
- Chat reply-preview/search description: root 44/44; RLS identity module 27/27; password-change 19/19 GREEN;
  baseline GREEN / exact generated-AST RED повторены root, canonical statuses не изменены.
- RSS build guard сохранён: workers=4; три следующих build/up passed;
  max samples 1914,1/1942,1/2010,8 MiB <2048, не continuous peak; root 14 tests passed.
- Owned-state bridge и LF marker прошли Windows RED/GREEN; настоящий signed probe exit 0.
  Exact 57-spec diagnostics и retained MFA/email-OTP regressions проверены локально.
  Детальные receipts промежуточных checkpoints сохранены в
  [STATUS на 38e8c6d](https://github.com/egorribun/university_ecosystem/blob/38e8c6d0268674f0cd975ecce8aeea1525741b06/docs/superpowers/plans/STATUS.md).
- `6f96234f4`: полный live RED — 63 passed / 111 failed / 8 project-scoped skips.
  Повторный защищённый smoke после seed: 18 passed / 2 project-scoped skips, exit 0.
  `status` exit 0: bytes/population generated state до/после совпали; stop/start ещё открыт.
- Новая owned live-приёмка `38e8c6d`: up exit 0; focused 8 failed, отдельный admin replay 6 failed.
  Activity indicator/table/page errors повторились; bounded stdout содержит React #418, без test attribution.
  Owned stop/teardown exit 0; синтетические ресурсы удалены, исходные 175 containers/94 volumes сохранены.
  Удалены 18 + 9 + 9 owned image tags без force; evidence/configs сохранены private.

## Среда и ближайшие действия

- Windows: Node 24.21.0, uv 0.11.28, Docker CLI/Engine доступны; «Docker отсутствует»
  не переносится на эту машину. RAM/порты/ресурсы и принадлежность стенда проверяются
  перед запуском. Пользовательские `.env`, volumes, backups и evidence сохраняются.
- Live запуск: чистый checkout и отдельный private run-owned state root;
  source freeze после commit, без ослабления guards; тяжёлые jobs по одному.
- Runtime `38e8c6d` подтвердил cap 50, TTL 30 минут и login 60/minute; причина 111 failures не доказана.
  Проверить numeric Activity geometry, queue API/render state и SSR hydration; session cleanup только после RED/review.
- Продолжить блоки 4/5: traceability ТЗ, RU/EN, light/dark, ширины
  360/390/768/1024/1440; small visual packages и пользовательское утверждение baseline.
  Полный live stack, повторный stop/start и данные требуют отдельного evidence.
- Закрывать mutation debt по поведению, без waivers/exclusions, ручных Killed,
  timeout inflation или переноса локального verdict в canonical report.
- Подтвердить deployed PostgreSQL/Alembic upgrade/rollback и BE-02, paired S3/DB
  restore с чтением URL, RPO/RTO, WS load, Envoy Gateway/kind и failure recovery.
  Historical audit dispositions 60/2/1 не заменяют review всех 63 IDs.

## Открытые релизные допуски

Exact-head canonical mutation pass и все coverage/security gates; три сопоставимых
полностью зелёных CI наблюдения; полный live/visual/performance acceptance;
утверждённые baselines; WS load; paired backup/restore и RPO/RTO; BE-02 Docker/kind;
финальный независимый security review и audit ledger; resulting-main evidence;
шесть сертифицированных GHCR digests, их kind-приёмка и release `v1.0.0`.

Admin bypass, force-push, изменение защиты ветки, удаление пользовательских данных
и переписывание истории запрещены. Внешнее production, реальные SMTP/push,
физические устройства, CDC и field CWV остаются вне согласованной области MVP.
