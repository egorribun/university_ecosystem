# MVP — оперативный статус

Срез на 2026-10-06 (Europe/Istanbul). [Мастер-план](MVP_MASTER_PLAN.md)
задаёт приёмку; [ТЗ MVP](University_Ecosystem_MVP.md) — продуктовые границы.
Работа возобновлена по поручению пользователя. Выпуск `v1.0.0` не подтверждён.

## Контрольная точка

- Работа только на `egorribun`, один checkout и [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306).
  Последний source с runtime-проверками — `80b40d291524ac059be3708d4bab6a408790203c`.
  Его результаты не подтверждают автоматически следующий HEAD.
- Root — единственный tracked writer и владелец Git. Три GPT-6 Luna Max
  работают параллельно над ограниченными приватными пакетами; root проверяет
  их код, происхождение evidence и результаты до интеграции.
- В `4ad881929` интегрированы SmartImage source-keyed fallback и versioned srcset,
  регрессии rotated legacy audit signature и persisted `NewsUpdated` title.
  Root независимо проверил RED/GREEN. Canonical affected frontend tests: 76/76;
  backend audit/news tests: 38/38. Это не release certification.
- В `80b40d291` добавлены CAS rejection, deterministic MFA export-order
  и persisted NewsUpdated news_id regression. Root воспроизвёл baseline PASS
  и точные AST-контроли: CAS 101/102/103/105, export-order 13, news-update 13 —
  call-phase AssertionError. После интеграции canonical affected tests: 23/23.
  До нового канонического producer mutation credit не присваивается.
- SmartImage CI gap воспроизведён на исходном коде. После независимого ревью
  убраны только недостижимые внутренние guards; внешняя URL-проверка и fallback
  сохранены. Root canonical focused suite: 20/20; statements 33/33,
  branches 41/41, functions 10/10, lines 28/28. Full CI ещё нужен.
- Текущий checkpoint добавляет persisted ranked-news tie/cursor regression:
  root baseline PASS, exact mutant 114 — call-phase AssertionError; canonical
  модуль 24/24. SQLite UDF задаёт score; PostgreSQL ranking этим не подтверждён.
- Targeted security patch: `source-map-js` 1.2.1 → 1.2.2 для GHSA-68fv-2mgg-jv7q.
  Peer review и root diff/hash checks пройдены; меняется только одна lock entry.
  Exception записан в PR #1306; cooldown 7 дней и allowlist сохранены.
  Frozen npm ci и root audit GREEN; локальный frontend build прошёл.
  Npm install вывел четыре transitive deprecation warnings; cleanup ещё открыт.
  Windows-generated WASM сохранён приватно; три исходных tracked artifacts
  восстановлены с hash checks. Canonical WASM parity остаётся отдельным gate.
- Перед checkpoint: fast preflight 9/9, harness 27/27, оба режима local
  Markdown link checker и Markdownlint пройдены. Это локальная проверка,
  не resulting-main release evidence.

## Hosted CI

