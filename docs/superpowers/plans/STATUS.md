# Статус выпуска MVP v1.0.0 — краткий текущий срез

Здесь только текущее состояние. Прошлые срезы, журналы hosted-run и доказательства —
в истории файла: `git log -- docs/superpowers/plans/STATUS.md`.

## Текущий срез — 2026-11-23

### `main` и пакет PR

- `main` = `15d7cadf46b4846b2ec56c6a054993357351b226`, обычный merge
  [#1573](https://github.com/egorribun/university_ecosystem/pull/1573) после 78 обязательных проверок
  и CodeQL на `93e9ff2f90125b2766a986366158b415da80f403`. Дерево совпадает с проверенным деревом PR.
- [PR Core smoke и NATS](https://github.com/egorribun/university_ecosystem/actions/runs/45132547291/job/137551129083)
  прошли на `74f19fa87`. Итог smoke — 52 passed и 2 skipped.
  [Receipt 14799565742](https://github.com/egorribun/university_ecosystem/actions/runs/45132547291/artifacts/14799565742)
  `2e966c5625dd2f6d75d3ca3aea8171e59c87f4b998e299c7026cb9612cb605f0`.
- [Main-push CI](https://github.com/egorribun/university_ecosystem/actions/runs/45136172801) и
  [CodeQL](https://github.com/egorribun/university_ecosystem/actions/runs/45136172080) прошли на `15d7cadf4`.
  У [quality evidence 14801686539](https://github.com/egorribun/university_ecosystem/actions/runs/45136172801/artifacts/14801686539)
  сверены SHA-256 архива и манифеста, точный source SHA и 13 компонентов без пропавших отчётов.
- [#1548](https://github.com/egorribun/university_ecosystem/pull/1548) закрыт без merge, #1557–#1561 открыты.

### Полный Core на `main`

[Полный Core 45139263654 на `15d7cadf4`](https://github.com/egorribun/university_ecosystem/actions/runs/45139263654/job/137572924120)
прошёл с 224 passed, 0 failed, 0 flaky и 8 сверенными skips. Все шесть AUD-154 прошли с первой попытки.
[Receipt 14803902142](https://github.com/egorribun/university_ecosystem/actions/runs/45139263654/artifacts/14803902142)
`2dbc08cb2a65c1e46f34b9c7e87d92c40a43423d2ca3b991960c6df2c3013dce` проверен. Серия — **1/2**.
[Второй зачётный Core 45166882952](https://github.com/egorribun/university_ecosystem/actions/runs/45166882952)
запущен на том же SHA в 14:37:35 по Стамбулу, через шесть часов после первого; `main` не меняется до его итога.

[Core 45124404884 на `bfc2b1a32`](https://github.com/egorribun/university_ecosystem/actions/runs/45124404884/job/137525350714)
стартовал в 09:29:12 по Стамбулу. Итог — 223 passed, 0 failed, 8 skipped, 1 flaky. Все шесть AUD-154
прошли с первой попытки. Desktop schedule reflow упал при возврате фокуса после Escape. Стенд остановлен.
[Receipt 14796648840](https://github.com/egorribun/university_ecosystem/actions/runs/45124404884/artifacts/14796648840)
`1c9231101e1b8dbf9a5251b2f0fc47478c1633b6603bb59ddae2b763e84e6439` проверен.

[Core 45103643982 на `facb80d35`](https://github.com/egorribun/university_ecosystem/actions/runs/45103643982/job/137459900882)
стартовал в 06:03:06 по Стамбулу. Результат — 221 passed, 0 failed, 8 skipped, 3 flaky; все шесть AUD-154
прошли с первой попытки. Повтор потребовался desktop-сценариям notification topics, direct Web Push и
schedule reflow. Стенд остановлен. [Receipt 14788721066](https://github.com/egorribun/university_ecosystem/actions/runs/45103643982/artifacts/14788721066)
`beae20efc8d46c600be636cdfc8a5f071f973d8b0f419df076e111ee16bc27ee` проверен.

Прежняя серия на `71ea9616c` завершилась после изменения `main` перед вторым результатом.

| Запуск | Итог | Receipt и SHA-256 |
| --- | --- | --- |
| [45064476734, job 137337440218](https://github.com/egorribun/university_ecosystem/actions/runs/45064476734/job/137337440218) | **224 passed, 0 failed, 8 skipped, 0 flaky** | [14772751398](https://github.com/egorribun/university_ecosystem/actions/runs/45064476734/artifacts/14772751398) `1499f38b11f6b1cd1177ccb09cafa05ef12cb4d50fdd2f75fe4829355cf4a816` |
| [45076129899, job 137373641322](https://github.com/egorribun/university_ecosystem/actions/runs/45076129899/job/137373641322) | **221 passed, 1 failed, 8 skipped, 2 flaky** | [14776214511](https://github.com/egorribun/university_ecosystem/actions/runs/45076129899/artifacts/14776214511) `739c2603ca0de9c84018555e8e1460891b6198cf40ee98a1d087d13e7b46637c` |

- Во втором запуске все шесть именных случаев AUD-154, включая desktop и mobile read-receipt,
  прошли с первой попытки. Сбои первой попытки: mobile Story memory, desktop notification-topics
  и mobile push; итог — один failed и два flaky. Серия зелёных полных Core сброшена.
- В локальном Chrome зависшие ответы изображений удерживали закрытую разметку Stories и слушателей.
  После очистки источников изображения при отсоединении рост исчез в пяти циклах с незавершёнными
  ответами. Причину hosted-сбоя нужно подтвердить следующим полным Core.
- В ограниченной выборке журнала worker есть ответ провайдера `410` с `subscription_age=lt_10s`.
  Этот класс отражает возраст серверной DB-записи, а не установленную причину ответа. Отпечаток
  endpoint в журнале не совпадает с endpoint сбоя desktop topics; endpoint mobile в доказательствах
  не записан. Связь наблюдения 410 со сбоями доставки не установлена.

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

1. Подтвердить второй зелёный полный Core на `15d7cadf4`, соблюсти двухчасовой интервал и сверить оба receipt.
2. По подтверждённой паре обновить AUD-154 и начать следующие этапы по мастер-плану.
3. Сохранять scoped DAST-доказательства для AUD-381.
