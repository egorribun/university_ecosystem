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
