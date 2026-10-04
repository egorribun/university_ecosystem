# MVP — оперативный статус

Срез на 2026-10-04 UTC. Работа возобновлена. [Мастер-план](MVP_MASTER_PLAN.md)
задаёт порядок приёмки, [ТЗ MVP](University_Ecosystem_MVP.md) — продуктовые границы.
Текущий этап исправляет и полирует существующую реализацию; новые предметные
функции не добавляются. Полная приёмка MVP и выпуск `v1.0.0` ещё не подтверждены.

## Проверяемый контекст

- Активная ветка — `egorribun`, основной PR — [#1306](https://github.com/egorribun/university_ecosystem/pull/1306).
  Кодовый checkpoint этого обновления — `9bebdf7f080aab26deafd7d281b993989897576c`;
  его дерево — `24c969e8f32bcf7ca7c86d74b5daefbb074d629a`. Происхождение локальных проверок и последующие
  изменения packaging разделены ниже.
- В `main` интегрированы отдельные исправления trusted workflow и изоляции
  benchmark-процессов; проверенный base — `6fa133b57f62c554162876d4e6d8349f8060fce9`.
  Пороги и число performance-измерений сохранены.
- Предыдущий опубликованный checkpoint `81db76d` имеет [matrix CI](https://github.com/egorribun/university_ecosystem/actions/runs/37141792594),
  [owned live acceptance](https://github.com/egorribun/university_ecosystem/actions/runs/37141792405)
  и [performance](https://github.com/egorribun/university_ecosystem/actions/runs/37141792464).
  Owned live прошёл 18 сценариев с двумя предусмотренными role skips;
  Go/WS-Hub/Rust benchmark gates прошли. [Security Policy Integrity](https://github.com/egorribun/university_ecosystem/actions/runs/37141790995)
  также прошёл. Полный mutation gate не зелёный; старые результаты не выдаются за
  итог нового exact-head CI.
- Исходники, локальные инструменты и evidence разделены. Секреты, пользовательские
  данные, volumes, backups, история Git и Alembic сохраняются. Source freeze и
  hashes фиксируются перед aggregate-проверками; тяжёлые локальные mutation jobs
  запускаются последовательно.

## Подтверждённый прогресс

- Полный локальный frontend unit/coverage-прогон на **Node 24.15.0** прошёл:
  **706 файлов, 8 489 тестов**, **100%** statements (19 135/19 135), branches
  (13 674/13 674), functions (4 562/4 562) и lines (17 116/17 116).
  Состав и hashes всех 4 623 authored inputs не изменились во время прогона.
  После него исправлен packaging диагностического адаптера: публичный digest
  перенесён в явный `.sha256` record, два уже существовавших пакета объявлены
  прямыми dev dependencies. Runtime source/tests и resolved package records
  сохранились; tooling, input inventory и secret checks проверены отдельно.
  Это локальное evidence, не полный hosted verdict окончательного commit.
- Исправлены cooldown запросов signing key и владение их отложенными результатами,
  отмена устаревшего поиска и принадлежность install prompt текущему аккаунту.
  Регрессии проверяют реальные pending, retry, generation-change и cache-сценарии,
  а также навигацию, расписание и RU/EN Activity labels. Убраны только проверенные
  дубли guards/defaults; действующие quality-пороги и исключения сохранены.
- Восстановлены необходимые inputs Python mutation workspace и изоляция
  logging-тестов. Локальная генерация на дереве `f5fde98c` сохранила **54 410** идентичностей мутантов;
  ограниченный настоящий stats-прогон прошёл **200 активных тестов** и отобразил
  **134 функции**. Два ранее проблемных outbox-сценария завершились за 15,59 и
  32,58 секунды при прежнем лимите 120 секунд. Это scoped evidence прежнего snapshot, не полный
  backend mutation pass нового checkpoint.
- CI на `367e97a` обнаружил orphan-классификацию новой subprocess-регрессии.
  Checkpoint `6bc0680` делает её реальные logging imports видимыми статическому
  inventory: выполняемый probe вынесен из строки в обычную приватную функцию.
  Его тело совпадает по AST, проверки/набор случаев/изоляция сохранены. Focused
  subprocess test, inventory, Ruff и secret checks проходят; allowlist не менялся.
  Hosted Source/Test Inventory job `111247692803` на `6bc0680` также прошёл.
- Обнаружена ошибка доказательности прежнего Stryker preload: замена глобального
  `String` меняла преобразования объектов и подавляла native TypeError, в том
  числе в реальном Vitest/jsdom. Затронутые исторические mutation outcomes имеют
  статус **provisional, diagnostic-only** и не дают release/mutation credit.
  Новый адаптер меняет только diagnostic fallback точно закреплённого Stryker
  module; версия, полный source digest, checksum path и форма record проверяются
  fail-closed. Native application semantics сохранены.
- Настоящий локальный producer smoke нового адаптера на отдельном snapshot
  прошёл 112 baseline tests и сохранил все 153 мутанта: 83 Killed, 64 Survived,
  4 Ignored и 2 RuntimeError с исходными application diagnostics. Exit 1 и
  отсутствие release marker ожидаемы; это проверка транспорта, не mutation closure.
  На окончательном packaging проходят 203 adapter/evidence contracts,
  Knip, staged detect-secrets и Gitleaks. Secret baseline/allowlist не расширялись.
- Python mutation workspace получает существующий `config/nats.conf.template`;
  восемь локальных copy/PowerShell contracts прошли. Hosted mutmut execution
  нового SHA ещё должен подтвердить исправление. Локальные Docker Semgrep и
  полный multiprocessing secret scan ограничены средой; их exact-head hosted
  проверки остаются обязательными, не помечаются локально пройденными.

## Ближайшие проверяемые результаты

1. Довести exact-head CI нового опубликованного batch до конечного вердикта, особенно
   Python mutation stats и последующее execution. Исправлять конкретные причины,
   не переносить чужие или старые verdicts между SHA.
2. Получить свежий полный mutation inventory с исправленным адаптером и продолжить
   scoped closure существующих auth/profile, уведомлений и расписания. Сначала supported user-visible состояния и воспроизводимые баги;
   для dead code — доказательство отсутствия потребителей. Неподтверждённые
   defensive/equivalent случаи остаются открытыми, без waivers и ручных статусов.
3. Связать каждый применимый пункт ТЗ и все 63 audit IDs с актуальным evidence
   или точным открытым ограничением. Product, visual и infrastructure acceptance
   не считать выполненными по unit coverage или mocked E2E.
4. Продолжить приёмку RU/EN на 360/390/768/1024/1440 px и предоставить небольшие
   визуальные комплекты для пользовательского review. Измерить предусмотренные
   master plan performance и memory критерии на указанной конфигурации.
5. Получить независимые deployed evidence для непустых PostgreSQL/Alembic
   upgrade/rollback, S3 paired backup/restore и DB URL reads, RPO/RTO, WS load,
   Gateway API/kind TLS/WS/gRPC и failure recovery. В текущей облачной среде
   отсутствует локальный Docker/live-стек. Браузерные инструменты доступны;
   hosted PR smoke закрывает только свой явно перечисленный набор.

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
не входят в MVP. Исторические checkpoint-результаты сохраняются в Git/evidence;
машинные пути прежних сессий не являются предпосылкой продолжения.
