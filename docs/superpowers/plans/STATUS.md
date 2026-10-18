# Статус выпуска MVP v1.0.0

Обновлено: 2026-10-18 (Europe/Istanbul). Порядок — [MVP_MASTER_PLAN.md](MVP_MASTER_PLAN.md), продукт — [ТЗ MVP](University_Ecosystem_MVP.md), качество — [ADR-047](../../adr/ADR-047-risk-based-quality-policy.md).

## Текущий приоритет

Полное закрытие [октябрьского аудита](../../audits/AUDIT-2026-10.md): все 512 AUD IDs, включая 507 исторически открытых пунктов и пять исторически закрытых. Для каждого нужны проверенное исправление и regression/runtime evidence либо обоснованный disposition. Исторический статус и наличие commit не заменяют приёмку текущего source. Общий процент закрытия пока не установлен. Приёмка MVP продолжается после этого приоритета.

Работа только через GitHub plugin, ветка `egorribun`, существующий [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306). Root управляет Git и принимает работу максимум трёх GPT-6 Luna Max агентов с непересекающимися файлами. Merge/deploy и обходы проверок не выполнялись.

## Текущая партия: tests-first контракты

На [4f03911](https://github.com/egorribun/university_ecosystem/commit/4f03911ca5ec53cefff0bd83f428c288f473e470) fast pre-commit остановил backend до выполнения тестов: Ruff свернул четыре коротких выражения в новом message-outbox regression. Исправление воспроизводит точный hosted diff; blob test-файла совпадает с выводом formatter. Assertions, fixture behavior, production-код и workflow не меняются. Это formatting blocker, не подтверждённый backend RED; backend regressions ещё должны реально выполниться.

На том же SHA подтверждены два ожидаемых frontend RED: `EventDetailEditDialog` не передал `evt-1` вторым аргументом upload helper ([shard 1](https://github.com/egorribun/university_ecosystem/actions/runs/39157404280/job/117764402190)), а `useEventCardLogic` оставил `event_id` в FormData равным null вместо `event-1` ([shard 3](https://github.com/egorribun/university_ecosystem/actions/runs/39157404280/job/117764402222)). Все четыре frontend shards завершились: 9287 PASS / 2 FAIL, 770 файлов. Это два конкретных contract failures, не сбой backend и не завершённая приёмка партии.

База — полностью прошедший CI [d35510a](https://github.com/egorribun/university_ecosystem/commit/d35510a1a6ace7bba113d0d2e0f1eebaebb8aac8). Эта партия меняет только tests и документацию; production-код пока остаётся прежним. Полной приёмки нового source ещё нет: сначала нужно получить настоящий hosted RED, затем внести минимальные исправления и выполнить собственный полный GREEN.

Проверяемые дефекты:
- Durable message-sent handler не включает строгую передачу ошибки NATS. Service/broadcaster assertions и real worker → EventBus → handler → service → broadcaster test требуют retryable event без notification writes/handler commit. Последний тест использует doubles для sessions/rows/repository/transport и доказывает in-memory переход, не PostgreSQL persistence или настоящий outage.
- Два редактора существующих событий не передают обязательный event ID при загрузке картинки. Tests закрепляют helper argument и FormData field, не ослабляя backend ownership.
- Workflow отменяет running owned live run при новом commit. Static contract требует literal cancel-in-progress=false в прежней concurrency group. Он сам не доказывает cleanup и не защищает от manual cancellation/runner failure.

Дополнительно events CRUD теперь прогревает collection cache до create и проверяет свежий список после create/update/delete. Это усиление HTTP/cache regression с PostgreSQL и существующими external-service doubles, без нового production behavior.

[Согласованный NATS-only proof](../specs/2026-10-18-owned-nats-outbox-acceptance.md) ещё не реализован и не запущен. Его owner-bound preflight, конечные deadlines, восстановление NATS, точный outbox и broker-storage oracle остаются обязательными. Создание события с картинкой требует отдельного owner-bound lifecycle с сохранением AUD-180/AUD-233; этот batch исправляет только контракты existing-event editors. Merge/deploy и NATS outage не выполнялись.

## Последняя полностью прошедшая CI-точка

[d35510a](https://github.com/egorribun/university_ecosystem/commit/d35510a1a6ace7bba113d0d2e0f1eebaebb8aac8), [Matrix 39153043118](https://github.com/egorribun/university_ecosystem/actions/runs/39153043118): все 23 workflows terminal (21 SUCCESS, два штатных SKIPPED), все 86 Matrix jobs terminal, failures 0. Полный paginated набор 136 check runs сопоставлен с 78 required context/app pairs: 77 SUCCESS, один NEUTRAL, ни одного failed/missing.

Python: 16372 PASS / 174 SKIP; PostgreSQL integration: 178 PASS / 9 SKIP и cleanup; frontend shards/static/build/contracts успешны. [Quality gate](https://github.com/egorribun/university_ecosystem/actions/runs/39153043118/job/117760994188): diff-cover 4458 строк / 0 missing / 100%, нормализация и validator успешны; quality-evidence artifact 12147286669, checksum проверен. Два недостижимых event-filter branches удалены без удаления visibility predicate, изменения порогов или исключений.

[Owned Live](https://github.com/egorribun/university_ecosystem/actions/runs/39153043004): 231 source contracts, 20 browser PASS, два штатных SKIP, успешная остановка контейнеров и metadata-only receipt (artifact 12146580632). Synthetic merge tree совпадает с branch tree. У старого отменённого [8d4f69c run](https://github.com/egorribun/university_ecosystem/actions/runs/39148403404) cleanup остаётся непроверенным; последующие успешные runs не устраняют эту неопределённость задним числом.

CodeQL: пять успешных языковых анализов и успешный aggregate с no-new-alerts в изменённом коде. Warning о >300 файлах привёл к пропуску diff-informed stage; обычные database/query/SARIF stages выполнены. Не заявляется отсутствие всех tool warnings. Checkov code-scanning NEUTRAL: configuration присутствует на main, но не найдена в PR comparison; это не отсутствие alerts. Отдельный Checkov IaC workflow успешен.

Это source-bound CI checkpoint, не закрытие всего аудита, не подтверждение production deployment и не разрешение release. Новая dependency-находка ниже остаётся открытой.

## Историческая последовательность коррекций

Эти результаты относятся к указанным SHA и не описывают текущие blockers. Полная последовательность и ограничения доказательств сохранены в [audit supplements](../../audits/AUDIT-2026-10.md#canonical-content-cache-regression-2026-10-18) и истории Git.

- [a71b9c90](https://github.com/egorribun/university_ecosystem/commit/a71b9c902b64e4016bf67d009e5a299d07098ab0): исходная опубликованная партия из 108 файлов. Четыре неуспешных workflow: Matrix, OpenAPI, Owned Live и Checkov. Последующие коррекции согласовали artifacts, TOTP fixtures, locked/paged maintenance и PostgreSQL fixtures; исходные failures не являются текущим verdict.
- [4108382](https://github.com/egorribun/university_ecosystem/commit/4108382288f88d69a4eed9c7aa40caacbe2a48c4): backend shards и PostgreSQL прошли; frontend выявил повторное стирание exact null после logout. Исправление сохранило исходный null assertion и очистку private state. Старый events CRUD skip после 401 был признан недостаточным proof и устранён.
- [3256286](https://github.com/egorribun/university_ecosystem/commit/3256286df36c66254371b80439449897d7ee1efe): logout regression прошёл в первом shard; отдельные несовместимые ожидания absent/null и форматирование потребовали следующей коррекции. Backend acceptance этой попытки отсутствовала из-за pre-commit. Последующие успешные frontend cohorts supersede эти failures.
- [731275d](https://github.com/egorribun/university_ecosystem/commit/731275dc0c3860cc86ae1f8b57021db5493d1adf): tests-first RED канонического cache; independent PostgreSQL reader видел committed update, HTTP GET возвращал старое значение. [7444e5c](https://github.com/egorribun/university_ecosystem/commit/7444e5c298ae769abe0b75a25248f2fd71ad1686) устранил этот дефект и прошёл functional jobs; отдельные 24 непокрытые строки потребовали последующей tests-only коррекции; их закрытие подтверждено на d5/d355.

Прежние локальные 490 Python / 433 frontend результаты и отдельные PostgreSQL/Linux проверки остаются историческими evidence, а не результатами нынешней cloud-only работы. Старое сообщение о 12 pending identities не устанавливает текущий blocker. Неповторение React 418 в последующих live runs не доказывает причину прежнего login flake. Frozen-RC full smoke и полная приёмка 59 specs остаются отдельными требованиями.

Исторический [cd08c35c checkpoint](https://github.com/egorribun/university_ecosystem/commit/cd08c35c8c0d144ff3c317aa3f16350a86e2a46c) также прошёл все применимые CI gates; его отдельные hydration/TOTP cohorts и старые live counts остаются evidence только того SHA. Он больше не является последней CI-точкой. Причина прежнего login flake не объявлена установленной.

## Зависимости, политика и ресурсы

- Новый follow-up: gateway косвенно использует mimetype 1.4.15, отозванную upstream из-за quadratic CDF processing (GHSA-jjmc-jx7j-hp68). Прямого request path к CDF detection не найдено; наличие зависимости не доказывает exploitability. Кандидат 1.4.16 опубликован 2026-10-17 и набирает семь дней maturity 2026-10-24 10:15:44 UTC. Точечное owner exception запрошено, но не получено; версия и go.sum не меняются до разрешения либо maturity. Нужны canonical hosted checksums и отдельный полный CI, без угадывания hashes. Остальной аудит продолжается независимо.

- Dependency checkpoint C8 (`5611eb00`) принят; последующие изменения проверяются на собственных SHA. Шесть compatibility holds и открытый SeaweedFS advisory сохранены в [dependency supplement](../../audits/AUDIT-2026-10.md#dependency-closure-supplement-2026-10-15). Удалённые `dependency-updates-2026-10`, `merge-exceptions.md` и `NEXT_SESSION_PROMPT.md` не восстанавливаются.
- Сохраняются baseline319, 78 required contexts, blocking CodeQL и обычные hooks. В опубликованном a71b9c90 policy содержит 263 записи; прежнее число 261 устарело. Эта коррекция не добавляет dispositions и не подтверждает отсутствующее в текущей проверке отдельное owner approval для двух новых записей. Новые unmatched identities остаются блокирующими. Finite131 касается только неизменённых migration blobs из base `ac74e915` до 2026-11-13; остальные Tier 0 и затронутые миграции требуют 100%.
- Исторические ограничения локальных проверок (сейчас работа только через GitHub plugin): один тяжёлый прогон одновременно. Admission RAM ≤75% / free ≥8 GiB; stop RAM ≥85% / free <4 GiB. Разрешение Linux screenshots: ≤80% / ≥6 GiB, cap 1 GiB / 2 CPU; Lighthouse: 75% / 8 GiB, cap 2 GiB / 2 CPU.
- В прежнем локальном checkpoint одноразовые PostgreSQL/Linux/Alloy контейнеры, сети и proxy image были удалены по точным ownership metadata. Успешный Alloy guard подтвердил неизменность source, отсутствие оставшихся owned процессов и минимум 14,85 GiB свободной RAM; BuildKit и его state volume также удалены. В том checkpoint два принадлежащих задаче Go cache volumes были временно сохранены; их текущее состояние через GitHub plugin не проверялось. Global prune и удаление чужих ресурсов, env, Git history или private rescue bundle не применяются.

## После аудита

Закрыть quality/live gates, пройти два полных запуска 59 specs с paired DB/S3 persistence/restore между ними, затем risk/a11y, 36 Linux captures News/Events/Schedule и решение владельца, serial LHCI 7×3, frozen-RC full smoke, final security review, ordinary merge/main checks, шесть GHCR images и релиз. Единственный утверждённый визуальный пакет — Home12 на `ddbbc84d`.

Staging/production не развёрнуты; фактические trusted proxy/CNI/PVC/CSI проверки и соответствующие operational решения остаются открытыми.