- [Matrix 37392002746](https://github.com/egorribun/university_ecosystem/actions/runs/37392002746),
  attempt 1: снимок 2026-10-06 01:09:21 UTC — 119 jobs: 97 success,
  20 skipped, 2 failure, 0 active/queued. Backend Python shard 3 завершён success.
- `Coverage & Quality Policy Gate` упал на `Normalize coverage evidence`;
  `CI Success` — зависимое падение. Frontend statements: 19 231/19 232;
  branches: 13 788/13 791. Единственный gap — SmartImage. Source и исходные
  counters проверены; Windows path projection не является canonical evidence.
  Каталог содержит 57 artifacts, coverage shards и mutation preflight;
  final quality manifest и mutation execution evidence ещё не получены.
  Global coverage и 100% viable mutation gate остаются открытыми.
- [Matrix 37399724694](https://github.com/egorribun/university_ecosystem/actions/runs/37399724694),
  attempt 1 на `80b40d291`: ранний снимок содержит Node audit failure и
  gateway lint checkout failure. Audit воспроизведён локально и исправлен
  текущим patch; checkout причина не установлена, логи ещё недоступны.
  Прогон неполный; следующие source changes требуют нового CI evidence.

## Мутационный долг

- Исторический [Matrix 37376193756](https://github.com/egorribun/university_ecosystem/actions/runs/37376193756),
  attempt 1: source `9f0208621f47b04883b488cc62dcf64eb055e70c`, producer
  `458de86f458283aa9fa16c7aa8b0697025a6070d`, совпадающий tree
  `ac46399765c0ce504cc7fbe570a77089a7254164`. Universe — 54 457.
- Root независимо валидировал группы 1–21: 749 selected, 608 killed,
  141 survived. Агент валидировал 33 группы: 1181 selected, 970 killed,
  211 survived; root replay расширенного набора ещё нужен. Числа частичные.
- Audit49, News12, CAS/export-order и ranked-news114 — локальные регрессии,
  без ручного Killed или предположительного пересчёта surviving population.
- `UserRepository.get` mutant 9 меняет PostgreSQL lock scope. Нужный PG-тест
  уже существует, но `mutmut` исключает integration. Это открытый разрыв
  среды/отбора, требующий канонической PG-проверки, не новый duplicate test.
- Redis type-cast/logging и MFA default/overwrite кандидаты требуют точного
  применения контракта эквивалентности; score не изменён. NATS80 остаётся открыт.

## Live и диагностика

- Новый owned stand запущен на `80b40d291`, readiness и seed прошли.
  Первый canonical smoke: 18 passed, 2 skipped. Старый cold admin page error
  на `9f0208621` не воспроизведён; причина и исправление не заявляются.
- Avatar V9.4-r3: desktop POST HTTP 200, page errors 0; изображение во viewport,
  loading lazy, complete true, naturalWidth/naturalHeight 0. Проверка failed.
  Outside-viewport гипотеза для этого измерения не поддерживается; причина
  декодирования не установлена. Mobile завершился до upload.
- Root выявил и проверил ошибку private r2 producer: module constant внутри
  browser callback. r3 исправлен и sealed: Python 10/10, Vitest 12/12,
  strict types и discovery 2 passed. Это диагностический код, не product fix.
- V9.4-r4 sealed и независимо проверен: Python 11/11, Vitest 14/14, strict
  types, discovery 2 и peer review. Runtime на 4ad: оба проекта остановились
  на file-chooser-received, uploads 0, page errors 0; категория runtime.
  Предполагаемый input lifecycle требует проверки, root cause не установлен.
  Оба ограниченных runtime receipts сохранены; r3/r4 не являются приёмкой аватара.
- V9.4-r5 root checks: Python 12/12, Vitest 16/16, strict types, discovery 2,
  source/private/dependency hashes. Runtime на 80b: оба input connected,
  setFiles completed и native change true; upload HTTP 200, page errors 0.
  Natural dimensions 0 во viewport; default SW и network bypass возвращают
  HTTP 200/image signature. Byte decode/root cause ещё не подтверждены.
- Текущий state:
  `C:/Temp/ue-live-acceptance/run-orchestrator-80b40d291-20261006-43e3864f50a5416d80a8587b94da62ec`.
  Stand остаётся привязанным к `80b40d291` после смены исходного checkout.

## Восстановление и сохранность

- Старый e2ba paired DB/S3 snapshot экспортирован приватно; root проверил
  hashes и ACL. Owned teardown завершён; env/secrets/backups/evidence сохранены.
- Старый 9f stand остановлен: 0 running, 35 exited containers, 14 volumes
  сохранены. Данные и нужное evidence не удалять без проверки принадлежности.
- 4ad stand также остановлен: 0 running, 35 exited containers, 14 volumes
  сохранены; stop receipt и resource counts проверены root.
- Старый DR RunId `6751bb0189fa45c2a6a2c6820e79b922` относится к 9f private plan;
  clock не начат, runtime не создан. Для 4ad нужен новый source-bound RunId.
- Private 4ad source snapshot/quiescence helpers V2 проверены root: hashes и
  12/12 offline tests, включая partial stop, duplicate receipt и timeout.
  Signed StandOwner даёт authority; DR-owner JSON сам по себе не подписан.
  Docker execution, source quiescence и новый RTO clock ещё не запускались.
- App-level restore, RPO/RTO, SpiceDB graph и search parity не подтверждены.
  Out-of-band writers helpers не проверяют; это явно ограниченная область.
- Private artifacts находятся в
  `C:/Temp/ue-orchestrator-1f5a42b2c5ec49c4bc020ea0752bd157` и доменных bundles.
  Release требует канонических переносимых artifacts. Scratch сохранён после
  отклонения удаления автоматической проверкой безопасности.

## Ближайшая работа

- Проверить coverage и dependency fixes в новом CI без ослабления контракта;
  получить новые canonical coverage/mutation evidence на resulting source.
- Завершить avatar diagnosis, интегрировать проверенные тесты, выполнить
  source-bound paired app restore и измерить RPO/RTO.
- Блоки 4/5 открыты: полная live traceability ТЗ, RU/EN, light/dark,
  responsive widths, SSR/PWA, performance и visual approval.
- Открыты 100% viable mutation score, три полных зелёных CI,
  migrations/rollback, BE-02, WS load, Envoy Gateway/kind, review 63 audit IDs,
  шесть certified GHCR digests и выпуск `v1.0.0`.

## Ограничения

Сохранять пользовательские env, volumes, backups и Git history. Не применять
admin bypass, force-push, global prune или изменение branch protection. Внешний
production, реальные SMTP/push, физические устройства, CDC и field CWV вне MVP.
