# Статус выпуска MVP v1.0.0 — краткий текущий срез

Здесь только текущее состояние. Прошлые срезы, журналы hosted-run и доказательства —
в истории файла: `git log -- docs/superpowers/plans/STATUS.md`.

## Текущий срез — 2026-11-22

### Текущий `main`

- Предыдущий `main` — `fc92e1835ac985eb151ed5564f4a7bbc4ede1db1`. Слиты обычным merge после всех 78
  обязательных проверок и CodeQL на source:
  [#1541](https://github.com/egorribun/university_ecosystem/pull/1541) → `149814844`,
  [#1544](https://github.com/egorribun/university_ecosystem/pull/1544) → `c506c637c`,
  [#1545](https://github.com/egorribun/university_ecosystem/pull/1545) → `d8a010b4`,
  [#1549](https://github.com/egorribun/university_ecosystem/pull/1549) → `fc92e183`.
  Подробности по каждому — в описании PR и в истории этого файла.
- [PR #1554](https://github.com/egorribun/university_ecosystem/pull/1554) слит: текущий `main` —
  `4e9246c99b4d2f6cb31a6511ad7208783a509337`.
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

### Последний полный Core: прежний `main` `fc92e183`

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
  следующих циклов. Его цикл и значения запишет диагностика из #1554 в следующем полном прогоне.
- Предыдущие полные Core на `main` (`149814844`, `c506c637c`, `d8a010b4`) тоже были красными.
  Каждый раз из-за одного-восьми flaky, при зелёных именных случаях AUD-154.

### DAST на текущем `main` `4e9246c9`

- [Run 45056164123](https://github.com/egorribun/university_ecosystem/actions/runs/45056164123) прошёл на точном SHA. Источник проверен.
- [ZAP](https://github.com/egorribun/university_ecosystem/actions/runs/45056164123/job/137312840507) не сообщил о средних или высоких находках;
  [отчёт](https://github.com/egorribun/university_ecosystem/actions/runs/45056164123/artifacts/14767843952) верифицирован, полного покрытия скан не подтверждает.
- [Nuclei](https://github.com/egorribun/university_ecosystem/actions/runs/45056164123/job/137312840552) не сообщил о средних, высоких или критических находках;
  [отчёт](https://github.com/egorribun/university_ecosystem/actions/runs/45056164123/artifacts/14768600299) опубликован.

### Предыдущий DAST: `fc92e183`

- [Run 45006312918](https://github.com/egorribun/university_ecosystem/actions/runs/45006312918):
  проверка доверенного source прошла.
- **Nuclei** прошёл, санитизированный отчёт пуст.
  [Артефакт 14748396373](https://github.com/egorribun/university_ecosystem/actions/runs/45006312918/artifacts/14748396373)
  имеет SHA-256 `e88643c475a19cddb70bbe0cf420c43dc9336ddfe916615646cba9a8eda0b402`.
- **ZAP** не прошёл severity gate: 17 informational, 7 low, 0 medium, 1 high (40024, «SQL
  Injection — SQLite»), `coverage_complete=false`.
  [Артефакт 14747819065](https://github.com/egorribun/university_ecosystem/actions/runs/45006312918/artifacts/14747819065)
  имеет SHA-256 `628574e9a608342faaa499203d5b2bf08d5e3fd6e3a8c4dba23a64323c0a053e`.
  Место срабатывания не публикуется по дизайну приватного отчёта.
- Локально 40024 не воспроизвёлся на Core-стенде того же дерева с тем же закреплённым образом.
  Проверены два варианта: только это правило, и полный активный скан с AJAX spider и лимитами
  hosted-запуска. В обоих 0 FAIL.
- Прежний DAST на `7c0af5d42` (до #1541) давал 4 medium (10055, 10202, 20012). Их закрыли решения
  владельца от 2026-11-21 (см. ниже).

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
- Dependabot npm принимается коммитом владельца только для неудерживаемых пакетов. Удерживаются
  maplibre-gl 6.15.0, jsdom 30.1.3, playwright и @playwright/test 1.64.1. Манифесты привязаны
  проекцией D1–D4 (ADR-047, одобрено 2026-11-15).
- Мутационные линии вне объёма MVP (2026-11-13).

## Следующие шаги

1. AUD-154: установить, почему FCM отвечает 410 на свежую подписку. Для этого отдельная
   ограниченная диагностика [#1556](https://github.com/egorribun/university_ecosystem/pull/1556). По
   первому расхождению из следующего полного Core определить причину сбоя Story Viewer. Затем два последовательных
   зелёных полных Core на `main` с read-receipt, не чаще одного запуска в два часа.
2. Dependabot #1548: принять девять неудерживаемых обновлений коммитом владельца. glob закреплён в
   `security/audit-allowlist.yaml`; @lhci/cli 0.16 меняет зависимые закрепления Lighthouse.
3. Обновить `docs/audits/*` до 512/512 по hosted-доказательствам, затем этапы 3–6 мастер-плана.
