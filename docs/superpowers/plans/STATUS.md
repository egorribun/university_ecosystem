# MVP — оперативный статус

Срез на 2026-10-04 UTC. [Мастер-план](MVP_MASTER_PLAN.md) задаёт порядок
приёмки, [ТЗ MVP](University_Ecosystem_MVP.md) — продуктовые границы.
Текущий этап исправляет и полирует существующую реализацию; новые предметные
функции не добавляются. Полная приёмка MVP и выпуск `v1.0.0` ещё не подтверждены.

## Проверяемый контекст

- Активная ветка — `egorribun`, основной PR — [#1306](https://github.com/egorribun/university_ecosystem/pull/1306).
  Проверенный кодовый checkpoint — `66ed540306b0929b8eb0ac02237e3bc70205382b`,
  дерево — `ca742d2bc9532a86a24cafeec62ef16f93bb5e2b`.
  Это обновление STATUS является последующей документационной дельтой.
- В `main` интегрированы отдельные исправления trusted workflow и изоляции
  benchmark-процессов; проверенный base — `6fa133b57f62c554162876d4e6d8349f8060fce9`.
  Пороги и число performance-измерений сохранены.
- Предыдущий опубликованный checkpoint `2595c0ebc674edb69557f3c6edd0a184973d62e2`
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
  **714 файлов, 8 594 теста**, без skips/failures, **100%** statements
  (19 141/19 141), branches (13 682/13 682), functions (4 561/4 561)
  и lines (17 123/17 123). Все **4 642 authored inputs** сохранили hashes во время
  прогона. Это локальное evidence кодового checkpoint выше, не hosted verdict.
- На том же замороженном candidate прошли **674 backend/quality теста в 41 файле**,
  без skips/failures и изменений authored inputs. Это объединённый affected-прогон,
  а не полный backend suite или PostgreSQL/RLS/SKIP LOCKED integration.
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
  Свежий manifest содержит **4 209 records**, включая все **4 208** применимых
  Git-authored paths без пропусков/дубликатов; дополнительный `tests/queries.log`
  классифицирован как utility. В hosted workflow такого совпадения выходных путей
  не обнаружено. Ruff, frontend types/lint/format, Markdownlint, links,
  detect-secrets и GitLeaks проходят; baseline изменён только в метаданных строк.
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
  к завершённой группе. Clock-регрессия исправлена в новом candidate, но для него
  требуется свежий canonical execution.
- Ни compile-invalid, ни equivalent residuals не получают ручной переклассификации.
  Частичные локальные mutation-прогоны не заменяют полный exact-head gate.

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
