# Статус выпуска MVP v1.0.0 — краткий текущий срез

Здесь только текущее состояние. Прошлые срезы, журналы hosted-run и доказательства —
в истории файла: `git log -- docs/superpowers/plans/STATUS.md`. Покрытие строк ТЗ — в
[матрице трассируемости](../../testing/mvp-traceability-matrix.md).

## Текущий срез — 2026-11-24

### `main` и пакет PR

- `main` = `7e54feee0397bbe3359dd4d5631f57cbc5604eb2` после обычного merge
  [#1577](https://github.com/egorribun/university_ecosystem/pull/1577) 2026-11-23 в 19:22:45 UTC.
  [Main-push CI](https://github.com/egorribun/university_ecosystem/actions/runs/45248333383) и
  [CodeQL](https://github.com/egorribun/university_ecosystem/actions/runs/45248331850) прошли.
  [Quality evidence 14856563853](https://github.com/egorribun/university_ecosystem/actions/runs/45248333383/artifacts/14856563853):
  SHA-256 архива `dd85291cb583dad0ec912f859b9e3622801f5c27ca84afb15f1216130ec726b8`, 13 компонентов, Tier 0 ready.
- 2026-11-23 влиты [#1574](https://github.com/egorribun/university_ecosystem/pull/1574),
  [#1576](https://github.com/egorribun/university_ecosystem/pull/1576) и #1577: перечисления фильтров событий,
  CSRF-ключ admin smoke, патчи Dependabot #1571/#1572, скрытие email участников чата, ускорение карты,
  ADR-056 о блокировке входа по email, исправления доступности.
- [#1578](https://github.com/egorribun/university_ecosystem/pull/1578) открыт: работа перерыва 2026-11-23/24 и
  исправления 2026-11-24. Его required checks на текущем head ещё не получены.
  - Caddy: `libcrypto3`/`libssl3` `3.5.9-r1` (исключение из cooldown,
    [DEPENDENCY_COOLDOWN_EMERGENCY.md](../../DEPENDENCY_COOLDOWN_EMERGENCY.md), истекает 2026-11-30).
  - ws-hub: `gorilla/websocket` на псевдоверсии с исправлением GO-2026-6278; подтверждение допуска
    в комнату (R23); Go-обновления из Dependabot #1579/#1580.
  - Статистика: пакетное чтение холодной сводки и fence заполнения кэша для Redis, Tiered и Memory.
    На NATS KV сводка не кэшируется.
  - Auth и профиль: одна JOIN-выборка сессии и пользователя, `/me` без записи pending email.
  - Чат: email не попадает в события typing и во внутренние проекции отправителя.
  - Доступность: brand-поверхности расписания используют `text-inverse-text` (тёмная тема 2.1:1 → 9.5:1).
  - Карта: раскладка маркеров рендерится как transition, Intl-форматтеры кэшируются.
  - npm: react-i18next 18.0.2 и axe-core 4.14.1 из #1575. Для `@lhci/cli` ≥ 0.16 (FSL) добавлен ignore Dependabot.
  - Live-стенд: повторный старт Core с сохранением подписанных портов; диагностика R23 и footer.

### Полный Core на `main`

Зачтённой пары нет. Нужны два последовательных green на неизменном `main` с интервалом фактических
стартов не менее двух часов. Во время серии ничего не сливать в `main`.

| Запуск на `7e54feee` | Итог |
| --- | --- |
| [45248403311](https://github.com/egorribun/university_ecosystem/actions/runs/45248403311/job/137951197987), 2026-11-23 19:24Z | **222 passed, 1 failed, 8 skipped, 1 flaky**. Упал desktop R23 `messenger-group-isolation`, mobile `notification-topics-delivery` прошёл со второй попытки (push 410). Все шесть AUD-154 с retry 0. [Receipt 14858397170](https://github.com/egorribun/university_ecosystem/actions/runs/45248403311/artifacts/14858397170) `b8457ddf032c51598df063fd54245f1ae4dad05aa9b063217850ddf5bcb1154b` |
| [45402369753](https://github.com/egorribun/university_ecosystem/actions/runs/45402369753), `schedule` 2026-11-24 13:20Z | Стенд не собрался: Alpine убрал `libssl3=3.5.9-r0` из индекса. Результата Core нет |

- На `a2d295bc7` и `15d7cadf4` серии тоже сорвались: flaky footer с ошибкой консоли, mobile map-zoom
  52–55 мс при пороге 50 мс. Порог не меняется; код карты ускорен в #1576 и #1578.
- Открыто: привязка HTTP 410 Web Push к событию и поколению подписки, доставка R23 за 60 секунд
  на полном пути Caddy/auth/NATS.

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
| 3. Core и продукт | Сценарии и матрица готовы. Локальные проверки R23, R29, R40, R59, R67 и R83 прошли (см. ниже); приёмка на подписанном стенде не проведена. |
| 4. Визуал и performance | Пакет 96 PNG на `7e54feee` дал 2 serious `color-contrast` на dark390 `/schedule`; они и тот же дефект на остальных brand-поверхностях исправлены в #1578. Нужен новый пакет после merge; утверждён только Home12. |
| 5. Security, ledger, данные | Scoped restore DB/S3 подтверждён (ниже). Браузерная проверка avatar на кандидате ожидается. |
| 6. Выпуск | Предварительные проверки собраны на `7e54feee`. Freeze и публикация v1.0.0 ожидаются. |

Бюджеты сборки на `7e54feee`: main JS 199,10 KiB raw, начальный JS 412,67 KiB gzip, крупнейший lazy-чанк
217,69 KiB gzip, MapLibre 6.18.0 289,41 KiB gzip
([bundle report 14855552498](https://github.com/egorribun/university_ecosystem/actions/runs/45248333383/artifacts/14855552498)).

### Локальные проверки этапа 3 (2026-11-24)

Это изолированные локальные прогоны, а не приёмка на подписанном стенде. Детали — в матрице,
SHA-256 receipts — в версии этого файла на `7d7125330`.

| Строка | Подтверждено локально | Открыто |
| --- | --- | --- |
| R23 | Go-хаб с ACK допуска: 671 тест с race, Chromium r1255 на обоих хабах | Полный путь Caddy/auth/NATS за 60 секунд на hosted Core |
| R29 | Матрица прав групп на ASGI и на реальном HTTP + PostgreSQL с RLS (`alembic upgrade head`) | Подписанный браузерный стенд |
| R40 | `/stats/summary` в пределах 5 SQL на PostgreSQL + Valkey, свежие данные после инвалидации | Заполненный браузерный сценарий на PostgreSQL/Caddy |
| R59 | Drawer и быстрые нажатия 390×844, максимум кадра около 16,8 мс | Штатный сценарий на полном стенде |
| R67 | Production SSR 500 и восстановление в изолированном Chromium | Hosted production-wrapper preflight |
| R83 | Messenger smoke в Firefox r1572 и WebKit r2388 (mocked) | Hosted nightly, физический Safari |
| Avatar/S3 | S3 put/head/get/delete, ASGI avatar PNG → WebP в S3 | Браузер и Caddy |

- Карта на production-сборке: первый одиночный wheel после загрузки MapLibre 6.18.0 приходит без
  `originalEvent`, поэтому `z` в URL не обновляется. Поведение при перекрытии ввода и бюджет 50 мс открыты.
- News на 720×450: поиск высотой 36 px и английская кнопка `All` шириной 39,23 px меньше цели 44×44.
- CSRF: отказ до обработчика помечен `X-CSRF-Rejected: 1`. Привязка CSRF к сессии — черновик вне `main`.

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

## Следующие шаги

1. Довести [#1578](https://github.com/egorribun/university_ecosystem/pull/1578) до зелёных required checks
   и обычного merge.
2. На новом `main` запустить два последовательных полных Core с интервалом не менее двух часов.
3. Привязка CSRF к сессии (черновик в stash), затем новый визуальный пакет и restore на одном стенде.
4. Разобраться с Web Push 410 и доставкой R23; проверить учёт skipped.
5. Приёмка строк этапа 3 на подписанном стенде после закрытия AUD-154.
