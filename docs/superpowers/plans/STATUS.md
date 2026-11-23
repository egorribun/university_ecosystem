# Статус выпуска MVP v1.0.0 — краткий текущий срез

Здесь только текущее состояние. Прошлые срезы, журналы hosted-run и доказательства —
в истории файла: `git log -- docs/superpowers/plans/STATUS.md`.

## Текущий срез — 2026-11-23

### `main` и пакет PR

- `main` = `05a462ffd648b9492e49ef001aba0cc5fdca434e`, обычный merge
  [#1567](https://github.com/egorribun/university_ecosystem/pull/1567) после 78 обязательных проверок
  и CodeQL на `116eb7dab290b62ea50efbee1d78a18115a71a80`. Предыдущий merge
  [#1562](https://github.com/egorribun/university_ecosystem/pull/1562) — `4fd3fbac9`.
- В #1567 восстановлены пять проверяемых условий мастер-плана. Все 13 адресных тестов прошли.
  [PR Core smoke](https://github.com/egorribun/university_ecosystem/actions/runs/45083110629/job/137395496781)
  на merge tree `08ee72e30` завершился с 52 passed и 2 skipped.
  [Receipt 14779020658](https://github.com/egorribun/university_ecosystem/actions/runs/45083110629/artifacts/14779020658)
  `753a480ccb304fff8059b7efeb141ff86ea3f52d914609e6cae0ac7a4551ace0`.
- [#1548](https://github.com/egorribun/university_ecosystem/pull/1548) закрыт без merge;
  #1557–#1561 остаются открыты. История перенесённых изменений — в соответствующих PR.

### Полный Core на `main`

Оба запуска были инициированы на тогдашнем `main` `71ea9616ccb7d950b3baee3855f38f5a64c62c62`.
Второй стартовал за десять секунд до merge #1562 и завершился уже после изменения `main`.

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

1. Проверить результаты main-push CI на `05a462ffd`.
2. Интегрировать исправление освобождения изображений Stories и ограниченную диагностику mobile push
   отдельным PR. Использовать новый полный Core для проверки исправления и разбора сбоев доставки.
3. Для AUD-154 получить два последовательных зелёных полных Core на неизменном `main`, с интервалом
   не менее двух часов между запусками и всеми именными случаями; затем оценить доказательства по
   критерию аудита.
4. Сохранять scoped DAST-доказательства для AUD-381 и проверять требования этапов 3–6 по мастер-плану.
