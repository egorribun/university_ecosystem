# Статус выпуска MVP v1.0.0 — краткий текущий срез

Здесь только текущее состояние. Прошлые срезы, журналы hosted-run и доказательства —
в истории файла: `git log -- docs/superpowers/plans/STATUS.md`. Покрытие строк ТЗ — в
[матрице трассируемости](../../testing/mvp-traceability-matrix.md).

## Текущий срез — 2026-11-28

### `main`

- `main` = `d5001041acff1aa77e34d84ef178b921d8ad4c7f` после обычного merge
  [#1697](https://github.com/egorribun/university_ecosystem/pull/1697) (ожидания FCM) 2026-11-27 в 23:37 UTC.
  Все 78 required checks и CodeQL прошли на head `c28e9bfdd`.
- После `7e54feee` влиты:
  - [#1578](https://github.com/egorribun/university_ecosystem/pull/1578): Caddy с `libcrypto3`/`libssl3`
    `3.5.9-r1` (исключение из cooldown, [DEPENDENCY_COOLDOWN_EMERGENCY.md](../../DEPENDENCY_COOLDOWN_EMERGENCY.md),
    истекает 2026-11-30); ws-hub с исправлением GO-2026-6278 и подтверждением допуска в комнату (R23);
    пакетное чтение сводки статистики и fence кэша (кроме NATS KV); одна JOIN-выборка сессии и
    пользователя; email не попадает в события typing.
  - [#1592](https://github.com/egorribun/university_ecosystem/pull/1592): CSRF привязан к `jti` сессии,
    офлайн-очередь сбрасывается при выходе; поиск и фильтры News 44×44; синхронизация карты с URL
    начинается с первого жеста пользователя; StoryViewer на тёмной сцене; патчи Dependabot.
  - [#1596](https://github.com/egorribun/university_ecosystem/pull/1596): maplibre-gl 6.19.0 (ADR-049,
    292 KiB); live-тест порядка сообщений ждёт подтверждения допуска в комнату перед отправкой.
  - [#1598](https://github.com/egorribun/university_ecosystem/pull/1598),
    [#1600](https://github.com/egorribun/university_ecosystem/pull/1600) и
    [#1606](https://github.com/egorribun/university_ecosystem/pull/1606): проба Web Push ждёт 15 секунд
    после подписки и переподписывается до двух раз; закрытая HTTP-диагностика `topics-status`.
  - #1615: удаления в cleanup сценария тем тоже сообщают свой статус через `topics-status`.
- Черновик [#1611](https://github.com/egorribun/university_ecosystem/pull/1611) в `egorribun` собирает то, что
  вливается после закрытия AUD-154: исправление service worker (#1604), проверенные черновики облачного
  агента #1601–#1610, R59 и R02 (Core вырастает с 232 до 244 кейсов).

### Полный Core на `main`

Зачтённой пары нет. Нужны два последовательных green на неизменном `main` с интервалом фактических
стартов Core-job не менее 7200 секунд, только с 8 утверждёнными skip и всеми шестью кейсами AUD-154 с
retry 0. Во время серии ничего не сливать в `main`.

- Core №1 на `d5001041a` ([46083562865](https://github.com/egorribun/university_ecosystem/actions/runs/46083562865))
  не зачтён: mobile `notification-topics-delivery` получил 403 на DELETE своего мероприятия (не записан
  best-effort `event#creator`; запись теперь повторяется при временных сбоях SpiceDB); flaky — map zoom
  (51 мс) и `messenger-membership-revocation`. На `0cc886f44` map zoom (50–76 мс) был шумом раннера.
- Серии на `7e54feee`, `a2d295bc7`, `15d7cadf4`, `dd7296b8d`, `91c414a75`, `29ae8dd63`, `e45e5520f`,
  `99867d9b1` и `1d5294bf` срывались на flaky. Все шесть кейсов AUD-154 каждый раз проходили с retry 0.
  - Web Push 410 у свежей подписки: снято выдержкой 15 секунд и переподпиской.
  - Гонка допуска в комнату при переподключении: исправлена в #1596.
  - footer; задержка доставки FCM → Chrome (ожидания подняты до 120 и 60 секунд).
  - `notification-topics-delivery`: 403 на cleanup мероприятия учителя (desktop на `1d5294bf`, mobile на
    `d5001041a`) — пропущенная best-effort запись SpiceDB `event#creator`.

### DAST на тогдашнем `main` `4e9246c99`: AUD-381 закрыт (scoped)

- [Run 45056164123](https://github.com/egorribun/university_ecosystem/actions/runs/45056164123):
  ZAP 0 high, 0 medium, 6 low, 18 informational, provenance привязан к `source_sha`.
  [Артефакт 14767843952](https://github.com/egorribun/university_ecosystem/actions/runs/45056164123/artifacts/14767843952)
  `3501574ad371dd943148d0431f261a0ba55676f2843e2783b2105ea31be6d8be`. Nuclei прошёл с пустым отчётом.

## Аудит: текущий итог — 511/512

Формальный итог: **511/512 (99.8%) accepted or resolved, 1 open**, **1S / 0P / 0U / 0N**.
Границы решений: [Scoped AUD-381 acceptance — 2026-11-22](../../audits/AUDIT-2026-11-06-full-reassessment.md#scoped-aud-381-acceptance--2026-11-22).

Счёт поддерживается в шести файлах: `docs/audits/INDEX.md`, reassessment, reconciliation,
`AUDIT-2026-10.md`, этот файл и `docs/README.md`. `docs/audits/*` меняются только по hosted-доказательствам
на точном SHA.

The current policy-file inventory is **524 dispositions / 242 baseline identities / 27 Gitleaks fingerprints / 15 Semgrep rows**. This is inventory only, not evidence of a passing scan or required checks.

| ID | Статус | Что нужно для закрытия |
| --- | --- | --- |
| AUD-154 | S | Два последовательных green полных Owned Live Acceptance run на неизменном source `main` (эквивалентность принята владельцем), включая read-receipt live spec. Для текущего `main` нужны новые доказательства. |

Состав — из [current 1-finding complement](../../audits/AUDIT-2026-10-30-reconciliation.md#current-1-finding-reconciliation--2026-11-22).

## MVP-этапы (ссылка: [MVP_MASTER_PLAN.md](MVP_MASTER_PLAN.md))

| Этап | Статус |
| --- | --- |
| 1. Решение и документы | Выполнен. |
| 2. Q1 и Q4 в CI | Интегрированы. Каждый новый SHA требует свежих required-check results. |
| 3. Core и продукт | Сценарии и матрица готовы. Пара полных Core для AUD-154 идёт (выше). Локальные проверки R23, R29, R40, R59, R67 и R83 прошли (см. ниже); приёмка на подписанном стенде не проведена. |
| 4. Визуал и performance | Пакет 96 PNG на `7e54feee` устарел: найденный в нём `color-contrast` исправлен в #1578. Нужен новый пакет на текущем `main`; утверждён только Home12. |
| 5. Security, ledger, данные | Scoped restore DB/S3 подтверждён (ниже). Браузерная проверка avatar на кандидате ожидается. |
| 6. Выпуск | Предварительные проверки собраны на `7e54feee`. Freeze и публикация v1.0.0 ожидаются. |

Бюджеты сборки на `1d5294bf` (#1615 меняет только live-тест): main JS 199,16 KiB raw, начальный JS
417,25 KiB gzip, MapLibre 6.19.0 291,95 KiB gzip при отдельном потолке 292 KiB
([bundle report 15065466421](https://github.com/egorribun/university_ecosystem/actions/runs/45702452209/artifacts/15065466421)).

### Локальные проверки этапа 3 (2026-11-24)

Это изолированные локальные прогоны, а не приёмка на подписанном стенде. Детали — в матрице,
SHA-256 receipts — в версии этого файла на `7d7125330`.

| Строка | Подтверждено локально | Открыто |
| --- | --- | --- |
| R23 | Go-хаб с ACK допуска: 671 тест с race, Chromium r1255 на обоих хабах; полный путь Caddy/auth/NATS проходит в hosted Core | — |
| R29 | Матрица прав групп на ASGI и на реальном HTTP + PostgreSQL с RLS (`alembic upgrade head`) | Подписанный браузерный стенд |
| R40 | `/stats/summary` в пределах 5 SQL на PostgreSQL + Valkey, свежие данные после инвалидации | Заполненный браузерный сценарий на PostgreSQL/Caddy |
| R59 | Drawer и быстрые нажатия 390×844, максимум кадра около 16,8 мс | Штатный сценарий на полном стенде |
| R67 | Production SSR 500 и восстановление в изолированном Chromium | Hosted production-wrapper preflight |
| R83 | Messenger smoke в Firefox r1572 и WebKit r2388 (mocked) | Hosted nightly, физический Safari |
| Avatar/S3 | S3 put/head/get/delete, ASGI avatar PNG → WebP в S3 | Браузер и Caddy |

### Scoped restore DB/S3 (§7.3)

На disposable owned stand на `7e54feee` проверены Alembic `202611200001`, 155 таблиц и 385 строк, 35 объектов
и 35 версий S3. Source DB и bucket совпали с baseline, две пробы DB→S3Storage совпали побайтно.
SHA-256 manifest `0b296bb76e904327b518136e3dd1afd0f3f4b783b338f9fcc99253ba31ec5cd6`,
dump `59ff0a8e259be2b5b34edd4bdf132655ebdcf3cf75c72b039561c7d48d77fddc`.
Это quiesced локальная проверка без гарантии отсутствия внешнего writer и без RPO/RTO. Teardown
подтверждён: 24 контейнера, 5 сетей и 7 томов удалены, другие проекты не затронуты.

## Решения владельца (действующие)

- AUD-381 — эфемерный Compose-стенд в CI (2026-11-12). AUD-484 — alerts 2995–3002 dismissed (2026-11-12).
- AUD-169, AUD-188, AUD-189, AUD-438, AUD-251 — kind + Calico как среда доказательств (2026-11-12).
- ZAP: 10106 исключено только для CI-стенда без TLS (2026-11-19). 10202/20012 — информационные для
  форм с `data-csrf="header"`, 10055-6 — принятый риск low, 10055-4 — исправление (2026-11-21). Любое
  другое исключение — только с согласия владельца.
- Демо-изображения хранятся в репозитории (2026-11-21).
- Dependabot принимается коммитом владельца; мажорные обновления разрешены (2026-11-22). Манифесты
  привязаны проекцией D1–D4 (ADR-047). maplibre-gl 6.19.0 принят (ADR-049 — 292 KiB, 2026-11-25).
  jsdom 31 принят. `@lhci/cli` держится на 0.15.1: 0.16 тянет `sentry` под FSL-1.1-Apache-2.0;
  Dependabot его игнорирует (2026-11-24).
- Мутационные линии вне объёма MVP (2026-11-13).
- Для frozen RC использовать smoke на X и release с Y после проверки ancestry и единственной
  разницы `quality/frozen-rc.json`.
- Для R83 обязательны mocked-сценарии Messenger в desktop Firefox и WebKit. Физический Safari проверяется
  отдельно. PR Owned Live остаётся advisory, Chromatic выключен.
- Независимое review auth, сессий и данных — на финальном кандидате до freeze. Риск шифртекста
  reset-ссылок в JetStream допускается для синтетического демо; условия — в release notes.
- Email участников чата скрыт; блокировка входа по email принята для MVP (ADR-056); CSRF привязывается
  к сессии (2026-11-23).
- OpenSSL 3.5.9-r1 в Caddy принят досрочно; fence статистики не поддерживает NATS KV (2026-11-24).
- Live Web Push: выдержка 15 с и до двух переподписок (2026-11-25); ожидания: нативное 120 с, проба 60 с (2026-11-26).
- Ожидание WebSocket-сообщения в `messenger-membership-revocation` — 60 с (2026-11-28).
  Service worker не обрывает чтения страницы при восстановлении той же сессии; исправление (#1604)
  вливается после зачёта пары (2026-11-25).

## Следующие шаги

1. Пара Core на `main` с поднятыми ожиданиями FCM и закрытие AUD-154 (512/512) одним коммитом шести
   файлов счёта по hosted-доказательствам.
2. Влить #1611: исправление service worker, черновики облачного агента, R59 и R02; затем проверить, ушёл ли
   flaky footer.
3. Стенд этапа 4 на новом `main`: пакет 96 PNG, restore и avatar в браузере; пакет утверждает владелец.
4. Приёмка строк этапа 3 на подписанном стенде.
5. Freeze кандидата, независимое review auth, сессий и данных, публикация v1.0.0.
