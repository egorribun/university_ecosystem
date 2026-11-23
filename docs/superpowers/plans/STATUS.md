# Статус выпуска MVP v1.0.0 — краткий текущий срез

Здесь только текущее состояние. Прошлые срезы, журналы hosted-run и доказательства —
в истории файла: `git log -- docs/superpowers/plans/STATUS.md`.

## Текущий срез — 2026-11-23

### `main` и пакет PR

- `main` = `15d7cadf46b4846b2ec56c6a054993357351b226`, обычный merge
  [#1573](https://github.com/egorribun/university_ecosystem/pull/1573). [Main-push CI](https://github.com/egorribun/university_ecosystem/actions/runs/45136172801) и
  [CodeQL](https://github.com/egorribun/university_ecosystem/actions/runs/45136172080) прошли; у [quality evidence 14801686539](https://github.com/egorribun/university_ecosystem/actions/runs/45136172801/artifacts/14801686539)
  сверены SHA-256 архива и манифеста, точный source SHA и 13 компонентов.
- Все черновики облачного агента и старые черновики закрыты по решению владельца 2026-11-23: #1426,
  #1506, #1507, #1557–#1561, #1563, #1565. Обновления Dependabot #1571 (кроме @lhci/cli) и #1572
  перенесены коммитами владельца.

### Полный Core на `main`

Серия на `15d7cadf4` не набрана; следующая начинается на новом `main` после merge текущего PR.

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

1. После merge текущего PR запустить новую пару полных Core на новом `main` с интервалом не менее двух часов.
2. Разобрать long task зума карты на mobile и нестабильную доставку Web Push.
3. Этапы 4 и 5 одним стендом на новом `main`: сначала скриншоты, затем restore.
4. Сохранять scoped DAST-доказательства для AUD-381.
