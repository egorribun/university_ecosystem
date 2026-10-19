# Статус выпуска MVP v1.0.0

Обновлено: 2026-10-19 (Europe/Istanbul). Порядок — [MVP_MASTER_PLAN.md](MVP_MASTER_PLAN.md), продукт — [ТЗ MVP](University_Ecosystem_MVP.md), качество — [ADR-047](../../adr/ADR-047-risk-based-quality-policy.md).

## Текущий приоритет

Полное закрытие [октябрьского аудита](../../audits/AUDIT-2026-10.md): все 512 AUD IDs, включая 507 исторически открытых пунктов и пять исторически закрытых. Для каждого нужны проверенное исправление и regression/runtime evidence либо обоснованный disposition. Исторический статус и наличие commit не заменяют приёмку текущего source. Общий процент закрытия пока не установлен. Приёмка MVP продолжается после этого приоритета.

Работа только через GitHub plugin, ветка `egorribun`, существующий [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306). Root управляет Git и принимает работу максимум трёх GPT-6 Luna Max агентов с непересекающимися файлами. Merge/deploy и обходы проверок не выполнялись.

## Последний принятый CI checkpoint

[f8545c8](https://github.com/egorribun/university_ecosystem/commit/f8545c8ddead5fdd88ac9a336f1fb083f752168a), [Matrix 39194937435](https://github.com/egorribun/university_ecosystem/actions/runs/39194937435): все 23 workflows завершены, 21 SUCCESS / два SKIP, failures нет. Matrix: 86 jobs, 72 SUCCESS / 14 SKIP. Все 136 check runs собраны по страницам 100+36 и сопоставлены с актуальными 78 required context/app pairs: 77 SUCCESS / один NEUTRAL, missing/duplicates/pending/failures нет.

NEUTRAL — Checkov/app57789, «1 configuration not found»: конфигурация присутствует на main, но не найдена в PR comparison, поэтому scanner не определил PR-introduced alerts. Это неопределённость сравнения, а не отсутствие alerts или файла на main. Отдельный Checkov IaC workflow и все пять языковых анализов CodeQL успешны. Не заявляется отсутствие всех findings или готовность к merge.

Python: 16417 PASS / 174 SKIP; PostgreSQL: 178 PASS / 9 SKIP; четыре frontend shards: 9318 PASS / 771 файл, frontend aggregate также успешен. Оба pre-commit и исправленный Prettier gate прошли. [Quality gate 117886129886](https://github.com/egorribun/university_ecosystem/actions/runs/39194937435/job/117886129886): diff-cover по coverage.xml — 4459 строк / 0 missing / 100%; coverage artifacts и quality contract valid, checksum manifest OK. Quality artifact 12162976903, Codecov inputs 12162882341.

Owned Live [39194937321](https://github.com/egorribun/university_ecosystem/actions/runs/39194937321): 20 browser PASS / 2 SKIP, owned stop/receipt/upload успешны; artifact 12161682381. Checkout e97f403a5ef386b32aca1a2a638e36ea062cedf3 имеет ровно tree b497b3c4d3c4192038cde2f2a895b113d071284b исходного f854. Архив receipt не извлекался; provenance проверен по run/log/metadata и Git tree.

AUD-003/004/006 приняты на уровне исправленного source, регрессионных тестов и собственного полного CI: однократное ICS escaping, adjacent next lesson и согласованный campus clock/автоматическая parity с сохранением ручного выбора. На tests-first f4 были реальные assertion failures; на f854 все соответствующие полные cohorts успешны. Quiet log backend shard zero сообщает 5585 PASS / 33 SKIP, но не печатает отдельный named ICS PASS; такой отдельный лог не заявляется. Это не deployment, не frozen-RC full smoke и не закрытие всего аудита.

Предыдущий полный checkpoint 7b340e7 и его source-bound RC/mimetype evidence сохранены в [audit supplements](../../audits/AUDIT-2026-10.md). Manifest source_sha остаётся null; actual RC не выбран, main/bootstrap activation и pre-merge full-smoke порядок остаются отдельным решением.

## Текущая партия: статистика регистраций

Tests-first [e3f8fbe](https://github.com/egorribun/university_ecosystem/commit/e3f8fbe2861b3bf6396eb0ac71b6e13264f299e3) и точечная Ruff-коррекция [4249718](https://github.com/egorribun/university_ecosystem/commit/4249718043bf4998a2d33cf651431a3a536bdee4) подтвердили реальные дефекты AUD-011/012/014. На 424 оба pre-commit gates прошли; ранний backend gate дал 21 FAIL / 15 PASS, включая отсутствие daily/streak и существующий SQL budget 7 запросов вместо 5. Full pytest после него не запускался. Все четыре frontend shards завершились: 21 assertion FAIL / 9323 PASS / 772 файла; три дополнительных failures относятся к non-finite TrendChip. PostgreSQL остановился на первом daily equality assertion: 1 FAIL / 162 PASS / 9 SKIP, без полного выполнения новых cases. Это реальные RED, не formatter/setup errors.

Контракт сохраняет правильный общий backend denominator и требует полные campus-day daily aggregates вместо capped recent, delta в percentage points / score points / event count и authoritative streak. Владелец подтвердил уникальные последовательные campus-дни мероприятий с регистрацией, окончание серии сегодня или вчера и независимость от фильтра 30/90/180 дней. Active/past eligibility, пятизапросный GET budget, cache isolation и bounded snapshot policy не ослабляются.

Ранний bounded backend запуск не заменяет полные shards, PostgreSQL service/query contracts, coverage/provenance и aggregate gates. HTTP/query-budget проверки остаются в обычной unit lane; RLS control statements не обходятся. В tests-first baseline изменены только восемь line_number references; все 319 identities и остальные поля сохранены.

Предыдущий e3 Owned Live завершил cleanup и receipt успешно, несмотря на новый commit: отдельная live concurrency group не отменяет активный прогон. Обычная Matrix group отменяет устаревшие runs, поэтому e3 shards 3/4 не дали полного результата. Собственный 424 Owned Live также завершил 20 browser PASS / 2 SKIP и cleanup: receipt 12164102527, checkout bbb69e1ae2bfc04eb8de4dda0dd453e71179117c с точным source tree d30ea09eb294191f8ff702b10adc068a24ab86bc. При этом 424 light-theme smoke отдельно остановлен RSS watchdog на 2050,1 МБ при лимите 2048 МБ до браузерных тестов; dark sibling успешен. Лимиты не увеличены. Ни RED, ни static review, ни cleanup старого SHA не закрывают текущую партию.

Минимальная реализация опубликована после observed RED: один scalar UNION ALL для attendance, по одному объединённому window read для grades/participation, complete daily и independent current streak; frontend использует проверенные Valibot поля и явные локализованные единицы. Старый cache payload не превращается в выдуманный график или серию. Независимый static review пройден; собственные hosted GREEN, query-budget proof и полная приёмка ещё требуются. На implementation 1e8 live preflight дал 229 PASS / 2 FAIL до запуска стенда: старые подписи колец и source assertion прежнего вызова grades. Два live specs и соответствующий source contract согласуются с новым кодом без ослабления metric/access/read-only проверок. Receipt 12164436479 отражает skipped startup/E2E/stop и не считается успешной live-приёмкой. Отдельный unauthenticated smoke на 1e8 прошёл в dark/light, включая обе сборки, route script и stop; RSS failure 424 не повторился без изменения лимитов. Static i18n gate дополнительно обнаружил случайное переименование EN ключа status.absent: восстановлен стабильный ключ, display text «not registered» сохранён. Cache-transition fixture получает явные daily aggregates без удаления исходных assertions; добавлена проверка перехода legacy cache → authoritative update. Scanner/quality/resource limits не ослаблены.

См. [спецификацию](../specs/2026-10-19-registration-analytics.md), [план](2026-10-19-registration-analytics.md) и [точные границы evidence](../../audits/AUDIT-2026-10.md#registration-analytics-hosted-red-and-implementation-checkpoint-2026-10-19-europeistanbul). AUD-011/012/014 и общий процент аудита пока не объявляются закрытыми.

## Проверенные Matrix исправления после hosted RED

База — tests-first [efd5483](https://github.com/egorribun/university_ecosystem/commit/efd5483c97810fff477aaf54201f710799f7b02e). Ruff correction прошла оба pre-commit gates; production-код до этой партии не менялся. На efd реально подтверждены четыре backend message contracts ([shard 0](https://github.com/egorribun/university_ecosystem/actions/runs/39158872405/job/117768386874): 4 FAIL / 5379 PASS / 49 SKIP), два frontend image-ID contracts и отдельный workflow concurrency contract ([shard 3](https://github.com/egorribun/university_ecosystem/actions/runs/39158872405/job/117773682192): 1 FAIL / 3413 PASS / 32 SKIP). Это конкретные ожидаемые RED, не formatting/fixture failures.

Минимальные исправления:
- ChatNotificationService получает keyword-only propagate_nats_failure=False и передаёт его существующему broadcaster; durable MessageSent handler включает True. Ошибка NATS выходит до notification writes и handler commit. Unit worker → EventBus → handler → service → broadcaster regression требует сохранения retryable outbox event, но использует doubles для DB/transport и не заменяет настоящий outage.
- Два редактора существующих событий передают точный ID в upload helper/FormData, сохраняя backend edit authorization.
- Owned Live оставляет прежнюю concurrency group, но не отменяет active run при новом commit. Это позволяет обычному запуску закончить cleanup; не защищает от manual cancellation, timeout или runner failure.
- Комментарии NATS согласованы с существующим CHAT_EVENTS: core publish не ждёт PubAck и сам не подтверждает persistence или browser delivery.

Retry остаётся bounded существующим лимитом (по умолчанию пять попыток, затем DLQ), не retry-until-success. In-process websocket fan-out происходит до NATS publish и может повториться при retry; exactly-once не заявляется.

На efd PostgreSQL integration прошла 178 PASS / 9 SKIP, включая усиленный events CRUD с прогретым collection cache и свежими списками после create/update/delete, а также news cache regression. Это реальный PostgreSQL, но cache/auth boundaries используют прежние doubles. Owned Live прошёл 231 source contract, 20 browser PASS / 2 штатных SKIP; stop и receipt upload успешны (artifact 12148403227). Actual NATS outage не выполнялся.

На 22b эти исправления прошли собственный Matrix/PG/frontend/live/quality, но тогда full GREEN блокировался Checkov finding; последующая коррекция и текущая приёмка 7b описаны выше. Старый efd не используется вместо этой проверки. [Согласованный NATS-only proof](../specs/2026-10-18-owned-nats-outbox-acceptance.md) остаётся следующим отдельным implementation/runtime этапом. Создание события с картинкой требует отдельного owner-bound lifecycle с сохранением AUD-180/AUD-233; эта партия исправляет только existing-event editors. Merge/deploy не выполнялись.

## Предыдущая полностью прошедшая CI-точка

[d35510a](https://github.com/egorribun/university_ecosystem/commit/d35510a1a6ace7bba113d0d2e0f1eebaebb8aac8), [Matrix 39153043118](https://github.com/egorribun/university_ecosystem/actions/runs/39153043118): все 23 workflows terminal (21 SUCCESS, два штатных SKIPPED), все 86 Matrix jobs terminal, failures 0. Полный paginated набор 136 check runs сопоставлен с 78 required context/app pairs: 77 SUCCESS, один NEUTRAL, ни одного failed/missing.

Python: 16372 PASS / 174 SKIP; PostgreSQL integration: 178 PASS / 9 SKIP и cleanup; frontend shards/static/build/contracts успешны. [Quality gate](https://github.com/egorribun/university_ecosystem/actions/runs/39153043118/job/117760994188): diff-cover 4458 строк / 0 missing / 100%, нормализация и validator успешны; quality-evidence artifact 12147286669, checksum проверен. Два недостижимых event-filter branches удалены без удаления visibility predicate, изменения порогов или исключений.

[Owned Live](https://github.com/egorribun/university_ecosystem/actions/runs/39153043004): 231 source contracts, 20 browser PASS, два штатных SKIP, успешная остановка контейнеров и metadata-only receipt (artifact 12146580632). Synthetic merge tree совпадает с branch tree. У старого отменённого [8d4f69c run](https://github.com/egorribun/university_ecosystem/actions/runs/39148403404) cleanup остаётся непроверенным; последующие успешные runs не устраняют эту неопределённость задним числом.

CodeQL: пять успешных языковых анализов и успешный aggregate с no-new-alerts в изменённом коде. Warning о >300 файлах привёл к пропуску diff-informed stage; обычные database/query/SARIF stages выполнены. Не заявляется отсутствие всех tool warnings. Checkov code-scanning NEUTRAL: configuration присутствует на main, но не найдена в PR comparison; это не отсутствие alerts. Отдельный Checkov IaC workflow успешен.

Это исторический source-bound CI checkpoint, не закрытие всего аудита, не подтверждение production deployment и не разрешение release. Более новый принятый checkpoint указан выше.

## Историческая последовательность коррекций

Эти результаты относятся к указанным SHA и не описывают текущие blockers. Полная последовательность и ограничения доказательств сохранены в [audit supplements](../../audits/AUDIT-2026-10.md#canonical-content-cache-regression-2026-10-18) и истории Git.

- [a71b9c90](https://github.com/egorribun/university_ecosystem/commit/a71b9c902b64e4016bf67d009e5a299d07098ab0): исходная опубликованная партия из 108 файлов. Четыре неуспешных workflow: Matrix, OpenAPI, Owned Live и Checkov. Последующие коррекции согласовали artifacts, TOTP fixtures, locked/paged maintenance и PostgreSQL fixtures; исходные failures не являются текущим verdict.
- [4108382](https://github.com/egorribun/university_ecosystem/commit/4108382288f88d69a4eed9c7aa40caacbe2a48c4): backend shards и PostgreSQL прошли; frontend выявил повторное стирание exact null после logout. Исправление сохранило исходный null assertion и очистку private state. Старый events CRUD skip после 401 был признан недостаточным proof и устранён.
- [3256286](https://github.com/egorribun/university_ecosystem/commit/3256286df36c66254371b80439449897d7ee1efe): logout regression прошёл в первом shard; отдельные несовместимые ожидания absent/null и форматирование потребовали следующей коррекции. Backend acceptance этой попытки отсутствовала из-за pre-commit. Последующие успешные frontend cohorts supersede эти failures.
- [731275d](https://github.com/egorribun/university_ecosystem/commit/731275dc0c3860cc86ae1f8b57021db5493d1adf): tests-first RED канонического cache; independent PostgreSQL reader видел committed update, HTTP GET возвращал старое значение. [7444e5c](https://github.com/egorribun/university_ecosystem/commit/7444e5c298ae769abe0b75a25248f2fd71ad1686) устранил этот дефект и прошёл functional jobs; отдельные 24 непокрытые строки потребовали последующей tests-only коррекции; их закрытие подтверждено на d5/d355.

Прежние локальные 490 Python / 433 frontend результаты и отдельные PostgreSQL/Linux проверки остаются историческими evidence, а не результатами нынешней cloud-only работы. Старое сообщение о 12 pending identities не устанавливает текущий blocker. Неповторение React 418 в последующих live runs не доказывает причину прежнего login flake. Frozen-RC full smoke и полная приёмка 59 specs остаются отдельными требованиями.

Исторический [cd08c35c checkpoint](https://github.com/egorribun/university_ecosystem/commit/cd08c35c8c0d144ff3c317aa3f16350a86e2a46c) также прошёл все применимые CI gates; его отдельные hydration/TOTP cohorts и старые live counts остаются evidence только того SHA. Он больше не является последней CI-точкой. Причина прежнего login flake не объявлена установленной.

## Зависимости, политика и ресурсы

- Новый follow-up: gateway использовал mimetype 1.4.15, отозванную upstream из-за quadratic CDF processing (GHSA-jjmc-jx7j-hp68). Прямого request path к CDF detection не найдено; наличие зависимости не доказывает exploitability. Кандидат 1.4.16 опубликован 2026-10-17 и набирает семь дней maturity 2026-10-24 10:15:44 UTC. После уточнения 2026-10-19 Europe/Istanbul владелец подтвердил исключение только для 1.4.15 → 1.4.16 с отдельным полным CI. Общий семидневный cooldown сохраняется. Canonical checksums подтверждены успешным hosted probe на 490a. Pin и go.sum обновлены на 1.4.16, отдельная коррекция добавила три hosted-generated workspace checksum-строки без изменения других requirements. Собственный Matrix/quality на 8fe8 прошёл; Checkov исправлен на d25, metadata согласованы на 7b. Финальный полный CI 7b прошёл с отдельной неопределённостью Checkov comparison, описанной выше. Остальной аудит продолжается независимо.

- Dependency checkpoint C8 (`5611eb00`) принят; последующие изменения проверяются на собственных SHA. Шесть compatibility holds и открытый SeaweedFS advisory сохранены в [dependency supplement](../../audits/AUDIT-2026-10.md#dependency-closure-supplement-2026-10-15). Удалённые `dependency-updates-2026-10`, `merge-exceptions.md` и `NEXT_SESSION_PROMPT.md` не восстанавливаются.
- Сохраняются baseline319, 78 required contexts, blocking CodeQL и обычные hooks. В опубликованном a71b9c90 policy содержит 263 записи; прежнее число 261 устарело. Эта коррекция не добавляет dispositions и не подтверждает отсутствующее в текущей проверке отдельное owner approval для двух новых записей. Новые unmatched identities остаются блокирующими. Finite131 касается только неизменённых migration blobs из base `ac74e915` до 2026-11-13; остальные Tier 0 и затронутые миграции требуют 100%.
- Исторические ограничения локальных проверок (сейчас работа только через GitHub plugin): один тяжёлый прогон одновременно. Admission RAM ≤75% / free ≥8 GiB; stop RAM ≥85% / free <4 GiB. Разрешение Linux screenshots: ≤80% / ≥6 GiB, cap 1 GiB / 2 CPU; Lighthouse: 75% / 8 GiB, cap 2 GiB / 2 CPU.
- В прежнем локальном checkpoint одноразовые PostgreSQL/Linux/Alloy контейнеры, сети и proxy image были удалены по точным ownership metadata. Успешный Alloy guard подтвердил неизменность source, отсутствие оставшихся owned процессов и минимум 14,85 GiB свободной RAM; BuildKit и его state volume также удалены. В том checkpoint два принадлежащих задаче Go cache volumes были временно сохранены; их текущее состояние через GitHub plugin не проверялось. Global prune и удаление чужих ресурсов, env, Git history или private rescue bundle не применяются.

## После аудита

Закрыть quality/live gates, пройти два полных запуска 59 specs с paired DB/S3 persistence/restore между ними, затем risk/a11y, 36 Linux captures News/Events/Schedule и решение владельца, serial LHCI 7×3, frozen-RC full smoke, final security review, ordinary merge/main checks, шесть GHCR images и релиз. Единственный утверждённый визуальный пакет — Home12 на `ddbbc84d`.

Staging/production не развёрнуты; фактические trusted proxy/CNI/PVC/CSI проверки и соответствующие operational решения остаются открытыми.
