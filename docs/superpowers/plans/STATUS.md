# Статус выпуска MVP v1.0.0

Обновлено: 2026-10-18 (Europe/Istanbul). Порядок — [MVP_MASTER_PLAN.md](MVP_MASTER_PLAN.md), продукт — [ТЗ MVP](University_Ecosystem_MVP.md), качество — [ADR-047](../../adr/ADR-047-risk-based-quality-policy.md).

## Текущий приоритет

Полное закрытие [октябрьского аудита](../../audits/AUDIT-2026-10.md): все 512 AUD IDs, включая 507 исторически открытых пунктов и пять исторически закрытых. Для каждого нужны проверенное исправление и regression/runtime evidence либо обоснованный disposition. Исторический статус и наличие commit не заменяют приёмку текущего source. Общий процент закрытия пока не установлен. Приёмка MVP продолжается после этого приоритета.

Работа только через GitHub plugin, ветка `egorribun`, существующий [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306). Root управляет Git и принимает работу максимум трёх GPT-6 Luna Max агентов с непересекающимися файлами. Merge/deploy и обходы проверок не выполнялись.

## Текущая партия и CI

На [d5ef191](https://github.com/egorribun/university_ecosystem/commit/d5ef1918d83f3f69787ff257ef14a6d98d8a8368) все функциональные lanes прошли. Python: 16370 PASS / 174 SKIP по четырём shards (5381/3763/3812/3414 PASS). Frontend: 9289 PASS в 770 файлах, ещё 22 production client-contract tests, static/build/aggregate успешны. PostgreSQL: 178 PASS / 9 SKIP, включая cache CRUD с независимыми readers, comment durability, real JetStream, scheduler/outbox и migration scenarios. Migration gate и rollback integrity успешны.

Предыдущие 24 непокрытые изменённые строки закрыты: [diff-cover](https://github.com/egorribun/university_ecosystem/actions/runs/39148882069/job/117747814212) прошёл с 4458 строками, нулём missing и 100% покрытия. Затем тот же job остановился на нормализации полного branch coverage: «python.branches misses must equal the current legacy-migration residual (1870, got 1872)». Допустимый остаток вычисляется из текущих отчётов ровно 131 разрешённой legacy migration; это не произвольный фиксированный порог. Причина двух дополнительных branch misses установлена по всем четырём shard tables и source: false arcs 235→237 и 326→329 в EventRepository недостижимы, потому что builder всегда добавляет обязательный manual-visibility predicate. Коррекция удаляет только два лишних if, оставляя WHERE безусловным; real-DB regression расширен на upcoming/archive/unfiltered режимы. Новому source нужен отдельный полный hosted прогон, без расширения исключения или снижения требований. Последующие manifest/policy validators не считаются выполненными.

Все 23 workflows terminal: 20 SUCCESS, два штатных SKIPPED, один Matrix FAILURE. В Matrix failures только Coverage & Quality Policy Gate и его зависимый CI Success. Полный paginated набор из 136 check runs сопоставлен с 78 required context/app pairs: 75 SUCCESS, два FAILURE, один Checkov NEUTRAL. CodeQL: пять успешных языковых анализов и no-new-alerts в изменённом коде, annotations 0. Checkov NEUTRAL означает отсутствие main comparison configuration, а не отсутствие alerts.

Tests-only партия добавила 25 guard/CLI cases и не меняла production-код. Ruff-форматирование двух argv calls исправлено по точному hosted diff. Полной quality-приёмки d5ef191 пока нет; последняя полностью принятая точка по-прежнему cd08c35c.

Следующая функциональная партия подготовлена и статически проверена, но не опубликована: tests-first контракты строгой передачи NATS failures из durable message-sent, event ID в двух существующих image editors и запрет автоматической отмены active owned live runs новым commit. Отдельно подготовлены прямые event collection warm/mutate/fresh GET assertions. Create-with-image требует безопасного owner-bound lifecycle с сохранением AUD-180/AUD-233. NATS outage, merge и deploy не выполнялись.

[Первичная itemized evidence-сверка](../../audits/AUDIT-2026-10.md#itemized-evidence-accounting-baseline-2026-10-18) остаётся ограниченным проходом, не процентом закрытия 512 IDs. Отдельный 63-ID INDEX ledger имеет другой namespace. Наличие source и успешных функциональных cohorts не заменяет финальную quality-приёмку.

## Чистота owned CI-стендов

Текущий [d5ef191 live run](https://github.com/egorribun/university_ecosystem/actions/runs/39148882046) подтвердил 231 contract, 20 browser PASS, два штатных SKIP, успешную остановку контейнеров и metadata-only receipt. Synthetic merge tree совпадает с branch tree. Python suite прошёл; quality acceptance блокируется отдельной нормализацией branch coverage.

У прежнего отменённого [8d4f69c run](https://github.com/egorribun/university_ecosystem/actions/runs/39148403404) cleanup не подтверждён: run/job terminal CANCELLED, stale metadata stop step и отсутствующий receipt не доказывают ни продолжающуюся очистку, ни утечку ресурсов. Следующий contract защищает running live run от автоматической отмены новым commit; manual cancellation и runner failure остаются отдельными рисками.

## Историческая последовательность коррекций

Эти результаты относятся к указанным SHA и не описывают текущие blockers. Полная последовательность и ограничения доказательств сохранены в [audit supplements](../../audits/AUDIT-2026-10.md#canonical-content-cache-regression-2026-10-18) и истории Git.

- [a71b9c90](https://github.com/egorribun/university_ecosystem/commit/a71b9c902b64e4016bf67d009e5a299d07098ab0): исходная опубликованная партия из 108 файлов. Четыре неуспешных workflow: Matrix, OpenAPI, Owned Live и Checkov. Последующие коррекции согласовали artifacts, TOTP fixtures, locked/paged maintenance и PostgreSQL fixtures; исходные failures не являются текущим verdict.
- [4108382](https://github.com/egorribun/university_ecosystem/commit/4108382288f88d69a4eed9c7aa40caacbe2a48c4): backend shards и PostgreSQL прошли; frontend выявил повторное стирание exact null после logout. Исправление сохранило исходный null assertion и очистку private state. Старый events CRUD skip после 401 был признан недостаточным proof и устранён.
- [3256286](https://github.com/egorribun/university_ecosystem/commit/3256286df36c66254371b80439449897d7ee1efe): logout regression прошёл в первом shard; отдельные несовместимые ожидания absent/null и форматирование потребовали следующей коррекции. Backend acceptance этой попытки отсутствовала из-за pre-commit. Последующие успешные frontend cohorts supersede эти failures.
- [731275d](https://github.com/egorribun/university_ecosystem/commit/731275dc0c3860cc86ae1f8b57021db5493d1adf): tests-first RED канонического cache; independent PostgreSQL reader видел committed update, HTTP GET возвращал старое значение. [7444e5c](https://github.com/egorribun/university_ecosystem/commit/7444e5c298ae769abe0b75a25248f2fd71ad1686) устранил этот дефект и прошёл functional jobs; отдельные 24 непокрытые строки потребовали текущей tests-only партии.

Прежние локальные 490 Python / 433 frontend результаты и отдельные PostgreSQL/Linux проверки остаются историческими evidence, а не результатами нынешней cloud-only работы. Старое сообщение о 12 pending identities не устанавливает текущий blocker. Неповторение React 418 в последующих live runs не доказывает причину прежнего login flake. Frozen-RC full smoke и полная приёмка 59 specs остаются отдельными требованиями.

## Последняя полностью принятая контрольная точка

На [cd08c35c](https://github.com/egorribun/university_ecosystem/commit/cd08c35c8c0d144ff3c317aa3f16350a86e2a46c) все 23 workflows terminal: 21 SUCCESS, два штатных SKIPPED, failures 0. [Matrix 39081296285](https://github.com/egorribun/university_ecosystem/actions/runs/39081296285), Coverage & Quality Policy Gate и CI Success прошли. Все 78 required context/app pairs найдены: 77 SUCCESS и отдельно проверенный Checkov code-scanning NEUTRAL из-за отсутствующей main configuration сравнения. NEUTRAL не означает отсутствие alerts.

[Owned live Core](https://github.com/egorribun/university_ecosystem/actions/runs/39081296370): 221 contracts, 18 browser tests, два штатных skips и успешный cleanup. Hydration regression: два tests; TOTP cohort: 22 tests со 100% измеренных метрик. Эти результаты относятся только к cd08c35c, не к последующим audit commits.

Причина прежнего flaky первого login не объявлена установленной. SSR hydration readiness defect имеет отдельное доказательство, не тождественное доказательству причины flake.

## Зависимости, политика и ресурсы

- Dependency checkpoint C8 (`5611eb00`) принят; последующие изменения проверяются на собственных SHA. Шесть compatibility holds и открытый SeaweedFS advisory сохранены в [dependency supplement](../../audits/AUDIT-2026-10.md#dependency-closure-supplement-2026-10-15). Удалённые `dependency-updates-2026-10`, `merge-exceptions.md` и `NEXT_SESSION_PROMPT.md` не восстанавливаются.
- Сохраняются baseline319, 78 required contexts, blocking CodeQL и обычные hooks. В опубликованном a71b9c90 policy содержит 263 записи; прежнее число 261 устарело. Эта коррекция не добавляет dispositions и не подтверждает отсутствующее в текущей проверке отдельное owner approval для двух новых записей. Новые unmatched identities остаются блокирующими. Finite131 касается только неизменённых migration blobs из base `ac74e915` до 2026-11-13; остальные Tier 0 и затронутые миграции требуют 100%.
- Исторические ограничения локальных проверок (сейчас работа только через GitHub plugin): один тяжёлый прогон одновременно. Admission RAM ≤75% / free ≥8 GiB; stop RAM ≥85% / free <4 GiB. Разрешение Linux screenshots: ≤80% / ≥6 GiB, cap 1 GiB / 2 CPU; Lighthouse: 75% / 8 GiB, cap 2 GiB / 2 CPU.
- В прежнем локальном checkpoint одноразовые PostgreSQL/Linux/Alloy контейнеры, сети и proxy image были удалены по точным ownership metadata. Успешный Alloy guard подтвердил неизменность source, отсутствие оставшихся owned процессов и минимум 14,85 GiB свободной RAM; BuildKit и его state volume также удалены. В том checkpoint два принадлежащих задаче Go cache volumes были временно сохранены; их текущее состояние через GitHub plugin не проверялось. Global prune и удаление чужих ресурсов, env, Git history или private rescue bundle не применяются.

## После аудита

Закрыть quality/live gates, пройти два полных запуска 59 specs с paired DB/S3 persistence/restore между ними, затем risk/a11y, 36 Linux captures News/Events/Schedule и решение владельца, serial LHCI 7×3, frozen-RC full smoke, final security review, ordinary merge/main checks, шесть GHCR images и релиз. Единственный утверждённый визуальный пакет — Home12 на `ddbbc84d`.

Staging/production не развёрнуты; фактические trusted proxy/CNI/PVC/CSI проверки и соответствующие operational решения остаются открытыми.
