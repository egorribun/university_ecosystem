# MVP — оперативный статус

Срез на 2026-10-03 UTC. Работа возобновлена. [Мастер-план](MVP_MASTER_PLAN.md)
задаёт порядок приёмки, [ТЗ MVP](University_Ecosystem_MVP.md) — продуктовые границы.
Текущий этап исправляет и полирует существующую реализацию; новые предметные
функции не добавляются. Полная приёмка MVP и выпуск `v1.0.0` ещё не подтверждены.

## Проверяемый контекст

- Активная ветка — `egorribun`, основной PR — [#1306](https://github.com/egorribun/university_ecosystem/pull/1306).
  Кодовый checkpoint этого обновления — `2d41e90b2ed526ddd019fac5fb09f727b732a71f`;
  его проверенное локально дерево — `889686da8b6b834c731775fbace1c2a0277511eb`.
- В `main` интегрированы отдельные исправления trusted workflow и изоляции
  benchmark-процессов; проверенный base — `6fa133b57f62c554162876d4e6d8349f8060fce9`.
  Пороги и число performance-измерений сохранены.
- Для предшествующего hosted checkpoint `6bc0680` проверены [matrix CI](https://github.com/egorribun/university_ecosystem/actions/runs/37138408049),
  [owned live acceptance](https://github.com/egorribun/university_ecosystem/actions/runs/37138407594)
  и [performance](https://github.com/egorribun/university_ecosystem/actions/runs/37138407678).
  Четыре backend shard, frontend unit/browser checks, coverage policy, owned live
  и performance прошли. Полный mutation verdict ещё отсутствует; новый exact-head
  CI после текущего batch остаётся отдельным допуском. [Security Policy Integrity](https://github.com/egorribun/university_ecosystem/actions/runs/37138406322)
  для этого SHA прошёл. Старые результаты не выдаются за текущие.
- Исходники, локальные инструменты и evidence разделены. Секреты, пользовательские
  данные, volumes, backups, история Git и Alembic сохраняются. Source freeze и
  hashes фиксируются перед aggregate-проверками; тяжёлые локальные mutation jobs
  запускаются последовательно.

## Подтверждённый прогресс

- На frontend snapshot `2d41e90` полный локальный
  `npm run test:unit-ci` прошёл: **698 файлов, 8 382 теста**, **100%** statements
  (19 119/19 119), branches (13 672/13 672), functions (4 556/4 556) и lines
  (17 106/17 106). Это Linux/Node 24.19.0 evidence, а не вердикт нового hosted CI.
  Последующее изменение STATUS проверено отдельно как документация;
  runtime source/test bytes после полного прогона не менялись.
- Проверенные исправления сохраняют регистрацию/QR при восстановлении и
  согласовании кэша, блокируют действия над ещё не сохранёнными комментариями,
  предотвращают двойную offline-навигацию из push, исправляют существующие
  локализованные admin labels. Дополнены реальные pending/retry/cancellation
  сценарии профиля, stories, Spotify и уведомлений. Действующие quality-пороги,
  исключения и timeout не ослаблены.
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
- Последний [owned live run на `6bc0680`](https://github.com/egorribun/university_ecosystem/actions/runs/37138407594)
  прошёл 18 сценариев с двумя предусмотренными role skips. Это ограниченный PR
  smoke на прежнем SHA; он не закрывает полный live E2E, повторный запуск/restore
  или resulting-main acceptance.
- Частичный canonical frontend inventory на `46b08e9` проверен по provenance:
  41/64 отчёта, 18 702/42 919 назначенных мутантов. В этом срезе остаются 1 069
  Survived, 2 NoCoverage, 16 Timeout и 15 RuntimeError; 908 Ignored имеют действующее
  основание. Срез неполный и не является score нового checkpoint. Producer success
  не означает прохождение 100% viable gate.

## Ближайшие проверяемые результаты

1. Довести exact-head CI нового опубликованного batch до конечного вердикта, особенно
   Python mutation stats и последующее execution. Исправлять конкретные причины,
   не переносить чужие или старые verdicts между SHA.
2. Продолжить scoped mutation closure существующих auth/profile, уведомлений и
   расписания. Сначала supported user-visible состояния и воспроизводимые баги;
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
