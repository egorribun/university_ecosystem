# MVP — оперативный статус

Срез на 2026-10-04 UTC. [Мастер-план](MVP_MASTER_PLAN.md) задаёт порядок
приёмки, [ТЗ MVP](University_Ecosystem_MVP.md) — продуктовые границы.
Текущий этап исправляет и полирует существующую реализацию; новые предметные
функции не добавляются. Полная приёмка MVP и выпуск `v1.0.0` ещё не подтверждены.

## Проверяемый контекст

- Активная ветка — `egorribun`, основной PR — [#1306](https://github.com/egorribun/university_ecosystem/pull/1306).
  Проверенный кодовый checkpoint — `40bec3868800f7411d045c4468e593df63d84ab0`,
  дерево — `b8bb8e60e0eec5dba9f3fd5df7462949d531de35`.
  Это обновление STATUS является последующей документационной дельтой.
- В `main` интегрированы отдельные исправления trusted workflow и изоляции
  benchmark-процессов; проверенный base — `6fa133b57f62c554162876d4e6d8349f8060fce9`.
  Пороги и число performance-измерений сохранены.
- Опубликованный `f39d5421341d84dd5e316fe9e88e2b4399758d0e` проверен в
  [matrix CI](https://github.com/egorribun/university_ecosystem/actions/runs/37213691132),
  [owned live acceptance](https://github.com/egorribun/university_ecosystem/actions/runs/37213690972)
  и [performance](https://github.com/egorribun/university_ecosystem/actions/runs/37213690906).
  Обычные unit/coverage, types, security, browser/live smoke и performance
  prerequisites прошли. Кампания завершилась failure на mutation gates:
  **367** terminal check-runs — **216 success, 20 skipped, 131 failure**.
  Это 128 backend mutation groups и три aggregate/required contexts;
  новых selector/provenance/clean-baseline failures не обнаружено.
  Тестируемый merge — `d1ae8fba7311fc196b555823e94d93dc7dc53740`,
  его дерево совпадает с опубликованным `f39d5421`. Эти результаты не считаются
  hosted проверкой последующего кодового checkpoint выше.
- Предыдущая кампания `b6d50fe468137b10942565bf5501000c04ec8437` завершена;
  все 64 frontend reports сверены с сохранением producer attempts. Mutation gates
  остались неуспешными. Старый live-contract блокер Enter исправлен; новый owned
  live smoke на `f39d5421` прошёл свой перечисленный набор.
- Более ранний checkpoint `2595c0ebc674edb69557f3c6edd0a184973d62e2`
  имеет [matrix CI](https://github.com/egorribun/university_ecosystem/actions/runs/37164443034),
  [owned live acceptance](https://github.com/egorribun/university_ecosystem/actions/runs/37164442808)
  и [performance](https://github.com/egorribun/university_ecosystem/actions/runs/37164442867).
  Все 367 check-runs завершены: 216 success, 20 skipped, 131 failure.
  Обычные unit/coverage, browser/live, types/build, security scan, Pact,
  Schemathesis и performance prerequisites прошли. Mutation gate не зелёный;
  эти результаты не заменяют CI нового опубликованного SHA.
- Исходники, локальные инструменты и evidence разделены. Секреты, пользовательские
  данные, volumes, backups, история Git и Alembic сохраняются. После замены
  облачной среды часть незапушенных правок восстановлена по совпадающим hashes,
  часть заново реализована и проверена. Потерянные локальные receipts не
  используются как доказательство нового candidate. Проверенные code checkpoints
  теперь сохраняются в GitHub до длительных aggregate-прогонов.

## Подтверждённый прогресс

- На точном кодовом дереве выше выполнены свежие полные frontend-прогоны:
  **719 файлов, 8 642 теста** на Node 24.15.0, без skips/failures/errors;
  **100%** statements (19 141/19 141), branches (13 680/13 680),
  functions (4 561/4 561) и lines (17 123/17 123). Полный shuffle
  seed 1306006, maxWorkers 4 также прошёл **8 642/8 642** без unhandled errors.
  Оба JUnit reports содержат одинаковые **8 642** уникальные test identities.
  Все **4 655 authored inputs** сохранили bytes и modes между прогонами.
  Это configured frontend unit suite, не browser E2E или canonical mutation pass;
  один shuffle seed не доказывает все возможные порядки.
- Affected backend evidence явно наследуется от
  `5edca1efafacfee272507cf407db6c4d9ee1f4be`: **1 646 уникальных
  backend/workflow/tooling tests в 102 файлах**. Каждый node прошёл setup,
  call и teardown ровно один раз; skips, errors, missing и duplicate IDs отсутствуют.
  Набор сохраняет все прежние **1 399** node identities из e73 и объединяет
  рассмотренные дополнения с их фактическими consumer controls.
  Между 5ed и нынешним checkpoint изменён только один frontend test clock;
  остальные **4 654 authored inputs**, включая весь backend и tracked tooling,
  побайтно совпали. Hashes всех 45 прежних evidence artifacts проверены.
  Новый backend-прогон не заявляется. Это affected union, не полный backend suite
  и не настоящая PostgreSQL/RLS/SKIP LOCKED/NATS/Elasticsearch integration.
- Scoped Python Ruff/format, Bash/PowerShell syntax, diff check, detect-secrets
  и Gitleaks из 5ed сохраняют свой исходный scope; для изменённого clock test
  отдельно прошли targeted lint/format и обе secrets-проверки.
  Свежая ownership validation нынешнего дерева проверила непустой manifest:
  **4 222 records**, все **4 221** применимых authored paths без пропусков и
  дубликатов; дополнительный `.git` — metadata worktree, не authored input.
  Baseline bytes не менялись. Локальный Docker/Semgrep container не запускался;
  будущие exact-head hosted gates остаются обязательными. Старые tooling/typecheck
  receipts не переименованы в свежие результаты объединённого дерева.
- Устранена зависимость existing `useScheduleTime` test от времени суток:
  `hasToday=false` проверяется в фиксированный момент внутри имеющегося урока.
  Раньше вечером удаление защитного условия оставалось незаметным; native control
  подтвердил это, а закреплённый clock даёт ожидаемый failed assertion.
  Production hook не менялся; это проверка его существующего defensive contract,
  не установленный пользовательский production bug. Raw f39 Survived сохраняется.
- Добавлены SSR QueryClient controls для Events и timer ownership для useClock:
  отдельные request caches, cursor/dedup boundaries, unmount/StrictMode/repeated
  mount/locale и сохранность чужого timer. Production frontend не изменён.
  Исторические Survived/Timeout не получают credit от локальных controls.
- Circuit cancellation теперь проверяется до освобождения занятого state lock:
  отмена среднего из трёх queued requests не лишает остальные прогресса.
  Тест дренирует всю owned работу и сохраняет primary/sibling/release failures.
  Реальный mutmut stats подтверждает связь нового теста с `_acquire_state_lock`;
  exact native mutant 9 даёт обычный failed assertion. Исходные budgets и
  production circuit code не менялись. Это локальное candidate evidence.
- Проверены независимые audit v2 HMAC fixtures с разрешённым empty action,
  граница session expiry точно в текущий instant, PostgreSQL identity forwarding,
  реальные Elasticsearch client argument checks и alias publication payloads,
  forwarding пяти SpiceDB transport options и SQLite/Alembic nullable drift.
  Контролируемые DB/HTTP/gRPC границы не выдаются за live server evidence.
- Visual Docker wrappers приведены к закреплённой в manifest/lock Playwright
  **1.63.0** с проверенным official OCI digest. PowerShell wrapper сохраняет
  ненулевой Docker exit code вместо ложного успешного завершения. Все **шесть**
  real-pwsh/stub-Docker cases фактически исполнены и passed в общем наборе;
  проверены verify/update, exit 0/17/125 и paths с пробелами. Это не настоящий
  Docker/Windows/browser прогон. Текущий Windows-only snapshot guard сохранён;
  all-skipped Linux invocation не считается визуальной приёмкой.
- Timing analyzer теперь распознаёт строго проверенную форму carried-forward
  jobs после partial rerun. Исходные timestamps сохраняются, неизвестная queue
  duration остаётся неизвестной, обычные chronology/provenance ошибки запрещены.
  Replay всех 316 настоящих job records сохраняет 172 success, 131 failure и
  13 skipped. Это compatibility repair отчёта, не превращение failed CI в success.
- Один отсутствовавший RZ-22-01 комментарий описывает попытку transaction/file
  rollback перед re-raise. AST обработчика сохранён; наличие 157 tags само по
  себе не доказывает корректность всех 157 broad exception handlers.
- Предыдущие исправления analytics/MFA, transactional outbox, session lifecycle,
  chat projection/replay, search rebuild, schedule/Enter/focus, Button tokens,
  async fixture ownership и документации сохраняются. Их подробные исторические
  проверки доступны в [STATUS на f39d5421](https://github.com/egorribun/university_ecosystem/blob/f39d5421341d84dd5e316fe9e88e2b4399758d0e/docs/superpowers/plans/STATUS.md#L40).
  Прежние 1 240/1 175/674 affected backend и 544 tooling/134 live-contract/47 policy
  результаты не подменяют свежий scope. Браузерный paint и deployed интеграции
  остаются отдельной приёмкой.
- Исторические outcomes старого Stryker preload, который заменял глобальный
  `String`, остаются provisional/diagnostic-only. Нынешний pinned transport adapter
  сохраняет runtime semantics; прежние 203 adapter/evidence tests и producer smoke
  относятся к своему packaging checkpoint, не являются новым aggregate verdict.
  Четыре старых локальных inventory receipts были признаны недействительными;
  missing/malformed/empty manifests теперь отклоняются fail-closed. Потерянные
  при замене среды receipts и неполные доказательства не переиспользуются.
- Quality thresholds, mutation exclusions и secret baseline не менялись.
  В новом wrapper test два узких `noqa: S603` документируют subprocess с фиксированными
  argv и собственным временным Git/Docker stub; новые policy allowlists не добавлялись.
  Локальные exact/native controls не переписывают canonical statuses;
  compile-invalid/equivalent residuals без установленного проверяющего механизма
  остаются открытыми. Восстановленные и заново реализованные изменения различаются
  по provenance; очередной просмотр 63 audit IDs не считается полной сертификацией.

## Полный mutation inventory на 2595c0eb

- Frontend: все **64** artifacts повторно скачаны и проверены; **42 897** signatures
  представлены ровно по одному разу, без пропусков/дубликатов/чужих записей.
  Итог: **36 771 Killed, 4 796 Survived, 11 NoCoverage, 44 Timeout,
  33 RuntimeError, 0 CompileError, 1 242 Ignored**. Открытых raw outcomes — **4 884**
  в 265 файлах. Aggregate корректно отклонил первый Survived; проверенный merged
  artifact не был выпущен. Успешные producer jobs не означают mutation pass.
- Backend: generation/stats прошли восемь частей и центральную проверку universe.
  PR-selected execution содержит **4 524 IDs** из **54 410** generated identities.
  127 завершённых групп дали **3 501 Killed, 969 подтверждённых Survived, 19 Timeout**.
  Группа 47 не завершила full-map confirmation из-за QR clock-boundary baseline
  failure; её 25 primary Killed и 10 unconfirmed primary Survived не приравниваются
  к завершённой группе. Clock-регрессия исправлена в `b6d50fe4`; историческая
  неполная группа не переименована в результат новой кампании.
- Ни compile-invalid, ни equivalent residuals не получают ручной переклассификации.
  Частичные локальные mutation-прогоны не заменяют полный exact-head gate.

## Завершённая mutation-кампания на b6d50fe4

Frontend preflight проверен по immutable Git inputs: **42 915** identities,
565 policy files, 43 файла без сгенерированных мутантов и 64 непересекающихся
assignments. Backend generation содержит **54 418** identities; проверенный
selected plan — **4 540** identities в 128 группах. Эти populations не наследуют
counts/verdicts от 2595c0eb. Attempt 1 завершился failure 2026-10-04 в 13:33 UTC;
полный snapshot содержит 367 checks: 214 success, 20 skipped и 133 failure.
После единственного retry attempt 2 также завершён failure: полный exact-head
snapshot содержит 367 checks — 215 success, 20 skipped и 132 failure, без pending.
Gate не зелёный. Число failed jobs не равно числу отдельных production bugs.

Backend завершён и полностью сверен: **128/128** groups, все **4 540** assignments
ровно по одному разу, без missing/foreign entries, все proof stages complete.
Итог — **3 673 Killed, 865 подтверждённых Survived, 2 Timeout**. Full-map
confirmation дополнительно убила 81 primary survivor. На сравнимых unchanged
function AST 112 прежних survivors и 17 timeouts теперь Killed; два прежних
Killed теперь Survived, два прежних Timeout сохранились. Это raw comparison,
не заявление о новых production regressions или ручной переклассификации.
Оба оставшихся Timeout — webpush caller и native circuit-lock contention.

Frontend attempt 1 полностью сохранён: **63/64** reports и **41 460/42 915**
identities ровно по одному разу. Raw totals: **35 483 Killed, 4 694 Survived,
8 NoCoverage, 34 Timeout, 31 RuntimeError, 0 CompileError, 1 210 Ignored**.
Aggregate независимо отклонил incomplete 63/64 inventory. Shard 027 остановился
до mutation execution при выборе artifact catalog; его **1 455** assigned
identities отсутствуют именно в attempt 1. После завершения кампании однократно
запрошен retry только этого job. В attempt 2 новый job `111447706572` прошёл
selector/download/provenance/preflight validation и свежий Stryker execution
на том же `b6d50fe4`, завершившись success. Его artifact `11307805307` содержит
ровно 1 455 assigned signatures: 1 394 Killed, 23 Survived, 6 Timeout и 32 Ignored.
Сохранённая identity preflight остаётся из attempt 1; первый attempt не подменяется новым.

Полное объединение содержит **64/64 reports и 42 915/42 915 identities** без
пропусков, дубликатов и чужих записей: 63 reports из attempt 1 и только shard 027
из attempt 2. Raw totals — **36 877 Killed, 4 717 Survived, 8 NoCoverage,
40 Timeout, 31 RuntimeError, 0 CompileError, 1 242 Ignored**. У каждой записи
сохранён исходный producer attempt. Aggregate теперь отклоняет реальный Survived
`shard-026:269`, а не отсутствие shard. Успешный retry producer не означает
mutation pass.

В локальном воспроизведении
конкурентная загрузка artifacts меняет valid total_count между страницами и
вызывает такой же прежний selector error. Исправление допускает три полных
перечитывания в прежнем общем 120-second budget, отбрасывает partial scan и
сохраняет provenance/digest/attempt checks. Его проверяют реальные extracted
workflow scripts и actionlint. Конкретная причина удалённого shard 027 не
установлена: прежний лог не сохранил значения ответа.

Отдельно partial rerun выявил несовместимость timing-ledger analyzer: GitHub
вернул carried-forward Contract Tests job с новым created_at после исходных
started_at/completed_at. Analyzer отклонил chronology; последующие render/upload
шаги не получили ledger. Исходные timestamps и ошибки сохранены. Это отдельная
неисправность диагностики повторного запуска, не новый production regression;
её узкое исправление включено в кодовый checkpoint выше и проверено replay,
но новый hosted partial-rerun verdict ещё не получен.

Завершённая кампания сохраняется для сопоставимого inventory. Локальные RED controls
и исправления не меняют её raw outcomes и не заменяют свежий canonical execution
следующего опубликованного checkpoint.

## Завершённая mutation-кампания на f39d5421

Run 37213691132, attempt 1, естественно завершился **2026-10-04 21:30 UTC**.
Frontend inventory запечатан в **21:34 UTC**: все **64/64 reports** проверены,
все **42 913** preflight signatures представлены ровно по одному разу,
без omissions/duplicates. Raw counts: **36 938 Killed, 4 669 Survived,
1 NoCoverage, 32 Timeout, 31 RuntimeError, 0 CompileError, 1 242 Ignored**.
Все producers прошли; aggregate явно отклонил `shard-026:269` со статусом
Survived. Validated-evidence и historical-cost uploads были skipped,
validated artifact отсутствует; required frontend context и CI Success failed.
Шарды 26 и 27 на этом head полностью опубликовали assignments с первой попытки;
старый retry не переносится. Timing ledger steps текущей попытки прошли.

Backend evidence полностью запечатан **2026-10-04 20:00 UTC**: все **128/128**
complete proofs и 138 archives проверены, **4 540 selected IDs** представлены
ровно по одному разу. Итог — **3 764 Killed и 776 подтверждённых Survived**;
остальные native statuses равны нулю, incomplete/baseline/forced-control failures
не обнаружены. Full-map confirmation дополнительно убила 104 из 880 primary
survivors. Все 128 jobs завершились failure на неизменённом mutation gate.

Generation содержит **54 418** identities; **49 878 unselected** не имеют
execution evidence и не считаются Killed или NoCoverage. Сопоставление одинаковых
source/function AST с b6 даёт 90 Survived→Killed, оба Timeout→Killed и один
Killed→Survived (circuit mutant 9). Остальные 775 survivors сохраняются.
Новый локальный regression control circuit 9 не меняет его текущий raw outcome;
причина прежнего Killed не установлена. Полнота execution evidence не меняет
неуспешный mutation verdict и не является полным viable score.

Frontend storage mutant 238 локально ловится уже существующим SSR test в
ограниченном native replay (205 unchanged tests). Canonical Timeout остаётся
неразрешённым: это не доказательство его удалённой причины. News mutant 224
сообщает hit-counter limit, что отличается от wall-clock deadline. Из всех
32 Timeout у **22** есть явный hit-limit reason, у **10** причина в raw report
не указана; отсутствие reason не доказывает wall-clock timeout. Schedule mutant
593 сменил Killed→Survived при одинаковом production source; bounded replay
подтвердил зависимый от времени суток fixture, исправленный в нынешнем checkpoint.
Raw статусы и лимиты не изменены. Успешные producers и локальные controls
не означают 100% viable mutation score.

Отдельный согласованный [checker diagnostic run 37215003443](https://github.com/egorribun/university_ecosystem/actions/runs/37215003443)
завершился **inconclusive** 2026-10-04 20:16 UTC по absolute deadline этапа
compiler parity. Он проверял исходный `2595c0eb` и assignment 27 из **1 460**
signatures, а не f39 population. Все результаты producer сохранены: **874 Killed,
532 CompileError, 18 Survived, 4 Timeout, 32 Ignored**. Из 532 CompileError
независимая сверка TS6/TS7 выполнена для **195**: **191** имеет точное совпадение
code/file/span, **4** отличаются кодами или диапазонами диагностики, **337**
остались непроверенными. Оба компилятора отвергают все 195 проверенных вариантов;
четыре расхождения сохраняют inconclusive по принятому точному критерию.

Все четыре compiler baseline прошли без ошибок. Sampled producer RSS peak —
**9.483 GiB**, минимальный наблюдаемый host headroom — **5.164 GiB**. Все десять
phase receipts сообщают quiescent cleanup без ошибок; прироста видимых OOM counters
не наблюдалось. Запуск с upload занял **4 ч 17 мин 47 с**, внутри установленного
лимита. Hidden constraints, несэмплированные пики и capacity всей кампании этим не
доказаны. Из 532 CompileError **527** раньше уже были Killed, **5** были Survived;
эти пять входят в 191 exact match. Другие 18 survivors остались Survived.
Каноническая конфигурация checker и исходные статусы не менялись; эксперимент
не даёт canonical kill/exclusion credit. Повторного запуска не было.

## Ближайшие проверяемые результаты

1. Получить конечный exact-head CI нового опубликованного batch. Исправлять
   конкретные причины, не переносить старые verdicts между SHA.
2. Продолжить semantic regression coverage по полному текущему mutation inventory.
   Сначала supported user-visible состояния и воспроизводимые баги; для удаления
   dead code требуется доказательство отсутствия потребителей. Неподтверждённые
   defensive/equivalent случаи остаются открытыми, без waivers и ручных статусов.
3. Связать применимые пункты ТЗ и все 63 audit IDs с актуальным evidence или точным
   открытым ограничением. Исторические 60/2/1 dispositions не являются новым аудитом.
4. Docker и визуальную приёмку выполняет владелец проекта; оба manual gates
   остаются pending. Подготовлен source-bound чек-лист. Нужны RU/EN на
   360/390/768/1024/1440 px, reviewed visual baseline, предусмотренные master plan
   performance и memory измерения. Перед выполнением фиксируется актуальный candidate SHA.
5. Получить deployed evidence для непустых PostgreSQL/Alembic upgrade/rollback,
   S3 paired backup/restore и DB URL reads, RPO/RTO, WS load, Gateway API/kind
   TLS/WS/gRPC и failure recovery. В текущей облачной среде отсутствует локальный
   Docker/live-стек; Docker-зависимую часть ручной проверки выполняет владелец проекта.
   Локальный paint новых Button состояний не подтверждён. Hosted PR smoke
   закрывает только свой перечисленный набор и не заменяет visual approval.

## Открытые release gates

Полный canonical mutation pass и exact-head CI; три сопоставимых полностью
зелёных наблюдения; полный live/visual/performance acceptance; пользовательское
утверждение визуальных baseline; WS load; deployed paired backup/restore и
RPO/RTO; BE-02 на Docker/kind; финальный независимый security review и audit
ledger; resulting-main evidence; шесть сертифицированных GHCR digests и их kind
приёмка. Существующие ограничения и rollout-требования должны войти в release
notes. До этих доказательств MVP не считается сертифицированным.

Административный bypass, force-push, изменение защиты ветки, удаление
пользовательских данных и переписывание истории остаются запрещены. Внешнее
production, реальные SMTP/push-провайдеры, физические устройства, CDC и field CWV
не входят в MVP. Исторические checkpoint-результаты сохраняются в Git;
недоступные локальные evidence нельзя считать текущим подтверждением.
