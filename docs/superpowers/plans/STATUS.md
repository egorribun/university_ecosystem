# Статус выпуска MVP v1.0.0 — краткий текущий срез

Здесь только текущее состояние. Прошлые срезы, журналы hosted-run и доказательства —
в истории файла: `git log -- docs/superpowers/plans/STATUS.md`.

## Текущий срез — 2026-11-23

### `main` и пакет PR

- `main` = `7e54feee0397bbe3359dd4d5631f57cbc5604eb2` после обычного merge [#1577](https://github.com/egorribun/university_ecosystem/pull/1577) 2026-11-23 в 19:22:45 UTC.
  На PR head `df56a3bb17d6cee3dced215f62b17b0c533aa94f` проверены 78 обязательных пар контекст/app и блокирующий CodeQL.
  [PR receipt 14852279190](https://github.com/egorribun/university_ecosystem/actions/runs/45242979321/artifacts/14852279190) относится к synthetic merge `0db0bb681a64246be9aa76dfb9afb05379c7a332`, SHA-256 `9350e127d050e623ce74938d23b46d1198f6d533bf861f820eec96ffa4ad2c39`.
- [Main-push CI](https://github.com/egorribun/university_ecosystem/actions/runs/45248333383) и [CodeQL](https://github.com/egorribun/university_ecosystem/actions/runs/45248331850) прошли на `7e54feee`.
- На `7e54feee` штатные collector и validator подтвердили все 12 main-push проверок политики выпуска.
  Bundle `check-runs.json`, SHA-256 `29208c5d5a05ce950a23dcf16d088995bf54929091e602ce0227037156743e32`.
- [Quality evidence 14856563853](https://github.com/egorribun/university_ecosystem/actions/runs/45248333383/artifacts/14856563853) — SHA-256 архива `dd85291cb583dad0ec912f859b9e3622801f5c27ca84afb15f1216130ec726b8`,
  манифеста `0a10dd0ce0e59541e831ac9a31257c7e2b2ad97659b39237919d13ea3bf0300f`. Проверены 13 компонентов, Tier 0 ready. Повторно сверены все 16 файлов отчётов.
- Исторический `main` `a2d295bc7b710a3db58956841146d43a6b086cbe` получен merge [#1576](https://github.com/egorribun/university_ecosystem/pull/1576).
  [CI](https://github.com/egorribun/university_ecosystem/actions/runs/45216326353), [CodeQL](https://github.com/egorribun/university_ecosystem/actions/runs/45216325892) и [quality evidence 14841408152](https://github.com/egorribun/university_ecosystem/actions/runs/45216326353/artifacts/14841408152) относятся к этому SHA. SHA-256 архива и манифеста, схема и 13 компонентов сверены.
- Исторический `main` `15d7cadf46b4846b2ec56c6a054993357351b226` получен merge
  [#1573](https://github.com/egorribun/university_ecosystem/pull/1573). [Main-push CI](https://github.com/egorribun/university_ecosystem/actions/runs/45136172801) и
  [CodeQL](https://github.com/egorribun/university_ecosystem/actions/runs/45136172080) прошли. У [quality evidence 14801686539](https://github.com/egorribun/university_ecosystem/actions/runs/45136172801/artifacts/14801686539)
  сверены SHA-256 архива и манифеста, точный source SHA и 13 компонентов. Эти доказательства относятся к тому SHA.
- Все черновики облачного агента и старые черновики закрыты по решению владельца 2026-11-23: #1426,
  #1506, #1507, #1557–#1561, #1563, #1565. Обновления Dependabot #1571 (кроме @lhci/cli) и #1572
  перенесены коммитами владельца.

- [#1578](https://github.com/egorribun/university_ecosystem/pull/1578) заблокирован на опубликованном head
  `23fcae763696cb76cba909ef04bfe95876f6379a`. Повтор [CI, attempt 2](https://github.com/egorribun/university_ecosystem/actions/runs/45266612785/attempts/2)
  завершился ошибкой выбора `libcrypto3=3.5.9-r0` и `libssl3=3.5.9-r0` в двух сборках Caddy.
  Затронуты [Trivy](https://github.com/egorribun/university_ecosystem/actions/runs/45266612785/job/138066650807),
  [log proof](https://github.com/egorribun/university_ecosystem/actions/runs/45266612785/job/138066649472)
  и итоговый [CI Success](https://github.com/egorribun/university_ecosystem/actions/runs/45266612785/job/138067629129).

### Полный Core на `main`

На `7e54feee0397bbe3359dd4d5631f57cbc5604eb2` [run 45248403311, job 137951197987](https://github.com/egorribun/university_ecosystem/actions/runs/45248403311/job/137951197987)
начался 2026-11-23 в 19:24:45 UTC и завершился неуспешно. Итог **222 passed, 1 failed, 8 skipped, 1 flaky**.
Все шесть результатов AUD-154 получены с retry 0, `stand_stop` прошёл. Учёт skipped ещё не подтверждён.
[Receipt 14858397170](https://github.com/egorribun/university_ecosystem/actions/runs/45248403311/artifacts/14858397170) имеет SHA-256 `b8457ddf032c51598df063fd54245f1ae4dad05aa9b063217850ddf5bcb1154b`.
Диагностические локации — mobile `notification-topics-delivery.live.spec.ts`, объявление 1111 и кадры 557, 584, 1265. Desktop `messenger-group-isolation.live.spec.ts` — объявление 254 и кадр 387.
Обе mobile-попытки дошли до ожидания нативного уведомления после записи in-app. Обе подписки совпали по короткому отпечатку с ответами HTTP 410 в ограниченной выборке worker. Для привязки 410 к конкретному событию требуется дополнительное доказательство.
Для desktop R23 редактированный лог фиксирует неуспешное ожидание входящего сообщения. Получатель и этап доставки по этому логу не установлены.
Зачтённой пары нет. Нужны два последовательных green на неизменном стабильном SHA `main`.

Исторический [run 45216520095, job 137839027140](https://github.com/egorribun/university_ecosystem/actions/runs/45216520095/job/137839027140) на `a2d295bc7` не прошёл из-за ошибки консоли во flaky desktop footer. Итог **223 passed, 0 failed, 8 skipped, 1 flaky**.
Все шесть результатов AUD-154 получены с первой попытки. [Receipt 14842876037](https://github.com/egorribun/university_ecosystem/actions/runs/45216520095/artifacts/14842876037), SHA-256 `290234f080d1ac92671b8fc551c11209c193b91fe191ed22cd594d54daa3c964`.

Серия на `15d7cadf4` сброшена, её история приведена ниже.

| Запуск | Итог | Receipt и SHA-256 |
| --- | --- | --- |
| [45139263654, job 137572924120](https://github.com/egorribun/university_ecosystem/actions/runs/45139263654/job/137572924120), `workflow_dispatch` | **224 passed, 0 failed, 8 skipped, 0 flaky** | [14803902142](https://github.com/egorribun/university_ecosystem/actions/runs/45139263654/artifacts/14803902142) `2dbc08cb2a65c1e46f34b9c7e87d92c40a43423d2ca3b991960c6df2c3013dce` |
| [45166882952](https://github.com/egorribun/university_ecosystem/actions/runs/45166882952), `workflow_dispatch` | отменён, результата Core нет | — |
| [45169213982, job 137709440731](https://github.com/egorribun/university_ecosystem/actions/runs/45169213982/job/137709440731), `schedule` | **222 passed, 1 failed, 8 skipped, 1 flaky** | [14824608244](https://github.com/egorribun/university_ecosystem/actions/runs/45169213982/artifacts/14824608244) `90d42470c6b089514deb5c9dffbda817a042c7b1c424b6510d78bb0d097c506c` (digest GitHub) |

- Run 45166882952: attempt 1 завис на установке Chromium (шаг 9 шёл 82 минуты вместо обычных
  ~36 секунд) и отменён до старта стенда. Attempt 2 отменён до старта, чтобы не дублировать плановый
  прогон и не нарушить двухчасовой интервал.
- В плановом прогоне все шесть случаев AUD-154 прошли с первой попытки. Упал mobile
  `map-zoom-longtask`: long task 52–55 мс при пороге 50 мс в обеих попытках (фаза обновления камеры
  после клика). Mobile notification topics прошёл со второй попытки: push `news` не пришёл в первой.
- Нестабильность карты на mobile и доставки Web Push уже встречалась в прогонах 2026-11-23 на `ea78b1fcf`
  и `facb80d35`.

### DAST на тогдашнем `main` `4e9246c99`: AUD-381 закрыт (scoped, 511/512)

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
| AUD-154 | S | Два последовательных green полных Owned Live Acceptance run на неизменном source `main` (эквивалентность принята владельцем), включая read-receipt live spec. После красного второго запуска серия сброшена; для текущего `main` нужны новые доказательства. |

## MVP-этапы (ссылка: [MVP_MASTER_PLAN.md](MVP_MASTER_PLAN.md))

| Этап | Статус |
| --- | --- |
| 1. Решение и документы | Выполнен. |
| 2. Q1 и Q4 в CI | Интегрированы. Каждый новый SHA требует свежих required-check results. |
| 3. Core и продукт | Подготовлены сценарии и матрица; итоговая приёмка не проведена. |
| 4. Визуал и performance | Проверка Stage 4 — 96 PNG с sidecars, 2 serious `color-contrast` на dark390 `/schedule` RU/EN (белый на `#38bdf8`, 2.14:1). На `a2d295bc7` serious-находки были в 28 вариантах. Утверждён только Home12, approval нового пакета не получен. |
| 5. Security, ledger, данные | Scoped restore DB/S3 подтверждён на одном disposable owned stand. Avatar не загружен. |
| 6. Выпуск | Собраны предварительные проверки на `7e54feee`. Freeze и публикация v1.0.0 ожидаются. |

Галерея — aggregate SHA-256 `6dd69c38516e8f4bf7d52d863bf0321fe873d5b85f69f146987d67d2d0671a0b`, safe summary SHA-256 `42df1d91ca9607015a39959ab41f64338c0a6f8b93febadc8646da7b01bd4dee`.

Бюджеты сборки на `7e54feee` подтверждены: main JS 199,10 KiB raw, начальный JS 412,67 KiB gzip,
крупнейший обычный lazy-чанк 217,69 KiB gzip, MapLibre 6.18.0 289,41 KiB gzip.
[Bundle report 14855552498](https://github.com/egorribun/university_ecosystem/actions/runs/45248333383/artifacts/14855552498),
[MapLibre inventory 14854778672](https://github.com/egorribun/university_ecosystem/actions/runs/45248333383/artifacts/14854778672).
Значение `runtimeClosure=unproved` сохранено в артефакте.

### Scoped restore DB/S3 (§7.3)

На одном disposable owned stand на `7e54feee0397bbe3359dd4d5631f57cbc5604eb2` проверены Alembic `202611200001`, 155 таблиц и 385 строк, 35 исходных объектов и 35 версий, multipart 0 и семь DB reference columns. Source DB и bucket совпали с baseline, два manifest receipts совпали.
Две DB→S3Storage пробы story/news совпали побайтно. SHA-256 manifest `0b296bb76e904327b518136e3dd1afd0f3f4b783b338f9fcc99253ba31ec5cd6`, dump `59ff0a8e259be2b5b34edd4bdf132655ebdcf3cf75c72b039561c7d48d77fddc`, source DB `2d2876e29d77f9f614c8b951ae693aa220e487455abdfac05823c0d47bd930f1`, table counts `a79a3014a35901321ad030a0d938658acfe5725800552ea13aa9511d477823f1`.
Это quiesced локальная проверка без гарантии отсутствия внешнего writer и без RPO/RTO.
Teardown подтверждён по signed preinventory и bounded Docker events. Удалены 24 контейнера, 5 сетей и 7 томов, остатков нет. Приватные PNG, sidecars и receipts сохранены, другие проекты не затронуты. Заключительная проверка привязок API для avatar после адресного старта не прошла, загрузка не выполнялась.

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
  ADR-049 поднят до 290 KiB для этой версии (2026-11-22). jsdom 31 принят: проверки inline-стилей
  читают объявление через `expectInlineStyle`, а не вычисленный стиль, который теперь раскрывает
  `var()`. Удерживается @lhci/cli 0.15.1: 0.16.1 тянет пакет `sentry` с лицензией
  FSL-1.1-Apache-2.0, которой нет в `allow-licenses` в `.github/dependency-review-config.yml`.
- Мутационные линии вне объёма MVP (2026-11-13).
- Для frozen RC использовать smoke на X и release с Y после проверки ancestry и единственной
  разницы `quality/frozen-rc.json`. Нужны успешный доверенный full-smoke receipt для X и
  собственные обязательные проверки для Y.
- Для R83 обязательны базовые mocked-сценарии Messenger в desktop Firefox и WebKit. Физический
  Safari проверяется отдельно. PR Owned Live остаётся advisory, Chromatic выключен.
- Независимое review auth, сессий и данных провести на финальном кандидате до freeze. Риск
  шифртекста reset-ссылок в JetStream допускается для синтетического демо после подтверждения
  изоляции Compose и отсутствия реальных данных. Записать условия и ограничения в release notes.

## Следующие шаги

1. Разобрать две serious-находки визуального аудита и итоги последнего Core.
2. На следующем стабильном SHA `main` запустить два последовательных зелёных полных Core с интервалом фактических стартов не менее двух часов. Во время серии ничего не сливать в `main`.
3. Проверить учёт skipped и разобраться с нестабильной доставкой Web Push.
4. Повторить проверку привязок API для avatar и подготовить визуальный пакет к утверждению.
5. Сохранять scoped DAST-доказательства для AUD-381.
