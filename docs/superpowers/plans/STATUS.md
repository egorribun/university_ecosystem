# MVP — оперативный статус

Срез на 2026-10-04 UTC. [Мастер-план](MVP_MASTER_PLAN.md) задаёт порядок
приёмки, [ТЗ MVP](University_Ecosystem_MVP.md) — продуктовые границы.
Текущий этап исправляет и полирует существующую реализацию; новые предметные
функции не добавляются. Полная приёмка MVP и выпуск `v1.0.0` ещё не подтверждены.

## Проверяемый контекст

- Активная ветка — `egorribun`, основной PR — [#1306](https://github.com/egorribun/university_ecosystem/pull/1306).
  Проверенный кодовый checkpoint — `2d669282437719ccae3fe5e2f71165a2fea44a66`,
  дерево — `1474d6de037e5c30336a8053676dfb8fcfde0c5a`.
  Это обновление STATUS является последующей документационной дельтой.
- В `main` интегрированы отдельные исправления trusted workflow и изоляции
  benchmark-процессов; проверенный base — `6fa133b57f62c554162876d4e6d8349f8060fce9`.
  Пороги и число performance-измерений сохранены.
- Опубликованный `b6d50fe468137b10942565bf5501000c04ec8437` имеет
  [matrix CI](https://github.com/egorribun/university_ecosystem/actions/runs/37184644787).
  Backend/frontend unit и coverage gates, browser smoke, types, security и
  performance prerequisites прошли. Attempt 1 и отдельный retry единственного
  frontend shard завершены; все 64 producer reports получены. Mutation gates
  остаются неуспешными; результаты ниже разделяют исходный и повторный attempts.
  [Owned live acceptance](https://github.com/egorribun/university_ecosystem/actions/runs/37184644560)
  остановился до Docker: структурный контракт ожидал старый вызов Enter без
  ограничения координат. Контракт исправлен в checkpoint выше; полный локальный live-contract suite
  (134 проверки) и 58 runtime keyboard controls прошли. Реальный live verdict нового
  checkpoint ещё не получен.
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

- Свежий полный frontend unit/coverage-прогон на **Node 24.15.0** прошёл:
  **718 файлов, 8 635 тестов**, без skips/failures, **100%** statements
  (19 141/19 141), branches (13 680/13 680), functions (4 561/4 561)
  и lines (17 123/17 123). Все **4 652 authored inputs** сохранили hashes и modes.
  Это локальное evidence кодового checkpoint выше, не hosted verdict.
- Дополнительный полный frontend shuffle (seed 1306006, maxWorkers 4) теперь
  также прошёл **8 635/8 635** без failures, skips и unhandled errors на том же
  замороженном дереве. Прежний `c883ad73` на этом порядке дал 18 failures в
  11 файлах и 2 unhandled errors; эти receipts сохранены. Исправлены владение
  deferred imports/crypto/IndexedDB work, lifecycle service-worker событий,
  сброс mock implementations, восстановление auth/storage/spies и изоляция
  browser-history fixtures. Cold QR fallback проверяется отдельным controlled
  import с существующим локальным SDK/MSW enrollment payload. Production code
  этих исправлений не менялся. Один успешный seed не доказывает все порядки.
- Свежий единый прогон на checkpoint выше прошёл **1 240 affected backend/workflow
  тестов** в 83 файлах, без skips, failures и ошибок. Он объединяет 1 175 tests
  предыдущего `4b35f8a5` и последующие 125: 60 фактических node identities
  совпадают и исключены из повторного исполнения. Каждый из 1 240 уникальных
  nodes прошёл setup/call/teardown ровно один раз; пропусков и лишних IDs нет.
  Проверены analytics/MFA/rate-limit/NATS/workflow, chat/webpush, circuit-lock,
  password-rehash, chat retry windows и search consumers. Это не полный backend suite и не настоящая
  PostgreSQL/RLS/SKIP LOCKED/NATS/Elasticsearch integration. Все **4 652 inputs**
  сохранены. Предыдущий `4b35f8a5` отдельно прошёл 1 175 tests; его
  первоначальный collection setup с конфликтующим именем внешнего recorder
  import сохранён как невалидная попытка. Нынешний прогон использует исправленный
  отдельный namespace recorder и не переименовывает прежние receipts.
- На текущем дереве прошли полные frontend types, scoped frontend/Python
  lint/format, nonempty inventory и secret scans. Предшествующий `827f19ab`
  отдельно прошёл полные frontend lint, scoped application mypy, actionlint,
  **544 tooling tests**, **134 live contracts**, **47 policy/baseline tests**.
  После него изменены только 12 рассмотренных source/test paths;
  код tooling/workflow controls и пороги не менялись. Прежние tooling receipts не
  переименованы в свежий прогон нового дерева. Тогда dependency layout был
  приведён к обычной директории с идентичными установленными файлами; исходный
  setup-specific отказ сохранён. Docker/live stack этими проверками не запускался.
- Семь paths между `827f19ab` и `4b35f8a5` содержали: шесть прежних cross-loop circuit сценариев
  с ограниченным owned subprocess preflight и тем же inline body; реальную
  account-scoped password rehash проверку; in-process Elasticsearch SDK deletion
  contracts; удаление из Skeleton избыточного default с публичными omitted/undefined
  controls. Тогда дополнительно 910 frontend consumer tests прошли нормально
  и на seeds 1306006/113017475. Эти прежние receipts не переименованы в новый
  snapshot; fake transport не считается live Elasticsearch.
- Последующие пять paths проверяют 24-hour completed chat replay и five-minute
  lease takeover через публичный dispatcher на FakeRedis; omitted/undefined
  debounce/scroll/observer defaults и владение cleanup. Отрицательные controls
  подтверждают сохранение исключений из upload/fixture cleanup. Это не live Redis,
  native browser geometry или browser animation proof. Ровно один private News
  helper теперь требует уже разрешённый caller-ом method; default остаётся на
  границе handleMutationError, body и public exports сохранены. Общее число
  frontend branches уменьшилось на два относительно `827f19ab` вследствие двух
  reviewed source simplifications, а не исключений или изменения порога.
- Локальные exact/native mutation controls не меняют canonical statuses.
  Empty-string delay/scroll variants не проходят types и не получают viable
  kill credit. Margin residual остаётся открытым: native zero-offset normalization
  не доказывает полную эквивалентность жизненного цикла hook.
- Реальная soft-delete запись проверяется повторным авторизованным edit и
  свежей DB session: tombstone целиком сохраняется. Webpush timeout tests
  независимо наблюдают завершение caller, освобождают/дожидаются своих workers
  и сохраняют неожиданные cleanup failures. Это тестовые контракты; прежний
  canonical webpush Timeout не переклассифицирован локальным replay.
- Необязательные глобальные LHCI wrapper links допускают read-only filesystem
  (EROFS); ошибки локальных links и неожиданные I/O ошибки по-прежнему
  завершают setup неуспешно. Реальный npm reinstall и запись в system paths
  при локальных проверках не выполнялись.
- Исправлена изоляция profile lifecycle fixture: незавершённая криптографическая
  работа предыдущего теста могла занять следующий одноразовый gate и вызвать
  перезапись ожидаемого test envelope. Теперь owned work завершается до
  восстановления spies, а тест ждёт собственную readable publication.
  Точное сравнение remote envelope сохранено. После воспроизведения на
  неизменённом baseline финальный auth shuffle прошёл **410/410**; это
  test-only correction, не заявление о найденном production regression.
- Новые tests проверяют реальные grade/attendance окна и cache invalidation,
  сохранение MFA challenge/delivery/outbox, population MFA metric,
  восстановление Redis client factory и сохранённый replayable NATS dead letter.
  Подмена network transport в NATS и прямой DI boundary MFA не выдаются за
  полноценные network E2E.
- Предыдущий восстановленный checkpoint `66ed5403` отдельно прошёл **674
  backend/quality теста в 41 файле**. Этот исторический affected-прогон не
  переименован в свежую проверку нынешнего дерева.
- Исправлено падение participation stats для события без категории: обязательное
  поле внутреннего DTO допускает уже разрешённый EventCreate/ORM null. Реальные
  сохранённые строки проверяют окна, проценты, дробные часы, recent projection и
  пользовательский cache/invalidation. Публичные hook/cache tests проверяют
  слияние истории Messenger и обновление/частичную доступность Activity.
  Точные локальные RED controls остаются диагностикой, не canonical kill credit.
- Исправлены границы выбранной ячейки расписания и владение Enter встроенными
  кнопками/ссылками. Modal focus и закрытие подсказок Events используют существующий
  focus trap. Button использует реально генерируемые theme utilities и блокирует
  default navigation/chooser у disabled polymorphic controls; цвета Spotify
  сохранены. DOM/SSR и emitted-CSS проверки не заменяют browser paint и visual acceptance.
- В списке чатов сохранён UUID последнего сообщения и добавлена одна batch-загрузка
  avatar данных только возвращаемых участников. Shared DTO contract не менялся;
  проверены чистые, загруженные, deferred и detached ORM-состояния и постоянное
  число запросов для одной и восьми бесед. Это не изменение avatar-проекции всех
  прочих endpoint-путей.
- Усилены проверки audit wire format через независимый HMAC и реальные DTO,
  auth/MFA, causal outbox delivery, Redis/circuit lifecycle, upload ownership и
  frontend session lifecycle. Тесты владеют отложенной работой и восстанавливают
  Storage/auth state; одноразовые ответы login mocks сбрасываются между cases.
  Повтор search pagination и раннее завершение worker приводят к ясной ошибке
  теста с завершением owned tasks. Старые Timeout/Survived статусы не переписывались.
- Четыре прежних локальных inventory receipts признаны недействительными:
  command receipt перезаписал manifest, а checker принимал отсутствующий files
  как пустой список. Теперь некорректный/пустой manifest отклоняется fail-closed.
  Свежий manifest содержит **4 220 records**, включая все **4 218** применимых
  authored paths без пропусков/дубликатов; дополнительные `.git` worktree
  metadata и `tests/queries.log` не считаются authored evidence. В hosted workflow
  такого совпадения выходных путей не обнаружено. Baseline изменён только в
  номерах строк существующих workflow/QR fixture entries и generated timestamp;
  fingerprints, entry counts, detector configuration и filters сохранены.
  Новые исключения не добавлены.
- Ранее исправлены cooldown signing-key запросов и владение их результатами,
  отмена устаревшего поиска и принадлежность install prompt текущему аккаунту.
  Реальные pending, retry, generation-change, cache, navigation и RU/EN Activity
  контракты сохраняются. Убраны только проверенные дубли guards/defaults;
  quality-пороги и исключения не расширялись.
- Прежний Stryker preload заменял глобальный `String` и подавлял native TypeError.
  Затронутые исторические outcomes остаются **provisional, diagnostic-only**.
  Новый адаптер меняет только diagnostic fallback закреплённого Stryker module;
  версия, полный публичный digest и checksum record проверяются fail-closed.
  На packaging checkpoint `9bebdf7f` прошли 203 adapter/evidence contracts, Knip
  и secret checks. Тогдашний настоящий producer smoke сохранил все 153 мутанта:
  83 Killed, 64 Survived, 4 Ignored, 2 RuntimeError. Это проверка транспорта,
  не mutation closure нового checkpoint.

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

## Текущая mutation-кампания на b6d50fe4

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
она ещё не исправлена в кодовом checkpoint выше.

Завершённая кампания сохраняется для сопоставимого inventory. Локальные RED controls
и исправления не меняют её raw outcomes и не заменяют свежий canonical execution
следующего опубликованного checkpoint.

## Ближайшие проверяемые результаты

1. Получить конечный exact-head CI нового опубликованного batch. Исправлять
   конкретные причины, не переносить старые verdicts между SHA.
2. Продолжить semantic regression coverage по полному текущему mutation inventory.
   Сначала supported user-visible состояния и воспроизводимые баги; для удаления
   dead code требуется доказательство отсутствия потребителей. Неподтверждённые
   defensive/equivalent случаи остаются открытыми, без waivers и ручных статусов.
3. Связать применимые пункты ТЗ и все 63 audit IDs с актуальным evidence или точным
   открытым ограничением. Исторические 60/2/1 dispositions не являются новым аудитом.
4. Продолжить приёмку RU/EN на 360/390/768/1024/1440 px и подготовить визуальные
   комплекты для пользовательского review. Проверить предусмотренные master plan
   performance и memory критерии на указанной конфигурации.
5. Получить deployed evidence для непустых PostgreSQL/Alembic upgrade/rollback,
   S3 paired backup/restore и DB URL reads, RPO/RTO, WS load, Gateway API/kind
   TLS/WS/gRPC и failure recovery. В текущей облачной среде отсутствует локальный
   Docker/live-стек. Браузерные инструменты доступны; локальный paint новых Button
   состояний не проверен. Hosted PR smoke закрывает только свой перечисленный набор.

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
