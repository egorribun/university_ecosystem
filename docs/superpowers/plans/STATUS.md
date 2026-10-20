# Статус выпуска MVP v1.0.0

Обновлено: 2026-10-20 (Europe/Istanbul). Порядок — [MVP_MASTER_PLAN.md](MVP_MASTER_PLAN.md), продукт — [ТЗ MVP](University_Ecosystem_MVP.md), качество — [ADR-047](../../adr/ADR-047-risk-based-quality-policy.md).

## Текущий приоритет

Полное закрытие [октябрьского аудита](../../audits/AUDIT-2026-10.md): все 512 AUD IDs, включая 507 исторически открытых пунктов и пять исторически закрытых. Для каждого нужны проверенное исправление и regression/runtime evidence либо обоснованный disposition. Исторический статус и наличие commit не заменяют приёмку текущего source. Полная сверка ещё не завершена; ниже указана подтверждённая нижняя граница закрытия. Приёмка MVP продолжается после этого приоритета.

Работа только через GitHub plugin, ветка `egorribun`, существующий [PR #1306](https://github.com/egorribun/university_ecosystem/pull/1306). Merge/deploy и обходы проверок не выполнялись.

## Текущая проверка аудита

Подтверждённая нижняя граница: 87 из 512 исходных AUD IDs. AUD-088 принят только на уровне rendered configuration по трём named PASS без пропусков; прежние 86 IDs сохраняются. [Scope, IDs и доказательства](../../audits/AUDIT-2026-10.md#evidence-checkpoint-87-verified-original-aud-ids). Это не полная сверка, не приёмка всего CI и не доказательство работы кластера.

На 47f35bf: frontend 9388 PASS / 779 файлов, все frontend static gates и production build прошли. Real SDK/Axios/MSW ETag cohort подтверждает разделение order/query/cache/ETag; повторная OpenAPI generation не даёт diff. PostgreSQL: 203 PASS / 9 прежних SKIP, включая raw HTTP rank/date counterexample. Оба pre-commit и inventory gates проходят. Exact hosted checkout/tree проверены.

NATS: на 2c85f95 focused backend — 847 PASS / 15 FAIL: четырнадцать ожидаемых collector-composition RED и прежний outage hold. Подтверждены 52 request/decode cases, 21 projection case и 28 preflight cases. Composition получила реализацию после RED, но её own GREEN ещё нужен; coordinator/CLI callers и outage не подключены. [Plan](2026-10-20-owned-nats-docker-observation.md).

Actual Core 911db82: 26 PASS / 2 прежних SKIP, cleanup 2026-10-20 00:03:56 UTC, receipt artifact 12230572763, exact source tree проверен. Обе темы проходят первые четыре и следующие семнадцать AUD-072 declarations при неизменённых assertions. Whole AUD-072 открыт: остальные consumers, theme collisions, malformed one-color mixes, AUD-085 utility emission и AUD-073 contrast не объявляются исправленными.

Frontend 2c85f95 — 9433 PASS / 6 intended FAIL / 784 файла. Новые RED относятся к fractional tab и pending Enter; static gates проходят, исправления ожидают own GREEN. AUD-066 принят как подготовка одного занятия выбранной недели с фильтрами и campus timezone, не full-calendar sync. AUD-071 теперь подтверждён неизменённым browser hit test на desktop/mobile; AUD-089/090 получают новые регрессии до изменения production. [Evidence](2026-10-19-ui-lifecycle-reconciliation.md).

Последний проверенный Core 4f64: run 39363500028 / job 118434859608, 28 PASS / 2 прежних SKIP в 03:33:51 UTC. Stop/receipt завершены в 03:34:13; artifact 12238472787, SHA-256 f795e14acd6f54805ffb4791aca20c6aa4439f72df490713b6401a12e82c8024. Это own-source browser proof, не full-CI, outage или deployment acceptance.

На a71c6d7 все 21 Compose projection cases проходят. Все 52 daemon request/decode cases проходят на 4f64; операции остаются без I/O. Collector composition реализована после четырнадцати наблюдавшихся RED и ожидает own GREEN; runtime callers не подключены. Все 28 existing AUD-084 cases прошли в verbose focused job; production preflight не меняется. Workflow расширен только на прежней строке 155, без сдвига baseline coordinates. [Scope](2026-10-20-owned-nats-docker-observation.md).

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

## Entrypoint and pending-input correction checkpoint

Source 2c85f95d2c9db0b7b51667947b89278752511570 is bound to checkout f64150fdefa36eee5a5928cc6cbbf919b489bceb and identical tree 5fb25a811b5a81caf12f8170f9c00573b2f03103. Contract job 118441928877 reports 125 PASS / four intended Make recipe FAIL in 32.27 seconds. Node job 118442417955 reports 592 PASS / four intended FAIL: VS Code still points at root/tests and three icon write-error scenarios exit zero. Icon success and missing-input controls pass.

Frontend totals 9433 PASS / six intended FAIL across 784 files. Job 118442418080 observes numeric 0.5/1.5/4.5 instead of General and duplicate pending rename callbacks; job 118442418051 observes no selected tab after real-schema validation of a fractional value. Existing behaviors and string-coercion controls remain passing.

Focused backend job 118442456006 reports 847 PASS / 15 FAIL in 226.67 seconds: fourteen unavailable collector-composition assertions plus the existing disabled-outage hold. Its three Helm hibernation tests explicitly PASS, with no skips for those nodes.

AUD-088 is accepted as the original rendered frontend/gateway positive-minimum defect. The two off-peak/daytime cases pass at 03:50:21/22 UTC and the disabled-state case at 03:50:23 in job 118442456006. They execute Helm against the tracked chart/dependency archives with synthetic CLI overrides and no dependency update or cluster contact. Hibernation remains disabled by default; no replicas, schedules or deployment settings change. This does not prove real KEDA zeroing, wake readiness, cron execution or availability. The verified lower bound becomes 87/512; other new findings remain open until their own corrected-source GREEN.

AUD-082/083/087/089/090 получили узкие исправления после наблюдавшихся RED; own GREEN ещё требуется. Makefile сохраняет baseline line188 без изменения baseline, использует один continued Python command и не удаляет tracked schema. Collector composition делегирует существующему collector, но runtime callers/outage остаются не подключены. Защитные gates, dispositions и required contexts не ослаблены.

## Verified 93-ID checkpoint

Source 1ed440f88de239971ce9e4e6900a41ed6adad7c3 is bound to hosted checkout 8bbbd09fc76189c0caa6993acfb008728a2d367b and identical tree 07c72b763fa54ec77bd1bcc6e435b06d76ec8579. Contract job 118448021392 passes all four real Make-recipe regressions and totals 129 PASS in 30.89 seconds. Node job 118448485714 passes all 596 tests with zero failures/skips, including actual JSONC discovery validation and five bounded icon-generator subprocess cases.

AUD-082 is accepted for the corrected tracked-test discovery configuration, not a physical VS Code session. AUD-083 is accepted for executable recipe ordering, failure propagation and retained schema with synthetic application/npm boundaries; real SDK/MSW parity remains governed by its existing drift gates. AUD-087 is accepted for nonzero output-error status with best-effort continuation, not a favicon-format change.

Frontend jobs 118448485907, 118448485830, 118448485880 and 118448485741 pass 2634, 2228, 2290 and 2287 tests respectively: 9439 PASS across 784 files. GroupInfoPanel's 41 branch cases pass at 04:09:04 UTC, settings schema's 27 at 04:11:05, and actual Settings closure's six at 04:14:13. Static job 118448485844 and production build 118448485767 also succeed.

AUD-089 is accepted for rejecting fractional numeric tabs to General while preserving historical string parsing and valid indices; actual Settings conditional rendering confirms one selected General panel. This is not a full-router or real-browser ARIA claim. AUD-090 is accepted for suppressing Enter-driven rename callbacks while isRenaming is true, retaining the draft and allowing one settled submission. It does not claim to eliminate every same-tick race before a parent prop update.

AUD-095 has recovered named real-transport proof in successful race-enabled Go job 118448423362: open Health.Watch and idle-drain cases pass at 04:08:59 UTC. The unchanged production helper is integrated into runServers. Acceptance is limited to the standard Health.Watch hang; arbitrary cancellation-ignoring handlers, exact wall-clock limits and whole-process/deployment shutdown remain outside scope. See [runtime cleanup and timing](2026-10-20-runtime-cleanup-timing.md).

Focused backend job 118448423252 reports 861 PASS / one existing disabled-outage workflow hold in 246.72 seconds. All twenty-one collector-composition cases now pass, in addition to the fifty-two request/decode controls. These replace the private collector in tests and do not establish real daemon observation, complete inventory or enabled runtime outage. Security/type, lint and source inventory checks pass; baseline 319, dispositions 263 and required context/app pairs are unchanged. This checkpoint is not full-CI or release acceptance; e150 remains the last fully accepted CI source.

Подтверждённый нижний предел: 93/512. Следующая партия проверяет независимое завершение ресурсов и корректную нижнюю границу CI timing; исправления этих пунктов ждут наблюдаемого RED. AUD-094 получает named selection существующих key-encoding tests. AUD-092 требует совместимого именования Service и всех потребителей. Общие P1/operational holds остаются открытыми.

Owned Core run 39367414064 / job 118447292623 finishes 28 browser PASS / two existing SKIP at 04:20:48 UTC on the same verified checkout/tree. Owned containers stop and the metadata receipt completes at 04:21:10, with upload at 04:21:11. Artifact 12241160221 has SHA-256 f4eaf7e8131cf21cfb7a512b4eae2c39155c4c77b3665c8157ebb9fe7719a502. This is the owned Core cohort, not the full 59-spec acceptance or an outage run.

## Cleanup, names and timing: observed RED, 95-ID ledger

Source db83651f0ff564ba92b4896af341884fcd591d8d and checkout 1dda18a4389d5689b70835afadd1f26b60fa8af4 have identical tree ca40cdca808e4a007c3138fa502738302c6b35d0. Focused job 118456912531 reports 888 PASS / 13 FAIL in 245.73 seconds: six intended independent-cleanup failures, four intended long-Service-name failures, two intended diagnostic timing failures, and the existing disabled-outage workflow hold. The successful shutdown, six short/boundary Helm renders, four zero-duration timing controls and existing restart/ordering controls pass. Formatter, lint and frontend static checks pass after the separate three-file whitespace correction; no assertion was weakened.

AUD-094 is accepted for colon-key get/set and glob invalidation with reversible encoding. The round-trip case explicitly passes at 04:40:36 UTC, all four encoding cases at 04:40:37, and the non-UTF-8 preservation case at 04:40:37 in job 118456912531. This is grammar-enforcing in-memory KV evidence, not a live broker, TTL, arbitrary empty-key or legacy escaped-name migration claim.

AUD-100 is accepted for the shared IndexedDB version mismatch and tested schema/data preservation. On unchanged source 1ed440f88de239971ce9e4e6900a41ed6adad7c3, checkout 8bbbd09fc76189c0caa6993acfb008728a2d367b has identical tree 07c72b763fa54ec77bd1bcc6e435b06d76ec8579. The 41-case useNewsInteraction suite passes in job 118448485830 at 04:08:56 UTC and the two-case offlineUpgrade suite in job 118448485741 at 04:15:45. Shared constants 6545bf984dcd92bffa553e378343b4b6d07cd4d9, page e952fbb26fb48cdaf7c61b5f63520cd3124aade8, worker b9724e87b49ee430bde9728e6f15a8e68b095c00 and tests 918ce1edb7f985df77bf76b6af44e4bd65f1f195 / 470c60de892e4981007d5d50f0bd1ced807bdef6 are unchanged through db83651. Page cases use worker-shaped database fixtures; the complementary worker cases invoke actual initOfflineQueue against fake-indexeddb. This does not establish a combined real-browser page/worker upgrade, cross-tab blocking, sync delivery or every historical schema migration.

The verified lower bound becomes 95/512. AUD-091/092/093 corrections now await their own GREEN and are not counted. AUD-096/097/098/099 and the next Compose preparation/decoding boundary are tests first, not accepted implementations. Baseline 319, dispositions 263, 78 required context/app pairs, blocking CodeQL and finite migration exception are unchanged. Last fully accepted CI remains e150; current intentional outage hold is not a release pass.

Next source changes preserve sequential cleanup with original exception objects, suffix-safe Service names and all generated references, and execution-duration-only diagnostic lower bounds. New listener/telemetry/diagnostic IPC/Spectral regressions and the no-I/O Compose scaffold remain separate from those corrections. No deployment, outage activation, baseline edit or new suppression is included.

## Spectral behavioral RED and scoped rule correction

Source 52db76bcd4b1287f67a497032ccb9a8a0bfbabff and checkout 88a46c6ce6f9c3aa9ef8f22ce864035e5e450805 have identical tree 9d04c284e64bf713bd528a8936f4eb58aa647afb. Actual pinned Spectral job 118461862364 produces zero response-rule diagnostics and the expected PII property warning at 04:57:08 UTC; the checker fails for exactly ten missing 200/default warnings. The owned fixture container is removed by its exact CID before the step reports failure.

The responses schema now rejects maps with no explicit 400–499 or 4XX key. Existing object/required checks, five-verb selector, warning severity, OAS extension and PII rule remain unchanged. AUD-099 is not accepted until corrected-source execution proves the diagnostic paths and preservation controls. A separate exact formatter join in the Gateway source-contract assertion removes the lint blocker without changing its expected text or behavior. The verified ledger remains 95/512.

## Evidence checkpoint: 99 verified original AUD IDs

Source 1fe2ae54f80587b4a2e4f341a287c17446956a28 and checkout a3e38d4022baa864821ce0e18b7caa7447f97260 have identical tree 4b0659d8b9c012d28f6d5e5cdcc232dc0578672c. Focused backend job 118465432563 reports 937 PASS / five FAIL in 274.91 seconds. All seven AUD-091 cleanup cases, ten actual Helm AUD-092 cases and six AUD-093 timing cases pass. Remaining failures are two listener reconnect regressions, two not-yet-implemented Compose boundary assertions and the intentional disabled-outage workflow hold.

AUD-091 is accepted for sequential independent cleanup, preservation of original exception identity, deterministic multiple-error chaining and finalizer cancellation handling. This does not prove bounded shutdown, recovery from startup failure or protection against arbitrary external cancellation. AUD-092 is accepted for suffix-safe names of the five Services and every generated reference, with valid short names unchanged; cross-release collisions, other resource names and deployed TLS remain outside scope. AUD-093 is accepted for using the maximum observed job execution duration as a diagnostic lower bound while preserving wall-clock observations and strict provenance checks.

Actual pinned Spectral run 39372798397 / job 118464191194 succeeds at 05:04:09 UTC on the same checkout/tree. All ten required warnings occur at the intended responses maps; explicit 400/4XX controls and excluded verbs remain clean, and PII/OAS preservation checks pass. The exact owned fixture CID is removed. AUD-099 is accepted for this five-verb, warning-severity rule, not an expanded API policy.

The verified lower bound is now 99/512. Baseline 319, dispositions 263, 78 required context/app pairs, blocking CodeQL and the finite migration exception remain unchanged. A new public test-sentinel disposition is awaiting explicit approval and has not been activated. Current partial cohorts do not replace e150 as the last fully accepted CI source.

### Observed RED and next corrections, not yet accepted

AUD-096 has two expected reconnect failures in job 118465432563; cancellation, open-connection InterfaceError, permanent SQL and authentication controls pass. The correction retries ConnectionDoesNotExistError and classifies InterfaceError as transport loss only when the connection was already closed before cleanup. Existing backoff and cancellation behavior remain unchanged. These use real asyncpg exception classes with controlled connections, not a live PostgreSQL outage.

AUD-097 has seven intended timing failures in frontend shard 118465493049 (2232 PASS / seven FAIL); disabled, failed-initialization and LHCI controls pass. The correction records the genuine provider-tree commit event before deferred telemetry initializes, reports once when both duration and reporter exist, and removes the listener on disabled or failed Web Vitals initialization. APP_TTI retains its wire name but is not browser TTI, completion of all Suspense descendants or route-data readiness. Two overload-related test typing errors are corrected without a suppression; the original fixture now publishes the actual hydration event instead of relying on telemetry initialization time.

AUD-098 has an observed natural-exit watchdog failure in Node job 118463052515 (597 PASS / one FAIL, zero SKIP), while the real-timer IPC control passes. The correction unreferences only the diagnostic IPC channel after installing its message handler. It does not force exit or remove support for querying a genuinely live process. All three corrected findings await their own GREEN and are excluded from 99.

## Evidence checkpoint: 102 verified original AUD IDs

AUD-098 is accepted on source c8c7462b4ac76d6406ae7dab7d1ecc4ca1ffbdf3, checkout b8c228a6a58d83938e2ecc303b4bd30e3ef2443c, identical tree 795962dc7a1ff72828b79c24abbf114004fe8c5f. Node job 118475833111 reports 598 PASS / zero FAIL / zero SKIP. At 05:46:49 UTC the real preloaded IPC child exits naturally in 41.21 ms, and the real-work timer control still responds to diagnostic IPC in 35.68 ms. This proves the diagnostic channel no longer owns process liveness; it does not authorize forced exit or claim every build handle is eliminated.

AUD-097 is accepted on source c8c7462b4ac76d6406ae7dab7d1ecc4ca1ffbdf3, checkout b8c228a6a58d83938e2ecc303b4bd30e3ef2443c, identical tree 795962dc7a1ff72828b79c24abbf114004fe8c5f. Job 118475833169 passes all 35 real-entrypoint regression cases at 05:51:20 UTC and finishes with 2239 PASS across 196 files. Static job 118475833188 and production build 118475833115 pass. Acceptance is bootstrap-to-provider-tree-commit measurement with once-only reporting despite deferred telemetry initialization and teardown on disabled/failed initialization; APP_TTI is not browser TTI, all descendant readiness or route-data completion.

AUD-096 is accepted on the same source and identical checkout/tree. Focused backend job 118477821142 reports 939 PASS / three FAIL in 237.76 seconds. All six named reconnect/control cases pass at 06:00:22–24 UTC, followed by both existing listener cases. Connection loss reconnects, cancellation does not retry, and open-interface, permanent SQL and authentication failures remain errors. This is controlled asyncpg lifecycle evidence, not a live PostgreSQL outage. The remaining three failures are the two unavailable Compose positive seams and the intentional disabled-outage workflow hold.

The verified lower bound is 102/512. Current Core live job 118472156734 reports 28 PASS / two existing SKIP at 05:46:33 UTC and completes owned-container cleanup and metadata-only receipt upload. Artifact 12243552222 has SHA-256 2d8410657f39ec5506a2ae281e6f34bb9ed72698260897b6c68bf73cbb8e4c7b. Contract job 118473411122 reports 154 PASS in 35.91 seconds. Neither partial cohorts nor Core browser evidence replace e150 as the last fully accepted CI source.

### Next no-I/O boundary and tests-first UI work

Compose preparation/decoding now implements the previously observed RED seams: exact v11 Core owner/pin/layout admission, copied inputs before clock callbacks, fixed explicit argv/environment, bounded confirmed process evidence, strict UTF-8/JSON decoding, and original-fingerprint projection matching. Fourteen additional controls cover clock-callback mutation, missing exact-class fields, malformed process types and excessive JSON nesting. Existing daemon implementation is unchanged. These seam calls perform no transport I/O; module import still initializes existing live_stand globals. Deadline checks sample elapsed time rather than preempting parsing. No runtime coordinator, CLI or outage is connected, and metadata matching is not daemon authenticity or complete inventory. Own GREEN remains required.

AUD-101 adds nine actual-script prepaint selection/one-shot cases, including system and invalid-preference dark-media regressions. Execution uses the unchanged script in a bounded JSDOM VM context; it does not prove physical browser paint or successful dynamic module loading. AUD-102 adds four production retry/close-failure cases with all owned gates and calls drained, no testing reset between failure and retry, and no destructive removal. AUD-104 adds three actual-component keyboard cases for compact/expanded profile controls. These are tests first; their production sources remain unchanged and none is accepted here.

Baseline 319, dispositions 263, required context/app pairs, blocking CodeQL and finite migration exception remain unchanged. The one public test-sentinel disposition remains awaiting approval, and the scanner still reports that finding. No waiver, baseline edit, deployment or outage activation is included.

## Evidence checkpoint: 103 verified original AUD IDs

AUD-108 is accepted for dispatching the mobile search shortcut on document with bubbling enabled. On source c8c7462b4ac76d6406ae7dab7d1ecc4ca1ffbdf3, checkout b8c228a6a58d83938e2ecc303b4bd30e3ef2443c has identical tree 795962dc7a1ff72828b79c24abbf114004fe8c5f. Job 118475833169 passes the complete 15-case MobileMenu.closure suite at 05:51:44 UTC, including its document-target/bubbling case. Source 01fd766f17085e424c2b6a1d922bdd1e917270b5 and tests 54e05221439b5165e85eb8b2a7c8b7eca5b854be are independently confirmed unchanged through c9a7bdd. This closes the event-target defect, not AUD-107's first-shortcut/deferred-listener race. The verified lower bound is 103/512.

Source c9a7bdd3987cbb48addbda22a24aa9520b982ea2 and checkout e9fdc2957bbf734bd34a03d4b845156dd713faa5 have identical tree 2181399540fa5e79d893ed45803b8bb645b5b976. Its frontend static job 118492262058 and Python lint job 118491862006 pass. The preceding three-file correction was whitespace-only; no regression assertion changed.

Frontend job 118492262050 reports 2247 PASS / four FAIL: exactly two actual-script theme failures (system and invalid preference with dark media) and two compact-name keyboard failures. The remaining controls pass. Job 118492262090 reports 2287 PASS / four FAIL: exactly the four production RxDB creation/cleanup recovery regressions. These results support the next narrow corrections, not acceptance.

Theme selection now preserves explicit dark/light and follows media preference otherwise. RxDB initialization now clears a failed creation attempt, awaits nondestructive close after collection-registration failure, and only then allows a new attempt; failed close retains the original rejected attempt and error. Promise-identity checks avoid clearing a newer cached attempt. The testing-only reset helper is unchanged. The compact profile-name button becomes disabled and aria-hidden while the avatar/settings controls and layout remain unchanged. AUD-101/102/104 require their own GREEN.

A new native-keyboard browser case is appended to the already Core-selected search-dialog-keyboard file, with no new skip. It runs both existing Chromium projects at explicit 1440x900 geometry, verifies real scrolling and focused-name release, compact Tab/Shift+Tab order, restored expanded activation and navigation. This is not mobile-layout or screen-reader proof. Navbar-layout-stability is in the full inventory, not the PR smoke selection; it is not cited as Core execution evidence.

### Compose depth refusal and remaining operational hold

Focused backend job 118494700539 reports 954 PASS / two FAIL in 270.28 seconds. Forty-five Compose cases pass, including both formerly unavailable positive seams. The new deeply nested unknown-field case fails because the decoder accepted it; relying on Python's recursion limit was insufficient. The other failure remains the intentional disabled-outage workflow hold.

The correction adds an iterative whole-document maximum of 64 containers, counting the project root as one, with explicit depth-64 acceptance and depth-65 refusal controls. The original deep fixture is retained. This bounds admitted decoded structure, not json.loads execution: the existing 1 MiB input cap and sampled deadline checks remain, with no preemption claim. No runtime coordinator, CLI collection or outage activation is added.

### Next actual-tool and safe-rendering regressions

AUD-103 is tests first. A generator extracts the unmodified Kubernetes rule groups and the existing immutable official Prometheus image from Compose. Six actual Promtool cases cover high/low producer-series boundaries and pending-to-firing timing; seven generator guards and one named real-gauge exposition test complement, but do not replace, that oracle. The independent hosted step has a three-minute cap inside the unchanged fifteen-minute job, bounded pull/create/start/inspect/cleanup, network-disabled evaluation and exact-CID removal. Both attachment status and inspected exited/zero status are required. Thresholds, durations and current metric expressions are unchanged pending observed RED. PR trigger coverage is unchanged; main push path filters are not expanded.

AUD-105 receives six real SearchDialog sentinel/escaping cases. The backend explicitly emits non-HTML MARK_OPEN/MARK_CLOSE sentinels; arbitrary API HTML must remain text. Malformed/unknown markers conservatively remain literal text. This slice does not close the separate e2e missing-UI success paths, change truncation or title highlighting, or permit raw HTML rendering.

Baseline 319, dispositions 263, 78 required context/app pairs, blocking CodeQL and the finite migration exception are unchanged. The public inspection-sentinel disposition remains pending approval. Only backend workflow line 155 receives the named gauge-test selection; its 631-line span and protected lines 396/406 remain unchanged. No deployment, release acceptance or security-policy bypass is claimed; e150 remains the last fully accepted CI source.

## Promtool harness prerequisite correction

On source 2bb79f814e77b9c0790c6cdd9626e43af7e52263, job 118500856916 stops at 07:15:06 UTC while extracting the image: constructing the entire Compose document with yaml.safe_load rejects its unrelated !override ports tag. Promtool was not executed, so this is not AUD-103 rule RED. Job 118503488447 separately reports one Ruff adjacent-string formatting change in the generator, blocking backend fan-out; no behavioral assertion failed in that formatter step.

Image extraction now composes SafeLoader nodes without constructing custom-tagged values, traverses exactly services/prometheus/image, and rejects ambiguous, missing, tagged or non-string path nodes. Thirteen additive CLI controls cover unrelated override tags and malformed paths. The independent source oracle uses nodes rather than the same failing whole-document constructor. Actual rules, assertions, image pin, Docker budgets and cleanup are unchanged. The formatter's exact string join is applied. Own hosted verification remains pending; the ledger stays 103/512 and no policy or baseline exception changes.

## Actual Promtool RED and metric-name correction

Source 6fa6bdbb5e15ac3208c2e3c8aaa813b134360e55 and checkout f4b5c659def06e79aca4ca9379419536fa43eeef have identical tree 0b4f53a95f28a7dd279aaccbeace50e42a3867d1. Actual pinned Promtool job 118505775746 reaches rule evaluation at 07:22:31 UTC and reports exactly the six missing positive pending/firing observations across the three high-input cases. No low-input or zero-state check fails. The script verifies an exited container state, preserves the nonzero execution outcome and removes owned CID 939822664f5b58379904ca433791e9dded4d26805fcff243f2be9966219e3c70.

The next correction changes only the three alert expressions to the real producer metric names: outbox_pending_events_total, db_pool_checkedout and db_pool_size. Thresholds, pending durations, labels and annotations are unchanged. AUD-103 still requires corrected-source actual-tool GREEN and named producer exposition proof; it is not included in the 103/512 ledger.

Separately, prior frontend static job 118504261645 rejects the newly added profile URL regular expression and one long-array formatting choice. The browser assertion now polls the parsed URL pathname for exact /profile equality without a regular expression; this preserves query/fragment tolerance. The SearchDialog fixture array receives a whitespace-only canonical-width join. No suppression, assertion deletion, new skip, secret-policy change or baseline edit is introduced.

## Evidence checkpoint: 105 verified original AUD IDs

Source 72b24b3cee31e7c812e5dc0a743583e96b724808 and checkout 8b84631850bb85651fcdb8f6e32e4219a9677ff4 have identical tree 141470a59d005a982f066bd122b8bffde508d4e2. Frontend static job 118510212101 and Python lint job 118509513060 pass.

AUD-101 is accepted for actual prepaint-script theme selection and one-shot initialization: job 118510212207 passes all 13 staticShellI18n cases at 07:37:23 UTC, including the nine new cases. Explicit light/dark remain authoritative; system, invalid, empty and missing values follow media preference. This is bounded VM/JSDOM evidence, not physical paint or dynamic-module loading.

AUD-102 is accepted for the tested production initialization lifecycle: job 118510212344 passes all 14 index.closure cases at 07:42:40 UTC and finishes with 2291 PASS. Creation failure permits a new attempt; collection failure waits for nondestructive close; failed close retains the original rejected attempt/error without reopening. A pending close keeps callers pending. This does not prove real IndexedDB or cross-tab cleanup. The verified lower bound becomes 105/512.

### Real-tool verification and test-selection correction

Actual pinned Promtool job 118508309959 succeeds at 07:29:52 UTC on the same source/tree with all six rule scenarios. Owned CID daf65e73b51c024f0879c539fe132874a92a43fcd90f1f2682dc1ae4130f0369 is removed. Focused backend job 118510014584 passes the named real-gauge exposition node at 07:41:01 UTC and reports 958 PASS / one intentional disabled-outage hold in 263.99 seconds. All 48 Compose preparation/decode cases, including depth-64 acceptance and depth-65/deeper refusal, pass.

The 20 generator guards were incorrectly placed outside the quick Contract job's tests/contracts/ selection. Its 154 PASS result did not execute them. They are now relocated intact to tests/contracts/test_prometheus_alert_rules.py; only the source-root expression changes for the new directory. The original workflow-contract test file is restored byte-for-byte to blob 5660293abe8719032788e64d499ac384f6ee6c4f. Require 20 named passes in the selected cohort, not only a changed total. AUD-103 remains uncounted pending this verification.

### Search correction and unresolved native focus

The same frontend shard reports 2256 PASS / one expected SearchDialog highlight failure. Its five new safety controls pass. The correction renders only exact backend MARK_OPEN/MARK_CLOSE pairs as React mark children; all surrounding and matched content remains escaped text. Malformed canonical syntax returns the entire literal string, and no HTML parser or innerHTML is introduced.

The three regular full-text scenarios now call shared strict scenario functions rather than returning successfully when UI is absent. Three Core-live wrappers execute those same functions after real student authentication, with only the exact GET search response controlled. Each requires the requested query, HTTP 200 and exact controlled response, then dialog-scoped relevant results, visible highlights or a positive empty-state message. Exact owned routes are removed afterward. No fixed sleeps, informational-success fallbacks or invented /search route remain. This establishes a path to PR execution of shared scenarios, not execution of the entire regular main-only nightly suite or backend search correctness. AUD-105 requires its own corrected-source proof.

AUD-104 remains open despite 12 component cases passing. Source 6fa6bdb's Core run 39385970385 / job 118508036021 reports 29 PASS / one FAIL / two existing SKIP: the new desktop-geometry case fails only in the mobile-emulated project at reverse Tab (line 94). Earlier focused-name release and forward Tab passed, but compact state was not observed again before reverse Tab. Auto-scroll/expansion is only a hypothesis. Additional soft assertions record bounded scroll, boolean compact-control state and fixed focus categories at distinct source frames, while preserving every original hard assertion and the redaction policy. No skip or production focus change is introduced without evidence.

### Next tests-first boundaries

AUD-106 adds nine actual-ESLint path/exemption cases, AUD-107 adds four real deferred-SearchDialog shortcut cases, and AUD-109 adds four bilingual pool-default/example contracts. Their target behavior/documentation is unchanged pending observed RED. The deferred suite does not claim deterministic cold-import unmount coverage. Backend line 155 selects only the four named documentation cases, preserving the 631-line span, protected lines and five-minute budget.

The unavailable observe_compose_metadata seam and 16 guarded in-memory cases specify exactly one existing run_private_process call, the identical Deadline, stable owner snapshots, private failure decoding and collector exception identity. Four admission controls should pass and twelve composition assertions should fail until implementation; this is a prediction, not observed evidence. No real process, coordinator, CLI caller or outage is activated.

Baseline 319, dispositions 263, 78 required context/app pairs, blocking CodeQL and finite migration exception remain unchanged. The public inspection-sentinel disposition still awaits approval. e150 remains the last fully accepted CI source; current partial cohorts and intentional holds are not release acceptance.

Core live job 118513510726 subsequently succeeds on 72b24b3. This later pass does not explain the preceding reverse-Tab failure: no relevant focus implementation changed between those runs. AUD-104 stays open while the added state assertions investigate reproducibility; a passing rerun alone is not treated as a causal fix.

Service workers are blocked only for the three new controlled Core search scenarios and their corresponding regular scenarios so interception is deterministic. Existing Core keyboard/navbar cases keep their original context configuration; these controlled scenarios do not prove service-worker search behavior.

## Verification checkpoint — 2026-10-20 08:33 UTC

Source ce03f6482c3c71f2902793337e47b3c2cf0925d6 and checkout 0cac93a97566369420b6e7a16e9b9c9c5e3d9ceb share tree ab20fff9923063e8ce10a36e8061807a0bffca89.

- AUD-103 now has all three required layers: actual pinned Promtool six-case GREEN and real producer exposition on 72b24b3, plus 20 named generator-guard passes in selected Contract job 118523150422 on ce03 (174 PASS, 41.90 seconds). The verified lower bound is 106/512 (20.7%).
- AUD-105: corrected SearchDialog behavior suite passes all 23 cases in job 118524020061 (2263 PASS overall). Core job 118522672667 reports 34 PASS / two FAIL / two existing SKIP; both failures are the compact-navbar declaration, not the six new controlled search instances. This is shared-scenario execution, not the entire regular nightly suite. Static job 118524019095 finds the non-React useMockApi utility called from prepareSearch; its import is renamed locally to setupMockApi without a rule suppression. Closure remains pending the static correction.
- AUD-104 remains open. New bounded state assertions show native forward Tab reaches settings but scrollY is no longer above 24; disabled/hidden compact state then exits before reverse Tab. Both projects fail the compact-state assumptions at frames 129–131 and 136–140. The corrected test re-establishes compact mode by scrolling while settings must retain focus, then independently requires native reverse Tab to reach the avatar. It removes the invalid requirement that native traversal preserve viewport scroll. No conditional success, prevented scrolling, manual blur or production focus change is introduced. Corrected-source browser proof is still required.
- AUD-106's nine actual-ESLint cases were not selected by the hosted test:wasm command; its 598 PASS did not execute them. Add the suite to that exact entrypoint once, protect the selection, and correct two whitespace-only formatter violations. Target ESLint exemptions are unchanged pending real RED.
- AUD-107 has real RED in job 118524019167: first Control+K and Meta+K fail to open the real dialog; ordinary-key and already-mounted-toggle controls pass (2284 PASS / two FAIL overall). The correction retains a store-local opening request until the lazy dialog subscribes after installing its normal shortcut handler; afterward that handler alone owns toggles. Existing passive promotion listeners, delay, lazy imports and safe summary rendering remain. Pending intent is cleared on Escape or final cleanup. Corrected-source proof and deterministic cold-import race coverage remain outstanding.
- AUD-109 has two default-documentation failures and two explicit 5/5 example controls passing in focused job 118523935315. Narrow the default extractor to its own bullet (adjacent bullets had no blank separator), update both languages to the actual CPU-derived defaults and 540-second recycle, and retain the explicit override example unchanged. Corrected-source GREEN is still required.
- Compose composition has twelve expected stub failures and four admission controls passing in that same job (964 PASS / fifteen FAIL, 273.91 seconds, including the intentional outage hold). Implement exactly one existing private collector call with the same Deadline and admitted owner snapshot, then decode. No runtime caller, CLI, daemon inventory or outage is activated; corrected-source GREEN remains pending.

Core cleanup and metadata receipt upload succeeded; artifact 12250332856 has digest 8c2255611329324e2477771ed9f6f27cacf643229987667dce6a8c5db22435e9. This does not turn the failed Core run into acceptance.

Baseline 319, dispositions 263, the pending public-sentinel approval, 78 required context/app pairs, blocking CodeQL, migration exception and the last fully accepted source e150 remain unchanged. No full-green or release claim is made.

## Verification checkpoint — 2026-10-20 09:00 UTC

Source 3cc49cd1e500f2960625e018942a6efaee842e2d and checkout 257a3d35376b0cb12b6aedb6c9cba883f16660b7 share tree eaf9ec9857c808adb96a3888e1e404584c48befe. The verified lower bound is now 109/512 (21.3%), adding AUD-104, AUD-105 and AUD-109.

### Newly verified original findings

- AUD-104: Core run 39394888535 / job 118535048190 reports 36 PASS / two existing SKIP at 08:56:45 UTC. Both projects execute the corrected native-keyboard scenario. Forward Tab skips the disabled hidden name; reverse Tab independently starts from a re-established compact state while settings retains focus, then reaches the avatar. Returning to expanded state restores name access and Enter navigation. This corrects a demonstrated test-precondition error, not a production scrolling behavior. The prior component suite remains 12 PASS in job 118536398965.
- AUD-105: that same Core run passes all six controlled search instances after real authentication. Shared regular/live scenario functions require the exact query, successful controlled response and visible results, highlights or positive empty state; missing UI cannot pass. SearchDialog's 23 behavior cases and three focus-trap cases pass in job 118536398965 (2263 PASS total). The corrected regular utility alias passes TypeScript and ESLint in job 118536398935; its only remaining formatting warning names the separate architecture-test file. This is not proof of the whole main-only regular nightly suite, native backend search, or service-worker search behavior.
- AUD-109: job 118535985402 passes all four bilingual defaults/explicit-override cases at 08:48:23–24 UTC. The per-process CPU-derived defaults and 540-second recycle are documented consistently; the explicit 5/5 override remains unchanged. No runtime defaults were altered.

Owned Core cleanup and receipt upload succeed. Artifact 12251734381 has digest 010b1a9fe601740208d87897c3462d7850da6e7e30cd7f3e54dec34497a0d982.

### Remaining work and bounded evidence

The focused backend cohort reports 978 PASS / one intentional disabled-outage hold in 267.37 seconds. All sixteen named Compose observation cases pass at 08:47:01–05 UTC, in addition to the preceding preparation/decode and daemon-observation contracts. This accepts the tested composition boundary only: no runtime caller, daemon provenance, coordinator, CLI or outage is activated.

AUD-106 now has actual hosted RED: Node job 118536398799 reports 613 PASS / three FAIL (616 total). Each moved navigation component fails its untranslated-JSX warning case; all six translation/exemption controls pass. Correct only the three obsolete ESLint file paths. Extract warning arrays in the tests without changing rule identity, severity or expected values to remove the remaining formatting ambiguity; require hosted GREEN.

AUD-107's four real-dialog shortcut cases and eighteen existing lifecycle cases pass in job 118536398994 (2286 PASS total). Six supplementary store-level cases now cover post-promotion intent, Escape, one-time consumption, mounted ownership, stale callbacks, replay ordering and already-prevented shortcuts. Those new cases are unexecuted; this finding remains outside the ledger pending their proof. They do not claim deterministic cold-module loading or native-browser race coverage.

### Next tests-first slice

- AUD-110 extracts the actual browser-serialized reduced-motion collector without correcting its parser yet. Twelve selected Vitest cases use owned DOM and actual JSDOM computed styles: five predicted list/unit failures and seven controls, preserving root/descendant order, literal SVG-tag exclusion, hidden HTML inspection and the ten-offender cap. No Core inventory, threshold or regular browser scenario count changes. Collector proof is not native Chromium reduced-motion acceptance.
- AUD-111 adds two selected synthetic-thread orchestration cases. One failed thread start must not prevent joining successfully started threads under the shared 1.8-second budget. No real threads run in this new test; implementation remains unchanged pending RED.
- AUD-112 extracts the actual regular hydration diagnostic classifier with existing phase-specific behavior unchanged. Twenty-four cases in the already-selected hydration suite predict six minified-code failures and eighteen controls. No claim that the regular browser scenario ran.
- AUD-113 adds three real QueryClient update/removal cases with unchanged current event ID, owned-client cleanup and local infinite GC retention. No rerender, mocked cache subscription or network request supplies the expected change; implementation remains unchanged pending RED.
- AUD-114 adds one dirty-refresh regression and two cancel/reopen/new-item controls using the actual dialog. Existing pristine-refresh, language/source and image-cleanup controls remain intact. This slice covers Russian-editor text, not all dirty image or English-source races.
- AUD-115 adds a real BatchSpanProcessor cancellation/flush regression and an equivalent constructor seam. A retained processor receives independent bounded test cleanup even on assertion failure; public shutdown is observed before that cleanup. The canceled production context remains unchanged pending RED. No network exporter, SDK upgrade or new lint waiver is introduced.

The hosted collection contract invokes pinned Playwright 1.63.0 --list with an explicit synthetic environment and owned temporary output. It privately validates exact source coverage and both projects, then emits only source SHA and integer counts. Failure output uses fixed phases, never raw JSON/stderr/environment. Listing imports modules but runs no browser, stand, global setup or test bodies. A direct-child timeout is not descendant containment. The historical full-suite 190 PASS / eight fixed runtime SKIP gate is unchanged until exact collection and runtime-skip evidence are reconciled.

Only backend workflow line 155 adds the two cheap orchestration cases; its 631-line span, protected lines and 300-second budget remain. Baseline 319, dispositions 263, pending public-sentinel approval, 78 required context/app pairs, blocking CodeQL and finite migration exception are unchanged. e150 remains the last fully accepted CI source; current partial GREEN and intentional holds do not constitute full acceptance or release.

## Verification checkpoint — 2026-10-20 09:32 UTC

Source f06aa73467dbb6885d469b73d1e2b6c327e19239 and checkout 332a2c379e9c531734683fb0ef1e35ce427ee750 share tree 3066ab640aa8c4f555a6a5a0c2addfbf2eeef9f0. AUD-107 now joins the verified ledger, bringing the lower bound to 110/512 (21.5%).

### Verified scope

Job 118546333989 passes all 24 DeferredGlobalOverlays lifecycle cases, including six new ownership/cleanup controls, and all four real-dialog shortcut cases; total 2292 PASS. This verifies first Control/Meta+K intent, ordinary promotion, single mounted toggles, pending-request cancellation, stale callback rejection, replay ordering and already-prevented shortcuts. It does not establish deterministic cold-module/native-browser race coverage.

Core run 39397984257 / job 118545359975 again reports 36 PASS / two existing SKIP at 09:22:41 UTC. Cleanup/upload succeed; receipt 12253583196 has digest f9a48fb8344754f23fa07169bb61ed6377134a63d275d332ff264dcfd1322891.

Node job 118546333849 reports 617 PASS. All nine actual ESLint path/translation/exemption cases pass. AUD-106 remains outside the ledger while its fixture-formatting issue is resolved. Static job 118546333985 passes TypeScript but reports two collection-helper lint errors and formatting in the hydration helper/architecture fixture. Correct the regex spacing and defer failure throwing until after owned cleanup. For the persistent architecture formatting discrepancy, stop speculative rewrites: a temporary bounded diagnostic reads only that fixed public fixture, runs installed Prettier with its real configuration, and emits its formatted source only on mismatch. Apply that exact output and remove the diagnostic/imports afterward; it is not permanent production functionality or a waiver.

### Actual RED and prepared corrections

- AUD-110/AUD-112: job 118546333829 has 2661 PASS / eleven FAIL. Five failures are the real motion collector's omitted list components/mixed units, with seven new controls passing; six failures are exact minified React codes, with eighteen new classifier controls passing. Correct component-wise duration inspection inside the serializable collector and exact code-token recognition while retaining phase-specific text matching.
- AUD-111: focused job 118546836331 has 979 PASS / two FAIL in 253.94 seconds. The all-started control passes; the failed-start case raises when joining an unstarted thread. Track only successfully started threads for joins, preserving the shared deadline and all other lifecycle behavior. The other failure is the intentional disabled-outage hold.
- AUD-113: job 118546333924 has 2291 PASS / three FAIL; the 87-case event suite has only the three cache update/removal failures. Use an instance-local reference-stable external-store snapshot and relevant query-cache subscription, preserving invalid-session/SSR behavior, order and first-duplicate semantics. Three supplementary unrelated-cache/remove-recreate controls remain to be executed.
- AUD-114: job 118546334084 has 2265 PASS / one dirty-refresh FAIL. Existing pristine refresh and reset controls pass; the 16-case branch suite also passes. Track actual edits for the current open/item/language session, retain pristine synchronization and source abort handling, and clear image state at session boundaries. Six supplementary English/image/abort cases remain to be executed. In-flight save completion across session changes is not claimed fixed.
- AUD-115: job 118546836542 reproduces zero exports/shutdown calls and no cleanup deadline after parent cancellation. Existing success/noop controls and Go lint job 118546836539 pass. Give telemetry cleanup a fresh five-second context retaining values but not inherited cancellation/deadline; the test checks its finite upper bound. This is a telemetry phase budget, not a total service-shutdown SLA.

All corrected-source results remain pending; no predicted pass is counted as verification.

### Collection-count reconciliation and next tests-first boundaries

Both hosted collectors measure 216 instances across 61 files (108 desktop, 108 mobile), without executing tests. Exact e150-to-f06 source comparison adds eight declarations / sixteen instances: five search/keyboard and three settings cases. Existing live specs, configuration, fixtures and all eight fixed skip identities are unchanged. The remaining two-instance difference against the historical 198 gate predates those additions; do not label all eighteen as new or claim historical runtime reconciliation.

The expected current full outcome would be 208 PASS plus eight exact skips, not observed full acceptance. Keep the old production 190/198 constants for tests-first evidence: eight additive acceptance/index controls predict four RED and four PASS, and the private collector now requires its measured total to match the finite source constant. This deliberately refuses before starting a stand when collection/count accounting disagrees. After observed RED, update both constants and canonical fixtures together without changing any skip identity, redaction rule or rejection control.

AUD-116 adds a regression for the absent tests/smoke CLI target; the existing endpoint smoke file is tests/test_smoke.py, not the separate live multi-service script. AUD-117 adds four direct/tiered real-cache-wrapper cases with mocked Redis acquisition, predicting two tiered failures and two direct controls. No network runs in these cases. AUD-118's API/service/test blobs and Elasticsearch dependency blocks match the last accepted source, but old quiet job logs did not expose named cases; select its existing three SDK-fallback cases for fresh evidence instead of modifying already-correct exception handling.

Only backend workflow line 155 adds the small named cohorts; 631 lines, protected lines and the 300-second budget remain. Baseline 319, dispositions 263, pending public-sentinel approval, 78 required context/app pairs, blocking CodeQL and finite migration exception remain unchanged. e150 remains the last fully accepted CI source. Current targeted GREEN, test-first RED and cleanup receipts are not full acceptance or release.

## 2026-10-20 10:02 UTC — corrected-source evidence and next gate repairs

Source 44a9d818cd1b8b25918e9404df3319c9c8716b11 and hosted checkout ba478d7120637fc98e8364edf11fc0f251f02861 have identical tree 160ddba4785e994ac81c34ad072d906d9ba02d24.

- AUD-110: frontend job 118561272734 passes all fourteen motion collector cases at 09:47:25 UTC, including the five previously failing duration-list cases. This accepts scanning every animation/transition duration component, not native reduced-motion behavior.
- AUD-111: focused backend job 118560600461 passes both failed-start/shared-budget cases at 09:49:40 UTC. Only successfully started threads are joined within the existing shared 1.8-second budget. These are controlled thread-boundary tests, not total process-shutdown timing.
- AUD-112: frontend job 118561272734 passes all thirty-two hydration diagnostic cases at 09:47:26 UTC. Exact React code tokens 418/423/425 are recognized without broad numeric false positives; this is classifier evidence, not real hydration recovery.
- AUD-118: backend job 118560600461 explicitly passes the three existing SDK connection/timeout/API-error fallback cases at 09:49:42–43 UTC. API/service/test blobs and pinned Elasticsearch dependency blocks were independently matched to the earlier accepted source; no unnecessary exception-handling rewrite is made.

- AUD-113: frontend job 118561272679 passes all ninety event branch cases at 09:50:26 UTC (2297 PASS overall), including the three original RED cases and three supplementary controls. Unchanged-ID navigation now follows QueryClient list updates/removals with stable snapshots; ordering/filtering/deduplication and invalid-session behavior are preserved. This is controlled cache-subscription evidence, not browser acceptance.

The backend cohort has 990 PASS / eight FAIL in 236.01 seconds. Its failures are exactly the intentional outage hold, the new smoke CLI target case, two tiered Redis metric cases and four full-count/index regressions. Frontend shard 1 has 2672 PASS; shard 2 has 2272 PASS; shard 3 has 2292 PASS; shard 4 has 2297 PASS. These partial cohorts do not constitute all-required-check acceptance.

### Repairs requiring new hosted evidence

AUD-116 now points the existing CLI command at tests/test_smoke.py, with its obsolete assertion and misleading live-environment description corrected. It does not invoke the separate multi-service live script. AUD-117 unwraps only TieredCache.l2 before the existing RedisCache admission; disabled metrics, direct Redis, non-Redis fallback and exception handling remain unchanged. Their observed RED cases remain selected, and neither finding is counted yet.

The actual 216-instance collection disagreed with the historical 198 bound in Node and Core preflight. Core job 118559639143 refuses at collection-count before state selection or Docker startup; its receipt write/upload succeeds. Four independent pure acceptance/index cases also fail as predicted. Update only the finite bound to 216, canonical pass expectation to 208 and six canonical fixture/output literals, preserving eight exact skip identities and the obsolete-190/missing/extra/index-217 rejection controls. This sets the expected full outcome; it does not claim 208 runtime passes.

AUD-115's real canceled-parent BatchSpanProcessor regression now passes under the race-enabled job 118560600165, but coverage is 99.9% because the shutdown-error warning branch is untested. Add a deterministic real SimpleSpanProcessor exporter-shutdown failure case with independently owned cleanup, warning assertions and idempotence control; keep the 100% threshold unchanged. The original batch-flush regression remains intact. AUD-115 is not counted until the coverage gate passes.

The installed formatter's exact architecture-fixture output is recovered from Node job 118561272673 and applied without changing assertions. Retarget the one temporary bounded diagnostic to the fixed public News mutation-contract fixture, the only other remaining formatter warning. Once its exact output is obtained, remove the diagnostic and both imports completely. AUD-106 remains uncounted pending clean verification. AUD-114's complete 26-case suite passes, but its formatter cleanup is still pending.

Baseline 319, dispositions 263, pending public-sentinel approval, all 78 required context/app pairs, blocking CodeQL and finite migration exception are unchanged. No workflow selection/budget, NATS runtime admission, release or deployment changes are made. e150 remains the last fully accepted CI source.

The verified lower bound is 115/512 (22.5%). Only the five accepted findings above enter this checkpoint.

## 2026-10-20 — exact formatter cleanup and next audit regressions

Source 9cface170aded2ea6c9fae3f296e25001c57938e and hosted checkout 926c452dfec8be9ee1cc53279d8e626823a3932d have identical tree 9bbe41e3f4ead7f12ff413202099018eb546e66e.

AUD-115's real canceled-parent BatchSpanProcessor and real SimpleSpanProcessor exporter-error controls both pass at 10:13:44 UTC in race-enabled job 118571825595. Coverage is 100.0% at 10:13:46; lint job 118571825413 and integration job 118571825157 succeed. Accept the original canceled-context flush defect within this telemetry phase; retain the five-second cleanup bound and do not infer a total process-shutdown SLA.

Node job 118572527812 reports 617 PASS / one expected temporary formatter diagnostic failure. Actual pinned collection now agrees with the 216-instance bound. Static job 118572527938 passes TypeScript, ESLint, i18n and Knip; only NewsDetailEditDialog.mutation-contract.test.tsx formatting fails. Apply its exact installed-Prettier output, remove the temporary diagnostic and both diagnostic imports completely, and retain every behavioral assertion. The architecture fixture already passes formatting. AUD-106/AUD-114 still require the cleaned source's verification; do not equate the temporary diagnostic's failure with a product regression.

AUD-116's exact existing-endpoint smoke command passes at 10:18:19 UTC in job 118571825464; the CLI target defect is accepted without claiming live multi-service execution. That cohort times out at its unchanged 300-second limit near 98%, after executing the selected prefix through the healthy-direct Redis control (including the unchanged intentional outage-hold failure). AUD-117's healthy-tiered case and the final count/index cases do not run, so their corrected-source acceptance remains pending. A rerun request is refused because the containing workflow is still running; no repeated request or gate bypass occurs. Consecutive test log intervals broadly rise from a 0.225-second median on 44a9 to 0.281 seconds on 9cface, but that is not a causal GC/DB attribution. Investigate the shared fixture cost; preserve all selections and the fixed budget.

Core job 118570418071 completes 36 PASS / two fixed SKIP at 10:22:18 UTC. Owned-container cleanup, receipt creation and upload succeed; artifact 12256873702 has digest fb48be7fd1efb05e81362264bffbd9ab5547db49bef36afdf389567f4744e0c1. This is Core acceptance, not full 208/eight runtime acceptance.

### Tests first: observed execution still required

- AUD-119: two standalone real-calendar local-midnight/month-rollover cases preserve displayed month, callbacks and timer cleanup. A separate Schedule mock-wiring case requires forwarding the existing shared instant without resetting the chosen month/lesson dots. The standalone cases use local Date construction, not fixed 24-hour or UTC arithmetic. Three REDs are predicted; no production clock change is made.
- AUD-120: three selected contracts load actual Grafana YAML and apply pinned Grafana 13.2.3 signed shift arithmetic to zero/sub-millisecond/one-second spans. The upstream createSpanLink.tsx behavior adds shifts and only repairs equal Loki endpoints. Current +1h/-1h is predicted to invert the range. This is configuration/arithmetic evidence, not running Grafana.
- AUD-121: two arbitrary SemVer prereleases rejected by Python metadata grammar must fail before any of four files changes; stable and existing rc.1 controls preserve accepted versions. Official packaging 26.0 version.py confirms nightly.1/feature-x are outside the Python grammar. Register the existing pure-Node suite exactly once in the already-selected frontend Node command, with an exact-once guard. It uses owned absolute temporary fixtures, no network or release invocation. Two REDs are predicted; production validation remains unchanged.
- AUD-122: two actual Helm renders compare image/default or explicit PORT against container/Service/named health probes for 3000 and 3100. The override is predicted RED and default is a preservation control. This is rendered configuration, not a socket/deployment test; no image or dependency update occurs.
- AUD-124: five DOM accessible-name regressions cover News edit, Add/Edit lesson and subject/fallback lesson details using real settings Dialog/providers; two EventCreate create/discard controls retain its existing fix. The original audit row truncates the location list, so the five-target reconstruction is explicit. The mocked LessonDetails closure suite is not used as ARIA evidence. No native screen-reader result is claimed.
- AUD-125: equal/backward/increasing clock cases require worker status to track the latest recorded outcome while retaining observed timestamps. Two REDs and one control are predicted. No sleeps, wall-clock coercion or production outcome-state change.
- AUD-126: actual MemoryCache tiers exercise late subsecond backfill and a shorter-L1 control without network/sleeps. Late promotion must not extend source expiration or turn a subsecond TTL into permanent storage. One RED is predicted. Backend-specific expiration and NATS per-entry expiry are not established.

Only backend workflow line 155 gains the three small Helm/worker/cache nodes; its 631-line span, protected lines and 300-second focused budget remain unchanged. Nine small existing/new regression nodes move earlier within that same line to obtain evidence before the slower cohort; comparison verifies the exact old argument multiset plus precisely three new nodes. Add --durations=30 --durations-min=0.1 for setup/call/teardown attribution on a completed run. No original selections are dropped, cleanup is not weakened, and the reorder is not represented as a timeout fix. AUD-123 remains open: the source label-level defect is confirmed, but no repository-selected immutable Fluent Bit identity/runtime lane has been established. Do not replace that missing proof with a tautological string assertion.

Baseline 319, dispositions 263, pending exact public-sentinel approval, all 78 required context/app pairs, blocking CodeQL, the finite migration exception and disabled NATS outage boundary remain unchanged. e150 remains the last fully accepted CI source. The new regression predictions are not accepted findings.

Verified lower bound: 117/512 (22.9%). Only AUD-115 and AUD-116 are added at this checkpoint; the new tests-first findings remain unaccepted.
