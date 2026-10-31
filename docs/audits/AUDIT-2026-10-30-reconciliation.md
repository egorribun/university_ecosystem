# Post-pause reconciliation — 2026-10-30

## Current 71-finding reconciliation — 2026-10-31

The [latest original-criterion decision](AUDIT-2026-10.md#scoped-five-finding-acceptance-and-aud-350-correction--2026-10-31)
changes **437 to 441 accepted / 71 open** by explicitly reopening **AUD-350**
and accepting **AUD-244/399/400/477/489**. The valid UTC receipt is retained,
not relabeled as proof against table rewrite/locking. All other accepted IDs
are preserved. This is a scoped registry correction, not a full-CI/release claim.

The [complete new review](AUDIT-2026-10-31-review.md) covers one commit and all
98 changed paths from adb5c91f to 112efb38, plus every one of the 75 IDs open at
that reviewed source. Its source tree equals the tested PR merge tree.
The matrix below is the exact remaining complement after the five acceptances
and one reopening: **18 S / 38 P / 12 U / 3 N = 71**.
S means source-fixed with applicable proof unestablished; P partial;
U original defect remaining; N not verified or original cause unproven.
Unchanged source dispositions are carried forward with their explicit limits,
not treated as fresh execution or inherited GREEN.

The 112 Matrix is terminal FAILURE: backend **22,662 PASS /27 FAIL /430 SKIP**,
frontend **10,647 PASS**, Matrix 91 jobs **60 success /15 failure /16 skipped**.
Owned Core is **46 PASS /2 FAIL /2 SKIP**. Required gates, baseline 315,
policy 494 and inactive Squawk admission are unchanged. AUD-311/490 remain S:
completed shard outcomes alone do not replace the skipped collected-universe
and selected-union verifier. New Nuclei/SW regressions remain separate,
unexecuted candidates until their own source run.

| ID | Class | Exact evidence boundary / remaining condition |
| --- | --- | --- |
| AUD-073 | S | Fresh 7 numerical/source tests pass; 101 gradient samples do not establish browser cascade/compositing contrast. |
| AUD-154 | S | Renderer markers repaired; actual realtime E2E locator/response chain unproved. |
| AUD-164 | P | Mandatory proxy configuration and Helm wiring retained; real two-client spoof-resistant limiter composition unproved. |
| AUD-167 | P | Trusted-proxy and rate-limit composition requires real topology proof. |
| AUD-169 | P | Declaration repairs retained; actual Secret URL, endpoints, DNAT and dependencies remain owner-proof hold. |
| AUD-178 | P | Fragment/referrer/redaction repairs retained; legacy URL CSP/Referer/emitted-log chain unproved. |
| AUD-188 | P | JWKS policy declarations improved; actual endpoint/refresh topology unproved. |
| AUD-189 | P | Tighter egress declarations retained; actual topology unproved. |
| AUD-208 | P | Raw warning gate remains strict; finite Squawk admission is prepared-inactive. |
| AUD-226 | P | Real-UTC expiry enforcement retained; finite 131-file exception and complete migration coverage remain. |
| AUD-231 | S | Helpers/stubs do not prove compiled SSR CSP/nonce composition and untrusted-script negatives. |
| AUD-245 | U | Global SPIRE Trivy suppressions still lack bounded path/expiry disposition. |
| AUD-251 | P | List/watch removed; cluster-wide nodes/proxy GET and live RBAC proof remain. |
| AUD-269 | S | Eight non-equivalent indexes preserved in source; applicable populated-chain proof unestablished. |
| AUD-270 | S | Source refuses instead of truncating; populated-chain proof unestablished. |
| AUD-272 | U | attempted_at/nullable uniqueness weakness remains. |
| AUD-274 | S | Parent preserves DND/timezone columns; three current preservation tests error before bodies on DuplicateColumn. |
| AUD-275 | P | Concurrent reply index added; interrupted/invalid-index recovery and users-index scope remain. |
| AUD-277 | N | Original USING(true) bypass cause was not established independently of restrictive policies; assess NULL/GUC separately. |
| AUD-278 | S | Events GIN restoration moved into upgrade; applicable PostgreSQL proof unestablished. |
| AUD-309 | U | Generic live-stand subprocess and POSIX/Windows lock waits remain unbounded. |
| AUD-311 | S | Filename Tier0 ownership rules added; four cases have only conditional cohort-pass inference because actual collection-union verification was skipped. |
| AUD-313 | U | Owned-stand environment/host checks and existing-admin password reconciliation remain. |
| AUD-321 | S | Conditional E2E handling repaired; affected fixtures/oracles unexecuted in reviewed evidence. |
| AUD-322 | P | Selected event CRUD proof does not establish active chaos execution. |
| AUD-327 | U | Legacy-role enum addition/use in one transaction remains; empty-chain success is insufficient. |
| AUD-332 | U | Windows symlink tests still lack native privilege probe. |
| AUD-334 | P | Named admission-refusal controls pass; blocked-writer and current/superseded replay composition remain. |
| AUD-346 | U | Nightly chaos dry-run does not execute recovery. |
| AUD-347 | S | MinIO source selection repaired; non-skipped ToxiProxy/MinIO execution unestablished. |
| AUD-348 | P | Backfill precedes DROP; existing empty destination rows may still exclude legacy Spotify values. |
| AUD-350 | P | Reopened: valid target-column UTC conversion proof retained, but direct ALTER remains and the original populated-table rewrite/locking criterion is not established. Single-call AST binding is not full-revision proof. |
| AUD-351 | S | Source handles incompatible queue IDs; authentic populated-row PostgreSQL preservation unproved. |
| AUD-360 | P | NULL rows hidden and INSERT triggers stamp tenants; all ordinary API producers remain unproved. |
| AUD-373 | U | Token-bearing backend HTTP hop remains unencrypted; Temporal JWKS HTTPS is another boundary. |
| AUD-375 | P | CSRF forwarding and genuine terminal 403 deletion repaired; cross-worker fallback and stale batch credentials remain. |
| AUD-378 | U | Version/ci.yml checks are not SLSA attestation verification. |
| AUD-380 | U | Promised Semgrep CI job remains absent. |
| AUD-381 | P | Scanner gates added, but Nuclei native-array parser and SQLMap completion/result retention are defective. |
| AUD-384 | S | Slack if now consumes step output; configured/unconfigured actual notification execution unproved. |
| AUD-392 | P | Nonlocal HIBP requirement repaired; original merged weak-password-default criterion remains. |
| AUD-393 | P | Specific DDL/module cleanup improved; complete historical behavior/proof remains incomplete. |
| AUD-414 | P | Scrypt floor raised; PBKDF2 permits one iteration. Approved RFC-vector scope unchanged. |
| AUD-416 | P | Fresh 9 fail-closed harness controls pass; actual selected fuzz campaign unproved. |
| AUD-420 | N | Private rescue inventory/location unverified; no private access authorized by this review. |
| AUD-422 | P | Additional settings documented; original timeout/poll/retention documentation remains incomplete. |
| AUD-423 | P | Baseline count and selected settings aligned; full cross-document consistency unproved. |
| AUD-426 | P | PostgreSQL work does not prove same-challenge HTTP step-up concurrency; old Lock shim remains. |
| AUD-428 | P | Individual tests improved; complete cross-language assertion census incomplete. |
| AUD-429 | P | Realtime environment selection and manual-only visual execution remain. |
| AUD-432 | P | Owned-core selected specs do not prove broader lockout/full-SSR/registration contracts. |
| AUD-433 | U | Fixture-created notification partitions do not repair historical migrations. |
| AUD-434 | P | Topics model/default inventory improved; compare_server_default remains absent. |
| AUD-436 | S | System32 whoami resolution repaired; native Windows execution unproved. |
| AUD-438 | P | Private metrics listener/lifecycle tests pass with 100% reported statement coverage; deployment isolation unproved. |
| AUD-447 | P | DLQ privacy tombstones improved; stale-overwrite races, historical errors and forged/escaped markers remain. |
| AUD-449 | S | Caddy filters repaired; actual production Caddy/Gunicorn emitted-log negatives unproved. |
| AUD-450 | S | Ordinary GUC bypass removed; applicable current ordinary-role negatives not established here. |
| AUD-454 | P | Fresh-DB fail-closed broadcast repair retained; borrowed-session/in-flight/live boundary remains. |
| AUD-455 | P | Cache-hit upload suppression avoids duplicates but cache-before-publication leaves failed-upload retries artifactless. |
| AUD-456 | U | LHCI MODE=test oracle remains nondiscriminating. |
| AUD-474 | S | Cookie observation reordered before cleanup; actual sequence/negative-reorder proof unestablished. |
| AUD-478 | P | Bounded revocation replay added; startup/shared-L2 admission barrier and retention>7 days remain. |
| AUD-480 | P | Dev dependency scan added; medium/low and ignore-unfixed/node_modules scope gaps remain. |
| AUD-482 | P | Caddy graph locked and built/scanned; govulncheck coverage and actual v3 advisory remain. |
| AUD-483 | P | Recursive read-only PR OSV inventory added; full applicable OSV/stdlib result validation unestablished. |
| AUD-484 | N | Current alert-specific remote security state not inspected; scan success is insufficient. |
| AUD-490 | S | Mandatory nonlocal idempotency secret retained; seven cases have only conditional cohort-pass inference because actual collection-union verification was skipped. |
| AUD-501 | S | Hidden-tab assertion/negative handler repaired; real hidden-clock/RAF execution unproved. |
| AUD-503 | P | ICS ownership corrected; WebSocket ownership still disagrees with actual consumers. |
| AUD-506 | P | Temporal HTTPS/default authorizer repaired; service-token producer still lacks required permissions. |

## Scoped progress after the 112-finding reconciliation

The following block is the historical 437-ID checkpoint; the current 441-ID decision and 71-ID complement are above.

The accepted lower bound is **437/512 (85.4%)**, with **75 IDs unaccepted**.
The [new original-criterion decision](AUDIT-2026-10.md#scoped-aud-151-and-aud-308-acceptance-on-source-c6a3d39b--2026-10-30)
adds only AUD-151 and AUD-308 using actual source-c6 Native execution, precise
immutable bindings and explicit proof limits. All 435 prior accepted IDs are
preserved. The complete historical 112-row review below remains anchored to
source 1cf; it is not relabeled as a fresh full-repository review.

The retained residual classification changes only by these two decisions:
**9 source-fixed/proof-pending, 29 partial, 34 original defects remaining,
2 unverified and 1 original asserted cause unproven =75 unaccepted IDs**.

| ID | Current disposition | Exact evidence / limit |
| --- | --- | --- |
| AUD-151 | accepted-scoped | Own c6 Native job 124188402770 executes the real readiness 2 / error 5 controls; listeners remain until hydration and actual route readiness, with failure cleanup. E2E consumes those helpers. EventEmitter/FakePage proof, not the unexecuted browser error-injection spec. |
| AUD-308 | accepted-scoped | Same blocking job executes architecture 18 / UI 1 / micromatch 13 / token 3, healthy selection plus 19 negative mutations, then actual standalone tokens:check (1017 definitions/646 references). Docker-stage modeling is not a Docker-build receipt; six unrelated Node skips remain skips. |
| AUD-334 | partial; not accepted | Own fc70 has 31 hook PASS, 3 real parser/provider/controller composition PASS and 2 Go loopback midstream/error-timeout cases PASS under race detection. A source-level controller cleanup seam still clears replay-rejection debt on transient disconnect; its real repeated-rejection/healthy-heartbeat cap regression has not yet executed. Generic wire errors have no exact request correlation. No cross-process/deployment proof. |
| AUD-447 | partial; not accepted | Existing malformed/duplicate/hash-mismatch rows retain plaintext. Source tracing shows that a repair followed by the existing protection exception would roll back before broker commit. Dormant/history and historical error text remain unprotected. Six bounded persisted SQLite regressions are staged in the accompanying tests-only commit; their hosted execution is pending. The lossless-storage design remains analysis, not production maintenance. |

The c6 Matrix is terminal FAILURE (71 success/4 failure/16 skipped,
no cancellation), despite 22,531 backend PASS / 428 SKIP / 0 FAIL. Coverage gates
are skipped. Its four failures are Alembic, frontend shard 2, frontend aggregate
and derived CI Success. The fc70 successor has its own terminal validation: all four backend shards
pass 22,531 tests with 428 skips and no failures; all four frontend shards
pass 10,518 tests. Alembic, Coverage & Quality Policy and derived CI Success
remain failed. The strict coverage normalizer reports 13 diagnostic failures;
Python changed-line coverage passes, but whole-component and Tier 0 floors
do not. These are not waived or equated with failed unit assertions. The [frontend aggregate](https://github.com/egorribun/university_ecosystem/actions/runs/41104111514/job/124237016644)
merges all four coverage reports and verifies 2457 changed lines at 100% line
coverage, with no assertion of 100% branch metrics. Neither that
receipt nor the scoped decisions establishes repository-wide quality/release
acceptance.
No policy inventory, waiver, retry cap, baseline or migration admission changes
are part of these decisions.

## Complete 112-finding reconciliation on source 1cf19a9b

This supersedes the *current-status interpretation* of earlier matrices, not
their historical record. Every one of the 112 IDs unaccepted at the 400-ID
checkpoint was re-read against its original criterion, current source,
test selection and actual own-source receipts. The original full 136-path
post-pause manifest below remains the historical 8787b00e review; it is not
relabeled as a new source-diff review.

The [criterion-specific decision](AUDIT-2026-10.md#scoped-35-finding-reconciliation-on-source-1cf19a9b-2026-10-30)
accepts exactly 35 IDs, preserving all 400 prior IDs:
**435/512 accepted; 77 remain unaccepted**. The full 112-ID partition is:

| Current classification | Count |
| --- | ---: |
| Accepted on bounded original criterion | 35 |
| Source-fixed, missing applicable execution proof | 10 |
| Partial | 30 |
| Original defect remains | 34 |
| Not verified | 2 |
| Original asserted cause unproven; separate related risks remain | 1 |
| **Total reviewed** | **112** |

The 35 additions are AUD-045, AUD-137, AUD-192, AUD-193, AUD-236, AUD-250, AUD-253, AUD-260, AUD-262, AUD-271, AUD-304, AUD-316, AUD-317, AUD-319, AUD-363, AUD-366, AUD-369, AUD-370, AUD-371, AUD-382, AUD-383, AUD-385, AUD-386, AUD-389, AUD-390, AUD-391, AUD-401, AUD-407, AUD-417, AUD-425, AUD-479, AUD-485, AUD-487, AUD-495, AUD-510.
No AUD-151/308, AUD-334, AUD-447 or Squawk activation is hidden in this count.

Source `1cf19a9b2e8f8f4e0b4d6bc91a309225c92cda13` and actual PR checkout
`c92fc01282e3f41dd9e2a60be6547fc087d95c28` share the complete tree
`3c42edbf6830f359059411c0310a07feef6613e8`.
Own Matrix 41069697810 is terminal FAILURE: backend 22,531 PASS /428 SKIP /0 FAIL,
frontend 10,492 PASS /3 FAIL /0 SKIP; coverage gates SKIP.
The linked decision contains full job URLs, named-vs-cohort inference rules,
116 immutable source/test bindings and per-finding limitations. Ordinary
Python PASS below is explicitly cohort-inferred, not a named-node receipt.
Current source-changing successors require their own validation.

| ID | Original criterion | Current classification | Exact disposition / remaining proof |
| --- | --- | --- | --- |
| AUD-045 | Pruner не распознаёт monthly names из исторической миграции | accepted-scoped | Historical YYYY_MM and runtime yYYYYmMM monthly partition names use the same retention calculation through the actual Rust/PyO3 consumer and Python caller. Rust job 124110243869: 97 PASS, four named aud045 historical-month controls; ordinary Python guard is cohort-inferred PASS. Limit: 13 owned-PG pruner cases SKIP. No destructive PostgreSQL pruning, Windows .pyd or deployment proof. |
| AUD-073 | Белый текст отправленных сообщений имеет недостаточный контраст на светлом violet gradient | source-fixed-awaiting-proof | Numerical stop/token controls 6 PASS (#7c3aed/#9333ea white ratios 5.699/5.382); complete interpolated/composited gradient and actual computed cascade remain unproved. Bounded browser fixture has not run. |
| AUD-137 | SSR-проверка сырых ключей не замечает обычный fallback i18next | accepted-scoped | Requested-locale validation rejects ordinary i18next fallback even when no raw qualified translation key remains; the live SSR spec consumes the same helpers. MainLayout SSR 6 PASS (124113373165), NewsHeader SSR 6 PASS (124113373285); Core helper bindings/negative controls PASS. Limit: Real renderToString/i18next and production matcher, not a completed full live hydration/browser run. |
| AUD-151 | Проверка JS-ошибок не ждёт готовности приложения | source-fixed-awaiting-proof | Readiness/error helper logic is source-fixed, but its 2+5 existing Node tests were absent from canonical hosted selection. Own 923 selection regression is now actual RED; no helper execution is inferred. |
| AUD-154 | Delivery test ждёт marker, которого нет в status renderer | source-fixed-awaiting-proof | Real Sent/Read ChatWindow markers pass within 63 tests; the modified realtime delivery locator/server-response chain remains behind REALTIME_E2E and has not run. |
| AUD-164 | Backend видит IP gateway: все анонимы делят лимиты login/register/MFA/reset | partial | Actual two-client trusted Caddy→gateway→backend identity/spoof composition not proved. Existing binder rejects Docker IpcMode=private while its synthetic fixture uses empty metadata. |
| AUD-167 | Rate-limit gateway и ws-hub сводится к одному IP прокси | partial | Actual proxy-peer/rate-limit two-client composition remains unproved; local header/source controls do not substitute for the full trusted chain. |
| AUD-169 | file-processor не стартует в staging/prod: revocation-Redis закрыт NetworkPolicy | partial | Helm egress/DNS/CIDR declarations repaired, but existing owner hold for actual Secret Redis URL/endpoints/DNAT/JWKS refresh remains; owned runtime harness not run. |
| AUD-178 | Токен сброса пароля попадает в access log (Referer) и в CSP-отчёты | partial | Fragment migration/new log-redaction controls pass; legacy query/path data in an early CSP document-uri before client migration remains unproved. Separate live harness is unselected. |
| AUD-188 | JWKS file-processor запрещён NetworkPolicy: через ~24 ч отклоняются все RS256-токены | partial | Ingress/egress source rules improved; actual deployment endpoints, DNAT/CIDRs and required service dependencies remain unverified under the existing owner hold. |
| AUD-189 | NetworkPolicy разрешает TCP/443 и DNS любому адресату, включая сервисы кластера | partial | DNS/CIDR and auth egress source repaired; actual endpoints/JWKS refresh/runtime topology remain unproved. Do not restate the original broad missing-rule claim. |
| AUD-192 | Postgres, Valkey, SpiceDB, Temporal и MinIO подключены к сети public вместе с frontend | accepted-scoped | Frontend no longer shares its network with the five storage services; unsafe namespace, link and host bypass variants are rejected while explicit local access remains. Own ordinary cohort PASS, including seven rendered Compose stacks and full/full-live. Docker/config-render helper did not skip. Limit: Declaration and actual Compose-render topology proof, not deployed network packets or host compromise resistance. |
| AUD-193 | Docker socket смонтирован в Alloy: `:ro` не ограничивает Docker API | accepted-scoped | Alloy no longer receives the Docker socket. Only the isolated unpublished proxy can access it; request allowlist and metadata projection are fail-closed. Gateway job 124112218630: named StreamingUnmodifiedCancellation, DockerMetadataProjectionRedaction, RequestAllowlistNegativeControls, AllowedContainerListValidatedPathQuery, StreamingTrailersDiscardedEOF PASS under go test -v -race; Compose controls cohort-inferred PASS. Limit: Owned loopback HTTP/stream/cancellation and transport doubles; no real Docker-daemon/Alloy/Loki deployment. Proxy package statement coverage is not universal branch coverage. |
| AUD-208 | Squawk-гейт проверяет пустой SQL для guard-миграций и ослаблен исключениями | partial | Finite 148 matcher remains prepared-inactive. All 11 current pins match, but tuple-merge graph rendering, all 141 other strict migrations, owned admission and actual consumer fail-closed controls remain absent. Raw 37 warnings still fail. |
| AUD-226 | Tier-0 миграции (`alembic/versions/**`) выпадают из требования 100% покрытия | partial | The 131-file unchanged migration coverage baseline is a bounded exception, not proof of 100% migration coverage or a complete merged report. |
| AUD-231 | SSR-страницы frontend отдаются без CSP, nonce-схема не работает | source-fixed-awaiting-proof | SSR entry nonce 14 PASS uses a TanStack double; HTTP5 CSP controls use stub SSR/static HTML. Actual compiled SSR→trusted-script/header nonce and untrusted-script negative composition remains missing. |
| AUD-236 | Вышедшая вкладка остаётся стейл-привязанной и отменяет публичные запросы | accepted-scoped | Stale signed-out tabs may perform fixed same-origin public News/Schedule reads without credentials or the private-session fence; private calls and account-isolated query keys remain guarded. Own frontend: anonymous News 10, Schedule 5, interaction 3, client 12, dashboard 3 and boundary 2 PASS (124113373068/165/273). Limit: Actual hooks/QueryClient/StorageEvent composition; HTTP/SDK/event delivery use doubles. Not real multi-tab browser/deployment proof. |
| AUD-244 | `zizmor.yml` отключает 15 аудитов, включая template-injection и dangerous-triggers | unfixed | Fifteen zizmor disables remain. |
| AUD-245 | Trivy-исключения KSV глобальные (без путей), срок пересмотра истёк | unfixed | Ten global SPIRE KSV suppressions lack bounded path/expiry disposition. |
| AUD-250 | Метрики кэш-Redis (9121) доступны любому pod; revocation-store это закрывает, app-chart нет | accepted-scoped | Redis metrics 9121 ingress is limited to the approved monitoring namespace/pods; Redis 6379 access remains separately bounded. Own cohort PASS: actual Helm rendering, all selecting-policy union, allowed monitoring and arbitrary-pod denial, widening negatives. Limit: Rendered policy, not live CNI packet enforcement. |
| AUD-251 | SPIRE agent получает кластерный nodes/proxy get/list/watch | unfixed | SPIRE node/proxy get/list/watch permissions remain broad. |
| AUD-253 | Лаунчер пишет .env.docker с секретами с umask по умолчанию на POSIX | accepted-scoped | The POSIX launcher creates private environment files at mode 0600 before the first secret byte, including permissive umask, collision and cleanup paths. Own cohort PASS with real pwsh and umask 000; missing pwsh would fail, not silently skip. Limit: POSIX file creation scope only; no Windows ACL assertion. |
| AUD-260 | Неограниченные выборки в скачивании вложений, посещаемости событий и приёме CWV | accepted-scoped | Attachment download filters identity before LIMIT2; legacy event traversal is bounded 100+1 and paginated reads use page+1; CWV retention performs ordered bounded 500 deletion. Own ordinary endpoint/service/SQLite cohort PASS for all three original surfaces. Limit: Separate PostgreSQL category-regex case SKIP. No claim that every optional database/filter test ran. |
| AUD-262 | Сбой Redis после commit даёт 500 при успешной отправке и дубликат при повторе | accepted-scoped | Keyed chat sends atomically commit message, event and durable receipt; expected post-commit Redis failures no longer turn committed sends into 500/duplicate retries. Replays reauthorize current membership and sender/chat scope. Own PG 124112218268: durable 5 named PASS (3.05s), lifecycle 27 and schema 12 named PASS; ordinary 7 cohort-inferred PASS. Actual PostgreSQL commits/new sessions, lost acknowledgements, lease-loss contention, receipt migration/FORCE RLS and uniqueness controls. Limit: Redis/completion failures are injected. Applies to current keyed writers and fixed 24h receipt lifetime, not historical cache-only/mixed-old writers, unkeyed requests, indefinite replay or external exactly-once delivery. |
| AUD-269 | Reconcile 202603280001 удаляет ~15 индексов горячих путей без восстановления | unfixed | Eight non-equivalent hot indexes remain lost; HNSW rename is excluded from that count. |
| AUD-270 | Cutover UUID делает TRUNCATE ... CASCADE дочерней таблицы вместо остановки | unfixed | TRUNCATE CASCADE applies to the dependent-table branch, not merely a partition-child cleanup. |
| AUD-271 | Копирование партиций не сбрасывает SERIAL-последовательности: дубли id | accepted-scoped | Partition migration resets each copied table's SERIAL sequence using pg_get_serial_sequence, MAX and setval so subsequent generated IDs do not collide. Own PG 124112218268: three named actual-upgrade controls PASS for copied positive IDs, empty tables and nonpositive legacy IDs, followed by real inserts. Limit: Scoped generated-ID correctness, not migration coverage-floor acceptance or every populated-database risk. |
| AUD-272 | UNIQUE «delivery once» включает attempted_at и не препятствует повторным пушам | unfixed | Uniqueness includes attempted_at/nullable values and the later reconciler preserves that weakness. |
| AUD-274 | Миграция 202511240001 теряет DND и часовой пояс пользователей | unfixed | DND/timezone columns are dropped before the later backfill. |
| AUD-275 | Индексы на messages и users строятся без CONCURRENTLY, docstring обещает обратное | partial | Blocking CREATE INDEX remains; removal of the false concurrent-build comment does not remove the locking risk. |
| AUD-277 | RLS с политикой USING(true) на восьми таблицах не изолирует данные | original-cause-unproven | Permissive TRUE combined with restrictive policy is not by itself the asserted bypass. Original cause unproven; separate NULL-tenant/GUC concerns remain under 360/450. |
| AUD-278 | GIN-индекс events.search_vector удалён и не восстановлен | unfixed | GIN restoration exists only in downgrade, not the upgrade path. |
| AUD-304 | Утилиты dark: следуют системной теме, а не выбору пользователя | accepted-scoped | Tailwind dark utilities follow the selected class theme rather than the OS preference; light/dark/system choices and later OS changes preserve that distinction. Own frontend 8 PASS (124113373068), native class-variant contract PASS; actual selector matching and theme context with SSR html-only control. Limit: No browser pixel/paint claim. |
| AUD-308 | Архитектурные и токен-гейты не запускаются в CI, два набора тестов мёртвые | partial | Boundary/token checks existed but two architecture suites and the full tokens:check command were omitted from the hosted Node gate. Own 923 now reproduces the omission; no closure before the corrected selection actually runs. |
| AUD-309 | live_stand.py: вызовы без таймаута и бесконечное ожидание блокировки | unfixed | Generic live-stand runner/git/npm/Chromium/Playwright/status subprocesses and POSIX/Windows lock acquisition remain unbounded. |
| AUD-311 | Tier-0 правила сопоставляют каталоги: security-модули по имени вне Tier 0 | unfixed | Tier0 directory mapping misses audit_service. |
| AUD-313 | Гейт owned-stand основан на переменных окружения; сид переписывает пароль администратора | unfixed | Live-seed ownership checks only environment/postgres host and still reconcile an existing admin password; stricter separate admin-smoke/demo preservation does not repair this route. |
| AUD-316 | .env.example: ключи без потребителя и нерабочий EVENT_FILE_SCANNER_ALLOW_ON_UNAVAILABLE | accepted-scoped | The example removes dead SPICEDB_HOST/PORT and SPICEDB_PG_SSLMODE inputs, uses SPICEDB_ENDPOINT, documents profiling's process-environment (not Settings dotenv) boundary, and removes the nonfunctional scanner allow-on-unavailable flag. Own ordinary cohort PASS: every original key, real Settings→SpiceDBClient endpoint, dotenv-only NoOp vs exported-env PyroscopeProfiler/address, both Compose env_file bindings, and fail-closed scanner consumer controls. Limit: No live SpiceDB/profiling/ClamAV network claim; scanner unavailability is injected at the client seam. |
| AUD-317 | Гейт MOD-30-01 слабее того, что описано в app/AGENTS.md | accepted-scoped | MOD-30-01 enforces SQLAlchemy relationship lazy="noload" or an explicit unique nonempty exemption, including statically recognized aliases, as required by app/AGENTS. Own cohort PASS:15 actual extracted Python subprocess controls, including malformed/alias/static-negative cases. Limit: Static AST contract, not arbitrary runtime metaprogramming analysis. |
| AUD-319 | Тест «тайминг-атак» проверяет только stdlib `secrets.compare_digest` | accepted-scoped | The timing-security regression now exercises the application's CSRFMiddleware signed POST path and rejects a forced HMAC comparison failure instead of only testing stdlib. Own ordinary cohort PASS: real ASGI middleware positive path and forced-false 403 control. Limit: Application-bound functional regression, not statistical constant-time proof or coverage of all compare_digest call sites. |
| AUD-321 | E2E: условные проверки с веткой-annotation делают тест зелёным | source-fixed-awaiting-proof | Unconditional 429/retry handling is repaired and Axios 2999/3000 boundary passes; the two E2E oracles/fixtures themselves are unexecuted. |
| AUD-322 | Интеграционные тесты событий и chaos молча пропускаются | partial | Actual event CRUD 6 PostgreSQL PASS; active chaos login/chat cases still skip. Five own chaos skips are not success. |
| AUD-327 | Upgrade через `148642dd1207` падает на legacy-БД с пользователями в верхнем регистре ролей | unfixed | Uppercase legacy enum values are added/used in one transaction; dedicated PostgreSQL case SKIP. Empty-chain success is not populated-upgrade proof. |
| AUD-332 | Тесты «when_supported» создают symlink без проверки привилегий | unfixed | Windows when_supported handling does not probe symlink privilege. |
| AUD-334 | Replay пропускается при rate limit или выключенном replay, пропуск не досылается | partial | Actual delayed generic rate-limit failures at 1051/5000ms and the bounded-recovery first cycle remain. Later cap/manual assertions are not reached. Invalid-token/network controls pass separately; new bounded recovery regression is not yet executed. |
| AUD-346 | Nightly chaos-loadtest всегда зелёный: dry-run отключает все проверки | unfixed | Nightly dry-run does not execute actual recovery. |
| AUD-347 | MinIO chaos-набор в nightly никогда не выполняется: заданы не те переменные | source-fixed-awaiting-proof | MinIO environment/selection fixed; actual non-skipped ToxiProxy/MinIO execution absent. |
| AUD-348 | Апгрейд 148642dd1207 удаляет Spotify-токены из users без переноса | partial | Backfill precedes DROP, but an existing empty destination row is excluded and can lose a legacy token. Dedicated PostgreSQL proof SKIP. |
| AUD-351 | 202603280001 падает на непустой notification_queue_jobs: integer record_id → UUID | unfixed | Integer record_id::text::uuid conversion remains. |
| AUD-360 | RLS: строки с tenant_id IS NULL видны всем тенантам, а приложение tenant_id не пишет (`alembic/versions/202607230001_multi_tenant_rls.py:153-161`) | unfixed | NULL tenant rows remain visible; News model/INSERT omit tenant_id. Dedicated PostgreSQL proof SKIP. |
| AUD-363 | WS /ws/chat не перепроверяет сессию после подключения (`app/api/websocket.py:201-256`) | accepted-scoped | Long-lived backend WebSocket activity rechecks the current session/MFA epoch instead of trusting only the connection-time authentication. Own ordinary cohort PASS: actual FastAPI WebSocket/manager and SQLite session/MFA changes, negative bypass controls; Redis/ticket boundaries doubled. Limit: Four owned PostgreSQL borrowed-session/RLS cases SKIP. No PostgreSQL tenant-isolation/pool or deployed revocation-latency claim. |
| AUD-366 | /healthz без аутентификации отдаёт версии миграций и параметры пула (`app/api/health.py:159-166`) | accepted-scoped | Anonymous health responses no longer expose pool/revision detail; cache hits, misses and preseeded detailed cache retain the redacted response and failure status. Own ordinary cohort PASS: six actual anonymous HTTP/cache/brief/liveness cases, dependency probes doubled and 503 retained. Limit: Response-surface proof, not production dependency availability. |
| AUD-369 | TLS к Temporal не включается без FP_TEMPORAL_API_KEY_FILE (`services/file-processor/cmd/file-processor/main.go:353-355, 357-390`) | accepted-scoped | Temporal TLS is configured independently of an API-key file; production/staging reject insecure transport while the explicit development path and API-key compatibility remain. Own file-processor Go job 124112218578: named TLSClientHello/development plaintext and environment controls PASS under -race. Real config→connectTemporal→SDK Dial→owned loopback peer inspects the first five bytes. Limit: TLS ClientHello proof, not completed certificate negotiation, Temporal server authorization or deployment. |
| AUD-370 | Приватные вложения отдаются inline с типом из конфигурируемого allowlist (`app/services/private_attachments.py:157-169`) | accepted-scoped | Private attachments inline only fixed JPEG/PNG/WebP/GIF types; other content is attachment with nosniff and private/no-store headers, with caller authorization/storage checks preserved. Own ordinary cohort PASS:10 actual ASGI header cases plus chat/event producer-consumer controls. Limit: No universal browser sniffing or unsafe-format rendering claim. |
| AUD-371 | Документированный флаг EVENT_FILE_SCANNER_ALLOW_ON_UNAVAILABLE не читается, тесты зелёные на моке (`app/services/file_scanner.py:231-246`) | accepted-scoped | Scanner unavailability fails closed through actual breaker/client/upload/chat consumer paths, without the retired permissive override. Own ordinary cohort PASS: real breaker and injected Clamd transport failure; bytes/upload/chat reject without saving. Limit: Transport failure seam, not a real deployed antivirus service. |
| AUD-373 | Внутренние HTTP-вызовы backend без TLS несут токены и identity (`charts/university-ecosystem/templates/gateway-deployment.yaml:86-87`) | unfixed | Backend token-bearing HTTP hop remains unencrypted. |
| AUD-375 | Replay очередей SW без CSRF-заголовка, без удаления при 403 и без взаимоисключения (`frontend/src/sw/offline.ts:279-291`) | partial | Legacy service-worker safe-hold controls pass, but CSRF/session replay 403 and cross-worker ownership remain unproved. |
| AUD-378 | «SLSA Provenance Dry-Run» в `ci-success` проверяет только существование `ci.yml` (`ci.yml:864-898`) | unfixed | Provenance verifier checks version/ci.yml only, not an attestation. |
| AUD-380 | `.semgrep.yml` заявляет запуск Semgrep в CI, но такого job нет (`.semgrep.yml:20-21`) | unfixed | Promised Semgrep job is absent. |
| AUD-381 | DAST, Scorecard и sqlmap не блокируют и не публикуют находки (`scorecard.yml:77`) | partial | Some SARIF producers exist; Nuclei/Scorecard thresholds and SQLMap artifact threshold remain absent, ZAP producer unproved. |
| AUD-382 | `mfa-key-overlap.sh`: пароль пишется в файл до `chmod 600` и не удаляется (`.github/deployment-smoke/mfa-key-overlap.sh:78-82`) | accepted-scoped | MFA smoke secret-bearing temporary files are private before first write and cleaned up across success, failure and signals without deleting foreign paths. Own ordinary cohort PASS with actual Bash and umask 000. Limit: curl/jq doubles; not live MFA verification. |
| AUD-383 | `db-perf-gate` маскирует ошибки создания партиций через `\|\| echo WARN` (`.github/workflows/db-perf-gate.yml:74-107`) | accepted-scoped | The database-performance partition validation gate preserves SQL/client failure before later diagnostic commands instead of masking exit status. Own ordinary cohort PASS: actual extracted Bash, four-table positive control and psqldouble SQL/client failures. Limit: Shell exit propagation, not database performance or live partition health. |
| AUD-384 | Slack-уведомление nightly не отправляется: `env` шага используется в его `if` (`.github/workflows/nightly-full-gate.yml:1066-1074.`) | unfixed | A step-level if refers to a value available only in that step's env. |
| AUD-385 | Legacy-проверки `backend-tests-*-dummy` становятся skipped (зелёными) при падении тестов (`ci.yml:2974-2988`) | accepted-scoped | Both legacy backend compatibility jobs run under always() and accept only successful backend-tests; failure, cancelled, skipped, missing and unexpected outcomes fail closed. Own ordinary cohort PASS: YAML binding and actual extracted Bash positive/negative states. Limit: Gate semantics, not a manufactured GitHub scheduler failure. |
| AUD-386 | `vuln-gate` для push в main пропускается при падении report-job (`skipped`) (`sbom.yml:267-274`) | accepted-scoped | The SBOM/security aggregate fails closed for eligible required jobs instead of accepting absent/failed results, preserving main/non-PR eligibility. Own ordinary cohort PASS: actual extracted Bash and source-bound eligibility controls. Limit: No privileged main workflow invocation claimed. |
| AUD-389 | pgvector-фолбэк в startup не перехватывает ошибки БД и не работает внутри прерванной транзакции (`app/core/lifespan.py:158-196`) | accepted-scoped | Optional pgvector startup handles only the expected extension errors inside a SAVEPOINT; search-enabled or unrelated missing-type failures remain fatal and the outer transaction remains usable where recovery is permitted. Own PG 124112218268: four named real-PostgreSQL cases PASS, including recovery, enabled-search failure, missing-type refusal and installed-extension positive control. Limit: The CREATE EXTENSION target is deliberately nonexistent in failure cases; transaction/savepoint/error are real. Not complete deployed startup proof. |
| AUD-390 | Ответы новостей помечены `Cache-Control: public`, хотя содержат личное `is_liked` (`app/api/news.py:66`) | accepted-scoped | User/tenant-personalized cached endpoints set private cache policy before lookup and keep identities separate across miss/hit/304/passthrough, preventing personalized News from public-cache treatment. Own ordinary cohort PASS: real Request/Response/MemoryCache with authenticated/idless/tenant cases; actual anonymous News HTTP and decorator/signature binding checked. Limit: Authenticated News producer-consumer binding plus direct decorator runtime, not an asserted authenticated News HTTP end-to-end receipt. |
| AUD-391 | Монитор воркера по умолчанию слушает `0.0.0.0` без аутентификации (`app/core/config/notifications.py:71-72`) | accepted-scoped | Notifications monitoring defaults to 127.0.0.1; explicit container binding remains deliberate and its host publication is loopback-only. Own ordinary cohort PASS: actual Settings→run_worker default/override composition and exact Compose host-publish controls. Limit: Monitoring starter is mocked; no actual listening-socket/deployment claim. |
| AUD-392 | Проверка утёкших паролей (HIBP) выключена по умолчанию и не требуется в production (`app/core/config/mixins/mfa_settings.py:42`) | unfixed | HIBP defaults off for registration/admin-create; reset/change checks are unconditional. Do not describe all password paths as disabled. |
| AUD-393 | Миграции глотают ошибки DDL и мутируют модульное состояние (`alembic/versions/202602010004_drop_legacy_columns.py:117-140`) | partial | Module mutation repaired; broad DDL exception-and-continue behavior remains. |
| AUD-399 | Блок test в vite.config.mts и src/test/setup.ts никогда не загружаются (`frontend/vite.config.mts:513-527`) | unfixed | Vite test setup is dead configuration differing from the actual Vitest setup. |
| AUD-400 | Правило workbox.runtimeCaching для API мёртвое и с неверным путём (`frontend/vite.config.mts:251-272`) | partial | Actual custom service-worker routing 10 PASS; dead injectManifest Workbox runtimeCaching configuration still declares the wrong /api policy. |
| AUD-401 | VAPID-ключ стенда создаётся с umask-правами и только потом получает 0600 (`scripts/live_stand.py:683-688`) | accepted-scoped | VAPID private-file creation uses exclusive/no-follow mode 0600 before the first write, with collision and serialization cleanup controls. Own ordinary cohort PASS: actual POSIX umask 0/fstat/empty-first-open/collision/close tests. Limit: Windows ACL behavior is only a seam, not native-Windows execution. |
| AUD-407 | Реестр mutation-исключений принимает будущие created_on и срок без предела (`scripts/quality/validate_quality_contract.py:662-676`) | accepted-scoped | Mutation exclusions reject future dates, expired entries and lifetimes beyond 30 days instead of treating them as valid. Own ordinary cohort PASS: five direct date-boundary controls against the production loader. Limit: No new exclusion or expiry extension. |
| AUD-414 | scrypt_derive принимает N=1, pbkdf2_derive принимает одну итерацию (`frontend/rust-crypto/src/lib.rs:27`) | unfixed | PBKDF2 low cost is an intentional RFC primitive vector; only actual app caller uses 100000/256. scrypt N=1 is accepted by primitive; actual caller uses 16384/r8/p1/dk32. No external weak-cost route found, primitive hardening remains open; do not silently change RFC vectors. |
| AUD-416 | wasm-fuzzer завершается с кодом 0 без фаззинга и нигде не подключён (`frontend/scripts/wasm-fuzzer.mjs:14-26`) | unfixed | Fuzzer may exit0 without artifacts; fixed tiny seeds/unselected execution do not establish the intended property. |
| AUD-417 | Chaos-оркестратор не откатывает фаулт при сбоях и утверждает нулевую потерю данных (`scripts/chaos/run_chaos_loadtest.py:206-258`) | accepted-scoped | Chaos orchestration always attempts UID-bound cleanup for known owned faults and reports cleanup failure; an unknown create outcome requires explicit manual recovery rather than a false cleanup/data-loss claim. Own ordinary cohort PASS:70 actual orchestrator/CLI/signal-callback controls. Limit: kubectl/API/HTTP/load use doubles; no live fault injection or data-loss acceptance. |
| AUD-420 | Rescue bundle и archive-inventory из INDEX.md и MVP-плана на диске отсутствуют (`docs/audits/INDEX.md:111-121, 139-143`) | not-verified | Private owner rescue-bundle location/inventory is unverified. No private access or restoration is authorized by this review. |
| AUD-422 | CONFIGURATION.md покрывает 95 из 290 полей Settings; часть переменных мимо Settings (`CONFIGURATION.md:89-90`) | partial | CONFIG remains explicitly nonexhaustive; SMTP_MFA_TOTAL_TIMEOUT_SECONDS, NOTIFICATIONS_SCHEDULER_POLL_SECONDS and NOTIFICATION_QUEUE_DEAD_LETTER_RETENTION_DAYS are undocumented. |
| AUD-423 | Числа, пути и значения по умолчанию в README/SECURITY/DEPLOY/AGENTS расходятся с кодом (`README.md:228, README.ru.md:226`) | partial | Selected documentation repairs exist; complete original multi-document semantic consistency remains unproved. No new mismatch is invented. |
| AUD-425 | STATUS.md утверждает согласованность 82 Markdown и даёт checkpoint, отстающий от HEAD (`docs/superpowers/plans/STATUS.md:131, 24`) | accepted-scoped | The current checkpoint replaces the false Markdown-link success claim with dated source-bound results and explicit unresolved gates; current authored relative links are checked. Own complete Python cohort includes test_current_authored_markdown_relative_links_resolve; no target skip/failure/xfail/quarantine. Current STATUS source reviewed. Limit: Cohort-inferred relative-link proof and truthful checkpoint only, not external links or correctness of every retained historical appendix. |
| AUD-426 | MFA-тесты гонки заменяют DB-атомарность на asyncio.Lock (`tests/security/test_mfa_race.py:21-34`) | partial | Real PostgreSQL MFA proof exists, but two distinct challenges/direct verify do not prove same-challenge consumption/HTTP step-up concurrency; old Lock shim remains. |
| AUD-428 | Около 140 Python, 17 Go и ~30 TS-блоков тестов без проверок результата (`Python`) | partial | Complete cross-language weak-assertion census remains incomplete. |
| AUD-429 | E2E realtime-набор и визуальные тесты в CI не выполняются (`frontend/tests/e2e/chat-realtime.spec.ts:21, 24`) | partial | Nightly realtime environment remains unset and visual checks are manual-only. |
| AUD-432 | E2E-live contract-тесты проверяют текст spec-файлов регулярками (`frontend/tests/e2e-live/auth-login-lockout.contract.test.mjs:15-60`) | partial | Owned Core actually ran 7 specs with 48 PASS/2 SKIP; broader lockout/full-SSR/registration suites remain unselected or checked only by source contracts. |
| AUD-433 | Промежуточное состояние свежей цепочки: notifications без партиций, записи падают до `202607020001` (`alembic/versions/148642dd1207_fix_missing_tables.py:~818-838`) | unfixed | Historical notifications partition parent has no child; a fixture-created default child is not the migration fix. Dedicated PostgreSQL case SKIP. |
| AUD-434 | `alembic check` не сравнивает server default; `push_subscriptions.topics` расходится с моделью (`alembic/env.py:170-180`) | unfixed | compare_server_default remains absent; topics Python default differs from SQL default. |
| AUD-436 | live_stand: whoami ищется через PATH, в Git Bash получается GNU-утилита (уточнено) (`scripts/live_stand.py:414–433 _windows_user_sid`) | source-fixed-awaiting-proof | System32 resolver source repaired; exact Windows-only case SKIP. ACL-byte tests mock the resolver and do not prove native path choice. |
| AUD-438 | /metrics ws-hub доступен без аутентификации, в отличие от backend и gateway (`services/ws-hub/main.go:485`) | unfixed | ws-hub metrics endpoint remains unauthenticated. |
| AUD-447 | Токен сброса пароля хранится открытым текстом в dead_letter_jobs (`app/services/auth_service.py:166-176`) | partial | New/reached valid payload protection is proved, but malformed/hash-mismatch/duplicate-key payload is deliberately retained as bad_bytes; dormant rows and historical error text are not cleaned. Actual PG dedup-lock PASS is not plaintext-removal proof. |
| AUD-449 | OAuth-код Spotify попадает в access-логи Caddy и gunicorn (`services/caddy/Caddyfile:195-201`) | source-fixed-awaiting-proof | Caddy filter source removes OAuth code, but Python regex emulation is not an actual emitted-log negative receipt. |
| AUD-450 | RLS-политика тенанта снимается обычным GUC app.bypass_rls (латентно) (`alembic/versions/202607230001_multi_tenant_rls.py:156-163`) | unfixed | Ordinary GUC bypass remains a latent database-boundary concern; dedicated PostgreSQL proof SKIP. No remote HTTP exploit is claimed. |
| AUD-454 | Гонка кэша участников чата: удалённый участник получает кадры до 1 часа (`app/api/ws/connection_manager.py:283-338`) | partial | Poisoned cache no longer authorizes the next broadcast: three ordinary controls pass via fresh DB lookup/fail-closed. Four borrowed-session PostgreSQL cases SKIP; in-flight/live boundary remains unproved. No surviving one-hour-cache bug is asserted. |
| AUD-455 | Повторный запуск nightly Stryker падает на дублях evidence из кэша (`.github/workflows/nightly-full-gate.yml:213-219, 232-237, 333-338`) | unfixed | Attempt-free Stryker cache can republish old evidence under a new attempt; aggregate rejects duplicate evidence. This is a source counterfactual, not an observed rerun. |
| AUD-456 | Тест LHCI-пути CSRF проходит по MODE=test и не проверяет LHCI (`frontend/src/api/__tests__/client.closure.test.ts:72-81`) | unfixed | LHCI branch is already before MODE=test, but its test is non-discriminating: deleting that branch still passes through MODE=test; production 25 controls do not set VITE_LHCI. |
| AUD-474 | Проверка «отказ CSRF не оставляет cookie» всегда истинна: cookie удаляется до чтения | source-fixed-awaiting-proof | Cookie observation now precedes cleanup in source; only regex contract passes, not execution of the sequence and negative reorder. |
| AUD-477 | Oversize-сообщение с последовательностью тихо отбрасывается после ACK | unfixed | NATS acknowledges enqueue before a later oversized-message drop without resynchronization. |
| AUD-478 | Durable-настройки NATS не применяются, cache.invalidate переигрывает 7 дней | unfixed | Durable configuration is stored but not used; cache-invalidation subscription remains DeliverAll without durable identity. |
| AUD-479 | dependency-review: allow-ghsas для двух HIGH GHSA fast-uri без владельца и срока (подтверждает AUD-379; сейчас инертно) | accepted-scoped | The global high-severity GHSA allowlist is removed; dependency-review preflight rejects its reintroduction even when inherited unchanged from the base. Own ordinary cohort PASS:11 allowlist/preflight controls bound before the dependency-review action. Limit: No new advisory waiver and no claim that every external vulnerability database is complete. |
| AUD-480 | PR-гейты не покрывают medium/low npm, dev-зависимости и unfixed (Trivy FS) | partial | Current npm audit includes dev dependencies; medium/low omission and Trivy ignore-unfixed/node_modules gaps remain. |
| AUD-482 | Caddy-образ: Go-зависимости разрешаются при сборке, lock в репозитории отсутствует, вне govulncheck и osv | partial | Caddy xcaddy full dependency graph remains unlocked and no complete final-binary scan is established; four overrides do not constitute the whole graph. |
| AUD-483 | osv-scanner (Go) запускается только на main: 75 открытых алертов (12 ID); stdlib-находки основаны на директиве `go 1.26.4` | partial | Main-only OSV gap remains; PR govulncheck/toolchain changes are partial. Historical 75/12 alert counts are not current observations. |
| AUD-484 | Устаревшие открытые алерты (code-scanning и Dependabot) не отражают текущие lock-файлы | not-verified | No permitted alert-specific GitHub endpoint is available to verify remote alert state; scanner success is not remote-alert closure. |
| AUD-485 | govulncheck молча пропускает модули при сбое go list (`.github/workflows/reusable-security-audit.yml:517-528`) | accepted-scoped | Go vulnerability audit rejects empty module discovery and preserves package-discovery/scanner failures, continuing other modules without masking the failed outcome. A successfully discovered module with no packages remains valid. Own ordinary cohort PASS:12 actual extracted Bash controls with go/govulncheck stubs. Limit: Execution/exit policy, not live vulnerability-database completeness. |
| AUD-487 | Проверка cross-repository в security-policy никогда не срабатывает (`.github/workflows/reusable-security-audit.yml:55, 63-66`) | accepted-scoped | Security branch-diff consumers validate exact same-repository head/base identity and syntax before fetching refs, rejecting foreign/missing/malformed scope. Own ordinary cohort PASS:56 actual Bash/git-stub controls across seven consumers. Limit: No privileged live fork run claimed. |
| AUD-489 | Мёртвая копия подписи аудита и тест, который проверяет её, а не прод (`app/utils/audit.py:11-51`) | partial | Dead signature helper and mirrored test remain disconnected from all 354 reviewed app Python callers. Independent production tests do exist; do not claim total absence of production signature tests. |
| AUD-490 | IDEMPOTENCY_HMAC_SECRET не требуется в production вопреки комментарию (`app/core/config/integrations.py:42-43, 68-138`) | unfixed | IDEMPOTENCY_HMAC_SECRET is optional/empty and falls back to unkeyed BLAKE2b; FILE support does not make it mandatory. |
| AUD-495 | cached() отбрасывает первый аргумент-объект и даёт общий ключ (латентно) (`app/deps/cache.py:689-692`) | accepted-scoped | Cached free/static functions retain the first business argument in cache keys while instance/class methods omit only their bound receiver. Own ordinary cohort PASS with real MemoryCache for instance/class/free/static functions and controlled logging failures. Limit: Not universal collision resistance for arbitrary object stringification. |
| AUD-501 | Тест паузы в скрытой вкладке не проверяет заморозку прогресса во время скрытия (`frontend/tests/e2e-live/story-viewer-keyboard.live.spec.ts:84, 90-100`) | source-fixed-awaiting-proof | Hidden-progress assertions and negative handler control are source-fixed; seven regex mutants pass, not actual hidden clock/RAF/oracle execution. |
| AUD-503 | Метки владения в инвентаре маршрутов расходятся с кодом (ICS, WebSocket /chat) (`scripts/check_route_dependency_inventory.py:187, 317-325`) | partial | All WEBSOCKET ownership still says worker_internal despite actual ASGI/chat/session consumers; ICS mapping was repaired. |
| AUD-506 | Temporal: ключи JWKS по HTTP и noop-авторизация принимают подменённые токены (`services/temporal/config.yaml:100-107`) | unfixed | Temporal HTTP/JWKS and empty-authorizer concerns are separate from accepted file-processor SDK transport TLS. |
| AUD-510 | Битая политика покрытия фронтенда молча заменяется эвристикой (`scripts/quality/validate_quality_contract.py:1275-1312`) | accepted-scoped | Malformed or missing coverage-source policy fails closed in both validator and normalizer instead of silently falling back to broad defaults. Own ordinary cohort PASS:102 malformed UTF-8/duplicate/missing/glob/tracked-source and producer-agreement controls. Limit: Synthetic metric/input controls; not merged-coverage success. All existing floors remain. |

### Squawk: current inactive-plan feasibility, not an admission

The read-only review covers all 142 migration full texts and their literal
revision graph:142 parsed revisions, one root/head, no missing parent or
duplicate revision, and 10 tuple-merge nodes. Existing metadata parser
`be2a19f8a918cfc6ae082c5ba83748f7c3829ba6` accepts only string/None parents,
so merge-aware parent-state rendering is a source-level blocker if those
nodes are reached, not 10 observed runtime failures.

All 11 source bindings in current policy
`f7179f7b8f0ac3e84b3af4a9ed3a2e92b569e923` match.
The compiled historical capture is 3d83fb27. The proposal blob
`dfd859c3fd7c7a8e13cf0bda5e68b8135c2af3d8` still labels 36f70a0f as current
at lines 295/352: a concrete documentation drift, recorded rather than silently
used as authority. The policy remains **prepared-inactive**, expiring
**2026-11-13T00:00:00Z**.

Own Alembic job 124112216254 checked only historical revision 148642dd1207
before raw 13+24 warnings failed; later upgrade/downgrade/single-head/drift
steps skipped. Current 323 historical-policy controls and the 41 renderer-lifecycle +
7 real-PostgreSQL controls prove existing bounded components, not
an activated adapter or all-other-migration success.

Remaining controls are graph-aware parent-state rendering (including merge
nodes), strict receipts for all 141 other migrations, fresh owned scratch
admission and expected post-state checks, source/run/file-ownership binding
in an actual consumer adapter, and real-shell negative cases for changed
warnings, expiry, nonhistorical migration errors and rejected admission.
No suppression, production database action, arbitrary historical rewrite,
new hash allowance or automatic activation is made by this review.

### Corrections to earlier partial descriptions

- AUD-316 covers every originally cited environment key, not only ClamAV:
  dead SpiceDB inputs are removed, SPICEDB_ENDPOINT has its real consumer,
  profiling's process-environment boundary and both Compose injections are
  tested. No live profiling/SpiceDB service is claimed.
- AUD-277's permissive TRUE policy combined with a restrictive policy is
  not by itself the asserted bypass; AUD-360/450 remain separate.
- AUD-454 no longer authorizes the next broadcast from poisoned cache;
  the remaining borrowed-session/in-flight boundary is not repaired by
  reasserting the obsolete hour-long-cache cause.
- AUD-392 affects registration/admin-create defaults, not unconditional
  reset/change checks. AUD-426 has real PostgreSQL evidence, but not the
  missing same-challenge/HTTP consumption case.
- AUD-480 currently includes npm dev dependencies. AUD-456's LHCI branch
  is already ordered before MODE=test; its test is still nondiscriminating.
- AUD-432's owned Core stand did run; only the broader unselected suites
  remain unproved. AUD-489 has independent production tests despite the
  dead mirrored utility test. Historical alert counts are not current
  observations of AUD-483/484.

### Follow-on execution gap, separate from acceptance

The tests-only successor 923dc6f adds no implementation change. Its actual
[Native/WASM job 124151502993](https://github.com/egorribun/university_ecosystem/actions/runs/41080879440/job/124151502993)
reproduces the missing canonical Node selection: one blocking stage instead
of two. The healthy control and all 19 negative variations pass; total 819 PASS /
1 FAIL /6 SKIP. A separate pinned Prettier diagnostic changes only quote
spelling of the same runtime string. The independently reviewed bounded recovery selects the five
already existing AUD-151/AUD-308 suites and the full tokens:check command,
without changing dependencies, lock graph, assertions or workflow gates.
Their own successful execution is still required before any additional
AUD-151/308 acceptance.

The separately reviewed three-file test/metadata package has explicit owner
publication permission: four baseline line moves/time only (all 319 identities
unchanged), gateway test-hook shutdown ownership, and one bounded WebSocket
recovery regression. Permission is not runtime PASS. AUD-334 production
behavior is unchanged and remains open.

## Retained historical reconciliation checkpoints

## Subsequent six-finding decision on bb2dea6c

The original complete 136-path manifest and 126-row classification below remain
the historical 8787b00e review, not a claim that those historical statuses are
current. A [later source-bound decision](AUDIT-2026-10.md#scoped-six-finding-acceptance-on-source-bb2dea6c-2026-10-30)
preserves all 394 accepted IDs and adds only AUD-030, AUD-310, AUD-409,
AUD-462, AUD-463 and AUD-476: **400 accepted / 112 unaccepted**.

- AUD-030's original four surfaces now have own-source UI/query evidence:
  comments 6+19, DLQ 15+31, chats 13+9 and the new real Map composition case
  1 PASS. The Map case reaches marker51 through the actual cursor hook/query,
  including pending, retention and exhaustion; SDK/canvas boundaries remain
  explicit. This supersedes only the historical open/proof-gap classification.
- AUD-310 and AUD-409 have 55 distinct named PASS receipts in the own-source
  Contract job. Malformed/empty/conflicting hook input fails closed; required
  absent/non-directory/empty roots are blocked. Stop truthfully describes
  its configured Ruff/TypeScript/Go-vet scope without removing the separate
  mandatory Python type-check and test obligations. Unknown names in valid
  tool envelopes are not silently reclassified as malformed payloads.
- AUD-462/463/476 have direct named `go test -v -race` receipts in the same
  source-equivalent ws-hub Unit job. The keyed membership mutex is released
  across external authorization/socket writes while revocation permits and
  fences remain; disconnect uses a bounded 16-worker close pool; personal
  notifications route to every exact-user session and never fall back to
  broadcast. Blocking Session/auth and direct NATS-input doubles are explicit;
  the two-session close case uses real loopback Gorilla WebSockets. No
  universal teardown deadline, deployed broker/browser delivery or unrelated
  gateway global-hook test-fixture repair is claimed.
- Actual checkout is PR merge `aabcbbca7166a0b676c4bc31eef041fb7b21f097`,
  source `bb2dea6c0afc135f39cc7cc4c92f24582fe754e5`; both whole trees are
  `b805d96a727efcb406b105fa7cc86123e0e4390f`. Finding-specific evidence is
  not transferred from a different tree or trusted-base policy job.
- AUD-334 remains open: the new raw invalid-resume-token/controller composition
  proof passes, but the three delayed generic-rate-limit/bounded-recovery
  failures remain. Their later cap/manual assertions are not reached.
  AUD-447 remains open because fail-closed delivery does not remove retained
  plaintext from malformed legacy PENDING rows. Neither is a new closure.
- Own frontend is 10,492 PASS / 3 FAIL / 0 SKIP; merged and changed-line
  coverage are skipped behind the failed-shard guard. No full-CI, backend,
  deployed infrastructure or release GREEN is inferred. Policy494,
  baseline319, Gitleaks26 and all existing gates are unchanged.

## Reviewed source recovery after the bd8 regression receipts

The [separate successor chain](https://github.com/egorribun/university_ecosystem/commit/f8971624264525b3dbd772fcc5b0b46820c9176a)
contains the formatter correction, opaque fixed-stage Map diagnostics, the
reviewed Chat ownership/pagination repair, an inactive 3d83 Squawk recapture
and the stale bundle-download contract repair: five code/evidence commits
across seventeen paths. The latter follows bd8's actual shard 2 failure and
requires the current exact artifact-ID/path/merge/digest dictionary without
changing any existing action pin, execution order or fail-closed assertion.
Its own runtime and coverage evidence is pending. No Map predicate or budget
is loosened by the diagnostic change, and no Squawk admission is activated.

Actual bd8 Map contracts pass 145/145 (all 29 negative variations and both
ceiling controls); the real artifact still fails the verifier after successful
ID/digest downloads. The next stage receipt must identify the cause. Its Chat
tests prove missing UI and a missing authoritative second-page refetch, not
the later account-race assertions that the absent UI prevented from running.
The new lifecycle/ownership tests still need their own GREEN.

The following 394-ID decision uses only completed 3d83 evidence. The original
136-path/126-row snapshot and all historical failures remain preserved below.

## Subsequent AUD-043/AUD-427 decision and current limits

The original 136-path manifest and 126-row matrix remain the historical
8787b00e review. The later [source-bound decision](AUDIT-2026-10.md#scoped-aud-043-and-aud-427-acceptance-on-source-3d83fb27-2026-10-30)
on 3d83fb27 preserves all 392 accepted IDs and adds only AUD-043 and AUD-427:
**394 accepted / 118 unaccepted**.

- The old AUD-043 partial classification is superseded only for its original
  stale-namespace criterion. The canonical news consumer and cold-generation/
  fresh-snapshot paths have 18+6+2 relevant cases supported by complete
  source-bound four-shard cohort inference, not named logs, live service or
  merged-coverage evidence. Authenticated events are not globally warmed.
- AUD-427 now has two named production ticket/revocation contract passes and
  actual WS emission consumed by the real frontend parser (seven accepted,
  four malformed rejected). Explicit transport doubles remain; AUD-428's
  broader weak-assertion census is still open.
- The previous unapproved annotation defect was corrected: the owner later
  approved exactly two local S603 and one S104 annotations. Own 3d83 Ruff
  check/import/format pass, backend actually ran, and all 12 exact scope
  controls are cohort-inferred PASS. No global exception was added.
- AUD-334 remains partial despite the fixed queued-writer delivery race:
  source tracing identifies a delayed generic-rate-limit recovery gap.
  Its prepared boundary/repetition tests still require their own runtime RED
  and bounded recovery proof. AUD-030 remains open beyond successful comments
  and direct-link/message controls.

Own 3d83 backend is 22,505 PASS / 428 SKIP / one old renderer-pin FAIL.
The full Matrix is terminal FAILURE (63 success / 12 failure / 16 skipped);
Coverage Policy and Codecov are skipped, not passed. Current scanner62 is a
finite technical-digest inventory, not a waiver: policy405/baseline319 remain
unchanged. Raw Squawk admission is still inactive.

The published successor bd8cfe9 contains the approved source-bound Map286
implementation, an isolated Map fixture and two chat lifecycle tests.
Its own [Actions](https://github.com/egorribun/university_ecosystem/actions/runs/41012528353)
must prove positive/negative controls and expose the remaining chat behavior.
The budget change is a declared six-KiB tradeoff, not an optimization or
proof of whole-application startup reachability. Historical review rows and
their earlier failure evidence are retained, not silently rewritten.

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
