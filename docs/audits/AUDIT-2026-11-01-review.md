# Post-pause source review and finding reconciliation — 2026-11-01

## Scope and completeness

Reviewed immutable range:
[06c08f9d…b72ca722](https://github.com/egorribun/university_ecosystem/compare/06c08f9d23130b7ffec6de5e89aa2ca6c19da6e9...b72ca72264eb31f9417a74390a1fe1963419ee5a).

- Exactly **one new commit**, `b72ca72264eb31f9417a74390a1fe1963419ee5a`, parent `06c08f9d23130b7ffec6de5e89aa2ca6c19da6e9`.
- Commit title: `fix(security): activate historical-148 admission and continue audit hardening (checkpoint)`.
  Its own message states that several lanes stopped mid-task and source was not
  fully verified. This review does not treat the title as proof of activation.
- Complete Git trees:6064→6085 entries, both `truncated:false`.
  Reviewed head tree: `52aae0798fae3676f336f7a6983d0f76d2c75461`.
- **94 changed paths = 73 modified + 21 new; no deleted or renamed paths**.
  Git compare and the complete-tree leaf delta agree exactly.
- Every changed/new path is accounted for below. Review covered each changed
  line/new file and relevant producer/consumer context; it does not claim every
  unchanged line of large historical files was re-audited.
- Read-only partitions: frontend 21, migrations 8, backend 18,
  infrastructure/tooling 19, policy/workflow/Go 28. No omitted or truncated
  changed-file content remained in the review.
- All 70 previously open IDs were reconciled:41 have current notes; 29 retain
  dated historical classifications explicitly without a new runtime verdict.

The published ledger at the reviewed source is **442 / 512**, policy 502,
baseline 315 and Gitleaks 26. This report supports seven separate scoped
acceptance decisions; it does not itself establish full release readiness.

## Source provenance and actual CI

Actual b72 PR checkout `dcd6518e9fc4691532a96e31559e0f296c370abd`
has parents main `4963face79be2da224d28779433df7ef219deeb4` and b72,
and the **identical complete tree 52aae079**.

[Matrix41312782528](https://github.com/egorribun/university_ecosystem/actions/runs/41312782528) is terminal:
**91 jobs = 61 SUCCESS / 14 FAILURE / 16 SKIPPED**, no cancellation.
Across 23 workflows: **17 SUCCESS / 4 FAILURE / 2 SKIPPED**.

| Lane | Actual result | Boundary |
|---|---|---|
| Backend unit | **23,395 PASS / 456 SKIP / 21 FAIL** across all 4 shards | Separate preflight 850 + 240 not included.17 failures are stronger-password-policy fixture drift; four others are Helm count, Semgrep source anchor, strict historical 148 pin and stale AUD-447 result double. |
| Frontend | **10,672 PASS / 3 FAIL**, 847 files | Three old listener-count assertions; build/bundle/WASM pass. KNIP separately reports2 unused exports. Aggregate is not green. |
| Owned Core | [41312782340](https://github.com/egorribun/university_ecosystem/actions/runs/41312782340) SUCCESS; 357 Node + 1 preflight + 52 browser PASS, 2 browser SKIP | User source also narrows capture padding±5 → ±2 seconds; this pass does not establish the old log-volume root cause or whole privacy chain. |
| PostgreSQL integration | [124867521632](https://github.com/egorribun/university_ecosystem/actions/runs/41312782528/job/124867521632):433 collected, 173 PASS/ 11 SKIP/ 1 FAIL, 248 NOTRUN after -x; separate13 + 5 PASS | Target-only AUD-350 adapter lacks autocommit context. Eight new populated-chain tests pass. RLS8 skip; later PG modules not reached. |
| DB performance gate | Focused91 PASS and supported roundtrip PASS | AUD-350 counterfactual1 PASS/ 1 adapter setup FAIL. Password image/renderer catalog skipped. |
| Alembic | Historical revision 148: 17 raw warnings — FAIL; finite admission rejects ordinary-parent-live SQL digest | Collector132, tenant46 and renderer41 pass; upgrade/schema-drift skipped. Neither raw fail nor mismatched admission is hidden. |
| Contract | 3615 PASS/ 2 FAIL, separate policy 848 PASS and transport41 PASS | Failures are strict148 pin and stale AUD-447 result double. |
| Dependency review | [41312782440 /job 124866476279](https://github.com/egorribun/university_ecosystem/actions/runs/41312782440/job/124866476279) FAIL | Caddy go-jose/v3@3.0.5 HIGH GHSA-mgcc-cww5-fp2q plus an unresolved exact license-row identity mismatch. No runtime exploit asserted; v4 update does not fix v3. |
| Nilaway | [41312782450 /job 124866476429](https://github.com/egorribun/university_ecosystem/actions/runs/41312782450/job/124866476429) FAIL | New metrics test lacks explicit response non-nil guard. |
| Unauthenticated smoke | Dark build RSS2210.2 MiB exceeds2048 MiB; runtime not reached | Light4routes200 /no hydration errors pass. No budget increase or inferred leak. |
| Coverage | Coverage Policy/Codecov SKIPPED | No merged coverage or release acceptance. |

Ruff, typing, inventory, baseline, Gitleaks, Checkov and CodeQL passed at b72.
These do not override the failed or skipped lanes.

## Findings and corrections from the complete source review

| Ref | Finding | Evidence class / next step |
|---|---|---|
| R1 | New event-GIN DROP/CREATE CONCURRENTLY in reconcile commits prior destructive/type changes before revision stamp. Failure before CREATE can retain a parent stamp over converted timestamps; retry under a non-UTC session may convert the instant again. An already-valid index is unnecessarily rebuilt. | Source-derived counterexample, **not yet executed RED**. Three separate tests-first controls cover existing OID/definition/data, failed-build persistence and non-UTC retry. AUD-278 /AUD-350 remain open. |
| R2 | No-Web-Locks lease renewal can reacquire after a newer worker drains/releases, allowing a stale queue snapshot to resend. A stale retry write can recreate a drained row. | Source-derived interleavings, not observed browser duplication. Two-module real-IDB tests-first draft has 2 predicted RED + 3 ownership controls. |
| R3 | The trusted RUM function drops all non-LCP/INP/CLS events while dead-letter reporting returns true; early events may precede deferred observability initialization. | Source producer/consumer mismatch, not a delivery receipt. Do not widen the CWV allowlist merely to suppress it. |
| R4 | Newly routed bare JSON mock API roots bypass the schema validator's early `/api/` prefix gate. | Test-harness source gap, not a production vulnerability claim. |
| R5 | Active PENDING/RETRYING DLQ dedup protects payload but can retain a previous reset-link-bearing error_message; the real producer subsequently commits. | Original AUD-447 storage criterion remains open. Separate real persistence/producer tests are design-only; no operational rows were inspected or scrubbed. |
| R6 | New MFA negative assertions are placed after the throwing await inside raises and are unreachable. A mechanical move of the false no-flush oracle would also be wrong: lockout flush is expected. | Test source finding; a separate precise HTTP429 /execute0 /flush1 /locked-state draft is not included in the recovery package. |
| R7 | User migration chart adds an idempotency-HMAC secret consumer while full runtime Settings and eager model imports remain. | Source mismatch with requested migration-config isolation. No deploy or silent rollback. Variant2 design must preserve genuine historical encryption/signing/Redis requirements. |
| R8 | New Helm replay test carries a local S603 annotation and an unbounded subprocess.run. | No additional annotation approval is inferred from this review. Exact scope/timeout decision remains separate; no global suppression. |
| R9 | Live-log capture padding changes±5 → ±2 seconds; a synthetic marker at exact completion does not establish the smaller timing margin's sufficiency. | Own Core passes but timing/capture completeness remains bounded. Cap 1 MiB, marker/nonce and fail-closed outcome remain present. |
| R10 | Stronger password12 /two-class defaults invalidate 17 old positive test inputs/old length messages. | Actual fixture failures, not evidence of an application regression. Recovery preserves production defaults and HIBP. An initial HIBP-off concern was explicitly retracted after reviewing the staging/production validator. |

The current policy rebind changes exactly records351 / 376 / 410, preserving the 502
population and all other records. Baseline keeps315 identities; only one line
number and generation time change. These are observed source deltas, not
authority for additional identities or a passing Squawk admission.

## Already accepted criteria touched by the delta

No proved regression of these original accepted criteria was established:

- AUD-040 retains finished/exhausted DLQ reopening, retry reset and caller-owned
  transaction semantics; AUD-447's retained-error residual is a different open
  storage criterion.
- AUD-050 UUID serialization is unchanged; broadcast preparation changes do not
  establish that old serialization failure.
- AUD-363 session/MFA epoch validation is not removed. New borrowed-session PG
  cases were not reached, which is absence of new proof rather than proof of
  regression.
- AUD-077 beacon fallback/no duplicate fallback, AUD-097 provider-commit TTI,
  AUD-078 registration/controller lifecycle, and AUD-184 consent/stale prompts
  remain in source. Three old count assertions stop early, so not every later
  assertion in those cases executed.
- AUD-100 uses one consistent IndexedDB version5 and preserves queues. An open
  old-v4-handle upgrade is not covered; this is not an established return of the
  old version mismatch.
- AUD-232 / 333 hooks and their accepted specialized oracles are unchanged; new
  reconnect E2E proves repeated OPEN only, not replay/history.
- File intersection alone is not a regression finding: AUD-341 / 365 / 319 original
  criteria are not the modified admin-create endpoint.

This is a scoped original-criterion review, not a blanket assertion that all
previous acceptance is immune to future regressions.

## Published narrow recovery after the review

[953c6aa2](https://github.com/egorribun/university_ecosystem/commit/953c6aa2aee8fb4044ccbbe3dd5cc26b568058f8)
contains exactly 5 independently reviewed paths in two commits:

- target-only AUD-350 adapter gets its explicit nullcontext autocommit adapter
  with same-active-outer-transaction assertions; not a full migration repair;
- new Go metrics test asserts non-nil response without suppression;
- stale AUD-447 fake follows actual Select/Update/CAS identity synchronization,
  preserving and strengthening all quarantine/no-publish/transaction assertions;
- service-worker registration tests recognize both real listeners and exercise
  their distinct consumers;
- two unused TypeScript exports are removed; runtime statements are unchanged.

Full tree `4ed0ca3abba9164c834b3f84950a92cef43379c8` has 6085 entries and
exactly those 5 modified leaves. PR merge `5e05942387f79864c4d37a42bd15ea61d3ce1d86`
has the same tree.

The final own-953 snapshot, verified from all 23 workflows and all 91 Matrix
jobs, is **terminal at 16:37:11 UTC**: workflows **19 SUCCESS / 2 FAILURE /
2 SKIPPED**, Matrix **64 SUCCESS / 11 FAILURE / 16 SKIPPED**, with zero
cancellations or reruns.

All four principal backend shards completed: **23,396 PASS / 456 SKIP /
20 FAIL**, 23,872 collected; separate preflights add 850 + 240 PASS.
The 20 failures are 17 stronger-password-policy fixtures, the migration
Secret projection's ten-versus-nine key mismatch, a stale Semgrep source
anchor, and the historical-148 strict source pin. AUD-447's former result-double
failure is gone, not evidence of complete retained-error storage remediation.

Frontend shards passed **10,675 tests in 847 files**, but changed-line coverage
failed on 10 of 2728 changed lines: seven webVitals, two offline upgrade and one
replay-lease line. Core succeeded with 357 Node, one preflight and **52 live
PASS / two SKIP**; the previous capture-volume root cause remains unproved.
Contract had 3616 PASS / one pin FAIL, plus 848 policy and 41 transport PASS.
DB gate had 91 + two AUD-350 + seven renderer PASS. Nilaway and the named Go
metrics socket test passed. AUD-447 had 85 unique named unit PASS.

Owned PG finished **330 PASS / 24 SKIP / one FAIL**; `-x` left 78 of 433
collected cases unexecuted. Its separate 13 + five preflights passed.
The tenantless RLS-identity fixture assertion failed; this is not proof that
correctly populated tenant context rejects authorized rows. Later teardown
MissingGreenlet is separate. Tenant-RLS eight and quarantine-CAS three were
skipped. The named AUD-270 / 274 / 351 receipts below remain scoped successes.

Alembic raw historical-148 lint and finite admission SQL digest still fail;
132 + 46 + 41 other passes do not override them. Dependency review still
reports Caddy go-jose/v3 HIGH and a separate exact identity mismatch, with no
identified full license/PURL rejection row. Coverage & Quality Policy Gate,
Trusted Codecov and rollback gate are **SKIPPED**, not GREEN.

[Own Matrix](https://github.com/egorribun/university_ecosystem/actions/runs/41321456248)
and [own Core](https://github.com/egorribun/university_ecosystem/actions/runs/41321456147)
are source-specific receipts. Neither terminal b72 nor this red own-953 run
establishes full GREEN for the next independently reviewed source.
Own-953 [Unauthenticated Routes Smoke](https://github.com/egorribun/university_ecosystem/actions/runs/41321456202)
succeeded. The earlier b72 RSS-cap failure is historical; this successful run
does not establish its root cause or eliminate build-memory variance.

### Seven criterion-specific decisions

All seven decisions preserve the previous 442 accepted IDs. The proposed published
partition is **449 accepted / 63 open**, not a claim that all changes or all CI pass.

| ID | Original criterion and evidence | Explicit limit |
|---|---|---|
| AUD-270 | UUID child cutover must stop instead of TRUNCATE. [Named owned PostgreSQL test](#postgresql-receipts) executes the actual refusal helper, preserves both physical rows, and passes an empty-table control. Source `202602010003_final_cutover_swap.py` blob `2b68ed78f66f6c129cc9d7c3905aab6142e5da98`, helper 129 and caller 258–266. | Guard-level original criterion, not a full populated UUID cutover, rollback or FK-safety claim. |
| AUD-274 | Three named 06c tests, repeated as three named PASS on own 953, preserve quiet-hours/timezone, existing destination precedence, and atomic refusal on incompatible NULL. Fixture `e85a6ac4e812f373e3535a75ca83447a2007e6e3`, migration148 `d762c45c9248c14eccf57ac8e9e2dae8867777c1`, retained-parent `d1bff8fa8814493d9f825f37d64e3909232caba2` are unchanged at b72. | Named 953 proof supplements historical source-equivalent receipts. The b72 run did not reach the module; the complete 953 PG job is still red. |
| AUD-311 | Four filename-tier matching controls cover 20 named security modules outside directory rules, preserve 21 old rules, directory positives and3 nonsecurity negatives. Normalizer `ad55b0837ccbe1f32f399ce3c983555dde9eb606` consumes the matching helper; mapping `c87b480f0c6e32038b1f8275c09c69b27ef33b57`; test `65debd72f419b6cd7cd456dee095fb3ab499c67f`. | **COHORT-INFERRED 4**, not individually named logs or successful enforcement of every coverage floor. |
| AUD-351 | Named owned PG predecessor→reconcile test preserves all 3 jobs: incompatible 2 are dead-lettered/rekeyed and the already-dead row keeps its prior error. Reconcile `6ffa5796dab0e55c8538364faf46071037ce5862`:492–516; fixture `7a375e3e63b41a75f0ad5f6d485877e39f810a5e`. | Fixes the integer→UUID failure without claiming the old notification target remains deliverable. |
| AUD-456 | Actual production-mode LHCI=true and LHCI=false controls discriminate no-fetch from exactly 1 credentialed csrf-cookie GET. `client.closure.test.ts` blob `906bf554e28af1a0f99cb374772323c76f72a50a`:72–101. [Own-b72 file-level 46 PASS (unchanged source at 953)](https://github.com/egorribun/university_ecosystem/actions/runs/41312782528/job/124867585115). | File-level receipt, not individual named logs or proof of all CSRF behavior. |
| AUD-490 | Config `312546f83a309c1bf4b443fe6ec4782099c2d078` rejects absent idempotency HMAC in staging/production. Test `8160b81453406121808b9abfa3c6da878295d652` covers configured positives and existing local/CI exemptions. | **COHORT-INFERRED 7**; does not solve migration-only Settings isolation. |
| AUD-503 | Canonical component-injected ICS and WebSocket/session/internal precedence now match the inventory 143 canonical/ 10 public/ 1 session/ 2 worker. Checker `48843a5f11c70a0d0e0ccce57c3b1bf948ec253f`; inventory `231183ee12c14e1c6ae0d998ce086e8b38f5e63f`; test `02a314b8756e0a7ec859a14c181963b30865596e`. | **COHORT-INFERRED 10**; label consistency, not new runtime authorization proof. |

### PostgreSQL receipts

[Own b72 PG job 124867521632](https://github.com/egorribun/university_ecosystem/actions/runs/41312782528/job/124867521632):

- `test_integer_record_ids_are_dead_lettered_and_kept_by_reconcile`: PASS 13:56:10.6067253 UTC.
- `test_cutover_guard_refuses_populated_child_and_keeps_every_row`: PASS 13:56:25.6429708 UTC.

[Historical 06c PG job 124827564668](https://github.com/egorribun/university_ecosystem/actions/runs/41299274876/job/124827564668)
records these three named tests at 11:09:46 / 48 / 50 UTC:

- `test_upgrade_preserves_legacy_user_preferences`;
- `test_upgrade_backfills_missing_preferences_without_overwriting_existing_rows`;
- `test_null_legacy_enabled_aborts_upgrade_without_losing_preferences`.

Their fixture runs real ancestry to `f7aa476e968a`, asserts the real four legacy
columns and absence of `user_preferences`, and does not recreate fake legacy
columns. Actual06c checkout `6ea734a1331b1fb4af9bfcd518474fc181ea1101`
has the same source tree as06c. Only the later env default-comparison setting
changed in this relevant env delta; root conftest and the three evidence blobs
remain unchanged.

[Own 953 PG job 124893678100](https://github.com/egorribun/university_ecosystem/actions/runs/41321456248/job/124893678100)
also records all three AUD-274 tests as named PASS on 2026-11-01:
15:44:21.7459113 / 15:44:23.6641412 / 15:44:25.5423036 UTC, respectively.
The tested merge `5e05942387f79864c4d37a42bd15ea61d3ce1d86` has exactly the
published 953 tree `4ed0ca3abba9164c834b3f84950a92cef43379c8`.
The later RLS fixture failure makes the complete PG job red; it does not
erase these named passes or establish a full migration-chain acceptance.

The same own-953 log also repeats AUD-351's
`test_integer_record_ids_are_dead_lettered_and_kept_by_reconcile` at
15:42:17.2867926 UTC and AUD-270's
`test_cutover_guard_refuses_populated_child_and_keeps_every_row` at
15:42:39.8702211 UTC. Their original-criterion limits remain unchanged.

### Why cohort inference is bounded

For AUD-311 / 490 / 503 the read-only review checked root collector
`1d677c8e`, pyproject `ecce4c43`, and reusable workflow `b608ccce`.
Collection groups complete files and assigns each file exactly once to one of
four shards. Actual TEST_PATTERN was `tests/`; all four cohorts completed,
with **23,872 outcomes = 23,395 PASS + 456 SKIP + 21 FAIL**.
Complete skip lists were79 / 143 / 116 / 118; none of the target cases had a skip,
failure or collection error, and their files have no relevant exclusion.
The selected workflow excludes only its documented Schemathesis and separate
quarantine-PG scope. This supports the explicitly labelled4 / 7 / 10 inference.
Raw manifests were not read and the independent union/coverage gate was
**SKIPPED**; no full policy or named-target PASS is claimed.

### AUD-269 is deliberately not accepted

The original audit says approximately 15 lost hot-path indexes, without an
authoritative enumerated subset. Reconstructing the pre-fix reconcile DROP-list
(blob `25089ec33a187982619796b3e9a8a8842056c9c8`) identifies **19 non-shadow
candidate names**, not a retroactive assertion that the original count was
exactly 19. The current nine-name PG test covers the eight preserved candidates
plus `ix_stored_events_processed_at`, which was not in that DROP-list.

| Disposition | Exact candidate names | Evidence boundary |
|---|---|---|
| Preserved (8) | `ix_chat_participants_chat_id_user_id`; `ix_chat_participants_user_id_chat_id`; `idx_messages_chat_pagination_covering`; `ix_messages_unread_chat_sender`; `idx_news_comment_cursor`; `ix_stored_events_aggregate_uuid`; `ix_stored_events_pending_aggregate_created`; `ix_stored_events_pending_created` | Removed from the destructive list; definitions and the existing nine-name PG controls were reviewed. |
| Concrete source-loss candidates (6) | `idx_active_sessions_user_valid`; `ix_active_sessions_user_active_created`; `idx_notifications_user_unread_created`; `ix_stored_events_pending`; `ix_user_profiles_full_name_lower`; `ix_user_profiles_full_name_trgm` | The current DROP loop remains; inspected reconcile, current ORM and retained metadata provide no equivalent replacement. This is a local DDL/source finding, not a measured deployed-query regression. |
| Source-equivalent replacement (3) | `ix_events_embedding_hnsw` → `ix_events_embedding`; `ix_news_embedding_hnsw` → `ix_news_embedding`; `ux_users_lower_email` → `ix_users_email_lower` | HNSW operator classes and absence of tuning clauses match the first two originals. The third replacement preserves UNIQUE lower(email), unlike a plain UNIQUE email constraint. |
| Equivalence unresolved (2) | `news_embedding_hnsw_idx`; `idx_messages_chat_created` | The first original has explicit m=16/ef_construction=64 omitted by the replacement; defaults are not assumed. A covering index sharing the second index's leading keys is not automatically exact or performance equivalence. |

Definition receipts include wave14 `fdf095a03427d0ee77924b331411c1bb352318fb`,
active-partial `7359d50d65aa93e0d066a677e442e6b792e3858f`,
profile-lower `bc649e3acffa5f73c12147d3a668d6ad6f875c2a`,
profile-trgm `fa267308cd960bd99d281aa9cf8d709f29b348c5`,
stored-pending `ae1a64590074892f54dc69bdea9dad5d87fb558e`,
initial-HNSW `dc5a9edcfa580e945c4089926b9c9d373b10c39d`,
tuned-news-HNSW `2b652bb2050625209541e91047666a9bc60d65e0`,
and original/retained lower-email definitions
`37576afad7b5e9b691ae8733b998be4b2a459681` /
`e328c9eaf0543945704d4dec4c1839cca2a1f9e3`.
The current reconcile blob is `6ffa5796dab0e55c8538364faf46071037ce5862`.

This establishes candidate-name coverage and the inspected local
drop/replacement definitions, not every differently named later index or a
deployed catalog. AUD-269 remains **partial/open**; the earlier eight-index
narrowing cannot close the original whole criterion.

## Complete 70-ID reconciliation

Codes: **S** source-fixed/proof-pending; **P** partial; **U** unfixed;
**N** unverified/original-cause-unproven. ACCEPT is restricted to the seven
decisions above. Before acceptance the updated descriptive partition is
21S/ 37P/ 9U/ 3N. After acceptance, **63 remain:15S/ 36P/ 9U/ 3N**.
Historical rows are explicitly marked rather than silently re-tested.

| ID | Original finding | Prior | Reviewed classification / decision | Evidence boundary |
|---|---|---|---|---|
| AUD-073 | Белый текст отправленных сообщений имеет недостаточный контраст на светлом violet gradient | S | S | Historical classification carried forward from the dated prior70 matrix; not a new source/runtime verdict. |
| AUD-154 | Delivery test ждёт marker, которого нет в status renderer | S | S | Realtime fixtures remain REALTIME_E2E-gated; no new actual delivery receipt. |
| AUD-164 | Backend видит IP gateway: все анонимы делят лимиты login/register/MFA/reset | P | P | Proxy/limiter source controls changed; complete original topology acceptance not established. |
| AUD-167 | Rate-limit gateway и ws-hub сводится к одному IP прокси | P | P | New composed admission/rate-key controls are not complete deployment/topology proof. |
| AUD-169 | file-processor не стартует в staging/prod: revocation-Redis закрыт NetworkPolicy | P | P | Original file-processor to revocation-Redis NetworkPolicy startup criterion remains unaccepted; no new deployment/connectivity proof. Separately, the migration chart adds an HMAC consumer while eager Settings remains, a separate uncompleted migration-settings isolation issue. |
| AUD-178 | Токен сброса пароля попадает в access log (Referer) и в CSP-отчёты | P | P | No-referrer alone does not prove the complete CSP document-uri/Referer/log chain; no observed exfiltration asserted. |
| AUD-188 | JWKS file-processor запрещён NetworkPolicy: через ~24 ч отклоняются все RS256-токены | P | P | Historical classification carried forward from the dated prior70 matrix; not a new source/runtime verdict. |
| AUD-189 | NetworkPolicy разрешает TCP/ 443 и DNS любому адресату, включая сервисы кластера | P | P | Historical classification carried forward from the dated prior70 matrix; not a new source/runtime verdict. |
| AUD-208 | Squawk-гейт проверяет пустой SQL для guard-миграций и ослаблен исключениями | P | P | Finite148 admission is wired but own run rejects ordinary-parent-live SQL digest; raw 17 warnings still fail. |
| AUD-226 | Tier-0 миграции (`alembic/versions/**`) выпадают из требования 100% покрытия | P | P | Source rebindings do not establish complete historical-migration Tier0 coverage. |
| AUD-231 | SSR-страницы frontend отдаются без CSP, nonce-схема не работает | S | S | Historical classification carried forward from the dated prior70 matrix; not a new source/runtime verdict. |
| AUD-245 | Trivy-исключения KSV глобальные (без путей), срок пересмотра истёк | U | U | Historical classification carried forward from the dated prior70 matrix; not a new source/runtime verdict. |
| AUD-251 | SPIRE agent получает кластерный nodes/proxy get/list/watch | P | P | Historical classification carried forward from the dated prior70 matrix; not a new source/runtime verdict. |
| AUD-269 | Reconcile 202603280001 удаляет ~15 индексов горячих путей без восстановления | S | P | HOLD: reconstructed 19-name non-shadow DROP population has 8 preserved, 6 concrete local source-loss candidates, 3 source-equivalent replacements and 2 unresolved definitions; nine catalog checks do not cover the original whole risk. |
| AUD-270 | Cutover UUID делает TRUNCATE ... CASCADE дочерней таблицы вместо остановки | S | ACCEPT | ACCEPT original refusal criterion: named PostgreSQL populated-child refusal preserves both rows plus empty positive; not a full UUID cutover proof. |
| AUD-272 | UNIQUE «delivery once» включает attempted_at и не препятствует повторным пушам | U | U | Historical classification carried forward from the dated prior70 matrix; not a new source/runtime verdict. |
| AUD-274 | Миграция 202511240001 теряет DND и часовой пояс пользователей | S | ACCEPT | ACCEPT original preferences preservation: three named own-953 PostgreSQL passes supplement historical source-equivalent 06c proof; the full 953 PG job fails later on a different fixture. |
| AUD-275 | Индексы на messages и users строятся без CONCURRENTLY, docstring обещает обратное | P | P | Three named reply-index valid/interrupted/missing cases pass; users functional index still uses plain CREATE. |
| AUD-277 | RLS с политикой USING(true) на восьми таблицах не изолирует данные | N | N | Original USING(true) cause remains unestablished independently of restrictive policies; eight new tenant-role PostgreSQL cases skipped. |
| AUD-278 | GIN-индекс events.search_vector удалён и не восстановлен | S | P | Two GIN happy-path passes do not cover unconditional valid-index DROP or transaction boundary before rebuild; new source-derived retry risk remains. |
| AUD-309 | live_stand.py: вызовы без таймаута и бесконечное ожидание блокировки | U | S | Generic subprocess/native-lock bounds are source-fixed; native/runtime boundary proof not supplied in this review. |
| AUD-311 | Tier-0 правила сопоставляют каталоги: security-модули по имени вне Tier 0 | S | ACCEPT | ACCEPT filename Tier0 matching criterion; explicit COHORT-INFERRED 4 with full shard allocation accounting, not successful enforcement of all coverage floors. |
| AUD-313 | Гейт owned-stand основан на переменных окружения; сид переписывает пароль администратора | U | U | Historical classification carried forward from the dated prior70 matrix; not a new source/runtime verdict. |
| AUD-321 | E2E: условные проверки с веткой-annotation делают тест зелёным | S | S | Browser oracles are unconditional but corresponding selected browser execution is absent. |
| AUD-322 | Интеграционные тесты событий и chaos молча пропускаются | P | S | Chaos auth/no-chat now fails rather than silently skips; actual active chaos execution remains unproved. |
| AUD-327 | Upgrade через `148642dd1207` падает на legacy-БД с пользователями в верхнем регистре ролей | U | U | Historical classification carried forward from the dated prior70 matrix; not a new source/runtime verdict. |
| AUD-332 | Тесты «when_supported» создают symlink без проверки привилегий | U | S | Native symlink privilege probe now exists; native Windows execution not supplied. |
| AUD-334 | Replay пропускается при rate limit или выключенном replay, пропуск не досылается | P | P | New blocked/superseded-writer source controls alone do not establish complete replay-admission proof. |
| AUD-346 | Nightly chaos-loadtest всегда зелёный: dry-run отключает все проверки | U | U | Historical classification carried forward from the dated prior70 matrix; not a new source/runtime verdict. |
| AUD-347 | MinIO chaos-набор в nightly никогда не выполняется: заданы не те переменные | S | S | Historical classification carried forward from the dated prior70 matrix; not a new source/runtime verdict. |
| AUD-348 | Апгрейд 148642dd1207 удаляет Spotify-токены из users без переноса | P | P | Historical classification carried forward from the dated prior70 matrix; not a new source/runtime verdict. |
| AUD-350 | 202603280001 перезаписывает outbox stored_events при смене типа на TIMESTAMPTZ | P | P | Table rewrite/locking criterion remains open; b72 target-only adapter failed setup, and953 restores that limited test adapter rather than fixing the migration. |
| AUD-351 | 202603280001 падает на непустой notification_queue_jobs: integer record_id → UUID | S | ACCEPT | ACCEPT populated integer-record conversion: real predecessor-to-reconcile preserves all 3 jobs, dead-letters/rekeys incompatible 2, preserves prior dead-letter error. |
| AUD-360 | RLS: строки с tenant_id IS NULL видны всем тенантам, а приложение tenant_id не пишет | P | P | Tenant source stamping/policies reviewed, but owned8 PostgreSQL cases skipped and ordinary API producer isolation remains unproved. |
| AUD-373 | Внутренние HTTP-вызовы backend без TLS несут токены и identity | U | U | Historical classification carried forward from the dated prior70 matrix; not a new source/runtime verdict. |
| AUD-375 | Replay очередей SW без CSRF-заголовка, без удаления при 403 и без взаимоисключения | P | P | Source counterexamples: expired-owner renewal can reacquire after successor release; stale snapshots may resend or resurrect drained rows. Tests-first draft not yet executed. |
| AUD-378 | «SLSA Provenance Dry-Run» в `ci-success` проверяет только существование `ci.yml` | U | U | Historical classification carried forward from the dated prior70 matrix; not a new source/runtime verdict. |
| AUD-380 | `.semgrep.yml` заявляет запуск Semgrep в CI, но такого job нет | U | U | Historical classification carried forward from the dated prior70 matrix; not a new source/runtime verdict. |
| AUD-381 | DAST, Scorecard и sqlmap не блокируют и не публикуют находки | P | P | Historical classification carried forward from the dated prior70 matrix; not a new source/runtime verdict. |
| AUD-384 | Slack-уведомление nightly не отправляется: `env` шага используется в его `if` | S | S | Historical classification carried forward from the dated prior70 matrix; not a new source/runtime verdict. |
| AUD-392 | Проверка утёкших паролей (HIBP) выключена по умолчанию и не требуется в production | P | S | Defaults12 /two classes and staging/production HIBP validator source are hardened. Earlier field-default HIBP warning was retracted; old positive fixtures fail stronger policy. |
| AUD-393 | Миграции глотают ошибки DDL и мутируют модульное состояние | P | P | No receipt establishes the entire historical DDL error/module-state behavior. |
| AUD-414 | scrypt_derive принимает N= 1, pbkdf2_derive принимает одну итерацию | P | P | Historical classification carried forward from the dated prior70 matrix; not a new source/runtime verdict. |
| AUD-416 | wasm-fuzzer завершается с кодом 0 без фаззинга и нигде не подключён | P | P | Historical classification carried forward from the dated prior70 matrix; not a new source/runtime verdict. |
| AUD-420 | Rescue bundle и archive-inventory из INDEX.md и MVP-плана на диске отсутствуют | N | N | Historical classification carried forward from the dated prior70 matrix; not a new source/runtime verdict. |
| AUD-422 | CONFIGURATION.md покрывает 95 из 290 полей Settings; часть переменных мимо Settings | P | P | Names inventory covers290 typed Settings fields, not outside-Settings variables or semantic documentation completeness. |
| AUD-423 | Числа, пути и значения по умолчанию в README/SECURITY/DEPLOY/AGENTS расходятся с кодом | P | P | Selected counts/inventory improve without full cross-document path/default consistency proof. |
| AUD-426 | MFA-тесты гонки заменяют DB-атомарность на asyncio.Lock | P | P | Source uses10 genuine parallel HTTP/request-scoped sessions; both owned concurrency tests skipped for PostgreSQL requirement. |
| AUD-428 | Около 140 Python, 17 Go и ~30 TS-блоков тестов без проверок результата | P | P | Additional assertions are not a complete cross-language assertion census. |
| AUD-429 | E2E realtime-набор и визуальные тесты в CI не выполняются | P | P | Changed browser fixtures do not remove opt-in/manual-only limitations. |
| AUD-432 | E2E-live contract-тесты проверяют текст spec-файлов регулярками | P | P | Selected Core/fixtures do not prove every lockout/full-SSR/registration contract. |
| AUD-433 | Промежуточное состояние свежей цепочки: notifications без партиций, записи падают до `202607020001` | U | U | Historical classification carried forward from the dated prior70 matrix; not a new source/runtime verdict. |
| AUD-434 | `alembic check` не сравнивает server default; `push_subscriptions.topics` расходится с моделью | P | P | compare_server_default and AST controls added; actual Alembic upgrade/schema-drift skipped. Old 'absent' description is superseded without acceptance. |
| AUD-436 | live_stand: whoami ищется через PATH, в Git Bash получается GNU-утилита (уточнено) | S | S | Historical classification carried forward from the dated prior70 matrix; not a new source/runtime verdict. |
| AUD-438 | /metrics ws-hub доступен без аутентификации, в отличие от backend и gateway | P | P | New metrics-isolation test is not deployment isolation proof; 953 fixes its nil-check setup. |
| AUD-447 | Токен сброса пароля хранится открытым текстом в dead_letter_jobs | P | P | Original plaintext-storage criterion remains open: active retained-error dedup source residual; b72 mock failure was stale result-double setup, PG CAS cases not reached. |
| AUD-449 | OAuth-код Spotify попадает в access-логи Caddy и gunicorn | S | S | Historical classification carried forward from the dated prior70 matrix; not a new source/runtime verdict. |
| AUD-450 | RLS-политика тенанта снимается обычным GUC app.bypass_rls (латентно) | S | S | Source role-bypass repair retained; all 8 relevant new owned PostgreSQL cases skipped. |
| AUD-454 | Гонка кэша участников чата: удалённый участник получает кадры до 1 часа | P | P | Four local membership cases pass; authoritative roster still precedes semaphore acquisition and borrowed-session PostgreSQL scope remains open. |
| AUD-456 | Тест LHCI-пути CSRF проходит по MODE=test и не проверяет LHCI | U | ACCEPT | ACCEPT nondiscriminating LHCI test criterion: production-mode positive/negative controls in current client.closure file46 PASS; not all-CSRF behavior proof. |
| AUD-474 | Проверка «отказ CSRF не оставляет cookie» всегда истинна: cookie удаляется до чтения | S | S | Historical classification carried forward from the dated prior70 matrix; not a new source/runtime verdict. |
| AUD-478 | Durable-настройки NATS не применяются, cache.invalidate переигрывает 7 дней | P | P | Held; previously blocked generation/repair operation not resumed or routed around. |
| AUD-480 | PR-гейты не покрывают medium/low npm, dev-зависимости и unfixed (Trivy FS) | P | P | Historical classification carried forward from the dated prior70 matrix; not a new source/runtime verdict. |
| AUD-482 | Caddy-образ: Go-зависимости разрешаются при сборке, lock в репозитории отсутствует, вне govulncheck и osv | P | P | Historical classification carried forward from the dated prior70 matrix; not a new source/runtime verdict. |
| AUD-483 | osv-scanner (Go) запускается только на main: 75 открытых алертов (12 ID); stdlib-находки основаны на директиве `go 1.26.4` | P | P | Historical classification carried forward from the dated prior70 matrix; not a new source/runtime verdict. |
| AUD-484 | Устаревшие открытые алерты (code-scanning и Dependabot) не отражают текущие lock-файлы | N | N | Historical classification carried forward from the dated prior70 matrix; not a new source/runtime verdict. |
| AUD-490 | IDEMPOTENCY_HMAC_SECRET не требуется в production вопреки комментарию | S | ACCEPT | ACCEPT mandatory configured-secret criterion outside existing local/CI exemptions; explicit COHORT-INFERRED 7, not migration-settings isolation. |
| AUD-501 | Тест паузы в скрытой вкладке не проверяет заморозку прогресса во время скрытия | S | S | Historical classification carried forward from the dated prior70 matrix; not a new source/runtime verdict. |
| AUD-503 | Метки владения в инвентаре маршрутов расходятся с кодом (ICS, WebSocket /chat) | P | ACCEPT | ACCEPT route-label consistency criterion: canonical ICS and session chat; inventory 143 / 10 / 1 / 2 and COHORT-INFERRED 10, not runtime authorization proof. |
| AUD-506 | Temporal: ключи JWKS по HTTP и noop-авторизация принимают подменённые токены | P | P | No new proof that Temporal producer carries required permissions. |

## Complete 94-path review manifest

Every row belongs to the one reviewed user commit, not to a hidden sampled
subset. Full blob identities are included so a later source can be reconciled
without applying stale postimages.

| Path | Change | Base blob | Reviewed blob | Review area |
|---|---|---|---|---|
| `.github/workflows/ci.yml` | modified | `26f6d29a19ca378b433ee2f8ba957ad518003776` | `880fd2ef6aab7fbd323a305753aff6f3cbf82898` | Policy/workflows/Go |
| `.secrets.baseline` | modified | `467a670df069686f162a074d7efaa6865b1d0d8e` | `ff80314530a10e5eb0837aa3cd3ba997f1dd433b` | Policy/workflows/Go |
| `CONFIGURATION.md` | modified | `0ea98f1d710a39616a126025426ae211eea21ffc` | `fdc95137d14954d378072851b4d91eba8376c78a` | Infrastructure/tooling |
| `alembic/env.py` | modified | `7ab4b58b7cab611b37b67dbb7c5bce31b5eeafb7` | `ac2f50a28639157129b5093cfa15d7ae1809cca3` | Migrations/schema |
| `alembic/versions/202603280001_reconcile_post_uuid_migration_drift.py` | modified | `2c6ca52b45f108cfd2737a8d140145ca4ed2e34e` | `6ffa5796dab0e55c8538364faf46071037ce5862` | Migrations/schema |
| `alembic/versions/202605300004_add_reply_to_message_id.py` | modified | `4fa3fa3266f1f8029a68d60b1fc9d9481b9c6637` | `56c794c302a709338d85a1148e61ea1b8e209acf` | Migrations/schema |
| `app/api/users.py` | modified | `ec68338268572e8a28ce67f6a501ffe42a801683` | `629fb05bf7915b8a61a4003dd09ca7b7cfce5be9` | Backend/auth/DB |
| `app/api/ws/connection_manager.py` | modified | `ae78f4efa11d18504a01dae9d85b6719a44c5018` | `6d7d7e81322e9b15a10be18e9e8ae530cd5ee59d` | Backend/auth/DB |
| `app/core/config/mixins/mfa_settings.py` | modified | `92ac7b8151be1095435e1e2e4e6fb6960b64dbda` | `1105613091a83cfb0486fca6b2cfe2445fdebd6a` | Backend/auth/DB |
| `app/core/db/listeners.py` | modified | `2ec6668d56ede56cdcab8e757f53531c1b51036f` | `1c8f7a90d673d3c7d30106db5b2df9ab5c1966ed` | Backend/auth/DB |
| `app/models/events.py` | modified | `5566be21e96559eb8a16e19a5bdb7c89d0d82a50` | `758915b8f7dc4559c9fa633ff8e097a3183fb422` | Migrations/schema |
| `app/workers/dead_letter_queue.py` | modified | `55e1cdb46a52ef4894fb01af5e3cc147f01544b2` | `498ccd2561ea353c9feeecd374810a0944f40da7` | Backend/auth/DB |
| `charts/university-ecosystem/templates/migration-job.yaml` | modified | `7ddc1d85db1af59fa4a94660e1ce3fd91a64389d` | `4fa5bf71f712b3415e9ed7490b54eb1ea0bac146` | Infrastructure/tooling |
| `charts/university-ecosystem/templates/validate-config.yaml` | modified | `126481a324627a918536b9fe6718e88ddc032a55` | `e86b887fd77a4718c4e7bea1740e2d52e9106040` | Infrastructure/tooling |
| `charts/university-ecosystem/values.schema.json` | modified | `72bacd2c87b3b7497ced7ef771de4d249687a6e1` | `0a3bb234218ec6999524194aea43909aaba60950` | Infrastructure/tooling |
| `docs/adr/ADR-047-risk-based-quality-policy.md` | modified | `181588141d4ad27276e1c0c839c0d1c102577be1` | `52d7f4163ccfd5bb352e345bca0e7dfd38230e1c` | Policy/workflows/Go |
| `frontend/src/__tests__/m1_offline_stress.test.ts` | modified | `22415c105967f730177ef3b0376544974d16147a` | `62411e5e6d8d24ae356f215db94c835fdfbc81c6` | Frontend/SW |
| `frontend/src/__tests__/server.entrypoint.test.ts` | modified | `1c92800fbd7424f24317bdd18f6f8ddb1eb7c91f` | `001789315fecb37ab0dd2239b488b209040aaa55` | Frontend/SW |
| `frontend/src/api/__tests__/client.closure.test.ts` | modified | `ed27502dfe915b68f7123a2b7216659af1f23090` | `906bf554e28af1a0f99cb374772323c76f72a50a` | Frontend/SW |
| `frontend/src/app/webVitals.ts` | modified | `d92d090b5bbb1194633f5212f8a190ee44c25327` | `a6ee595cee6391ca997ebffc2fc0ff2d2418b287` | Frontend/SW |
| `frontend/src/constants/notificationInteractionsDb.ts` | modified | `6545bf984dcd92bffa553e378343b4b6d07cd4d9` | `ff4a2f4dd6fd967eb93010fcbb21154e152e9380` | Frontend/SW |
| `frontend/src/constants/serviceWorkerMessages.ts` | modified | `97a10e873bf82323872a46b10f5d21d9538d8c63` | `557d206391e74228ad5bfc4e3a541d92826f730b` | Frontend/SW |
| `frontend/src/push/register-sw.ts` | modified | `975f684d988b7a9217e8e8e028e4cf682a41d866` | `32b6292a7c249e92e3e7f5bc6ee9b9681e3a9678` | Frontend/SW |
| `frontend/src/server.ts` | modified | `78af66693bc3058402ca2f0a22c01355184104df` | `e7992cd94b4700a6b867eefe4604b4e6ddb1a8b5` | Frontend/SW |
| `frontend/src/sw/__tests__/audit375.queue-serialization.test.ts` | modified | `898021e0a27f72400359a76eea32cab9b2df095a` | `a8f914201f392c9d63b4877955e433129a4ba641` | Frontend/SW |
| `frontend/src/sw/__tests__/offline.test.ts` | modified | `c42863a014f3814f607de90cbb48e1a71e9ea782` | `00c62780ce85e15e1005d58a14e4ab0afff097f6` | Frontend/SW |
| `frontend/src/sw/__tests__/offlineUpgrade.test.ts` | modified | `49de6846dd8b4f69ac0cef8e75b00e10493d5b1f` | `650e96de46ecc11d30b5c466aabdf1f57c3b4761` | Frontend/SW |
| `frontend/src/sw/__tests__/sw_offline.test.ts` | modified | `b1f332296841d99e6710c7c3d9dc13709d2a5246` | `424883235529b886ae4fa731a66acd25564213e0` | Frontend/SW |
| `frontend/src/sw/offline.ts` | modified | `3aecc216318bdd98f750a884ab319735753faca7` | `261cfe6a4ee24fccd0595ac7e7f616e54459b867` | Frontend/SW |
| `frontend/src/sw/offlineDeadLetterListener.ts` | added | new | `aa1eb8b8df5abd9025b5a17d72781ecab9b1e24c` | Frontend/SW |
| `frontend/src/sw/replayLease.ts` | added | new | `236aa64294c4d400739fb91fe526141a7056788f` | Frontend/SW |
| `frontend/src/sw/replayPolicy.ts` | modified | `d4e0b24967e45036a42022bb0e1b1b4e4a71af08` | `9264382b5e5528628e74f2b7abe3a0e9bd2603de` | Frontend/SW |
| `frontend/src/tests/sw.test.ts` | modified | `3e9e9522081e94c758081a3bcc29bcce1f740dbd` | `73157928cc8b36766653e2d05f6b883d15a50c5f` | Frontend/SW |
| `frontend/tests/e2e-live/password-reset-live.contract.test.mjs` | modified | `6b9aa8c794665e08be3212fdc8dbb6e55548a0ce` | `fae63623dadae0de1f97611127eee6d84aba7d90` | Frontend/SW |
| `frontend/tests/e2e/chat-realtime.spec.ts` | modified | `e2820cf6f914ed508e2d8ae0b6b033bdb240bbbc` | `b568a66b29ac971358daea4e6bc326b9790f31ab` | Frontend/SW |
| `frontend/tests/e2e/rate-limit-ux.spec.ts` | modified | `f75a2dda913a32886079735d1d253086099c407a` | `0e35c0055ce3ff5b8e99a30ebc05c869bdb6e014` | Frontend/SW |
| `frontend/tests/e2e/utils/mockApi.ts` | modified | `f86c078e8ed16a085d653b1c23985dba87078a69` | `754371e8ff23ad14e91447efbf8873614de37bd9` | Frontend/SW |
| `quality/historical148-squawk-policy.json` | modified | `f7179f7b8f0ac3e84b3af4a9ed3a2e92b569e923` | `de98854e4ab2c63cd691a973f6d7f61dbc1691dd` | Policy/workflows/Go |
| `quality/route-dependency-inventory.json` | modified | `a5081e6a2dc67caa96d421f1abde35b26407990d` | `231183ee12c14e1c6ae0d998ce086e8b38f5e63f` | Policy/workflows/Go |
| `quality/security-false-positive-dispositions.json` | modified | `3297911f218c336f8797d7e1d6c266834b2433d0` | `3eeb2ac0050fc07e8e1c29f9d46431fbb2ec602e` | Policy/workflows/Go |
| `scripts/check_route_dependency_inventory.py` | modified | `7c343cc3174489f9de0e2198532b0c12d2053d84` | `48843a5f11c70a0d0e0ccce57c3b1bf948ec253f` | Policy/workflows/Go |
| `scripts/live_stand.py` | modified | `1a89421fa9d061d390e70b5399eeece74602f5af` | `7bde5637caada4eeef9177c46bd8fc6ce97ccc19` | Infrastructure/tooling |
| `scripts/quality/historical148_squawk_admission.py` | added | new | `71702561a9800a8bd3711977887b729cd40e7aec` | Policy/workflows/Go |
| `scripts/quality/validate_historical148_squawk.py` | modified | `8f88709ee55a9718daecfe25844ccc17aeb4d2b2` | `2dd99cb72ce46e8524e344a9144d8ab0d33db49b` | Policy/workflows/Go |
| `scripts/verify_secrets_baseline.py` | modified | `18307fd00ae1bc27ab3a08d141ea2cbd373bd2ed` | `96cfe31e16c6bbb21676415ad5f1dfcb10ae905d` | Policy/workflows/Go |
| `services/gateway/cmd/gateway/aud167_trusted_proxy_ratelimit_test.go` | added | new | `c176014540f03f50602900304e99efafa395731e` | Policy/workflows/Go |
| `services/ws-hub/main.go` | modified | `3770b9580b380530f54fa26c0ca0d4fb18c2ace4` | `04382cebfeb8e54a7747a3b8ba0062ba95653a0a` | Policy/workflows/Go |
| `services/ws-hub/main_aud438_metrics_isolation_test.go` | added | new | `bc7e713ae1cb7676dfe0d3c6142b26c3bbabc5bb` | Policy/workflows/Go |
| `services/ws-hub/main_aud478_readiness_test.go` | added | new | `4e5580e6e8c15f308e63030320bb3aa4cb83a86a` | Policy/workflows/Go |
| `services/ws-hub/pkg/hub/aud167_trusted_proxy_admission_test.go` | added | new | `208dbcd28af7b6bc43157bfa1c3baa51446a2255` | Policy/workflows/Go |
| `services/ws-hub/pkg/hub/aud320_python_contract_test.go` | modified | `280ed1f3316f47201e7af0c46fa661517dd6d1d9` | `0c3138b5db4bca99600f1236ffdf0905079e57e1` | Policy/workflows/Go |
| `services/ws-hub/pkg/hub/aud334_superseded_replay_blocked_writer_test.go` | added | new | `cd4e3971e9e7594b481d9da2722cfce089faaaff` | Policy/workflows/Go |
| `services/ws-hub/pkg/hub/aud478_admission_barrier_test.go` | added | new | `a85c262cacea2b04562fa89c5399798a6f424164` | Policy/workflows/Go |
| `services/ws-hub/pkg/hub/handlers.go` | modified | `8d32ee8fffe9ba4c52238189136d3125dc17a63d` | `a93430d12272ee5cb10bfe3afdc8edee91ba2d86` | Policy/workflows/Go |
| `services/ws-hub/pkg/hub/hub.go` | modified | `3776b8c2df971f5d694785f82c758601a671fca3` | `b072fb930d944166b5b904205bc879049dec0713` | Policy/workflows/Go |
| `start-docker.ps1` | modified | `61b6c063781d58bac6da1243c87be88363c62f64` | `0b55c84fa3beb1fd60f180e8830b83dfcbcdd442` | Infrastructure/tooling |
| `tests/chaos/test_resilience.py` | modified | `0d451925f7cb76c6dade074774f3ed553fe3480d` | `77555c0da19058ad3e4bf6e9d8a552336b32cbcf` | Infrastructure/tooling |
| `tests/integration/test_aud269_275_278_351_populated_chain_postgres.py` | added | new | `7a375e3e63b41a75f0ad5f6d485877e39f810a5e` | Migrations/schema |
| `tests/integration/test_aud277_360_450_tenant_rls_postgres.py` | modified | `e0b2b1bde5f93bc0041ebe52d3e22b67cb921c26` | `55c512f08ba956d1b910b89df814c288b563f5a5` | Backend/auth/DB |
| `tests/integration/test_aud363_454_borrowed_session_postgres.py` | modified | `89a97fdc88ab084fd53361e82f15a4cefbc9a2b7` | `3433651108aed54097118cc6d7c6b680ff63172b` | Backend/auth/DB |
| `tests/integration/test_aud447_quarantine_cas_postgres.py` | added | new | `e92f8ef5a914e3d65b656e52e0e4d0a3293c8d51` | Backend/auth/DB |
| `tests/integration/test_rls_matrix.py` | modified | `78cd5fd4b7f2b2cd391d9e49ef89329e6d6c0401` | `ad1d08ac663b2dfb3778c1658a6f4080c6b14963` | Backend/auth/DB |
| `tests/security/test_mfa_race.py` | modified | `46a6b660ff15c87a6dd3204dce33b90ed86aacde` | `7476ac8a528493820bdabe45fc8069d6bc1cb541` | Backend/auth/DB |
| `tests/symlink_support.py` | modified | `9b5c8d9496272bcac2568402d8ad7e944feef17a` | `db3a9562cbd4bb0a69f07290b3428efd806f45a3` | Infrastructure/tooling |
| `tests/test_alembic_env_compare_server_default.py` | added | new | `ae1c3e3ca651afde5ea441bea1a4c79c8923f633` | Migrations/schema |
| `tests/test_aud275_reply_index_concurrent.py` | modified | `0a60661161450c0f2a467dda0e1423316b7fadf0` | `76df2786fcb35ef641888ade8aee117ca2c27d1c` | Migrations/schema |
| `tests/test_aud350_reconcile_migration_coverage.py` | modified | `4b86a4dafb4939ba5d87c35aab6b224cd90dcbb4` | `fce7e7dabc90fde2fe0e51c29f5e89325ea9954a` | Migrations/schema |
| `tests/test_aud392_password_policy_defaults.py` | added | new | `2f75bf2cff4117314424075e4b70b42098bce5a1` | Backend/auth/DB |
| `tests/test_aud447_quarantine_persistence.py` | modified | `87664d3fef0b45ba1dd903cd542b17291c48d146` | `03f4e1dd8226fbc433532de279bc74627418fdb9` | Backend/auth/DB |
| `tests/test_aud454_websocket_membership_race.py` | modified | `b0cf137e7c44736d2b3383459bd3ec827c01219d` | `aad0a4e453ca32a557e6107b4d2c21656b6f17fc` | Backend/auth/DB |
| `tests/test_auth_concurrency_extra.py` | modified | `cbe0f72310062d847c4fff4b5f15a093baacf619` | `c18d01fd6621243dbdd34874bb817774e783414a` | Backend/auth/DB |
| `tests/test_auth_coverage_extra.py` | modified | `a1f51437192fb735c01efe89b93de7229ad08db7` | `be81a4883c4af4a993ec08e688fda7dbd7dc37d1` | Backend/auth/DB |
| `tests/test_auth_recovery_codes.py` | modified | `115b61ca5bd15bf20656d1ce6bf4ef3cbf385a85` | `4aa81057eed4784636af7d6f7721fe7403e0bb39` | Backend/auth/DB |
| `tests/test_chaos_no_silent_skip_contract.py` | added | new | `84ba60350b778824c2794e9d56572d2495ca43bb` | Infrastructure/tooling |
| `tests/test_configuration_settings_inventory.py` | added | new | `09a3292afa33d68fdcfd5f1fda6e34d2951fd2f7` | Infrastructure/tooling |
| `tests/test_connection_manager_closure.py` | modified | `37634a9dd903a0a7b4aed5ebbe7f94aeedc41a79` | `4c7688dc8cca22f1786efb7dca00d23c75a93ff8` | Backend/auth/DB |
| `tests/test_docker_startup_contracts.py` | modified | `39700233cbdd860eec8aaf094980d15f820abd8a` | `889556805aad43a33cda0569be4460502d4e8d4c` | Infrastructure/tooling |
| `tests/test_docs_count_consistency.py` | added | new | `80a81ed80c1d43fc51a218629b65a3a19795f1d9` | Infrastructure/tooling |
| `tests/test_helm_aud168_169_followup.py` | modified | `8b527fb6b9c6cacf99f942f7eecf615e16f0c699` | `37e2509983144f2d299f523d9325558b902d598b` | Infrastructure/tooling |
| `tests/test_helm_ws_hub_replay_window.py` | added | new | `bb52a8c94ae7791882578edaf54a5dc2dbd7d474` | Infrastructure/tooling |
| `tests/test_historical148_squawk_admission.py` | added | new | `15dda0cefee65709da948cb8c44eff8df0aa1715` | Policy/workflows/Go |
| `tests/test_historical148_squawk_admission_workflow.py` | added | new | `c7c567920a1e2a66b5831d97d8f12f2b98da722c` | Policy/workflows/Go |
| `tests/test_historical148_squawk_policy.py` | modified | `fb49958e174752d906ef5551fe18175ba3d6bdc3` | `d07d7beabcabb21d843601109bb7c3c072d46abd` | Policy/workflows/Go |
| `tests/test_live_stand.py` | modified | `0f5ea79a4e6adb7fe5db66997d51aeaccbddf5a9` | `e0bfffdb4b913311704af704faf2caaefae2c43b` | Infrastructure/tooling |
| `tests/test_live_stand_subprocess_timeouts.py` | added | new | `7c50a557c3266b92d2c30de941f3a91d5e276166` | Infrastructure/tooling |
| `tests/test_migration_148642dd1207_diagnostic_ci.py` | modified | `3840ff66811bbed6d0a3922ca285281979d71f49` | `2a21cce5d0dc50d649eb579fb2e90dec6623b894` | Policy/workflows/Go |
| `tests/test_migration_148642dd1207_squawk_json_ci.py` | modified | `be0db760c4392b498c70f01588943264aef5a1f8` | `aebf2364875762d6772ba5cee9400f377897fa86` | Policy/workflows/Go |
| `tests/test_route_dependency_inventory.py` | modified | `3648bd1b3f7489e37ebe707b13d2e81e1415a6fb` | `02a314b8756e0a7ec859a14c181963b30865596e` | Policy/workflows/Go |
| `tests/test_secret_file_config_contract.py` | modified | `6909e4ffe2552a15b345b930ed7ed0252eea8806` | `7ec92b64d0b0c50555e09023eb26ea08e778bfa0` | Infrastructure/tooling |
| `tests/test_squawk_shell_propagation_contract.py` | modified | `872b8bb34ce25bf4087f3352d674d822d152c64b` | `7a510c558dc44fff1ba128d5a2dc191f8f0ae89c` | Policy/workflows/Go |
| `tests/test_start_docker_live_owner_key_paths.py` | modified | `c2478f708937c05430d1b4d7e751feee91d37bea` | `75c812b698c7b15b3ed310e22c03be17218ef332` | Infrastructure/tooling |
| `tests/test_symlink_privilege_probe_contract.py` | added | new | `14086ca7d71677ddf318e333fbe322fc7075375a` | Infrastructure/tooling |
| `tests/test_tenant_rls.py` | modified | `226e0697c9bf86d5fc802edccfa65b6b6fbe6abf` | `81e925fc12c86737048bb065894e19e5b0497a76` | Backend/auth/DB |
| `tests/test_verify_secrets_baseline.py` | modified | `a31e0e67c467b52b125d0bafcb33817dc8f9805d` | `03a4a53abae4a4040233845b33901d9292e16d11` | Policy/workflows/Go |

## Ordered continuation and restrictions

1. Preserve the terminal red 953 receipts and validate the next source with
   its own CI; do not inherit fixture recovery, merged coverage or full GREEN.
2. Publish only independently reviewed bounded test/fixture packages on a
   fresh branch lease. The password7 plus GIN/replay tests-first9-path draft is
   separate from acceptance documentation; actual scanner matches are required
   before any additional finite disposition can be considered.
3. Obtain actual GIN/replay persistence/interleaving RED before production
   repair. Retained DLQ error persistence and the discarded dead-letter
   telemetry remain separate causal tasks.
4. Implement migration-config isolation in staged tests-first slices, without
   giving the migration pod a new HMAC consumer as a shortcut or weakening
   genuine historical migration requirements.
5. Keep AUD-269 partial until the six local source-loss candidates and two unresolved definitions are resolved against the original criterion.
   Preserve raw Squawk failures, exact policy bounds and owned-only evidence.

No merge, deployment, production database operation, force push, expanded
secret access, global scanner exception or raised threshold is performed or
authorized by this document.
