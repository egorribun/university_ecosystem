# Статус выпуска MVP v1.0.0 — краткий текущий срез

Здесь только текущее состояние. Прошлые срезы, журналы hosted-run и доказательства —
в истории файла: `git log -- docs/superpowers/plans/STATUS.md`.

## Текущий срез — 2026-11-22

### `main` и пакет PR

- `main` = `71ea9616ccb7d950b3baee3855f38f5a64c62c62`. Слиты обычным merge после всех
  обязательных проверок:
  [#1541](https://github.com/egorribun/university_ecosystem/pull/1541) → `149814844`,
  [#1544](https://github.com/egorribun/university_ecosystem/pull/1544) → `c506c637c`,
  [#1545](https://github.com/egorribun/university_ecosystem/pull/1545) → `d8a010b4`,
  [#1549](https://github.com/egorribun/university_ecosystem/pull/1549) → `fc92e183`,
  [#1554](https://github.com/egorribun/university_ecosystem/pull/1554) → `4e9246c99`,
  [#1556](https://github.com/egorribun/university_ecosystem/pull/1556) → `71ea9616c`.
  Подробности по каждому — в описании PR и в истории этого файла.
- #1556 при каждом ответе провайдера 404 или 410 записывает закрытый класс возраста подписки
  (`lt_10s` … `ge_600s`, `unknown`) без самого времени, и в строках `push 410` наблюдения worker.
  Полный Core на `71ea9616c` запущен: [run 45064476734](https://github.com/egorribun/university_ecosystem/actions/runs/45064476734).
- Закрыты черновики облачного агента: устаревшие или перенесённые #1523, #1547, #1550, #1553,
  #1555 и мутационные #1542, #1543, #1551, #1552. Для доработки открыты #1426, #1506, #1507.
  Перенесены #1557 (R14), #1558 и #1559 (Stories), #1560 (AUD-381), #1561 (тест PATCH) вместе с
  исправлением API.
- Состав #1554:
  - **RUSTSEC-2026-0592.** `b77621408` упал на Cargo Deny и Rust vulnerability gate из-за
    переполнения стека в `Url::origin()` в `url` 2.5.8. Это транзитивная зависимость `ammonia`
    в `wasm-sanitizer`.
    - Исправление обновляет `url` до 2.5.9 в основном и fuzz-lockfile и пересобирает WASM.
    - Переподвязка один к одному: записи 444, 447 и 450. Инвентарь остаётся 524.
  - **R29.** Матрица трассируемости приведена к коду и ТЗ §6: добавлять участников и
    переименовывать группу может любой участник, удалять других — только владелец, выйти может
    каждый. Взято из черновика облачного агента #1550.
  - **ws-hub.** На `93d677662` покрытие ws-hub упало до 99,9%: не покрыта ветка отмены в ожидании
    разрешения на запись в комнату. Тест считал первый вызов `Done()` признаком ожидания, но
    `authorizeSession` раньше вызывает `Done()` через `context.WithTimeout`. Теперь проверка
    сессии в тесте кешируется, как в соседнем тесте, и отмена всегда попадает в ожидание.
  - **Story memory.** Добавлена диагностика `firstMismatch`. Она записывает первый цикл, в котором
    счётчики DOM разошлись с прогретым снимком.

### Полный Core на `main` `fc92e183`

| Запуск | Итог | Сбои первой попытки | Receipt (SHA-256) |
| --- | --- | --- | --- |
| [44993593499](https://github.com/egorribun/university_ecosystem/actions/runs/44993593499/job/137119776922) | 220 passed, 1 failed, 8 skipped, 3 flaky | desktop notification-topics (обе попытки); flaky: reflow расписания, MapLibre phase 2, группа Messenger | [14744561230](https://github.com/egorribun/university_ecosystem/actions/runs/44993593499/artifacts/14744561230) `46bcd88b…f9611` |
| [45014106658](https://github.com/egorribun/university_ecosystem/actions/runs/45014106658/job/137182595658) | 220 passed, 2 failed, 8 skipped, 2 flaky | Story memory desktop и mobile (обе попытки); flaky: фокус в расписании, mobile notification-topics | [14752895011](https://github.com/egorribun/university_ecosystem/actions/runs/45014106658/artifacts/14752895011) `7773d74e…e991e` |

- В обоих запусках все шесть именных случаев AUD-154 прошли с первой попытки, включая desktop и
  mobile read-receipt. Красный запуск не заменяет требуемые два зелёных подряд.
- **Push.** Во всех трёх сбоях notification-topics worker записал `push 410` ровно для того
  endpoint, который браузер получил при подписке. Это видно по префиксам SHA-256: `eff98e4577`,
  `2d318bab88` и `39be2760a4`.
  - Перед ожиданием и при сбое браузер держал ту же подписку (`subscription=same`). Ротации не было.
  - 410 приходил на первую доставку (`scenario=news`) в свежую подписку. Остальные отправки в том
    же хвосте получили 2xx.
  - Строку подписки удаляет только ответ провайдера 404 или 410 (`app/services/webpush.py`).
    Лимита или вытеснения подписок нет.
  - Почему FCM отозвал подписку, не установлено.
- **Story memory.** Счётчики DOM цикла 0 совпали с прогретым снимком, расхождение — в одном из
  следующих циклов. Его цикл и значения запишет `firstMismatch` после слияния #1554.
- Предыдущие полные Core на `main` (`149814844`, `c506c637c`, `d8a010b4`) тоже были красными.
  Каждый раз из-за одного-восьми flaky, при зелёных именных случаях AUD-154.

### DAST на `main` `4e9246c99`: AUD-381 закрыт (scoped, 511/512)

- [Run 45056164123](https://github.com/egorribun/university_ecosystem/actions/runs/45056164123)
  (`workflow_dispatch`, attempt 1). Проверка доверенного source, ZAP и Nuclei прошли.
- **ZAP.** Gate «medium or high» прошёл: 0 high, 0 medium, 6 low, 18 informational. 40024 не
  повторился. Provenance привязывает отчёт к `source_sha` `4e9246c99`, этому запуску и
  закреплённому образу ZAP; `origin_response_verified=true`. `coverage_complete=false` записывается
  всегда, по дизайну. [Артефакт 14767843952](https://github.com/egorribun/university_ecosystem/actions/runs/45056164123/artifacts/14767843952)
  имеет SHA-256 `3501574ad371dd943148d0431f261a0ba55676f2843e2783b2105ea31be6d8be`.
- **Nuclei** прошёл, отчёт пуст.
  [Артефакт 14768600299](https://github.com/egorribun/university_ecosystem/actions/runs/45056164123/artifacts/14768600299)
  имеет SHA-256 `2a2cdadbe68f11f8092ba731dbf26c6707593323d654ecc6e8e85e72fac5be4f`.
- Прежний DAST на `fc92e183` ([run 45006312918](https://github.com/egorribun/university_ecosystem/actions/runs/45006312918))
  давал 1 high (40024). Локально он не воспроизвёлся, ни на одном правиле, ни на полном скане.

### Справочно

- **Сборка Caddy.** Alpine удалил `zlib-1.3.2-r1.apk` из `v3.23/main`. С `01a434839` APK берётся
  диапазоном байт из официального ISO Alpine 3.23.8, с проверкой размера и прежнего SHA-256 для
  каждой архитектуры. `libapk` и `apk-tools` закреплены на 3.0.9-r0.
- **Нагрузка backend** (измерено 2026-11-21). Одна сессия aioboto3 на экземпляр `S3Storage` и
  event loop, AVIF со speed 8, лимит памяти backend в Compose 768M. Холодная серия из 175
  изображений: 175/175 ответов 200, p95 3,4 с вместо 21,7 с, событий OOM нет.
  `/api/v1/img` имеет отдельный бюджет `RATE_LIMIT_STATIC`.

## Аудит: текущий итог — 511/512

Формальный итог: **511/512 (99.8%) accepted or resolved, 1 open**, **1S / 0P / 0U / 0N**.
Границы решений: [Scoped AUD-381 acceptance — 2026-11-22](../../audits/AUDIT-2026-11-06-full-reassessment.md#scoped-aud-381-acceptance--2026-11-22).

Счёт поддерживается в шести файлах: `docs/audits/INDEX.md`, reassessment, reconciliation,
`AUDIT-2026-10.md`, этот файл и `docs/README.md`. `docs/audits/*` меняются только по hosted-доказательствам
на точном SHA.

The current policy-file inventory is **524 dispositions / 242 baseline identities / 27 Gitleaks fingerprints / 15 Semgrep rows**. This is inventory only, not evidence of a passing scan or required checks.

### Открытые находки

Состав — из [current 1-finding complement](../../audits/AUDIT-2026-10-30-reconciliation.md#current-1-finding-reconciliation--2026-11-22).

| ID | Статус | Что нужно для закрытия |
| --- | --- | --- |
| AUD-154 | S | Два последовательных green полных Owned Live Acceptance run на `main` (эквивалентность принята владельцем), включая read-receipt live spec. Notification-topics падает, когда FCM отвечает 410 на первую доставку в свежую подписку, которую браузер продолжает держать; причина отзыва не установлена. |

## MVP-этапы (ссылка: [MVP_MASTER_PLAN.md](MVP_MASTER_PLAN.md))

| Этап | Статус |
| --- | --- |
| 1. Решение и документы | Выполнен. |
| 2. Q1 и Q4 в CI | Интегрированы. Каждый новый SHA требует свежих required-check results. |
| 3. Core и продукт | Подготовлены сценарии и матрица; итоговая приёмка не проведена. |
| 4. Визуал и performance | Утверждён только визуальный пакет Home12. |
| 5. Security, ledger, данные | Восстановление DB/S3 backup никогда не запускалось. |
| 6. Выпуск | Не начат. |

## Решения владельца (действующие)

- AUD-381 — эфемерный Compose-стенд в CI (2026-11-12). AUD-484 — alerts 2995–3002 dismissed (2026-11-12).
- AUD-169, AUD-188, AUD-189, AUD-438, AUD-251 — kind + Calico как среда доказательств (2026-11-12).
- ZAP: 10106 исключено только для CI-стенда без TLS (2026-11-19). 10202/20012 — информационные для
  форм с `data-csrf="header"`, 10055-6 — принятый риск low, 10055-4 — исправление (2026-11-21). Любое
  другое исключение — только с согласия владельца.
- Демо-изображения хранятся в репозитории (2026-11-21).
- Новые PR облачного агента интегрируются пачкой, без экспериментов с новыми workflow.
- Dependabot npm принимается коммитом владельца; мажорные обновления разрешены (2026-11-22). Манифесты
  привязаны проекцией D1–D4 (ADR-047). maplibre-gl 6.18.0 принят: его чанк весит 289,41 KiB, и
  ADR-049 поднят до 290 KiB для этой версии (2026-11-22). Удерживаются:
  - jsdom 30.1.3: jsdom 31 вычисляет `var()` в `getComputedStyle`, это ломает 54 теста `toHaveStyle`;
  - @lhci/cli 0.15.1: 0.16.1 тянет пакет `sentry` с лицензией FSL-1.1-Apache-2.0, которой нет в
    `allow-licenses` в `.github/dependency-review-config.yml`.
- Мутационные линии вне объёма MVP (2026-11-13).

## Следующие шаги

1. Отправить пакет PR: обновления из #1548 (восемь, Playwright 1.65.1, maplibre-gl 6.18.0),
   перенесённые черновики облачного агента и STATUS. Затем закрыть #1548 и перенесённые черновики.
2. AUD-381 закрыт по DAST на `4e9246c99`. Повторить DAST, только если изменится стенд или код,
   который проверяет ZAP.
3. AUD-154: по run 45064476734 разобрать класс возраста подписки при каждом 410 и `firstMismatch`
   story memory и исправить обе причины. Затем два последовательных зелёных полных Core на `main` с
   read-receipt, не чаще одного запуска в два часа.
4. Перенести 54 теста `toHaveStyle` на jsdom 31 и принять его.
5. После AUD-154 обновить `docs/audits/*` до 512/512 по hosted-доказательствам, затем этапы 3–6 мастер-плана.
