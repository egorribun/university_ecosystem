# Статус выпуска MVP v1.0.0

Обновлено: 2026-10-20 (Europe/Istanbul). Порядок — [MVP_MASTER_PLAN.md](MVP_MASTER_PLAN.md), продукт — [ТЗ MVP](University_Ecosystem_MVP.md), качество — [ADR-047](../../adr/ADR-047-risk-based-quality-policy.md).

## Текущий приоритет

Полное закрытие [октябрьского аудита](../../audits/AUDIT-2026-10.md): все 512 AUD IDs, включая 507 исторически открытых пунктов и пять исторически закрытых. Для каждого нужны проверенное исправление и regression/runtime evidence либо обоснованный disposition. Исторический статус и наличие commit не заменяют приёмку текущего source. Полная сверка ещё не завершена; ниже указана подтверждённая нижняя граница закрытия. Приёмка MVP продолжается после этого приоритета.

Работа только через GitHub plugin, ветка `egorribun`, существующий [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306). Merge/deploy и обходы проверок не выполнялись.

## Текущая проверка аудита

Подтверждённая нижняя граница: 86 из 512 исходных AUD IDs. Приняты AUD-071 по настоящим desktop/mobile browser regressions и AUD-086 по named stability cases; прежние 84 IDs сохраняются. [Scope, IDs и доказательства](../../audits/AUDIT-2026-10.md#evidence-checkpoint-86-verified-original-aud-ids). Это не полная сверка и не приёмка всего CI.

На 47f35bf: frontend 9388 PASS / 779 файлов, все frontend static gates и production build прошли. Real SDK/Axios/MSW ETag cohort подтверждает разделение order/query/cache/ETag; повторная OpenAPI generation не даёт diff. PostgreSQL: 203 PASS / 9 прежних SKIP, включая raw HTTP rank/date counterexample. Оба pre-commit и inventory gates проходят. Exact hosted checkout/tree проверены.

NATS: на a27af92 focused backend — 736 PASS / 1 прежний outage hold. Все 57 reader и 55 lock/composition cases проходят, включая девять прежних private-policy RED. Explicit UID/0700/0600 проверяются по уже наблюдаемым metadata; это не authentication происхождения ключа. Exact checkout/tree проверены. Runtime adapters и outage не включены. [Reader plan](2026-10-19-owned-nats-owner-reader.md).

Actual Core 911db82: 26 PASS / 2 прежних SKIP, cleanup 2026-10-20 00:03:56 UTC, receipt artifact 12230572763, exact source tree проверен. Обе темы проходят первые четыре и следующие семнадцать AUD-072 declarations при неизменённых assertions. Whole AUD-072 открыт: остальные consumers, theme collisions, malformed one-color mixes, AUD-085 utility emission и AUD-073 contrast не объявляются исправленными.

Frontend 4f64cda — 9430 PASS / 784 файла, без failures. Все static gates и production build проходят. AUD-066 принят как подготовка одного занятия выбранной недели с фильтрами и campus timezone, не full-calendar sync. AUD-071 теперь подтверждён неизменённым browser hit test на desktop/mobile; AUD-089/090 получают новые регрессии до изменения production. [Evidence](2026-10-19-ui-lifecycle-reconciliation.md).

Core a27af92 run 39353709178 / job 118403589608 passes 26 browser cases with two existing skips at 01:45:40 UTC. Owned stop and receipt finish at 01:46:02; artifact 12234748128 has SHA-256 d8e280b30eaf28edf69b07e8db66a9b848f91f4900cd7db1a999ac25edd342d3. Checkout f7c8ff223aad624287d28f0b7c93dc6d207c6ff0 has the exact a27 source tree. No outage execution or full release acceptance follows.

На a71c6d7 все 21 Compose projection cases проходят. Все 52 daemon request/decode cases проходят на 4f64; операции остаются без I/O. Следующая collector composition пока unavailable и получает тесты. Все 28 existing AUD-084 cases прошли в verbose focused job; production preflight не меняется. Workflow расширен только на прежней строке 155, без сдвига baseline coordinates. [Scope](2026-10-20-owned-nats-docker-observation.md).

История промежуточных RED/GREEN, коррекции тестов и receipts сохранены в audit supplements и тематических планах. Прежний platform skip устранён; результаты текущих проверок описаны выше. Новых skip identities или waiver нет. P1 holds 164/167/169/174 сохраняются. Последний полностью принятый CI — e150. Baseline 319, dispositions 263, 78 required context/app pairs и security gates неизменны. Merge/deploy не выполняются.

## Последний принятый CI checkpoint

[e15027a](https://github.com/egorribun/university_ecosystem/commit/e15027afdb4793838de373463654fb9ffc31d079), [Matrix 39240974262](https://github.com/egorribun/university_ecosystem/actions/runs/39240974262), принят 2026-10-19 в 11:46 UTC: все 23 workflows terminal, 21 SUCCESS / два SKIP. Matrix: 86 jobs, 72 SUCCESS / 14 SKIP. По двум страницам 100+36 сверены 136 check runs с актуальными 78 required context/app pairs: 77 SUCCESS / один NEUTRAL, без missing/duplicates/pending/failures.

Checkov/app57789 NEUTRAL — «1 configuration not found»: конфигурация main не найдена в PR comparison, поэтому PR-introduced alerts не определены. Это не отсутствие alerts или файла на main. Отдельный Checkov IaC и пять CodeQL analyses успешны. 319 baseline identities, 263 dispositions, 78 contexts, blocking CodeQL и finite 131-file migration exception сохранены. Готовность к merge/deployment не заявляется.

Python 16509 PASS / 174 SKIP; frontend 9355 PASS / 772 файла; PostgreSQL 202 PASS / 9 SKIP. Focused gate 220 PASS / 62.86s, frozen-RC contracts 45 PASS / 11.49s. Все 15341 frontend branch arms hit; zero/unlocated/truncated — ноль. Оба pre-commit, smoke workflow и production build успешны. Исторический dd17 RSS-margin risk не объявлен устранённым.

[Quality gate 118040612402](https://github.com/egorribun/university_ecosystem/actions/runs/39240974262/job/118040612402): diff-cover 4536/0/100%, test universe 16683 nodes, coverage/provenance/schema/contract valid; quality artifact 12184206100, sha256:d3054722c97f12cc565784870cdbb02bc93771f0ac2d4c86a3f36b745b433666. CI Success 118041197078 сформировал и загрузил actual attempt-bound timing report, artifact 12183714114, sha256:0a74eb338fdb4b05131dcddce670a8b08a6e94e142aa8a5a401da4b20fd8fb80.

[Owned Live 39240974198](https://github.com/egorribun/university_ecosystem/actions/runs/39240974198): 20 browser PASS / 2 SKIP, stop/receipt 11:21:19 UTC, upload 11:21:20; artifact 12182134427, sha256:d546f1a0b65501be311d80d056f05cbe0dee9383e9e5a6589dafd287e639d4e0. Checkout 7bcad3a2a2dded9b1d329e1d3660297b5f3d7bf7 имеет exact tree 02d2e75c94a1d7907bec8ee79ab1bc558d2a6579 source e150. Архив не извлекался. Это auth/role/reset smoke, не все Activity browser scenarios или 59 full-smoke specs.

AUD-471 принят на уровне исправленного source, регрессий и собственного полного CI: реальный API startup требует SMTP вне development до открытия ресурсов, независимо от process-role label; общая загрузка Settings для Alembic не требует API SMTP. TLS, precedence, role schemas, migration secrets, revocation/TOTP requirements и email delivery/retry/DLQ semantics сохранены. Это не deployment или доставка через реальный почтовый провайдер.

Предыдущие принятые AUD-003/004/006 (f854), AUD-011/012/014 и reset-fragment diagnostic correction (606d) сохраняют прежний ограниченный scope. Подробная история RED/коррекций — в [audit supplements](../../audits/AUDIT-2026-10.md). Manifest source_sha остаётся null: actual RC, main/bootstrap activation, pre-merge full smoke и deployment — отдельные решения. Полная сверка ещё не завершена; подтверждённая нижняя граница указана выше.

## Последняя партия: AUD-471 и граница запуска API

Tests-first 49592 дал 15 DID NOT RAISE failures / 184 PASS. Model-validator в 626bf прошёл focused gate, но staging Alembic job 118004339366 выявил настоящую регрессию (1 FAIL / 79 PASS / 4 SKIP): миграции намеренно используют общий authentication-capable профиль api. Подмена migration-role или добавление фиктивного SMTP в migration manifest не использовались.

Boundary tests 0f57 сначала остановились на Ruff RUF043; это не RED поведения. Raw-string correction e99 дал настоящий hosted RED: job 118018910264, 14 FAIL / 206 PASS за 56.08s. Два shared Settings случая блокировались старым validator; 12 API lifespan случаев доходили до resource sentinel вместо SMTP rejection.

В e150 requirement перенесён из Settings model validator в explicit typed API preflight после CDC и до scheduler/container/DB startup. Process-role label не обходит проверку. Существующий source-helper проверяет те же parsed values через этот preflight; assertions сохранены. Новые bare Settings tests отдельно доказывают migration compatibility. Четыре production lifecycle doubles получили synthetic relay без снятия assertions. Standalone outbox MFA по-прежнему нуждается в SMTP для собственной доставки; это не blanket exemption.

Ранее падавший test_staging_online_alembic_uses_rendered_file_secrets_and_advances_head прошёл в job 118023102059 в 11:05:49 UTC; весь PostgreSQL набор 202 PASS / 9 SKIP за 271.32s. Это свежая source-bound приёмка после коррекции, не перенос результата старого checkpoint.

## Следующая партия и границы доказательств

[Согласованный NATS-only proof](../specs/2026-10-18-owned-nats-outbox-acceptance.md) выполняется по [плану](2026-10-19-owned-nats-outage.md).

- На 7195378 все 251 pure NATS cases (inventory, correlation, restoration evidence, worker policy, outbox state, broker evidence, deadlines) и прежние CLI/frozen-RC contracts прошли: early job 118116223502, 1 FAIL / 298 PASS / 72.36s. Единственный FAIL — намеренно отсутствующий live outage step. Следующий coverage report и later shard stages в этом job не выполнялись; full GREEN не заявляется.
- CLI разрешает help, но actual invocation по-прежнему блокируется до state/I/O. Coordinator runner/wait прошли собственный RED/GREEN,101 deterministic cases PASS. Bounded adapters не реализованы. NATS не отключался; pure snapshot/deadline проверки не являются runtime restoration proof.
- Следующий этап: private subprocess RED/GREEN и bounded owner-scoped transport и только после safety verification — точный PR repository/ref gate и hosted outage. Подробная RED/GREEN история сохранена в audit supplement. PDF AUD-015 остаётся отдельной подготовленной задачей.

Отдельный ordinary Live на 2a2 (run 39259367152/job 118087289920) дал 19 PASS / 2 SKIP / 1 FLAKY и остался FAILED: redacted frame password-reset.live.spec.ts:174 указывает на initial loginWith после регистрации, но причина ещё не установлена. Stop/receipt/upload успешны; artifact 12190998654. Ослабление теста или приёмка через повтор не выполняются. Следующий fb822 Live 39261859320/job 118095392215 прошёл 20 PASS / 2 SKIP с успешным cleanup/receipt/upload (artifact 12192064647), но это не устанавливает причину или устранение flake.

Канонический denominator: 18 P1 + 122 P2 + 234 P3 table definitions + 133 below-P3 bullets + пять исторически закрытых = 512 уникальных AUD IDs без пропусков. Поздние таблицы-ссылки не добавляют новых находок; 63-ID legacy INDEX — другой namespace. Полного актуального per-ID acceptance ledger пока нет.

Текущий проверенный минимум — 25 IDs на уровне source/regressions: AUD-003, AUD-004, AUD-005, AUD-006, AUD-008, AUD-011, AUD-012, AUD-014, AUD-025, AUD-026, AUD-028, AUD-038, AUD-166, AUD-168, AUD-170, AUD-171, AUD-172, AUD-173, AUD-179, AUD-182, AUD-201, AUD-338, AUD-458, AUD-471, AUD-491. Это не полный closed count/процент по512 и не deployment acceptance. На d13 job118122925227 все22 дополнительных cases получили named PASS (общий early gate1 FAIL / 320 PASS / 75.41s); их прежние execution gaps закрыты без изменения assertions. AUD-172 принят для UUID enqueue/handler correction с actual event-runtime и mock-backed news/comment round trips, не для outage или recipient ACK. AUD-166/168/458 дополнительно сверены с exact e150 source и именованными Go/PG PASS. Для AUD-165 выбраны три existing regression cases; их результат ещё ожидается. Подробные границы — в audit supplements.

AUD-164/167 требуют фактического trusted-proxy runtime, AUD-169 и отдельный AUD-189 — реального CNI/egress acceptance; source/chart CI не заменяет отсутствующий deployment. Для AUD-165 уже есть API regression, подтверждающий игнорирование avatar_url/cover_url при регистрации, и owner-key cleanup guard: отсутствие объединённого register-then-delete теста не доказывает оставшуюся уязвимость. Новая прикладная правка только из-за этого пробела не требуется.

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
- Сохраняются baseline 319, 78 required contexts, blocking CodeQL и обычные hooks. В опубликованном a71b9c90 policy содержит 263 записи; прежнее число 261 устарело. Эта коррекция не добавляет dispositions и не подтверждает отсутствующее в текущей проверке отдельное owner approval для двух новых записей. Новые unmatched identities остаются блокирующими. Finite131 касается только неизменённых migration blobs из base `ac74e915` до 2026-11-13; остальные Tier 0 и затронутые миграции требуют 100%.
- Исторические ограничения локальных проверок (сейчас работа только через GitHub plugin): один тяжёлый прогон одновременно. Admission RAM ≤75% / free ≥8 GiB; stop RAM ≥85% / free <4 GiB. Разрешение Linux screenshots: ≤80% / ≥6 GiB, cap 1 GiB / 2 CPU; Lighthouse: 75% / 8 GiB, cap 2 GiB / 2 CPU.
- В прежнем локальном checkpoint одноразовые PostgreSQL/Linux/Alloy контейнеры, сети и proxy image были удалены по точным ownership metadata. Успешный Alloy guard подтвердил неизменность source, отсутствие оставшихся owned процессов и минимум 14,85 GiB свободной RAM; BuildKit и его state volume также удалены. В том checkpoint два принадлежащих задаче Go cache volumes были временно сохранены; их текущее состояние через GitHub plugin не проверялось. Global prune и удаление чужих ресурсов, env, Git history или private rescue bundle не применяются.

## После аудита

Закрыть quality/live gates, пройти два полных запуска 59 specs с paired DB/S3 persistence/restore между ними, затем risk/a11y, 36 Linux captures News/Events/Schedule и решение владельца, serial LHCI 7×3, frozen-RC full smoke, final security review, ordinary merge/main checks, шесть GHCR images и релиз. Единственный утверждённый визуальный пакет — Home12 на `ddbbc84d`.

Staging/production не развёрнуты; фактические trusted proxy/CNI/PVC/CSI проверки и соответствующие operational решения остаются открытыми.

## Последняя проверка границ

Source a71c6d7c756c53bd31ea661053a9974ee9fdc497 is bound to checkout fbb400bb797ed0fd683515f19da1d9275c483953 and identical tree e164ddb9bbe0550e010832adead33404763a552d. Focused job 118415057333 reports 831 PASS / 7 FAIL in 212.74 seconds: six intended unavailable daemon request/decode assertions and the existing disabled-outage workflow hold. All twenty-one Compose projection cases and all twenty-eight existing preflight cases pass.

AUD-084 is accepted narrowly for bounded runner return when an exited parent leaves inherited output pipes open. The real Linux regression test_run_check_deadline_when_descendant_inherits_output_pipes passes at 02:16:19 UTC. Source was already corrected and is unchanged; adding named selection supplies the missing source-bound proof. Windows drain cases are simulated API controls, not physical Windows execution. Bounded return does not claim termination of every detached descendant.

После a71 RED исправление AUD-071 на 4f64 прошло настоящий browser hit test на desktop/mobile и formatter. Все 52 daemon assertions проходят после реализации проверки explicit inputs и supplied bytes без I/O; runtime adapters/outage остаются выключенными. Core после двух ожидаемых failures остановил owned containers в 02:22:24 UTC. Эти результаты не заменяют полный CI.

## Latest acceptance and next tests

Source 4f64cdad18186e3c8634505f11931dd99de5ccda is bound to hosted checkout ac85a98a815cd2c6d5aa17f363b73323bb3a4bcc and identical tree 77fa13ecba7ed054a4b6b8f452a1a73316729ba3. Frontend finishes 9430 PASS across 784 files. Static job 118436013198 and production build 118436013233 pass. Focused backend job 118435856906 reports 837 PASS / one existing disabled-outage hold in 220.14 seconds, including all fifty-two daemon request/decode cases.

AUD-071 is accepted: Core run 39363500028 / job 118434859608 passes 28 browser cases with two existing skips at 03:33:51 UTC. The unchanged paused-clock hit-target and ordinary-click assertions now pass on desktop and mobile. Pointer events are restored only for Snackbar content; outer positioning, Alert markup and dismissal timing remain unchanged. Owned stop and receipt finish at 03:34:13; artifact 12238472787 has SHA-256 f795e14acd6f54805ffb4791aca20c6aa4439f72df490713b6401a12e82c8024.

AUD-086 is accepted for paired-artifact stability debounce. Earlier source a71c6d7 and checkout fbb400bb797ed0fd683515f19da1d9275c483953 have identical tree e164ddb9bbe0550e010832adead33404763a552d. Job 118415281373 explicitly passes all seven behavioral cases at 02:13:08 UTC: unchanged fresh samples, same-metadata content changes, either output changing despite restored mtime, disappearance/reappearance, stale outputs, missing client assets and continuous churn. Its Node cohort totals 590 PASS / zero FAIL/SKIP. Source blob aa7ea4265ec21ed9d88fc253785d0bc9660adb72 and test blob ce5227820d601c7412d7788f36431d287ab192b3 are unchanged in 4f64. This establishes sampled shell/server stability, not producer completion, stability of every client asset or universally safe producer termination.

The lower bound advances from 84 to 86 original AUD IDs. None of these results enables outage, replaces full-CI acceptance or establishes deployment readiness.

Tests-first партия AUD-082/083/087/089/090 не меняет их production source. Existing AUD-088 render cases добавлены только в прежнюю строку 155 focused selection; нужны три named PASS, не SKIP. No-I/O daemon validation завершила свой bounded proof, но collector composition, inventory и outage ещё не готовы. [Quality entrypoints](2026-10-20-quality-entrypoints.md).
