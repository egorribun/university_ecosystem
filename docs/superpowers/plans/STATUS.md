# MVP — оперативный статус

Срез на 2026-10-05 (Europe/Istanbul). [Мастер-план](MVP_MASTER_PLAN.md)
задаёт приёмку; [ТЗ MVP](University_Ecosystem_MVP.md) — продуктовые границы.
Goal активен. Полная приёмка и выпуск `v1.0.0` не подтверждены.

## Контекст и источник доказательств

- Работа только на `egorribun`, один checkout и [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306).
  Проверенный опубликованный source — `01ffea1b5d0eca52f0b76e44d83aac3cb5890b71`;
  до изменений этой сессии HEAD, remote и PR head совпали; новые checkpoints локальные.
- После контрольной точки `2e78ce97d0daccd9d9ea74606ae07974a42ab555`:
  **123 коммита, 908 изменённых файлов**. Актуальный `main`
  `6fa133b57f62c554162876d4e6d8349f8060fce9` входит в историю ветки.
- Пользователь подтвердил включение [AUDIT_PROMPT.md](AUDIT_PROMPT.md) в Git.
  Исходные bytes сохранены в `cf9f5609`; инструкции шаблона не заменяют поручение пользователя.
  Tracked tree до этой сессии был чист.
- Root координирует три GPT-6 Luna Max: backend, frontend, CI/инфраструктура.
  Владельцы пишут в непересекающиеся файлы; Git-операции выполняет root.
- Полные исторические receipts, population, ограничения и сравнения сохранены
  в [предыдущем STATUS](https://github.com/egorribun/university_ecosystem/blob/01ffea1b5d0eca52f0b76e44d83aac3cb5890b71/docs/superpowers/plans/STATUS.md).
  Старые результаты не переименовывать в проверки нового SHA; отсутствующее
  локальное evidence не считается доступным доказательством.

## Актуальная hosted-проверка опубликованного source

- [Matrix 37236971603](https://github.com/egorribun/university_ecosystem/actions/runs/37236971603),
  attempt 1, source `01ffea1b5`: кампания ещё выполняется; окончательный verdict неизвестен.
  Четыре failed backend groups (1/4/6/8) имеют complete source-bound proofs:
  суммарно 143 selected, 126 Killed / 17 Survived. Это score-gate failures,
  а не полный inventory или runtime/provenance failures.
  Наличие успешных prerequisites не означает полного CI pass.
- [Owned live acceptance 37236971288](https://github.com/egorribun/university_ecosystem/actions/runs/37236971288)
  завершился success на том же SHA. Он подтверждает только перечисленный PR smoke;
  полную продуктовую, визуальную и disaster-recovery приёмку не заменяет.
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
  **1 646 уникальных tests / 102 файла**, setup/call/teardown без пропусков,
  дублей, skips/errors. До `40bec3868` весь backend/tooling побайтно совпал;
  новый backend run не заявляется. Это affected union, а не полный backend suite
  или PostgreSQL/RLS/NATS/Elasticsearch live integration.
- Regression controls покрывают session expiry/MFA, audit HMAC wire format,
  chat replay/attachments, search publication, SSR cache/session isolation,
  circuit waiter cancellation, timer ownership и deterministic schedule clock.
  Они не изменяют raw mutation outcomes и не являются release certification.
- Visual wrappers закреплены на Playwright 1.63.0 и official OCI digest;
  PowerShell сохраняет Docker exit code. Шесть stub-Docker cases passed;
  настоящий container/browser paint этим не подтверждён.
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

- Локальные commits: `5e2de259` (MFA export), `db329110` (cache regression),
  `8d84b200` (Bash contract). Push отложен до terminal текущей canonical кампании.
- Все применимые changed-file pre-commit hooks прошли. Synthetic fixture
  генерируется в runtime; новых suppressions/baseline entries нет.
- Исправлен экспорт MFA: public DTO не содержит отношения; отдельная проекция
  возвращает сохранённый count и безопасные enrollment metadata с изоляцией владельца.
  Root: 26 целевых backend tests passed; это не полный coverage/mutation допуск.
- Frontend: регрессия account-null cache isolation; root 25 tests passed.
  Native RED на историческом `shard-026:359` не даёт canonical Killed credit.
- Windows contract fixture выбирает Git Bash; отрицательные cases проверяют
  ожидаемую причину отказа workflow. Root focused contract lane прошёл.
- Первый preflight: 7/9 passed. Два failures устранены; отдельные повторные
  format и focused-contract lanes passed. Это не единый новый 9/9 report.
- Изменения production/tests прошли независимое scoped review; Git-операции root.
  Проверки относятся к base `01ffea1b5` с рабочим diff; hosted verdict не подменяются.
- Live build на `e150f009` остановлен RSS watchdog: frontend при SSR start
  достиг 2052,5 MiB при лимите 2048 MiB. Приёмка браузером не запускалась.
  Owned stop прошёл, running containers нет. Лимит не ослабляется;
  на `23550c18` native workers по умолчанию ограничены четырьмя; Docker GREEN
  ещё не подтверждён. Root: 14 build/telemetry tests и changed-file hooks passed.
- `405cd32a`: retained expired/revoked MFA regression; агент 26 tests passed,
  root persisted case passed; scoped review approved. Нового mutation verdict нет.

## Среда и ближайшие действия

- Эта сессия работает на Windows: Node 24.21.0, uv 0.11.28;
  Docker CLI/Engine доступны. Прежнее облачное ограничение «Docker отсутствует»
  не переносится на эту машину. RAM/порты/ресурсы и принадлежность стенда проверяются
  перед запуском. Пользовательские `.env`, volumes, backups и evidence сохраняются.
- Для source-bound live запуска нужен чистый source checkout и отдельный private
  run-owned state root; код и утверждённый документ закоммичены; source freeze
  начинается после финального status checkpoint. Guard не ослабляется. Тяжёлые jobs выполняются по одному.
- Проверить конечный exact-head CI и свежий mutation inventory; независимо разобрать
  backend auth/security/data, frontend session/realtime и CI/инфраструктурные изменения.
  Исправления получают RED/GREEN, review и scoped проверки до root commit/push.
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
