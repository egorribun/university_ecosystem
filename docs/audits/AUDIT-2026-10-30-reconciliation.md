# Post-pause reconciliation — 2026-10-30

## Subsequent source-bound decision on 778696a

The original 136-path manifest and 126-row classification below are retained
as the reviewed 8787b00e snapshot, not silently rewritten by later test results.
A subsequent [scoped AUD-512 acceptance](AUDIT-2026-10.md#scoped-aud-512-callback-panic-acceptance-2026-10-30)
adds only that ID to the published 391: **392 accepted, 120 unaccepted**.
Its real callback wrappers and all 11 named race-test controls pass on source
778696a; the same Go job fails the separate AUD-334 writer regression.
No real-broker acknowledgement or full-CI acceptance is claimed.

On the same source, all 10,466 frontend tests pass, including the previous
News/replay regressions. AUD-030 nevertheless remains partial: the chat-list
UI still reads the first twenty entries without exposing next-page state.
The original matrix's source-only and partial labels are not automatically
promoted by unrelated green tests. [STATUS](../superpowers/plans/STATUS.md)
records the exact current evidence and remaining CI boundaries.

## Scope and complete coverage

Reviewed [source 8787b00e3a9e6c59ce4156366fdbd9f856a4952c](https://github.com/egorribun/university_ecosystem/commit/8787b00e3a9e6c59ce4156366fdbd9f856a4952c) against
[ec9a4d58a802c9165f8e243bca0f4bc5f664bdf7](https://github.com/egorribun/university_ecosystem/commit/ec9a4d58a802c9165f8e243bca0f4bc5f664bdf7):
**136 paths, 83 modified and 53 added, no deletions or renames**.
The [comparison](https://github.com/egorribun/university_ecosystem/compare/ec9a4d58a802c9165f8e243bca0f4bc5f664bdf7...8787b00e3a9e6c59ce4156366fdbd9f856a4952c)
contains three commits: 4963face79be2da224d28779433df7ef219deeb4,
d1c8e96d5957ec9e0b4bb64c1fabb2e23ccc5a97 and the reviewed source.

Complete recursive Git trees (5,964 base entries; 6,017 head entries) were
untruncated and independently produced exactly the same 136-path blob delta.
All changed/new bodies and relevant callers, fixtures and instructions were
read. Review partitions were frontend 38, backend/Go/Rust 35, infrastructure 38,
security/Map 13 and documentation/dependency 12. Unchanged large prefixes were
compared byte-for-byte, not claimed as newly re-reviewed line by line.
No omitted/truncated body or compare-limit hole is concealed.

Reviewed tree `36b4abc7fb0b7e4d0d9a0c95439d73b9b60885b6` equals tested
merge `b528dce8f791c4938c2ca13391564d2715151ad1`.
Both endpoint lock graphs already contain DOMPurify3.4.17 despite the merge
commit title. The actual dependency delta only declares already installed
parse5 8.0.1 directly; installed dependency-node records are unchanged.

The separate [13-file recovery be88aed](https://github.com/egorribun/university_ecosystem/commit/be88aed8053c3230342e7c7cf517f62fa3abc0e4)
was independently reviewed against immutable postimages. It is not silently
included in the original 136-path scope and requires its own CI.

## Acceptance and all open findings

The reviewed snapshot contains **386 unique accepted IDs**, preserving 383 and
adding only 258/365/418. All **126 unaccepted IDs** were classified below:
**5 confirmed-ready, 48 source-fixed-awaiting-proof, 35 partial, 37 unfixed,
1 not independently verified**. The separate
[five-ID decision](AUDIT-2026-10.md#scoped-aud-155-aud-320-aud-406-aud-486-and-aud-500-acceptance-2026-10-30)
adds only155/320/406/486/500: **391/512 (76.4%), 121 still unaccepted**.
Classification is not automatic acceptance, and passing characterization of
unsafe behavior is not a fix.

For the previously added258/365/418, all eleven listed source/test identities
still match. [PostgreSQL job123790043690](https://github.com/egorribun/university_ecosystem/actions/runs/40970439106/job/123790043690)
independently confirms nine named258 cases, including32,768 messages and130
attachments; main cohort389 PASS/16 SKIP. Privileged-role fixtures and mocked
cache/hub effects do not prove restricted RLS or live delivery for that path.
365's bounded date-window and418's missing-key fail-closed source match their
criteria. Their retained local12/26-case stdout/JUnit hashes are not retrievable
hosted execution receipts in this GitHub-only review; no independent execution
or possession of those local artifacts is claimed. Existing scoped decisions
are preserved with that explicit evidence limit.

## Exact reviewed-source CI and known blockers

All 23 workflows are terminal: 18 success, 3 failure, 2 skipped.
[Matrix40976492839](https://github.com/egorribun/university_ecosystem/actions/runs/40976492839) has 60 jobs:
16 success,14 failure,30 skipped. Backend and Alembic execution was skipped
after pre-commit; failing compatibility aggregators are not executed tests.

- [Pre-commit123806386763](https://github.com/egorribun/university_ecosystem/actions/runs/40976492839/job/123806386763):
  two OSV subprocess lint errors and one formatter-only test diff.
- [OpenAPI123805700378](https://github.com/egorribun/university_ecosystem/actions/runs/40976492831/job/123805700378):
  current cursor fields missing from generated schema/types/mock.
- [Inventory123806386926](https://github.com/egorribun/university_ecosystem/actions/runs/40976492839/job/123806386926):
  catalog59 workflows/184 jobs PASS; two genuine source bindings and one
  unbounded fixture sleep fail. No skip-policy expansion is needed.
- [Frontend lint123807407113](https://github.com/egorribun/university_ecosystem/actions/runs/40976492839/job/123807407113):
  two type errors and one children lint error.
- [Shard2](https://github.com/egorribun/university_ecosystem/actions/runs/40976492839/job/123807407217):
  2,552 PASS/3 replay-recovery FAIL.
  [Shard3](https://github.com/egorribun/university_ecosystem/actions/runs/40976492839/job/123807407283):
  2,474 PASS/7 comments cursor/fallback/optimistic/downgrade FAIL.
  Shards1/4 have2,931 and2,498 PASS.
- [Bundle123808250692](https://github.com/egorribun/university_ecosystem/actions/runs/40976492839/job/123808250692):
  137 PASS/2 FAIL. Compressible password-dictionary .mjs can miss its1,250 KiB
  raw ceiling. Separately parse5 accepts a misnested fixture rejected by the
  strict test contract; this is not itself a proven budget exploit.
- [WASM123807407270](https://github.com/egorribun/university_ecosystem/actions/runs/40976492839/job/123807407270):
  814 PASS/1 collection FAIL/6 SKIP. New desktop/mobile story tests require224,
  not222 instances; approved eight skips and skip-index cap are separate.
- [Core123805700001](https://github.com/egorribun/university_ecosystem/actions/runs/40976492769/job/123805700001)
  stopped at collection before the stand. Native helper receipts remain
  usable only for their exact bounded criteria.
- [Contract123806386825](https://github.com/egorribun/university_ecosystem/actions/runs/40976492839/job/123806386825):
  consumer3,589 PASS/1 stale-renderer-pin FAIL, security681 PASS, renderer41 PASS.
  Earlier five secret-binding failures are repaired; no new identity is admitted.
- [Baseline123806642422](https://github.com/egorribun/university_ecosystem/actions/runs/40976492839/job/123806642422):
  60 unmatched scan findings remain for finite technical-hash triage.
  They are not automatically secrets, approved exceptions or closed findings.

CodeQL, Pact, dependency review, Nilaway, fuzzing and DB Performance pass their
actual selections, not skipped backend/browser/Windows/infrastructure paths.

At the later be88 checkpoint, its own pre-commit, inventory, WASM, OpenAPI/types,
MSW and [Owned Core](https://github.com/egorribun/university_ecosystem/actions/runs/40980172506) pass;
[Matrix](https://github.com/egorribun/university_ecosystem/actions/runs/40980172611)
reports all 91 jobs terminal: 58 success, 17 failure and 16 skipped.
The four backend shards total **22,425 PASS / 428 SKIP / 28 FAIL**;
separate preflight cohorts are not added to those totals.
Failures are SQL capture (19), Squawk shell/privacy (3), cold-cache/generation
(4), renderer source pin (1) and OpenAPI snapshot (1).
The refreshed workflow summary is terminal FAILURE. All 23 workflows are
terminal: 20 success, one failure and two skipped; no runs were cancelled.
Coverage Policy is skipped, not passed. Tested merge
`f175a7326aece8d0708a14ce5c6d57f6bbc74ef6` has the same tree
`2a88693f513a42bb218c38aaafb3c65d0f4220a2` as be88.
Frontend formatting, ws-hub lint, semantic cursor/replay/bundle,
migration/source-pin and hash gates remain unresolved.

## Affected accepted criteria

No source/receipt-supported reopening was found within these affected criteria;
this is not a new exhaustive runtime audit of all 386 accepted IDs.

- Frontend direct029/076/100/114/135/209/216/220/298/302/498 and adjacent
  101/156/157/232/333/337/376 retain their scoped boundaries. Current controller,
  draft-retention, prepaint and offline suites support those limits.
  AUD376 is persisted ETag-without-snapshot/304, not cursor pagination:
  unchanged source has ETag cache76/client4/SSR2 PASS. New cursor failures
  remain AUD030; existing watchdog controls do not close334.
- Backend028/031/170/180/181/196/338/339 retain news sanitation/ownership,
  anonymous projection, explicit commits and mutation cache rotation.
  263/266/388 health boundaries are preserved;413/469 and adjacent411/412
  native overflow/input/HMAC guards remain.166/458/511 hub channel/eviction/
  revocation boundaries remain;465 DLQ retry guard is unchanged.
  New043 generation/snapshot and334 cancellation races are distinct gaps.
- Infrastructure225/461/504 preserve EXPLAIN fail-closed, parameter/SeqScan and
  same-connection/savepoint rollback logic; no new current PG proof is implied.
  475 changes only three catalog guard leaves, not required/advisory/context
  metadata; current catalog PASS is not the full negative suite.
- Security185/186 keep unchanged verifier/policy boundaries.
  247's binary-integrity closure does not claim migration safety: stale renderer
  capture is a new source-evidence gap, not return to tag-only installation.
  AUD208 remains open.

## Ordered continuation and restrictions

1. Complete current recovery receipts and preserve exact failures.
2. Repair actual comments cursor and replay causes against existing RED tests.
3. Repair raw .mjs ceiling and parser contract without broad budget changes.
4. Prove Go cancellation/write-permit interleaving before its production fix.
5. Execute blocked backend/Go/PG suites and reassess 48 source-fixed candidates.
6. Bind stable renderer to fresh owned capture; retain raw Squawk warnings and
   strict verification of other migrations. Admission remains inactive.
7. Triage the final source's complete unmatched scan inventory and obtain any
   exact finite owner decision. Prior 58 approval does not transfer.
8. Address remaining matrix causes in bounded test-first batches.

Docker IpcMode=private rejection, unfinished DB-perf query-capture integration
and Go cancellation race are source-backed findings, not hosted runtime RED
receipts yet. Policy405, baseline319, Gitleaks26, coverage floors, inactive
Map286 and Squawk admission remain unchanged. No merge/deploy, production-data
migration, new access or gate suppression is implied.

## Complete 126-ID matrix

Snapshot states below precede the separate five-ID acceptance. Original criteria
are retained; source repairs and missing execution are distinguished explicitly.

| ID | Original criterion | State at reviewed source | Evidence and remaining scope |
| --- | --- | --- | --- |
| AUD-030 | Пагинация не доведена до UI комментариев, DLQ, чатов и событий карты | partial | Anonymous cursor adapter3 PASS; hook remains offset-only and seven current cursor/fallback/reconciliation cases FAIL. Other pagination surfaces cannot compensate. |
| AUD-043 | Прогрев news/events записывает в устаревшие cache namespaces | partial | Shared warmup namespace repaired, but cold non-Redis generation is not retained and stale DB snapshot may be tagged with a later generation; new tests await execution. |
| AUD-045 | Pruner не распознаёт monthly names из исторической миграции | source-fixed-awaiting-proof | Monthly-name/OID-parent/NOWAIT/caller-transaction guards repaired. Private Windows .pyd and opt-in owned-PG pruner proof absent; no current tracking-comment violation. |
| AUD-073 | Белый текст отправленных сообщений имеет недостаточный контраст на светлом violet gradient | source-fixed-awaiting-proof | Six numerical gradient/token contrast controls PASS; rendered browser contrast not established. |
| AUD-137 | SSR-проверка сырых ключей не замечает обычный fallback i18next | source-fixed-awaiting-proof | MainLayout SSR6 and native requested-locale negatives PASS; actual SSR-to-hydration browser run absent. |
| AUD-151 | Проверка JS-ошибок не ждёт готовности приложения | source-fixed-awaiting-proof | Listeners/readiness helper repaired, but new aud151-news-errors.test.mjs is not selected by inspected blocking commands; browser proof missing. |
| AUD-154 | Delivery test ждёт marker, которого нет в status renderer | source-fixed-awaiting-proof | Delivery assertion binds actual message identity and Sent/Read role; REALTIME_E2E guard still prevents current ordinary-suite execution. |
| AUD-155 | Ошибка optimistic-операции откатывает несвязанные изменения message cache | confirmed-ready | Token-owned rollback replaces snapshot restore; rollback.integration36, reverse-send1, clear-recovery2 and ownership11 PASS. Scoped source/local concurrency acceptance, not live certification. |
| AUD-164 | Backend видит IP gateway: все анонимы делят лимиты login/register/MFA/reset | partial | Source normalization and synthetic topology binder exist; actual leased two-client/proxy-chain proof is absent. |
| AUD-167 | Rate-limit gateway и ws-hub сводится к одному IP прокси | partial | Compose trusted peers and bounded probe witnesses exist; actual topology proof absent and binder rejects Docker default IpcMode=private. |
| AUD-169 | file-processor не стартует в staging/prod: revocation-Redis закрыт NetworkPolicy | partial | Redis release-scoped egress/render controls exist; actual CNI endpoint proof absent. |
| AUD-178 | Токен сброса пароля попадает в access log (Referer) и в CSP-отчёты | partial | Reset fragments and source protections exist; early legacy-query/path CSP probe lacks live receipt. |
| AUD-188 | JWKS file-processor запрещён NetworkPolicy: через ~24 ч отклоняются все RS256-токены | partial | JWKS egress/render controls exist; actual CNI endpoint proof absent. |
| AUD-189 | NetworkPolicy разрешает TCP/443 и DNS любому адресату, включая сервисы кластера | partial | CIDR exclusions/DNS selectors have effective-union negatives; real endpoint/CNI evidence remains on hold. |
| AUD-192 | Postgres, Valkey, SpiceDB, Temporal и MinIO подключены к сети public вместе с frontend | partial | Compose frontend_net isolates storage; historical local Docker claim lacks independently verified current source-bound receipt. |
| AUD-193 | Docker socket смонтирован в Alloy: `:ro` не ограничивает Docker API | partial | Alloy uses a GET-only socket proxy rather than direct socket. Current discovery/log-stream/isolation proof remains unverified. |
| AUD-208 | Squawk-гейт проверяет пустой SQL для guard-миграций и ослаблен исключениями | partial | Owned renderer/graph exist, but raw37 Squawk warnings remain blocking and full nonhistorical chain is unproved; current source pin is stale. |
| AUD-226 | Tier-0 миграции (`alembic/versions/**`) выпадают из требования 100% покрытия | partial | Alembic included in coverage; finite131 legacy baseline until2026-11-13 is not proof of all-migration100% merged coverage. |
| AUD-231 | SSR-страницы frontend отдаются без CSP, nonce-схема не работает | source-fixed-awaiting-proof | Per-request SSR nonce/header/HTML transform implemented; current actual browser CSP proof absent. |
| AUD-236 | Вышедшая вкладка остаётся стейл-привязанной и отменяет публичные запросы | source-fixed-awaiting-proof | Credentialless public paths and isolated caches have scoped PASS; complete stale-tab/public-route browser evidence absent. |
| AUD-244 | `zizmor.yml` отключает 15 аудитов, включая template-injection и dangerous-triggers | unfixed | Fifteen zizmor disable annotations remain; checkout credential hardening does not remove original suppressions. |
| AUD-245 | Trivy-исключения KSV глобальные (без путей), срок пересмотра истёк | unfixed | Ten global SPIRE KSV exceptions still lack path/expiry scope; finite Kyverno fixture exceptions are separate. |
| AUD-250 | Метрики кэш-Redis (9121) доступны любому pod; revocation-store это закрывает, app-chart нет | source-fixed-awaiting-proof | Redis metrics selector/effective-union negatives exist; current executed policy proof was blocked. |
| AUD-251 | SPIRE agent получает кластерный nodes/proxy get/list/watch | unfixed | SPIRE agent still grants get/list/watch on nodes/proxy. |
| AUD-253 | Лаунчер пишет .env.docker с секретами с umask по умолчанию на POSIX | source-fixed-awaiting-proof | PowerShell env creation uses CreateNew/UnixCreateMode0600 before writes; real pwsh umask/first-write controls need current receipt. |
| AUD-260 | Неограниченные выборки в скачивании вложений, посещаемости событий и приёме CWV | source-fixed-awaiting-proof | Attachment identity/limit2, my-events cap100/page+1 and CWV bounded500 implemented; complete named cross-surface runtime evidence pending. |
| AUD-262 | Сбой Redis после commit даёт 500 при успешной отправке и дубликат при повторе | partial | Durable command receipts and Redis-completion failure handling exist; current PG/concurrency/schema/legacy durability proof incomplete. |
| AUD-269 | Reconcile 202603280001 удаляет ~15 индексов горячих путей без восстановления | unfixed | Eight non-equivalent hot indexes remain lost; renamed equivalent HNSW is not counted as loss. |
| AUD-270 | Cutover UUID делает TRUNCATE ... CASCADE дочерней таблицы вместо остановки | unfixed | Partition child TRUNCATE CASCADE remains. |
| AUD-271 | Копирование партиций не сбрасывает SERIAL-последовательности: дубли id | source-fixed-awaiting-proof | Sequences reset after copying three tables; unit/generated-ID PG controls exist but current execution unverified. |
| AUD-272 | UNIQUE «delivery once» включает attempted_at и не препятствует повторным пушам | unfixed | Uniqueness includes attempted_at/nullable columns; characterization demonstrates duplicate/null admission, not remediation. |
| AUD-274 | Миграция 202511240001 теряет DND и часовой пояс пользователей | unfixed | DND timezone dropped without preservation within upgrade; later backfill does not prove original data survives. |
| AUD-275 | Индексы на messages и users строятся без CONCURRENTLY, docstring обещает обратное | partial | False CONCURRENTLY wording removed; blocking create_index remains. |
| AUD-277 | RLS с политикой USING(true) на восьми таблицах не изолирует данные | partial | Permissive TRUE is combined with restrictive tenant policy, so TRUE alone is not a proven bypass; separate360/450 remain. |
| AUD-278 | GIN-индекс events.search_vector удалён и не восстановлен | unfixed | Dropped search-vector GIN index not restored within upgrade. |
| AUD-304 | Утилиты dark: следуют системной теме, а не выбору пользователя | source-fixed-awaiting-proof | Class-based dark variant compiled8/prepaint9 PASS; type recovery separate, browser appearance not established. |
| AUD-308 | Архитектурные и токен-гейты не запускаются в CI, два набора тестов мёртвые | partial | Some architecture/CSS tests run; ui-barrel/boundary-micromatch and tokens:check not selected. tokens:sync is different. |
| AUD-309 | live_stand.py: вызовы без таймаута и бесконечное ожидание блокировки | unfixed | Generic runner/git/install/Chromium/Playwright/status subprocesses still lack timeouts. |
| AUD-310 | PreToolUse пропускает пустой или нераспознанный payload | source-fixed-awaiting-proof | Malformed/missing/conflicting hook payloads fail closed; current named proof missing, unknown well-formed tools intentionally allowed. |
| AUD-311 | Tier-0 правила сопоставляют каталоги: security-модули по имени вне Tier 0 | unfixed | Tier0 directory rules still miss audit_service filename criterion. |
| AUD-313 | Гейт owned-stand основан на переменных окружения; сид переписывает пароль администратора | unfixed | Live seed target trusts environment-only ownership and host postgres; stricter admin-smoke path does not repair it. |
| AUD-316 | .env.example: ключи без потребителя и нерабочий EVENT_FILE_SCANNER_ALLOW_ON_UNAVAILABLE | source-fixed-awaiting-proof | Dead env keys/fail-open flag removed; actual Settings/env/Compose scanner controls need current execution. |
| AUD-317 | Гейт MOD-30-01 слабее того, что описано в app/AGENTS.md | source-fixed-awaiting-proof | AST gate enforces literal noload/unique exemption/aliases; current gate/negative-test receipt pending. |
| AUD-319 | Тест «тайминг-атак» проверяет только stdlib `secrets.compare_digest` | source-fixed-awaiting-proof | Real ASGI CSRF middleware/comparator controls replace stdlib-only test; current execution pending, not statistical timing proof. |
| AUD-320 | Pact ws-hub сверяет копии логики и NATS-subjects, которых нет | confirmed-ready | Actual Python producer-to-Go production handler Pact29+1 PASS and anchored Go test0.009s; no live NATS/durability claim. |
| AUD-321 | E2E: условные проверки с веткой-annotation делают тест зелёным | source-fixed-awaiting-proof | Unconditional429/manual retry/Retry-After assertions exist; boundary1 PASS, browser suite unrun. |
| AUD-322 | Интеграционные тесты событий и chaos молча пропускаются | partial | CRUD assertions improved, but chaos still silently skips failed-login/no-chat cases. |
| AUD-327 | Upgrade через `148642dd1207` падает на legacy-БД с пользователями в верхнем регистре ролей | unfixed | Enum addition and cast still share historical transaction. |
| AUD-332 | Тесты «when_supported» создают symlink без проверки привилегий | unfixed | when_supported symlink tests still lack Windows privilege probe. |
| AUD-334 | Replay пропускается при rate limit или выключенном replay, пропуск не досылается | partial | Frontend recovery3 actual FAIL; separate Go cancellation-versus-permit race source-backed, not yet runtime RED. |
| AUD-346 | Nightly chaos-loadtest всегда зелёный: dry-run отключает все проверки | unfixed | Nightly chaos still --dry-run and omits recovery assertion. |
| AUD-347 | MinIO chaos-набор в nightly никогда не выполняется: заданы не те переменные | source-fixed-awaiting-proof | MinIO endpoints/credentials now match actual consumer; named non-skipped nightly execution pending. |
| AUD-348 | Апгрейд 148642dd1207 удаляет Spotify-токены из users без переноса | partial | Backfill precedes drop but excludes pre-existing empty destinations, so legacy token loss remains. |
| AUD-351 | 202603280001 падает на непустой notification_queue_jobs: integer record_id → UUID | unfixed | Historical integer record IDs still cast to UUID text. |
| AUD-360 | RLS: строки с tenant_id IS NULL видны всем тенантам, а приложение tenant_id не пишет (`alembic/versions/202607230001_multi_tenant_rls.py:153-161`) | unfixed | NULL-tenant rows remain cross-tenant visible and News inserts omit tenant ownership. |
| AUD-363 | WS /ws/chat не перепроверяет сессию после подключения (`app/api/websocket.py:201-256`) | source-fixed-awaiting-proof | Inbound/outbound authoritative WS revalidation plus ASGI/PG controls exist; current owned-PG proof missing. |
| AUD-366 | /healthz без аутентификации отдаёт версии миграций и параметры пула (`app/api/health.py:159-166`) | source-fixed-awaiting-proof | Public health always brief including cache paths; current named HTTP/cache execution pending. |
| AUD-369 | TLS к Temporal не включается без FP_TEMPORAL_API_KEY_FILE (`services/file-processor/cmd/file-processor/main.go:353-355, 357-390`) | source-fixed-awaiting-proof | Temporal TLS1.3 independent of API key, SDK-byte controls exist; current runtime proof missing, no external handshake claim. |
| AUD-370 | Приватные вложения отдаются inline с типом из конфигурируемого allowlist (`app/services/private_attachments.py:157-169`) | source-fixed-awaiting-proof | Only four raster MIME types inline, others attachment/nosniff/private; current negative-control execution pending. |
| AUD-371 | Документированный флаг EVENT_FILE_SCANNER_ALLOW_ON_UNAVAILABLE не читается, тесты зелёные на моке (`app/services/file_scanner.py:231-246`) | source-fixed-awaiting-proof | Scanner unavailable/breaker returns503 and retired flag removed; actual Settings/transport suite needs current receipt. |
| AUD-373 | Внутренние HTTP-вызовы backend без TLS несут токены и identity (`charts/university-ecosystem/templates/gateway-deployment.yaml:86-87`) | unfixed | Gateway backend identity/token transport remains HTTP. |
| AUD-375 | Replay очередей SW без CSRF-заголовка, без удаления при 403 и без взаимоисключения (`frontend/src/sw/offline.ts:279-291`) | partial | Legacy SW queues held without network/deletion; safe retention is not session-CSRF replay or cross-worker lifecycle completion. |
| AUD-378 | «SLSA Provenance Dry-Run» в `ci-success` проверяет только существование `ci.yml` (`ci.yml:864-898`) | unfixed | Provenance gate still checks verifier version and ci.yml existence, not artifact signature/provenance. |
| AUD-380 | `.semgrep.yml` заявляет запуск Semgrep в CI, но такого job нет (`.semgrep.yml:20-21`) | unfixed | Promised Semgrep scanner job remains absent; SARIF validator is not scanner execution. |
| AUD-381 | DAST, Scorecard и sqlmap не блокируют и не публикуют находки (`scorecard.yml:77`) | partial | Nuclei/Scorecard lack finding thresholds; SQLMap result/threshold and ZAP SARIF provenance incomplete. |
| AUD-382 | `mfa-key-overlap.sh`: пароль пишется в файл до `chmod 600` и не удаляется (`.github/deployment-smoke/mfa-key-overlap.sh:78-82`) | source-fixed-awaiting-proof | Private MFA temp/umask077/cleanup implemented; real Bash harness needs current executed receipt. |
| AUD-383 | `db-perf-gate` маскирует ошибки создания партиций через `\|\| echo WARN` (`.github/workflows/db-perf-gate.yml:74-107`) | source-fixed-awaiting-proof | Strict partition shell/psql ON_ERROR_STOP implemented; shell negative tests pending, query-capture integration separate. |
| AUD-384 | Slack-уведомление nightly не отправляется: `env` шага используется в его `if` (`.github/workflows/nightly-full-gate.yml:1066-1074.`) | unfixed | Slack if reads env declared only on same step. |
| AUD-385 | Legacy-проверки `backend-tests-*-dummy` становятся skipped (зелёными) при падении тестов (`ci.yml:2974-2988`) | source-fixed-awaiting-proof | Compatibility jobs always run and require successful producer; shell failure/cancelled/skipped controls need current execution. |
| AUD-386 | `vuln-gate` для push в main пропускается при падении report-job (`skipped`) (`sbom.yml:267-274`) | source-fixed-awaiting-proof | Main vulnerability gate requires all producers with bounded checksum-pinned OSV installer; source/shell proof is not privileged-main execution. |
| AUD-389 | pgvector-фолбэк в startup не перехватывает ошибки БД и не работает внутри прерванной транзакции (`app/core/lifespan.py:158-196`) | source-fixed-awaiting-proof | pgvector fallback uses savepoint/narrow SQLSTATE; current real-PG controls pending. |
| AUD-390 | Ответы новостей помечены `Cache-Control: public`, хотя содержат личное `is_liked` (`app/api/news.py:66`) | source-fixed-awaiting-proof | Personalized ETag/cache uses private,no-store and identity-aware keys; current miss/hit/304 receipt pending. |
| AUD-391 | Монитор воркера по умолчанию слушает `0.0.0.0` без аутентификации (`app/core/config/notifications.py:71-72`) | source-fixed-awaiting-proof | Worker metrics default127.0.0.1 and explicit override preserved; current test/socket proof pending. |
| AUD-392 | Проверка утёкших паролей (HIBP) выключена по умолчанию и не требуется в production (`app/core/config/mixins/mfa_settings.py:42`) | unfixed | HIBP remains disabled, length8/zxcvbn1; parser hardening does not repair production-policy defaults. |
| AUD-393 | Миграции глотают ошибки DDL и мутируют модульное состояние (`alembic/versions/202602010004_drop_legacy_columns.py:117-140`) | partial | Module-list mutation fixed; broad DDL exception-and-continue remains. |
| AUD-399 | Блок test в vite.config.mts и src/test/setup.ts никогда не загружаются (`frontend/vite.config.mts:513-527`) | unfixed | Dead Vite test/setupFiles differs from actual separate Vitest configuration. |
| AUD-400 | Правило workbox.runtimeCaching для API мёртвое и с неверным путём (`frontend/vite.config.mts:251-272`) | partial | Custom SW runtime-cache10 PASS, but dead injectManifest workbox rule and incorrect /api paths remain. |
| AUD-401 | VAPID-ключ стенда создаётся с umask-правами и только потом получает 0600 (`scripts/live_stand.py:683-688`) | source-fixed-awaiting-proof | VAPID opened O_EXCL/O_NOFOLLOW0600 before serialization; four controls need current execution. |
| AUD-406 | Сканер i18n исключает src/api/stories.ts, а английская ошибка попадает в UI (`frontend/scripts/i18n-scanner.mjs:127`) | confirmed-ready | Stories scanner inclusion/negative controls and four EN/RU typed-upload fallback cases PASS; scoped original criterion ready. |
| AUD-407 | Реестр mutation-исключений принимает будущие created_on и срок без предела (`scripts/quality/validate_quality_contract.py:662-676`) | source-fixed-awaiting-proof | Future/reversed/expired/>30day approvals rejected; 30positive/31negative controls need current receipt. |
| AUD-409 | Stop-гейт обещает тесты и type checker и пропускает отсутствующие каталоги (`.agents/hooks/stop_quality_gate.py:1-9, 55-59, 74-78, 134-138`) | source-fixed-awaiting-proof | Hook truthfully reports Ruff/TS/Go and rejects missing roots; actual boundary/reason proof pending. |
| AUD-414 | scrypt_derive принимает N=1, pbkdf2_derive принимает одну итерацию (`frontend/rust-crypto/src/lib.rs:27`) | unfixed | Rust PBKDF2 minimum1 and scrypt N=1 remain allowed. |
| AUD-416 | wasm-fuzzer завершается с кодом 0 без фаззинга и нигде не подключён (`frontend/scripts/wasm-fuzzer.mjs:14-26`) | unfixed | WASM fuzzer still exits0 without artifacts, uses tiny seeds and is not CI-selected. |
| AUD-417 | Chaos-оркестратор не откатывает фаулт при сбоях и утверждает нулевую потерю данных (`scripts/chaos/run_chaos_loadtest.py:206-258`) | source-fixed-awaiting-proof | Chaos finally cleanup uses confirmed UID/preconditions; uncertain creates/manual and data-loss NOT VERIFIED remain explicit; contract execution pending. |
| AUD-420 | Rescue bundle и archive-inventory из INDEX.md и MVP-плана на диске отсутствуют (`docs/audits/INDEX.md:111-121, 139-143`) | partial | Rescue location is honestly historical/unverified; GitHub-only review cannot prove owner-controlled private artifact possession. |
| AUD-422 | CONFIGURATION.md покрывает 95 из 290 полей Settings; часть переменных мимо Settings (`CONFIGURATION.md:89-90`) | partial | Selected configuration docs match runtime, but exhaustive Settings/env inventory remains absent. |
| AUD-423 | Числа, пути и значения по умолчанию в README/SECURITY/DEPLOY/AGENTS расходятся с кодом (`README.md:228, README.ru.md:226`) | partial | API docs/metrics paths repaired; exhaustive README/SECURITY/DEPLOY/AGENTS consistency not established. |
| AUD-425 | STATUS.md утверждает согласованность 82 Markdown и даёт checkpoint, отстающий от HEAD (`docs/superpowers/plans/STATUS.md:131, 24`) | partial | Current386 list is coherent; fresh full136/126 reconciliation is this document, not inherited historical link-check proof. |
| AUD-426 | MFA-тесты гонки заменяют DB-атомарность на asyncio.Lock (`tests/security/test_mfa_race.py:21-34`) | unfixed | MFA race tests still model DB atomicity using asyncio.Lock and sleeps instead of real PG contention. |
| AUD-427 | Контрактные тесты Redis-ключей и WS-кадров проверяют собственные словари (`tests/contracts/test_redis_key_contracts.py:26-56`) | source-fixed-awaiting-proof | Real Redis ticket/session producers/consumers via fakeredis replace self-dictionaries; current Redis execution pending, Pact wire proof separate. |
| AUD-428 | Около 140 Python, 17 Go и ~30 TS-блоков тестов без проверок результата (`Python`) | partial | Selected weak assertions improved, but complete original Python/Go/TS census and negative-control proof missing. |
| AUD-429 | E2E realtime-набор и визуальные тесты в CI не выполняются (`frontend/tests/e2e/chat-realtime.spec.ts:21, 24`) | partial | Ordinary realtime guard unset in nightly; visual-audit remains manual-only. |
| AUD-432 | E2E-live contract-тесты проверяют текст spec-файлов регулярками (`frontend/tests/e2e-live/auth-login-lockout.contract.test.mjs:15-60`) | partial | Executable helper negatives improve some live contracts; many still regex-only, current reviewed-head stand did not run. |
| AUD-433 | Промежуточное состояние свежей цепочки: notifications без партиций, записи падают до `202607020001` (`alembic/versions/148642dd1207_fix_missing_tables.py:~818-838`) | unfixed | Notifications partitioned without child; positive default-child fixture is not source remedy. |
| AUD-434 | `alembic check` не сравнивает server default; `push_subscriptions.topics` расходится с моделью (`alembic/env.py:170-180`) | unfixed | compare_server_default absent; Python defaults are not server-default proof. |
| AUD-436 | live_stand: whoami ищется через PATH, в Git Bash получается GNU-утилита (уточнено) (`scripts/live_stand.py:414–433 _windows_user_sid`) | source-fixed-awaiting-proof | Windows helper resolves whoami/icacls under SystemRoot/System32; actual Windows/Git Bash receipt missing. |
| AUD-438 | /metrics ws-hub доступен без аутентификации, в отличие от backend и gateway (`services/ws-hub/main.go:485`) | unfixed | WS-hub /metrics remains without auth wrapper. |
| AUD-447 | Токен сброса пароля хранится открытым текстом в dead_letter_jobs (`app/services/auth_service.py:166-176`) | partial | Reached valid retained auth payloads are protected during dedup/replay; dormant or malformed legacy rows and historical errors remain unremediated. Admin projection alone is not storage cleanup. |
| AUD-449 | OAuth-код Spotify попадает в access-логи Caddy и gunicorn (`services/caddy/Caddyfile:195-201`) | source-fixed-awaiting-proof | Literal/encoded OAuth code filters and disabled backend access logs exist; exact Spotify-code negative receipt missing. |
| AUD-450 | RLS-политика тенанта снимается обычным GUC app.bypass_rls (латентно) (`alembic/versions/202607230001_multi_tenant_rls.py:156-163`) | unfixed | Caller-controlled app.bypass_rls=on still bypasses restricted-role policy. |
| AUD-454 | Гонка кэша участников чата: удалённый участник получает кадры до 1 часа (`app/api/ws/connection_manager.py:283-338`) | partial | Next-broadcast roster uses DB, but in-flight old roster/live hub boundary not covered by current controls. |
| AUD-455 | Повторный запуск nightly Stryker падает на дублях evidence из кэша (`.github/workflows/nightly-full-gate.yml:213-219, 232-237, 333-338`) | unfixed | Cached shard republished under new attempt retains old producerAttempt; aggregate rejects duplicate attempt. |
| AUD-456 | Тест LHCI-пути CSRF проходит по MODE=test и не проверяет LHCI (`frontend/src/api/__tests__/client.closure.test.ts:72-81`) | unfixed | LHCI test sets VITE_LHCI but stays MODE=test; separate production-CSRF tests do not cover branch. |
| AUD-462 | Ключ членства держится через сетевую запись и вызовы бэкенда | source-fixed-awaiting-proof | Authorization/socket I/O moved outside membership lock with permits; current Go proof pending, cancellation race separately open. |
| AUD-463 | Отключение пользователя закрывает сокеты последовательно под writeMu | source-fixed-awaiting-proof | Hub snapshot unlocks before bounded parallel disconnect; current shutdown/multiconnection proof pending. |
| AUD-474 | Проверка «отказ CSRF не оставляет cookie» всегда истинна: cookie удаляется до чтения | source-fixed-awaiting-proof | Cookie observed before cleanup with status/profile guards; browser proof missing. |
| AUD-476 | Уведомления без to/room уходят всем; to=user_id никому не доходит | source-fixed-awaiting-proof | Notifications require matching recipient and fan out all user sessions; current Go routing execution pending. |
| AUD-477 | Oversize-сообщение с последовательностью тихо отбрасывается после ACK | unfixed | Queue admission ACK precedes oversize drop, so sequenced message can disappear without resync. |
| AUD-478 | Durable-настройки NATS не применяются, cache.invalidate переигрывает 7 дней | unfixed | Durable config unused; invalidation DeliverAll lacks durable identity. |
| AUD-479 | dependency-review: allow-ghsas для двух HIGH GHSA fast-uri без владельца и срока (подтверждает AUD-379; сейчас инертно) | source-fixed-awaiting-proof | allow-ghsas absent and real YAML-negative fixtures exist; action SUCCESS does not prove dedicated negatives executed. |
| AUD-480 | PR-гейты не покрывают medium/low npm, dev-зависимости и unfixed (Trivy FS) | unfixed | npm audit filters high/critical; medium/low omission remains. |
| AUD-482 | Caddy-образ: Go-зависимости разрешаются при сборке, lock в репозитории отсутствует, вне govulncheck и osv | partial | Selected xcaddy overrides/inventory producer do not supply complete locked final-binary graph or runtime scanner evidence. |
| AUD-483 | osv-scanner (Go) запускается только на main: 75 открытых алертов (12 ID); stdlib-находки основаны на директиве `go 1.26.4` | partial | Go SBOM remains main-only; PR reachable-symbol scan is separate, current complete alert reconciliation missing. |
| AUD-484 | Устаревшие открытые алерты (code-scanning и Dependabot) не отражают текущие lock-файлы | not-verified | Enabled plugin does not expose remote security-alert inventory; scanner success does not enumerate remote alerts. |
| AUD-485 | govulncheck молча пропускает модули при сбое go list (`.github/workflows/reusable-security-audit.yml:517-528`) | source-fixed-awaiting-proof | Module/package discovery now fail closed; actual empty/space/discovery shell controls need current proof. |
| AUD-486 | LHCI-фолбэк принимает упавший прогон и пустые метрики как успешный (`frontend/scripts/lhci-windows-fallback.mjs:270-281`) | confirmed-ready | Complete finite LHCI report/cleanup classifier and four focused controls PASS; six Windows-only cases SKIP, no native-Windows certification. |
| AUD-487 | Проверка cross-repository в security-policy никогда не срабатывает (`.github/workflows/reusable-security-audit.yml:55, 63-66`) | source-fixed-awaiting-proof | Policy fetch verifies actual head/base repositories; dedicated same/fork/malformed negatives need current execution. |
| AUD-489 | Мёртвая копия подписи аудита и тест, который проверяет её, а не прод (`app/utils/audit.py:11-51`) | unfixed | Dead audit-signature copy and mirror tests remain distinct from production AuditService. |
| AUD-490 | IDEMPOTENCY_HMAC_SECRET не требуется в production вопреки комментарию (`app/core/config/integrations.py:42-43, 68-138`) | unfixed | IDEMPOTENCY_HMAC_SECRET remains optional/empty in production validation. |
| AUD-495 | cached() отбрасывает первый аргумент-объект и даёт общий ключ (латентно) (`app/deps/cache.py:689-692`) | source-fixed-awaiting-proof | cached includes all positional args; receiver/free/static/privacy regressions need current execution, not arbitrary __str__ collision guarantee. |
| AUD-500 | E2E-очистка проглатывает ошибки удаления и маскирует первичный отказ (`frontend/tests/e2e-live/messenger-reconnect.live.spec.ts:397-405`) | confirmed-ready | Wired reconnect helper11 PASS preserves primary errors and fails cleanup-only with bounded deadline; no browser deletion claim. |
| AUD-501 | Тест паузы в скрытой вкладке не проверяет заморозку прогресса во время скрытия (`frontend/tests/e2e-live/story-viewer-keyboard.live.spec.ts:84, 90-100`) | source-fixed-awaiting-proof | Hidden-progress/live clock controls added; native contract PASS, actual desktop/mobile execution missing. |
| AUD-503 | Метки владения в инвентаре маршрутов расходятся с кодом (ICS, WebSocket /chat) (`scripts/check_route_dependency_inventory.py:187, 317-325`) | partial | ICS classification fixed, but all WEBSOCKET still worker_internal despite actual ASGI route/session. |
| AUD-506 | Temporal: ключи JWKS по HTTP и noop-авторизация принимают подменённые токены (`services/temporal/config.yaml:100-107`) | unfixed | Temporal HTTP JWKS and empty authorizer remain. |
| AUD-510 | Битая политика покрытия фронтенда молча заменяется эвристикой (`scripts/quality/validate_quality_contract.py:1275-1312`) | source-fixed-awaiting-proof | Frontend policy loader fails closed on invalid/duplicate/schema/unsafe globs; valid duplicate fixture repairs old test, current receipt pending. |
| AUD-512 | recover в NATS-колбэках не Term-ит сообщение: вечные повторы (`services/ws-hub/pkg/hub/hub.go:1153-1159`) | source-fixed-awaiting-proof | Callback panic TERMs, failedTERM NAKs5s; auth panic remains retryable and releases barrier. Current Go execution pending. |

## Complete changed-path manifest

Every postimage below was reviewed at the immutable source. Full-tree comparison
establishes completeness; no compare truncation or deletion is omitted.

| Path | Change | Reviewed Git blob |
| --- | --- | --- |
| `.github/deployment-smoke/mfa-key-overlap.sh` | modified | `65795d5eed7f7960365ac07f7ea1697d0e24d57b` |
| `.github/workflows/ci.yml` | modified | `83b85e522a1c45aa5101ff932022b6f5f9bb85cd` |
| `.github/workflows/db-perf-gate.yml` | modified | `2ad14b6d6d81bc7c4b56b3283f835024bec53dc5` |
| `.github/workflows/reusable-frontend-tests.yml` | modified | `f206db6203dc2ec6e25d3914571a388ea2c3b9d1` |
| `.github/workflows/sbom.yml` | modified | `af5d04d7d8a8ba4c88d8ca8ebfe280300ff80722` |
| `app/api/dlq.py` | modified | `1fb5d476968b3da38857aa9aa8698b239b9f394f` |
| `app/api/health.py` | modified | `bbc0d880fbc299e043d4262ae7016419511f2ca9` |
| `app/api/news.py` | modified | `ae49e1bc1804de8f01556fef22f0916ebf738db3` |
| `app/auth/security.py` | modified | `6681ce36edd6837df10f64acf7687a8d2a4f14ce` |
| `app/repositories/news_repository.py` | modified | `c076fbf2b5c950dbb003e81259458c36aa35fb04` |
| `app/schemas/news.py` | modified | `f626bb13608a8bc3283b12c5fd6ab8db2947e6d6` |
| `app/services/news_service.py` | modified | `3a3ca4b72d8f309e2f0beeedf5b0bcae6804c81c` |
| `app/services/partition_manager.py` | modified | `ff179699dfec64f640168923777b0aad4eda97ab` |
| `charts/university-ecosystem/templates/network-policy.yaml` | modified | `6f5a6e656a301e7daeff73f06dd5c4e98c6e8e5a` |
| `charts/university-ecosystem/values.yaml` | modified | `915469942d42240c7a3fdef168da7645ff4984e5` |
| `CONFIGURATION.md` | modified | `b6e927fa377fa19b7ff3afc9a4e0afa2799ef378` |
| `docker-compose.go.yml` | modified | `f10f8dded9552326b462634ed6438a259b2c86e8` |
| `docs/audits/AUDIT-2026-10.md` | modified | `01fcfc6050faa8a52d7a8facc594c6cca96b1bcb` |
| `docs/audits/INDEX.md` | modified | `986d58673466bca0bb59a42a14d5fc22ee4d3dcc` |
| `docs/DEPLOY.en.md` | modified | `3905c42f3f2b013ef0f8fe2d410cea2ca63da73b` |
| `docs/DEPLOY.md` | modified | `5aebdb5b93569ca6432d29dc0577f06aa1dcfb6c` |
| `docs/README.md` | modified | `5ff4581eb19c45aa184b5921da21b3501aabc2b2` |
| `docs/superpowers/plans/MVP_MASTER_PLAN.md` | modified | `e31378be3afefb0f872505895300a4dc18c8ee3e` |
| `docs/superpowers/plans/STATUS.md` | modified | `c8c1bd9ab72b65a5c2e6e41da6f645d2220e10b1` |
| `frontend/package-lock.json` | modified | `bca44c20963dee107dc81931380a79cddcf63c92` |
| `frontend/package.json` | modified | `d7d1dce98698637c4555feee4f36a7de27879027` |
| `frontend/public/theme-init.js` | modified | `91e0447f96ea2654bfa5e7a25994dcc09b7cc0a4` |
| `frontend/scripts/aud151-news-errors.test.mjs` | added | `bdb798cd53a73a19761762ad4e12d9695a78cd7c` |
| `frontend/scripts/check-bundle-budget.mjs` | modified | `efa7f420fe99ee7d9af7abc2285d490f92e6dc62` |
| `frontend/scripts/check-bundle-budget.test.mjs` | modified | `a5c260022832f67275aff48930a90dc7fd32086e` |
| `frontend/scripts/final-html-root-inventory.test.mjs` | modified | `7e1432d9ea096f8e440b5ff4228d6272a4e127b6` |
| `frontend/scripts/maplibre-build-metadata.mjs` | modified | `fc611bdb4bd35dea8b51139c7b97c28a307f1589` |
| `frontend/scripts/maplibre-build-metadata.test.mjs` | modified | `750bc531256fe32600853035cbc548d4cf2b8ca7` |
| `frontend/scripts/maplibre-graph-binding.mjs` | added | `dc9402aed3dd20d629df66d95b09c6d8faa78161` |
| `frontend/scripts/maplibre-graph-binding.test.mjs` | added | `b20a3f77bd359af81b847ca3557683b017eed9c9` |
| `frontend/src/api/__tests__/client.anonymous-interactions-cursor.audit.test.ts` | added | `bfe63ff0548160cf23bb2b1d38c82858e05460be` |
| `frontend/src/api/__tests__/client.rate-limit-boundary.audit.test.ts` | added | `a14e0c9b2b21950e404d7c7ba9c69fa4ea92b8c6` |
| `frontend/src/api/client.ts` | modified | `a28c82d148d629b8c0df477225029012f34854d8` |
| `frontend/src/components/layout/__tests__/MainLayout.ssr-i18n.audit.test.tsx` | added | `b4e652fb22d65513f0d70f1eaafe95c7ab1bd28c` |
| `frontend/src/components/news/NewsComments.tsx` | modified | `7dd2d06afc199a22c30a79503ca7257cfca757fd` |
| `frontend/src/hooks/__tests__/useChatWebSocket.aud334.test.tsx` | added | `a1c04fecaa70b8cffc4f8e643dcb58dfd6d5a2c3` |
| `frontend/src/hooks/features/__tests__/useMessengerController.clearRecovery.audit.test.tsx` | added | `27420130976278315b25f6def11273b56a037d00` |
| `frontend/src/hooks/features/__tests__/useMessengerController.clearRecoveryState.audit.test.ts` | added | `8aa6cc9fbdaaf3b16fbdf861ca24f79ab9918967` |
| `frontend/src/hooks/features/__tests__/useMessengerController.rollbackSends.audit.test.tsx` | added | `cefaf5fb8d2c820d4f3a949feed514684e78c464` |
| `frontend/src/hooks/messengerProjection.ts` | modified | `16586458b88926b8c95f0fbb9f940574bab57429` |
| `frontend/src/hooks/useNewsInteraction.ts` | modified | `babc8ae159fcc650bdbf0ab3c7bb9447bd038838` |
| `frontend/src/i18n/locales/en/news.json` | modified | `75dcd88f1e758d1a2056ec3d52461cc8b16909b5` |
| `frontend/src/i18n/locales/ru/news.json` | modified | `9899113d8686ca914792b29b7356a095751057da` |
| `frontend/src/pages/__tests__/NewsDetail.comments-retry.audit.test.tsx` | added | `8bd39c72ec86426443e9ca3e449411fd4e1dd6f2` |
| `frontend/src/pages/__tests__/StoriesAdmin.relative-time-locale.test.tsx` | added | `2d8cd28bd70ec17a9b89b553441a4aaf2384a628` |
| `frontend/src/pages/NewsDetail.tsx` | modified | `dc256babc0bf7e3953b395a4525b580599a90f00` |
| `frontend/src/pages/StoriesAdmin.tsx` | modified | `6a0a41282f107e57ce4ec9d734203e4d95dee4ee` |
| `frontend/src/sw/__tests__/audit375.lifecycle-hold.test.ts` | added | `9900a01729222819f296ad3287c155d20e22485b` |
| `frontend/src/tests/aud304DarkVariant.test.tsx` | added | `16fb7507d14993144abc0462568a37d38f346f68` |
| `frontend/src/tests/ssrThemePrepaintConflict.test.ts` | added | `540fa463d1abea48d20a82cc3f805938a1afc01a` |
| `frontend/tests/e2e-live/aud178-reset-referer-csp.live.spec.ts` | modified | `53b7fa87268f78f293174923508e960e103bee20` |
| `frontend/tests/e2e-live/register-double-submit-lifecycle.d.mts` | added | `c965b8843498101f9af849c27f2d42da89a602a7` |
| `frontend/tests/e2e-live/register-double-submit-lifecycle.mjs` | added | `85c748b96ba2228fb2b966a3eede370c6906f3b1` |
| `frontend/tests/e2e-live/register-double-submit.contract.test.mjs` | modified | `aae04ca3870c17949b321ee9c8730345d14bcacd` |
| `frontend/tests/e2e-live/register-double-submit.live.spec.ts` | modified | `9d983ff00268aad1760561319da90bc20f0b04ce` |
| `frontend/tests/e2e-live/ssr-common-locale.d.mts` | added | `04a3a42c3005104132db27ab176ef01b3c7432c8` |
| `frontend/tests/e2e-live/ssr-common-locale.mjs` | added | `fc9ca73bd18b69692c8c9fa5aff225ab3d90b1c9` |
| `frontend/tests/e2e-live/ssr-hydration-i18n.contract.test.mjs` | modified | `006c66fe8f8bc807a00560243804664e029a20e4` |
| `frontend/tests/e2e-live/ssr-hydration-i18n.live.spec.ts` | modified | `07419de7e6824cb2d3cc040e67fad2c7f7059544` |
| `frontend/tests/e2e-live/story-viewer-keyboard.contract.test.mjs` | modified | `a47bce7f46f8972bf66d5388d01ae2a7eebaad53` |
| `frontend/tests/e2e-live/story-viewer-keyboard.live.spec.ts` | modified | `a2ea99ff61fde6ffcd1cc36b8ef0fb1cca56fa7d` |
| `frontend/tests/e2e/aud151-news-errors.d.mts` | added | `8598d7bbcee56c777b225f4b83c27debda67f637` |
| `frontend/tests/e2e/aud151-news-errors.mjs` | added | `c8d8a3dc9ea13de6645df006f302721b4fa635c4` |
| `frontend/tests/e2e/news-create-admin.spec.ts` | modified | `ee705eec9b10ff35d98758f6b65d3afb3d1d7c83` |
| `native/rust_ext/src/lib.rs` | modified | `91143d6b9405e0134b44d05729a9c26f507bf50e` |
| `quality/ci-check-catalog.json` | modified | `df928c6a33c3334f3b27a7aca16bcc7e129b2d7a` |
| `README.md` | modified | `6f32101c901f160641537b94d0b5becb3bb76cb4` |
| `README.ru.md` | modified | `7640d3e9bb894d64e1f87cb81f8fbe247792061b` |
| `renovate.json` | modified | `eed1b79fcff29c731f38f2f7cbddc43c7b359c4f` |
| `scripts/db_explain_check.py` | modified | `755041c098af668b4c94f97c3da34d2aabbdda32` |
| `scripts/live_stand.py` | modified | `efd4e566ca7fed682af5ba1d3bd7b51e29f47fc0` |
| `scripts/owned_client_ip_acceptance.py` | modified | `ae7ad717238cabf410e2c81d49b70e36a0e8faed` |
| `scripts/owned_client_ip_probe.py` | modified | `ee4cc7fe802a756be3a6c4ecd1a3e25d7db93ee7` |
| `scripts/owned_client_ip_runtime.py` | added | `b7bca84d04db23982b7a870d63b00cf2e7a31244` |
| `scripts/quality/render_live_alembic_sql.py` | modified | `27febaf0f99c01e4ca45af448513d2aa4d58739b` |
| `services/file-processor/cmd/file-processor/coverage_closure_additional_test.go` | modified | `29cb6194b52718f9e6a94649eb868bf45378f4cf` |
| `services/file-processor/cmd/file-processor/main_coverage_test.go` | modified | `43bc043172235c70dc53ae7af0141d84f6b7a602` |
| `services/ws-hub/pkg/config/aud167_trusted_proxy_normalization_test.go` | added | `a7078958f42b984c09da595caf30b8ab462d2d15` |
| `services/ws-hub/pkg/config/config.go` | modified | `8925fdb79b560baaa6ff8da2093934095b60b79f` |
| `services/ws-hub/pkg/hub/aud334_existing_replay_membership_test.go` | added | `cdcf1dd232d1461ad67375c3db0d00984a397050` |
| `services/ws-hub/pkg/hub/aud334_inbound_limit_backpressure_test.go` | added | `38c671e85c82b843ee7bd915e132d8d16172a13f` |
| `services/ws-hub/pkg/hub/aud512_panic_delivery_test.go` | added | `acc5bd3a4ef4be8fa088a8585fc88d6b2e607e5f` |
| `services/ws-hub/pkg/hub/client.go` | modified | `8274489cea442327c1119bc2e0b4697eabd576c5` |
| `services/ws-hub/pkg/hub/hub.go` | modified | `afa491045b08b745d6397fbbc3ec4c1551291ec8` |
| `tests/contracts/test_ci_release_capacity_contract.py` | modified | `13bd324cd71b3f1f3dfcf69068b28c2ae63efc73` |
| `tests/integration/test_aud363_454_borrowed_session_postgres.py` | modified | `89a97fdc88ab084fd53361e82f15a4cefbc9a2b7` |
| `tests/integration/test_redis_contract.py` | modified | `232667aaf2357a5be5da0009b62d6263d6da33d0` |
| `tests/test_alembic_live_sql_render.py` | modified | `f8f6bcdee01ad9db65d9315cfa6d89c23e8c4a75` |
| `tests/test_aud_dbperf_current_capture.py` | added | `1bfe1ebc40572323d89651cfec032755cbb463d4` |
| `tests/test_aud_dbperf_current_logs.py` | added | `d6e5bfd5469f7b3d32d98500bc5be4bc45a0e7df` |
| `tests/test_aud_dbperf_current_workers.py` | added | `ed89dfccbeb103872fb6bbb4d8a55c141fd4e0fd` |
| `tests/test_aud_health_current_cache.py` | added | `536609349c8c0ece3ef4d8780a00c00e987157ca` |
| `tests/test_aud_health_current_memory.py` | added | `b092ff4ccae4ca3dbaa2cf797ce2b327fbcc4bc6` |
| `tests/test_aud030_news_current.py` | added | `8cfe7c27719e42a832ae8ec43761e1b8ae41d1ff` |
| `tests/test_aud043_cache_current.py` | added | `33462fa81a55a0683373cc64be3b1e929d262a29` |
| `tests/test_aud045_partition_guard.py` | added | `ede7c166cff13c665edc55e77714243585fbe009` |
| `tests/test_aud045_partition_pruner_postgres.py` | added | `8f81d05b0dc47a0e22a37e77e141756e84112f51` |
| `tests/test_aud164_backend_trusted_peer_stack.py` | added | `d15980f324aa49762837aebe71388c11014f19d8` |
| `tests/test_aud164_owned_client_ip_probe_topology.py` | added | `f691a84a5f1a61f9824c977e6ec2d267e973dbdb` |
| `tests/test_aud167_compose_ws_hub_trust.py` | added | `1aef5c732e13f384d783f55f1a8968d2ed5a4cb4` |
| `tests/test_aud169_188_189_networkpolicy_topology.py` | modified | `c351043b049a91b8bf6995d304790244f608dcea` |
| `tests/test_aud189_networkpolicy_exclusion_guard.py` | added | `6164afbbc4f915202da49e930c05e57d83de4c86` |
| `tests/test_aud192_compose_network_topology.py` | modified | `9470f69babcf81716bc4b3eb3caac05b84e63df2` |
| `tests/test_aud250_redis_metrics_networkpolicy.py` | modified | `ed4ba0e44f971bb644ede7548d590f97538d479a` |
| `tests/test_aud363_asgi_revalidation.py` | added | `a5627af899aea0baee661c7df90c4e2fcdf5158c` |
| `tests/test_aud382_mfa_smoke_private_files.py` | added | `87c191e610e128e1ab87090c81331445b9710061` |
| `tests/test_aud383_db_partition_gate.py` | added | `213fa3cb7fe35c94cca0a12d6c1cb3bd6b43bbf3` |
| `tests/test_aud385_386_ci_fail_closed.py` | added | `b0cc352ea8963e562a8b828173e21b2357fc3393` |
| `tests/test_aud386_osv_release_installer.py` | added | `927c98226698a6ee139403844cc0d2318facbb26` |
| `tests/test_aud392_hibp_wire_contract.py` | added | `cc9c75d0fe0cfbb436ba5f216bb6083814241046` |
| `tests/test_aud409_417_hook_chaos_contract.py` | added | `3d1005f3cea4c8d669bbee76729358e33e80bc6d` |
| `tests/test_aud427_428_contract_quality.py` | added | `ddea2f63c0a17028cef9b9ebe967bfe35cbcc79b` |
| `tests/test_aud447_dlq_admin_error_privacy.py` | added | `159ab60be0c2014d26cce69ceace20f95ff4834f` |
| `tests/test_auth_concurrency_extra.py` | modified | `cbe0f72310062d847c4fff4b5f15a093baacf619` |
| `tests/test_auth_security_extra_coverage.py` | modified | `1b1b583b9d42189e06d01b7c39d993e7c216fb49` |
| `tests/test_bundle_analysis_dependency_contract.py` | added | `e28ee909a9e30ae6fbe3c5d70eafdfaa7340607b` |
| `tests/test_dependency_update_automation_contract.py` | modified | `a4492dace6d8dee4264feab5ea1d4c2c114c53db` |
| `tests/test_historical148_squawk_policy.py` | modified | `c73ef21bb130a8f69beec2b8deed4b5e8ef66a01` |
| `tests/test_migration_148642dd1207_squawk_json_ci.py` | modified | `be0db760c4392b498c70f01588943264aef5a1f8` |
| `tests/test_owned_client_ip_acceptance_v2.py` | added | `12d2dd696b8d5504a7822828bf2a58077612c0dc` |
| `tests/test_owned_client_ip_acceptance.py` | modified | `3af99666643810d829f26dc8edc40ed79da6c49b` |
| `tests/test_owned_client_ip_probe_transport.py` | modified | `4446b933c967d2c2bd02cb5928a6878376fc1680` |
| `tests/test_owned_client_ip_probe.py` | modified | `1faa727973a29bd3ecb216bdef9d616665064744` |
| `tests/test_owned_client_ip_runtime_topology.py` | added | `02523de1b3c9accf8020d2eb015b4bd4cb1d4ebc` |
| `tests/test_partition_manager_closure.py` | modified | `65429fb6d604cc6b467cab8d016b8e5544f6b4f8` |
| `tests/test_partition_manager.py` | modified | `b41957113f5d30933b338e486ebe8dee71e24101` |
| `tests/test_quality_workflow_contract.py` | modified | `e1d7ea24e8af75fedf1a56ab7aa3bf0805aaffd5` |
| `tests/test_services_extra.py` | modified | `0f7c3bb82180e1aaba663171ffd8f7f2d4d76835` |
| `tests/test_squawk_shell_propagation_contract.py` | added | `9ed89095a77a80eed52f4030af7f33dcc4f577eb` |
| `tests/test_vapid_private_file_aud401.py` | added | `404c781710907e3b7d031c39f1bc810ec3761dbc` |
| `tests/test_verify_secrets_baseline.py` | modified | `110b1080dc452334b712fbf3b1e844cba65c8f4e` |

## Проверка 4b83ddc7 и восстановление строгой проверки Ruff

Source: [4b83ddc75b7c0842c38350351330e19dd2a634c2](https://github.com/egorribun/university_ecosystem/commit/4b83ddc75b7c0842c38350351330e19dd2a634c2).
Проверенный merge commit — `2080de7b4995ccea3549863091babab10462ccf7`; оба
имеют tree `7e5cd43d198b410a5363a2f71f2dc5a4948ee938`. Все 23 workflow
завершены: 20 success, 1 failure, 2 skipped; отмен и активных запусков нет.
Это не полный GREEN и не новая приёмка: реестр остаётся **392/512**, открыты 120.

- [Matrix 40996751214](https://github.com/egorribun/university_ecosystem/actions/runs/40996751214):
  21 success / 9 failure / 30 skipped. Backend shards, PostgreSQL integration,
  Alembic и Matrix Go race не исполнялись после fast-lint failure.
- Frontend: 10 466 PASS в 835 файлах; aggregate проверил provenance четырёх
  shards и 2 297 изменённых строк, 0 missing, 100% differential coverage.
  Production build и 142 focused bundle checks PASS. Реальный analyzer больше
  не отклоняет HTML producer pair; остаётся один MapLibre chunk 285.83 KiB при
  действующем лимите 280 KiB. Лимит 286 KiB ещё не активирован.
- [Owned Core 40996750786](https://github.com/egorribun/university_ecosystem/actions/runs/40996750786):
  338 preflight PASS, 1 browser PASS, live 48 PASS / 2 SKIP; NATS outage и cleanup
  SUCCESS. Receipt artifact: `12952541787`. Это owned Core topology, не
  frozen-RC full-stack или production deployment proof.
- [Go Fuzzing 40996751231](https://github.com/egorribun/university_ecosystem/actions/runs/40996751231):
  новый AUD334 race-window regression явно PASS в обоих hub invocations.
  Это запуск без `-race`; пропущенная Matrix race-проверка им не заменяется.
- [DB Performance 40996751094](https://github.com/egorribun/university_ecosystem/actions/runs/40996751094):
  required SQL capture действительно включён; 212 repository tests PASS,
  232 unique SQL, 80 EXPLAIN checks PASS. Это healthy capture proof, а не
  выполнение всех новых отрицательных capture regressions.
- Contract: 3 589 PASS / 1 FAIL (старый renderer source pin); security 681 PASS,
  scoped 41 PASS. Новые Squawk shell20, Redis launcher32 и полный Python
  regression cohort на этом source не исполнялись.

### Исправление пропуска policy review

Независимая повторная проверка обнаружила два новых `noqa: S603` в
`scripts/quality/run_owned_redis_contracts.py`, опубликованных без требуемого
отдельного owner grant. Это конкретный пропуск первоначального implementation
review. Прежнее разрешение ADR-047 для coverage worker на них не распространяется.

В этом consistency-пакете оба неподтверждённых S603 комментария удалены без
изменения runtime-логики. Новый предложенный S104 комментарий не публикуется.
Ожидается строгий Ruff RED на двух subprocess sites и сравнении Docker HostIp;
это прогноз для нового source, а не уже выполненная проверка. Запрос на ровно
три source-bound annotations остаётся открытым. Ни молчаливого расширения
исключения, ни маскирования литерала, ни изменения Ruff configuration нет.

Повторно проверены annotation additions полного post-pause compare и полные
тексты восьми файлов, чьи patches GitHub не вернул. Других новых suppressions
не обнаружено. Директива NewsComments `jsx-a11y/no-autofocus` уже существовала
в том же компоненте на исходном checkpoint; она не является новой находкой.

Два тестовых файла приведены к точным hosted Ruff/Prettier postimages.
В `.secrets.baseline` изменены только два номера строк chart metadata
(572 → 573, 573 → 574) и время генерации; все 319 identities, статусы и настройки
сохранены. Это не разрешение новых scanner findings: собственный hook 4b83
сообщил 62 unmatched path/type/hash identities. Полный metadata-only triage
сопоставлен с публичными техническими fingerprints, но policy 405 не изменена
и новое разрешение на эти identities не получено.

Следующие независимые шаги: завершить source-bound Map286 contract и тесты в
ранее согласованных границах; после отдельного решения по Ruff проверить новый
source полностью, получить actual Alembic capture и только затем согласовать
окончательный finite hash delta. Ни старые GREEN, ни этот snapshot не заменяют
проверки следующего SHA.
