# Post-pause audit review — 2026-10-28

Evidence snapshot: **2026-10-28 18:28 UTC**. This is a source/evidence
reconciliation, not an all-green or release-ready claim. Later publication does
not change the source identities or historical counts in this snapshot.

**Publication update, 2026-10-28 20:32 UTC:** the separate reviewed ledger update
is now published in
[f89776d996afb94ba58048e31b3de8e6e37249f6](https://github.com/egorribun/university_ecosystem/commit/f89776d996afb94ba58048e31b3de8e6e37249f6).
It records **377/512 accepted, 135 remaining**, preserving all 351 earlier IDs.
Its parent 1310be3c publishes the eight fixture/route-inventory/tracking-test
changes described below. The dated 18:28 snapshot and candidate wording remain
historical, not a claim that publication is still pending. This new source
requires its own CI; earlier passing cases do not establish its full validation.

## 1. Immutable scope and review coverage

The reviewed owner delta is exactly:

- Pause base [3fa77d7f31668e9fd8d740e91e775f74c5352adf](https://github.com/egorribun/university_ecosystem/commit/3fa77d7f31668e9fd8d740e91e775f74c5352adf),
  tree `7b8579fb771e67a485a4b75d6a5bfc7c83208211`.
- Owner checkpoint [b09532bd84ec7e51913fa7ea098f4d994fc44cb7](https://github.com/egorribun/university_ecosystem/commit/b09532bd84ec7e51913fa7ea098f4d994fc44cb7),
  tree `5c19964a472ab7e36c4abfb21d5ec1b4189e67c9`.
- Two direct-parent commits, in order:
  [0b4bab061774a67c3cba2e053c6083331aa46282](https://github.com/egorribun/university_ecosystem/commit/0b4bab061774a67c3cba2e053c6083331aa46282)
  (`ci(quality): capture bounded Trivy and historical Squawk diagnostics`),
  then b09532bd (`audit closure checkpoint`).
- [Comparison](https://github.com/egorribun/university_ecosystem/compare/3fa77d7f31668e9fd8d740e91e775f74c5352adf...b09532bd84ec7e51913fa7ea098f4d994fc44cb7):
  ahead by two, behind by zero; **256 paths = 180 modified + 76 added**,
  no deleted or renamed paths.
- Complete recursive Git trees, not truncated comparison patches, establish
  the full manifest. All changed files have mode `100644`; no migration
  implementation file changed in this particular owner delta.

The first substantive review covered all 256 changed files before continuation
commits were published: source, tests, workflows, configuration, documentation,
dependency-related contracts and their interactions, not only failing CI.
Acceptance reconciliation also considered all 161 unaccepted findings and 65
previously accepted IDs whose source paths were touched.

This document reconstructs the immutable inventory and corrects/rechecks
conclusions using later evidence. It does **not** present inventory rebuilding
as another full line-by-line review of all 256 files. A manifest row establishes
scope and blob identity, not GREEN, exhaustive behavioral coverage, or absence
of undiscovered defects. GitHub plugin reads/writes were the repository access
route for this continuation; no local checkout or deployment is implied.

| Domain | Changed files |
| --- | ---: |
| CI workflows | 8 |
| Documentation | 4 |
| Frontend tooling | 11 |
| Frontend | 102 |
| Go services | 6 |
| Python application | 27 |
| Python integration tests | 7 |
| Python tests/contracts | 75 |
| Quality inventories | 1 |
| Repository tooling | 9 |
| Root configuration | 5 |
| Rust/WASM | 1 |
| **Total** | **256** |

## 2. Continuation source and validation identity

Published continuation commits preserve the owner checkpoint:
[a926443a46abebc6f311bd2883708947cd8b7668](https://github.com/egorribun/university_ecosystem/commit/a926443a46abebc6f311bd2883708947cd8b7668)
and
[2b9e820248936f61d0a6798b2b0479d37048702a](https://github.com/egorribun/university_ecosystem/commit/2b9e820248936f61d0a6798b2b0479d37048702a).

The evidence source here is 2b9e8202, tree
`d0003151a84717631919a8a804b55c0c42255ee7`. Its tested PR merge
`cee407aedc79cb8dfd69f68d53fc986e0b53bf79` has the same tree.
The manifest covers only the owner delta, not those later continuation changes.

## 3. Corrected findings and causal fixes

### StaticFS attachment producer/schema mismatch; download claim withdrawn

The earlier HTTP-only download-prefilter hypothesis was **not proved**:
a manually constructed relative-URL attachment failed the ORM constraint
before reaching download. It could not establish a download 404.

The replacement test uses the real storage factory, StaticFS upload, attachment
service, message dispatcher and database persistence path. On 2b9, the declared
default produces `/static/chat_uploads/...` and fails INSERT/autoflush at
`ck_attachment_url_scheme`:
`test_real_static_chat_upload_persists_and_remains_readable[declared-static-default]`,
[job 122999652637](https://github.com/egorribun/university_ecosystem/actions/runs/40739668483/job/122999652637),
18:20:44 UTC. This is a producer/model failure, not an observed HTTP response.

The explicit absolute-base parameter is included by whole-file sharding and
absent from the exhaustive terminal non-pass summary. That establishes its
PASS through selection plus summary, not a separately printed named PASS row.

The producer/model incompatibility predates the owner delta. Historical
migration inspection did not find the ORM HTTP(S) CHECK in migrations.
Existing migration-created PostgreSQL databases can therefore differ from
metadata-created test databases: actual constraints, persisted relative URLs
and download behavior in such a database remain unverified.

Two invalid manual download cases were replaced, without changing the CHECK
or SQL authorization prefilter. A causal fix must align configured producer
URL, persisted representation, private delivery and StaticFS reader. Do not
assume the frontend origin is a trusted backend origin or relax the constraint
to make a fixture pass.

### Full Compose notification-metrics configuration mismatch

Source inspection finds a default notification-worker metrics listener on
`127.0.0.1:9101`, no bridge-interface override in
`docker-compose.full.yml`, and a Prometheus target of
`notifications-worker:9101`. The internal-network worker's own loopback
health check may succeed while that service-address scrape cannot reach it,
unless an external environment override supplies the missing binding.

This is a source/configuration finding, not a measured deployed scrape failure.
User-generated environment contents are not assumed. A correction must retain
standalone loopback defaults and avoid publishing this port to the host.
No runtime closure of AUD-366/AUD-391 follows from this analysis.

### Article mutation lifetime: semantic RED to GREEN

Moving the same account from article A to warm article B previously retained
A's mutation observer and pending edit state. The regression was RED on a926.
Source 2b9 keys the complete article component by article ID rather than only
remounting its comments subtree; the regression also checks both interaction
caches after completion.

The active case about retiring the old article's pending edit passed at
18:05:34 in
[job 123000064880](https://github.com/egorribun/university_ecosystem/actions/runs/40739668483/job/123000064880):
comments-pagination file **6/6**, shard **2491/2491**. This proves that tested
observer/cache boundary, not cancellation of every asynchronous article action.
NewsDetail patch coverage is 100%; full frontend patch coverage is not.

### Messenger collisions: semantic RED to GREEN; network recovery still open

The former finite immediate-retry loop could abandon reconciliation during
repeated query updates. The correction retains initial immediate attempts,
then waits for a quiet period on the exact owned query, checking query/session
generation before waiting, before fetch and after response. Temporary listeners
and timers are cleaned up.

The former collision regression passed at 18:00:20 in
[job 123000064895](https://github.com/egorribun/university_ecosystem/actions/runs/40739668483/job/123000064895),
shard **2915/2915**. Seven new quiet-period/ownership/cleanup cases passed at
18:02:00 in
[job 123000064898](https://github.com/egorribun/university_ecosystem/actions/runs/40739668483/job/123000064898),
shard **2500/2500**.

The original rollback-noninterference boundary is supported by the existing
34-case integration suite, but a failed direct refresh after a committed
mutation is not yet a reproduced recurrence of that defect. Operation completion
invalidates the owned queries; later cache writes can clear their invalidated
state. The production QueryClient enables focus/reconnect refetching, while this
direct refresh bypasses Query retry/error tracking and does not itself expose
the query-error Retry UI. These source facts establish neither permanent
abandonment nor guaranteed immediate recovery. Runtime characterization of
focus/reconnect recovery remains pending. Do not encode a hypothetical defect
as an expected no-retry behavior or treat the collision fix as full AUD-155
acceptance. Other messenger patch-coverage gaps remain.

### CI, fixtures and generated artifacts

Published corrections include finite live-suite counts, scoped media-query
spying, My Events mocks, translations, Pact/UoW interfaces, runtime-generated
synthetic test credentials, baseline metadata and generated frontend API files.

- Seven live-count boundary cases PASS, including current 222 instances,
  obsolete inventories and missing/extra results; focused cohort **848 PASS**
  in job 122999652637.
- [Pre-commit](https://github.com/egorribun/university_ecosystem/actions/runs/40739668483/job/122997537298),
  [Security & Types](https://github.com/egorribun/university_ecosystem/actions/runs/40739668483/job/122997537534),
  [baseline integrity](https://github.com/egorribun/university_ecosystem/actions/runs/40739668483/job/122998470035),
  [frontend OpenAPI regeneration](https://github.com/egorribun/university_ecosystem/actions/runs/40739668483/job/122999652173)
  and [Contract Tests](https://github.com/egorribun/university_ecosystem/actions/runs/40739668483/job/122997537336)
  pass. The old PowerShell timeout did not recur; no causal PowerShell fix is claimed.
- [Pact workflow](https://github.com/egorribun/university_ecosystem/actions/runs/40739668195)
  passes all three jobs; cross-process replay is not live-broker acceptance.
- Canonical route inventory capture is complete:
  [job 122997537747](https://github.com/egorribun/university_ecosystem/actions/runs/40739668483/job/122997537747),
  **54,365 bytes**, SHA256
  `ffc9c4c81effe6b9048f329ae887181de6cc6ffef72be76c81012c3ac866f9eb`,
  **156 routes: 143 canonical / 10 public / 3 worker, mixed 0**.
  Twenty-one changed rows plus the health function rename explain 24 reported
  discrepancies including the summary. This is AST signature ownership,
  not runtime DI/session proof. Verified ledger publication and capture removal
  are prepared separately.
- Backend `tests/contracts/snapshots/api_openapi_v1.json` is still stale.
  Its structural drift is the same four API changes as the now-current
  frontend schema, not evidence of an MFA regression.
- Two dynamic PG guards lack tracking comments; the current grammar also
  does not accept canonical AUD IDs. The revision-slot env name AUD148 is
  not finding AUD-148. Registered finding IDs and owners must be checked;
  recognized skips never substitute for actual owned-PostgreSQL execution.
- Registration, encrypted-mail task and locked-membership fixture mismatches
  require fixture consistency, not rollback of privacy/encryption/lock semantics.
- A direct declaration of the already-locked semver 7.8.4 and the My Events
  formatter postimage were not part of source 2b9. No dependency graph/version
  or integrity change is authorized by that metadata correction.

## 4. Current evidence is not fully green

All four frontend unit shards on 2b9 total **10,360 PASS**. The
[aggregate coverage gate](https://github.com/egorribun/university_ecosystem/actions/runs/40739668483/job/123007333876)
fails at **97%**, below the unchanged 100% requirement. Missing patch lines are
in EventsFeature, useChatWebSocket and messengerProjection. Passing unit shards
are not passing all frontend quality checks.

Backend shard 0 is **4811 PASS / 3 FAIL / 81 SKIP**: default StaticFS producer,
backend OpenAPI snapshot and route ledger. Other backend legs were still
running at this snapshot; no terminal full-Matrix count is claimed.

[Owned Core](https://github.com/egorribun/university_ecosystem/actions/runs/40739668573/job/122997532560)
is **46 PASS / 2 FAIL / 2 SKIP**. Desktop/mobile reset flows expect a public
registration ID despite the intentional generic `{status: "ok"}` response.
NATS outage is skipped. Restore neither ID disclosure nor broader access to
make the test green.

Other blockers include Source/Test Inventory, frontend lint/source contracts,
MapLibre bundle analysis, filesystem security classification and Alembic Squawk.
MapLibre's narrow approved proposal and the greenfield Squawk proposal are not
active merely because discussed. Squawk's raw warnings are real migration risks;
the ordinary loop stops at the historical failure and does not prove later
changed migrations clean.

## 5. Acceptance reconciliation

At this snapshot the published registry has **351 distinct accepted IDs out of
512; 161 remain unaccepted**. All 161 were considered, not only new code failures.
The following **26 evidence-ready candidates** were independently rechecked
against original criteria. Recording them in a separate reviewed registry
update would yield **377/512 (73.6%)**, leaving 135. This report itself does not
perform that ledger update or relabel its pending publication as complete.

Most runtime receipts are b09532bd / tested merge1c9eb18a, same tree5c19964a.
AUD-323 uses 9fe5e34c / merge3714b2da, same tree362fceeb. Relevant blobs were
reconciled against 2b9. AUD-333 has fresh 2b9 complete-file execution: its fast
active case is included in the 109-case suite, not separately printed as a
named PASS line. Historical cases inside failed jobs remain case-level proof.

| Candidate | Original criterion and bounded proof | Receipt and limits |
| --- | --- | --- |
| AUD-015 | Cyrillic PDF output: Real jsPDF output with the committed TTF recovers Cyrillic/mixed titles and date through the active font ToUnicode map; forced Helvetica is a negative control, and font-load failure does not save a PDF. | [activityExport.pdf-real.test.ts: 5 PASS](https://github.com/egorribun/university_ecosystem/actions/runs/40710285904/job/122895530702). 15:03:30 UTC. Build job122895530518 emitted the 199.70 kB font. Not browser rendering or current HTTP delivery. |
| AUD-147 | Head title/description duplication: Rendered root/page head composition has one localized metadata set across fallback, failed nested routes, custom metadata and navigation/language transitions. | [aud147-297.head-output.test.tsx: 12 PASS](https://github.com/egorribun/university_ecosystem/actions/runs/40710285904/job/122895530589). 14:58:39 UTC. Page bodies are stubbed; this is not deployed SSR certification. |
| AUD-162 | Declared Node engine range: The range ^24.15.0 OR >=26.0.0 matches root-lock metadata and engine-strict, and is a subset of installed/locked Babel, jsdom and all non-optional engine ranges. The old range produces counterexamples. | [Seven named AUD-162 cases PASS](https://github.com/egorribun/university_ecosystem/actions/runs/40710285904/job/122895530301). 14:58:17 UTC. The missing direct semver declaration remains a separate consistency defect; these cases used the verified locked installation. |
| AUD-279 | Lesson-note persistence: React lifecycle and IndexedDB cases exercise queued newer writes, leaving/reopening, account/session transitions and delayed initial reads. | [useLessonNotes.persistence.audit.test.tsx: 15 PASS](https://github.com/egorribun/university_ecosystem/actions/runs/40710285904/job/122895530318). 14:58:09 UTC; existing useLessonNotes.test.ts also 44 PASS in job122895530484. Not browser-process/OS crash durability. |
| AUD-297 | Route-specific localized titles: Login, registration, reset, settings, map and messenger, including parameterized variants, receive route-specific titles across nine route IDs. | [aud147-297.head-output.test.tsx: 12 PASS](https://github.com/egorribun/university_ecosystem/actions/runs/40710285904/job/122895530589). Same bounded head-output proof as AUD-147; not every real page body or full hydration protocol. |
| AUD-303 | Committed mutation versus refresh failure: Avatar, cover, email and email-MFA successes remain distinguishable from subsequent profile-refresh failures; old-account results are fenced. | [useMediaUpload.closure.test.tsx: 38 PASS; useEmailChange.test.tsx: 17 PASS](https://github.com/egorribun/university_ecosystem/actions/runs/40710285904/job/122895530702). useEmailMfa.test.tsx: 22 PASS in job122895530318. Controlled API boundaries, not actual email delivery; merged cover/MFA scope included. |
| AUD-306 | Request-local public SSR authorization: Real router and AsyncLocalStorage exercise authenticated, anonymous, pending and interleaved requests plus redirect-origin controls without shared-client auth leakage. | [_public.test.tsx: 49 PASS](https://github.com/egorribun/university_ecosystem/actions/runs/40710285904/job/122895530589). 14:58:36 UTC. Not hosted SSR operation. |
| AUD-307 | Existing default social-image asset: Default and blank-image paths point og:image/twitter:image to existing /icon-512.png. | [SEOTest.test.tsx: 12 PASS](https://github.com/egorribun/university_ecosystem/actions/runs/40710285904/job/122895530484). 15:05:02 UTC. Regular asset blob ee48b370623de8d8de18b1625e7e41b94eae91eb is 33,745 bytes; no current HTTP delivery claim. |
| AUD-323 | Missing news/schedule PostgreSQL tests: Real PG cases exercise claim serialization, concurrent image swaps, populated ownership-migration validation, schedule conflict locks, stale reads/cache and seed/API coordination. | [12 news plus 7 schedule cases PASS, none skipped](https://github.com/egorribun/university_ecosystem/actions/runs/40643936500/job/122669479742). 06:34:15–06:42:19 UTC. Entire job372 PASS/9 unrelated SKIP. Resolves absence of integration coverage, not comprehensive CRUD acceptance. |
| AUD-333 | Reconnect history refresh: The active conversation is refetched after disconnect/reconnect even after sendLeave clears the active-room ref. | [useMessengerController.branches.test.tsx: 109 PASS](https://github.com/egorribun/university_ecosystem/actions/runs/40739668483/job/123000064898). Fresh source2b9e8202, 18:00:05 UTC; whole shard2500/2500. The active unguarded case is 'refetches the open chat messages after a socket disconnect and reconnect'. The fast case has no separate printed log row: inclusion is established by complete-file execution and source inspection. Not full AUD-155 closure. |
| AUD-387 | Kyverno security-context precedence: Real Kyverno CLI rejects root/Unconfined overrides and tested host network/PID/IPC/path/port boundaries, including init/ephemeral containers; the exact SPIRE exception is exercised. | [72 PASS/0 FAIL](https://github.com/egorribun/university_ecosystem/actions/runs/40710285904/job/122893405468). 14:53:55 UTC. Not deployed admission/CNI evidence. |
| AUD-397 | Settings reduced-motion behavior: Real Framer accordion/tab behavior handles initial reduced motion and preference changes during the same mount. | [Layout.reducedMotion.test.tsx: 3 PASS](https://github.com/egorribun/university_ecosystem/actions/runs/40710285904/job/122895530702). 15:03:48 UTC; test-environment behavior, not an exhaustive visual review. |
| AUD-402 | Finite Vite build deadline: Invalid BUILD_MAX_WAIT_MS fails before spawn/preparation; accepted/default bounds terminate and clean up the owned child. | [16 named controls PASS](https://github.com/egorribun/university_ecosystem/actions/runs/40710285904/job/122895530301). 14:58:17 UTC; no relaxation of the timeout guard. |
| AUD-403 | Visual-smoke HTTP outcome classifier: Unsuccessful main-document HTTP statuses, including404/500, are rejected rather than classified as successful pages. | [Named HTTP-status classifier and broader failure controls PASS](https://github.com/egorribun/university_ecosystem/actions/runs/40710285904/job/122895530301). 14:58:27 UTC. Classifier behavior, not a complete visual browser run. |
| AUD-404 | Post-build shell precedence: Fresh dist/client wins over stale .output/public; Nitro fallback remains when no Vite shell exists. | [Both post-build-shell.contract.test.mjs cases PASS](https://github.com/egorribun/university_ecosystem/actions/runs/40710285904/job/122895530301). 14:58:23 UTC. |
| AUD-405 | Lock-bound Lighthouse fallback version: Installed Lighthouse CLI resolution is checked against lock metadata; inconsistent metadata and overriding versions are rejected. | [Three named CLI-selection controls PASS](https://github.com/egorribun/university_ecosystem/actions/runs/40710285904/job/122895530301). 14:58:22 UTC. Windows cleanup/overlap runtime cases skipped on Linux are not accepted here. Later test changes are only two inspected Prettier wraps; implementation unchanged. |
| AUD-408 | Clean-index Python-2-except coverage: The checker scans tracked working-tree Python with a clean index, preserves staged-byte semantics and fails closed on enumeration/read/type/link/limit errors; CI invokes it. | [All18 named cases PASS](https://github.com/egorribun/university_ecosystem/actions/runs/40710285904/job/122893404682). 15:00:29–15:00:35 UTC. No checker exclusion introduced. |
| AUD-411 | Rust/Python event-chain parity: Lowercase, uppercase and mixed-case stored hashes follow Python's case-sensitive verdict. | [event_chain_hash_case_matches_python_fallback PASS](https://github.com/egorribun/university_ecosystem/actions/runs/40710285904/job/122893405436). Real Rust/PyO3 suite93/93 passed twice. |
| AUD-412 | Zero-duration slot search: The Python binding returns no slot for zero duration with occupied and empty schedules while retaining input bounds. | [zero_duration_never_returns_a_slot_through_python PASS](https://github.com/egorribun/university_ecosystem/actions/runs/40710285904/job/122893405436). Same real Rust/PyO3 execution. |
| AUD-413 | Partition-expiry overflow safety: Checked retention/year arithmetic and out-of-i64 Python integers produce bounded false results without swallowing ordinary type errors. | [Unrepresentable-retention, out-of-range-int and maximum-year controls PASS](https://github.com/egorribun/university_ecosystem/actions/runs/40710285904/job/122893405436). Same real Rust/PyO3 execution; no panic observed in these cases. |
| AUD-415 | Positive PyO3 expiry assertion: The binding test uses real generated partition names and asserts old=true, future=false and malformed=false. | [test_pyo3_bindings_coverage PASS](https://github.com/egorribun/university_ecosystem/actions/runs/40710285904/job/122893405436). 14:56:36 and14:57:02 UTC. Current source lines1176–1209 retain the assertions. |
| AUD-419 | Truthful progress-artifact documentation: ADR-045 explicitly states that progress diagnostics are informational and uploading them as workflow artifacts is unimplemented. | [Documentation-only correction](https://github.com/egorribun/university_ecosystem/blob/2b9e820248936f61d0a6798b2b0479d37048702a/docs/adr/ADR-045-mutation-hang-diagnostics-without-a-kill-watchdog.md). Blob a5fd54e7a83e4b2e9c435c1fb5890b81640fb9be. No uploader implementation is claimed. |
| AUD-439 | Keyboard-accessible lesson dragging: The actual DnD keyboard sensor and pointer behavior are exercised together with disabled/delete-control boundaries. | [DraggableLessonCard.keyboard.test.tsx: 6 PASS](https://github.com/egorribun/university_ecosystem/actions/runs/40710285904/job/122895530318). 15:00:13 UTC. Not an end-to-end production editor test. |
| AUD-442 | Serialized checkpoint-registry bound: Actual UTF-8/JSON escaping, Unicode, reload and protected-room retention respect the persistent read bound. | [chatReplayCheckpoints.test.ts: 47 PASS](https://github.com/egorribun/university_ecosystem/actions/runs/40710285904/job/122895530484). 15:03:46 UTC. |
| AUD-460 | Account-scoped push buffers: Same-owner remount, logout and account changes do not expose prior-owner feedback; delayed old logout is fenced. | [Account-isolation suite: 3 PASS](https://github.com/egorribun/university_ecosystem/actions/runs/40710285904/job/122895530589). Existing feedback suite78 PASS in job122895530484. Mocked transport/worker deliveries, not live push infrastructure. |
| AUD-497 | Pure React profile updater: Actual React replay invokes the updater twice while committed query/storage side effects occur once. | [Replay case within useProfileSync.mutation-contract.test.tsx: 203-case suite PASS](https://github.com/egorribun/university_ecosystem/actions/runs/40710285904/job/122895530318). 14:57:44 UTC; side-effect timing is checked, not inferred from mocked setter call counts. |

The other 135 IDs in Appendix B retain their original criteria without an
invented readiness classification. Absence from the candidate packet means
this reconciliation supplies no sufficient acceptance proof, not that no
implementation work exists. AUD-247 and AUD-361 are not added by inference.

## 6. Next ordered work and safety limits

1. Preserve exact-source CI failures and results; no inherited GREEN.
2. Align the proven StaticFS producer/model boundary without weakening
   authorization, URL constraints or trusted-origin requirements.
3. Publish the verified route ledger and backend OpenAPI snapshot; remove
   temporary capture code once its intended artifact is verified.
4. Complete approved dependency metadata/formatting and fixture repairs;
   execute the strict AUD tracking tests before its implementation.
5. Recover Core's owned identity through authenticated evidence and bounded
   cleanup, preserving the privacy response and current session reservations.
6. Close behavioral patch-coverage gaps without lowering thresholds.
7. Publish only separately reviewed, source-bound acceptance entries.
8. Implement reviewed MapLibre/Squawk work only within explicit approved
   bounds. Temporary risk acceptance is not elimination of migration risks.

No secret values, session logs, scanner bypasses, new dispositions or lowered
required checks belong in this work. Preserve all intervening owner changes
and publish only through concurrency-checked updates of `egorribun`.

## Appendix A. Complete owner-delta file manifest

Each row is an inventory identity, not a per-file correctness or runtime verdict.

| Path | Change | Domain | Old blob SHA | Owner-checkpoint blob SHA |
| --- | --- | --- | --- | --- |
| `.agents/hooks/common.py` | modified | Root configuration | `420cbb26cb6eb4a1d9e84e479bb18c5186af5715` | `ed25ed053654741ff126cd1a6c3932a7b060da2d` |
| `.agents/hooks/pre_tool_safety.py` | modified | Root configuration | `b3f1e0ac79a1b8193791ce7e9a2f9056ea079a5c` | `ab19d3acb76fe3a028e92919c4d5c491a462e02c` |
| `.agents/hooks/runner.py` | modified | Root configuration | `03fad8af03b342d63b808fbb71f2966bce3de50e` | `2c0a16559de3fc89383a7b818f2004101d75c592` |
| `.agents/hooks/stop_quality_gate.py` | modified | Root configuration | `42624f2b6ced3bcdec77e9c1f6383c4cf7cc8db7` | `6b91d9cb620ea5dc230be800bf897c556497e2f6` |
| `.env.example` | modified | Root configuration | `86e59e33f36cee29293ef8fa61a076c205e9b18c` | `ee1f505fef7269218a5dcd7de45ac8b306b918b5` |
| `.github/workflows/checkov.yml` | modified | CI workflows | `c5bb8fbb0f65c975d571a6194bd9690c714ea02a` | `573b005fbb827e1708ef072d7d7778e63868e140` |
| `.github/workflows/ci.yml` | modified | CI workflows | `7933306fcf080a194e4124720d69fadff88a6267` | `eb16cb7480a545a4014efb1b96c72f65f64b94a4` |
| `.github/workflows/codeql.yml` | modified | CI workflows | `ca4bbe79b30fa45b69aafc2e7c20fbbdfce246d5` | `156f228e3bd25027bc2c24db4da8b0e06e704fa0` |
| `.github/workflows/contract-tests.yml` | modified | CI workflows | `d9a691b068324a1c1d79ef8b29eab39173d9dc11` | `c9bb8df53ecbbaead3509762a4b3f224448f1fd9` |
| `.github/workflows/dependency-review.yml` | modified | CI workflows | `61abbe7b1333db6bfa28439f7d53ab7aa673cfc8` | `864e81016caf2cb4a0559e9246a5c3abdaf5ca2e` |
| `.github/workflows/gitleaks.yml` | modified | CI workflows | `edba09f6ed0ce1cbee75e82661822cf1aaeeb3e4` | `4fc6e0c2e252eb55f1eca236d7c2d36736cfa7d6` |
| `.github/workflows/reusable-security-audit.yml` | modified | CI workflows | `57c076a55383018d71d0e182eda57e88835dcbf9` | `95d890cbf181b72453fd8b1624c2b3b0fe11b0fb` |
| `.github/workflows/zizmor.yml` | modified | CI workflows | `e303afbf4ea564a813b9a0010d374b0f18dcb60d` | `a4119f41a3107ab6797df5977e1a4374f6dcf6f8` |
| `app/api/auth/login.py` | modified | Python application | `6dfa8179ee6018e1de387ffdcc657c50f9e449ac` | `4a495986b0f037c1487164f1ac80d970d108cec4` |
| `app/api/chat.py` | modified | Python application | `9e020019c8f0bef03d63c324d35c104fea290218` | `8b96289a75cc3a2384f2f2906284fdc4240caeea` |
| `app/api/events.py` | modified | Python application | `659b4024c2c39daaaa6026b918ee0617dbabfdf9` | `d58d1657cc22f14353dcd438c6c9126b69f4cc0f` |
| `app/api/health.py` | modified | Python application | `1ca91690379f472d73fb900be80ba331a7c0822d` | `6c473258e27210af712ba283aa24f62b93bb7cd4` |
| `app/api/users.py` | modified | Python application | `d4114b16f9e45e892fe3ba73f58e0efcded4840c` | `ec68338268572e8a28ce67f6a501ffe42a801683` |
| `app/api/websocket.py` | modified | Python application | `924bb54466ee262a55fc899718b4d321546e9edb` | `4c05db60ad660f6d2524e4ddd610432ad320d20c` |
| `app/api/ws/auth.py` | modified | Python application | `0f928260491968a7d4b19ac387dc20672d27073d` | `35e2676f61deb6753a298b6a7da5b0edb4f539ba` |
| `app/api/ws/connection_manager.py` | modified | Python application | `94f3fce18da0998225dcaa659b33a3b1bfddd31e` | `ae78f4efa11d18504a01dae9d85b6719a44c5018` |
| `app/api/ws/presence.py` | modified | Python application | `b581b0d18903518e711a772bcbbf86f4ffac53aa` | `c5467082b445b640699ef6f8f283e21933e193cc` |
| `app/core/config/notifications.py` | modified | Python application | `77bb8f2d45a4ad51d70bcce0dab9792dab9e9838` | `c2e0212377644265c017cee21b4179ee5261f1d8` |
| `app/core/events.py` | modified | Python application | `fa6768de90731efff1aa931ca32a58807fe8170d` | `017101435b6cbb898dd244d24fb9277ce0c9b215` |
| `app/core/lifespan.py` | modified | Python application | `267e619bd8e29c0f80acc696fb33370d8e315140` | `ebb5613410c1383613d16883ade3cdd1bfb59079` |
| `app/core/localization/dictionary.py` | modified | Python application | `0154f2f2be2b11016a7834af1f27eec3dc78b468` | `1a17a38b3912554ebf76656da4b1431470759fe5` |
| `app/deps/cache.py` | modified | Python application | `c314c5b443a430f40547fe9ff82aac98ac052cbb` | `b1dcdd78033f9fb6958804477c9543c5d1187530` |
| `app/repositories/chat_repository.py` | modified | Python application | `8d2a7211110bcb9a212b087c10dd0911094f4403` | `c24477931fa06033d6f3d98604dd28649bcc650c` |
| `app/repositories/event_repository.py` | modified | Python application | `9cc69537ec2c0640d79828b925693cb33aec52ea` | `00cbcd4ee839319f524136f5725495c8e4dafabd` |
| `app/repositories/user_repository.py` | modified | Python application | `fc45eb2564aa5ea99f833c3da57a22590036e095` | `10f9ab6cb7bbcff3f765893a1c035c1699fd77c0` |
| `app/services/auth_service.py` | modified | Python application | `9b32797fbc8763bd14ce029718e0bf7829e8f380` | `425cc1317c51ea07b7336b9c8d43e20fb980781b` |
| `app/services/cache_warmup.py` | modified | Python application | `dee001f885e1e5a3067188e2158f9338be668e77` | `8002877acfc0b33bb18f1b62a18440c7447b813c` |
| `app/services/chat/command_service.py` | modified | Python application | `003d35aa8849c6a7ab8e0a8ab64fe2b6240b34fe` | `30c8fe9bb2550786b75d94c369982a769a5e9c20` |
| `app/services/chat/notification_service.py` | modified | Python application | `da9cf052f2888766a8543e33b65ec2322972fc62` | `c5e92fe173c1777c5921b49e2e01a76add0834f2` |
| `app/services/event_handlers.py` | modified | Python application | `3f25579b19acf744d2504b7e1d32f69c77a43793` | `86f8c3e16e244206d9807e051ed99d3440f5cad2` |
| `app/services/event_service.py` | modified | Python application | `d7b2f95b8a0b63f6873529f7784c0da72e0b9c29` | `7fe1d1b7cc76a5e25e8819f26a5837447bb6b8fb` |
| `app/services/file_scanner.py` | modified | Python application | `d3dd251c185ef771bdb04e73b50356e7d597cc3d` | `13838decc0efc10ce3d50ced62817356315d617f` |
| `app/services/user/compliance_service.py` | modified | Python application | `71e6c6ed089418b302f9ec8fd3c2ef546ae0d080` | `c31feab2a3cf4d7660f6ab3fff0958a9bde03b4b` |
| `app/tasks/email.py` | modified | Python application | `aa400a5e8e7b721b171ad85f8c1ffb6ae7fab625` | `babdd5f993968b548f9c68c391da3014d2036861` |
| `app/workers/outbox.py` | modified | Python application | `00641f9089a964d8cf864079a736ffddb163a63c` | `859ba2d4a89c6989d621b80916a968d8008039f4` |
| `docs/api_versioning.md` | modified | Documentation | `7f749c14175b627274f83712a1b81d815e553e2f` | `c6e88fb258887d586f08f9f16469d90178ee9cd1` |
| `docs/audits/AUD169-188-189-networkpolicy-runtime-harness.md` | added | Documentation | `absent` | `3a0a8760366725f1e25bec69157fbf3e2c570a70` |
| `docs/superpowers/plans/MVP_MASTER_PLAN.md` | modified | Documentation | `52d7c7b22c976cbc68bde6ccbd3f3dbffaca2d16` | `f7458de7318cbb4cb86f3cad67dd69b0523e7733` |
| `docs/superpowers/plans/STATUS.md` | modified | Documentation | `5dd55f5b37a852b6007e41e7e825e83731bd11c4` | `9b5482a3a783875c0fc396e6e0a55bc674decb06` |
| `frontend/index.html` | modified | Frontend | `95c12e3c36020ff614873483324db990f94c641b` | `a6069b8749826554762b5d2261369e680d254b98` |
| `frontend/scripts/aud162-engine-contract.test.mjs` | added | Frontend tooling | `absent` | `0d28359c114c02f24eaab2c68528f8279dda8334` |
| `frontend/scripts/build-orchestrated.contract.test.mjs` | modified | Frontend tooling | `e9a471e0834868580701a4f92e602216f6756c6c` | `2c07fda382911d3050662d4a97120fa40cc20ffd` |
| `frontend/scripts/build-orchestrated.mjs` | modified | Frontend tooling | `aa7ea4265ec21ed9d88fc253785d0bc9660adb72` | `b1ad151d15e5037dda163fb2cf0d39028ee3fd97` |
| `frontend/scripts/frontend-quality-contract.test.mjs` | modified | Frontend tooling | `8e7c6dde3f5de3412298286a407549d254bb80dd` | `6d6de298b6754b6df1f8d3109913180b4bfc163b` |
| `frontend/scripts/i18n-scanner.mjs` | modified | Frontend tooling | `e7de27e735a4adee0b1a2e0375a77747a2c89d86` | `3f6b067a29304db6739fee30fb4639c37063ef10` |
| `frontend/scripts/i18n-scanner.test.mjs` | modified | Frontend tooling | `e0487173b51598771257cc5ed2e21a7b8a08618b` | `c6318cd8c7bbaed013204bc9c5d17fe3cddf9bcb` |
| `frontend/scripts/lhci-windows-fallback.mjs` | modified | Frontend tooling | `0941f4c2e6eb961e6d18b1c7f4be497b841fb721` | `b107b5f7c9c898facaf63a5e52dac5bdf27d751f` |
| `frontend/scripts/lhci-windows-fallback.test.mjs` | modified | Frontend tooling | `7ee6ea7e67e9569c9ecd7d6f74da48396d70037c` | `0e18e07224031554853dac0234ead65f250830ea` |
| `frontend/scripts/maplibre-build-metadata.mjs` | added | Frontend tooling | `absent` | `05ec0a4d475f6113351ea870f9e6a17f025a634b` |
| `frontend/scripts/maplibre-build-metadata.test.mjs` | added | Frontend tooling | `absent` | `b508a52a234578badf17e1f28333b58ed46fa3d2` |
| `frontend/scripts/verify-backend-ws-wire.mjs` | added | Frontend tooling | `absent` | `07e0da86075bc340546c8edc70ad6149d761e994` |
| `frontend/src/__tests__/m1_offline_stress.test.ts` | modified | Frontend | `214d307b422bf4797a809a208c1f26deb3d8f0ab` | `22415c105967f730177ef3b0376544974d16147a` |
| `frontend/src/api/__tests__/stories.closure.test.ts` | modified | Frontend | `bd0d3ce6fc38029d4d5926625b6cced1c9f465b3` | `e82ee1ca7df476d53b5b7f435e19285522f9ee8a` |
| `frontend/src/api/hooks/__tests__/myEventsPage.audit.test.tsx` | added | Frontend | `absent` | `9fef669a9bb728d53477a60ad0fd3678e576b746` |
| `frontend/src/api/hooks/events.ts` | modified | Frontend | `06b70b61de3ba82452fd1c3f356cdc873467bace` | `1616d62112e8782fab8a9d63e4bf2379d8c42610` |
| `frontend/src/api/stories.ts` | modified | Frontend | `1d94eb8dac80df4321f5e688bc70a9ce7cbfd1ac` | `45799f8e41aea40972bc1958ae232024d6d5f4dd` |
| `frontend/src/app/__tests__/queryClient.persistence-ownership.test.ts` | modified | Frontend | `2c3468b2339f4685af1545d13ae0068af7f2607a` | `d1aa80c834924a89698e72107dff799b86cd4b59` |
| `frontend/src/app/__tests__/queryClient.quota.closure.test.ts` | modified | Frontend | `7e0dde6092b787a6f2bc3ecf4ab13cd881093912` | `a84569ccd51bd7f42bad30c8c7c4981f85852f9d` |
| `frontend/src/app/__tests__/queryClient.session-isolation.test.ts` | modified | Frontend | `067347504e85793687d0d516320231ccc60df1f1` | `4a3a0046e711904bcddc0ecdee74510b9b58a793` |
| `frontend/src/app/queryClient.ts` | modified | Frontend | `e873638de871ffa120d1333ad44406b9669d003c` | `333cd99561bbe6d8309d411178c3ee3817116c6c` |
| `frontend/src/app/sessionMutationCache.ts` | modified | Frontend | `8cbb67846c676ac3d13d540a988814db00c49e6a` | `3d8bc2144d9800b085549aeb20b9a25aa897f69f` |
| `frontend/src/components/events/EventCard/EventCard.tsx` | modified | Frontend | `4e3dd19050e6212f68bfbf54500a5233cf230563` | `043af7e06400f5e2100fc821a1f81b81b287a60d` |
| `frontend/src/components/events/EventCard/__tests__/EventCard.my-qr.audit.test.tsx` | added | Frontend | `absent` | `7e7a4a16635bbf5c4d2cf0196c6ed7619c7b500c` |
| `frontend/src/components/feedback/__tests__/LivePushToasts.account-isolation.test.tsx` | added | Frontend | `absent` | `29270390e2d9ea3f52138f979c21dba330cbf02d` |
| `frontend/src/components/news/NewsCard.tsx` | modified | Frontend | `3e8ea9b0338bfd9567a674c3943754ae912e2c83` | `931efe7aba3740ccb0e15b8d02e3f65a1614623b` |
| `frontend/src/components/news/NewsComments.tsx` | modified | Frontend | `3ef5bce48e38dac36290bef2b41b1272b0b50777` | `c680faf36ff6716005b6ca779ee41745a71d18ef` |
| `frontend/src/components/news/__tests__/NewsCard.closure.test.tsx` | modified | Frontend | `ce3ae135b5123b4c10de7985718772ee86938867` | `e46091d61ccd712a886463f3c2a00a1a234bd8e5` |
| `frontend/src/components/news/__tests__/NewsComments.pending-actions.test.tsx` | modified | Frontend | `fa9dd80c1cd962cb41dd079ab24cd33af1622e09` | `52c44034a7604785c6b95418d15cec54f2d9ab7f` |
| `frontend/src/components/news/__tests__/NewsComments.test.tsx` | modified | Frontend | `d221aba96a0ed3159edf0d53ce691f91236e6e16` | `3a4cebfb0bbe65e9275b5b425eee3623984b4325` |
| `frontend/src/components/schedule/DraggableLessonCard.tsx` | modified | Frontend | `3929de938d8a834872d284b740a31ab2300e4777` | `a62bba80b3d5cc05c0410f8bc66ab227ec596c9b` |
| `frontend/src/components/schedule/__tests__/DraggableLessonCard.closure.test.tsx` | modified | Frontend | `69a517721ed2287968c339163adbeece59dcab83` | `42a4c6172082886a0cde8e197746f0866dd90399` |
| `frontend/src/components/schedule/__tests__/DraggableLessonCard.keyboard.test.tsx` | added | Frontend | `absent` | `0d25d87536e522d3b41e7813c0b96f62b0e340d4` |
| `frontend/src/components/settings/ui/Layout.tsx` | modified | Frontend | `bb2ef19e91b94412893e6c34026c6b465958363a` | `5da3827516151d68ef36c691c5c985c6ad1af520` |
| `frontend/src/components/settings/ui/__tests__/Layout.reducedMotion.test.tsx` | added | Frontend | `absent` | `2c9813a9809be5d0476a50d99e26e036d1f41182` |
| `frontend/src/components/ui/PageRouteSEO.tsx` | modified | Frontend | `a3463b5f3f99dfebe6df63c2f93df870c6982a35` | `4f4acb78a210ea980146392cb19fa3814d012235` |
| `frontend/src/components/ui/SEO.tsx` | modified | Frontend | `b878d2aa6f2e9b08aecdc27e775461865ab76380` | `9ba95f920650ceb8d4d8164182e3b99104eee4fe` |
| `frontend/src/components/ui/__tests__/SEOTest.test.tsx` | modified | Frontend | `7476b01696f5f4d94e3c0360938d94e2db78ac87` | `8154eee04c81821a71a5e86299d444efea47b606` |
| `frontend/src/components/ui/__tests__/ui-survivor-contract-3.test.tsx` | modified | Frontend | `c3181822d57be444f04dced5b986883cab85b477` | `926d18c6b2146a67787009c52cbe6c0c9640f700` |
| `frontend/src/contexts/MessengerContext.tsx` | modified | Frontend | `340b8009e089a8a37259273f878c2f7aa68e2a9f` | `b69343b4734f11cf9d994901d9ac4852d6c71876` |
| `frontend/src/contexts/MessengerShellProvider.tsx` | modified | Frontend | `1bbaa2d850a16251d05cb6be5bb2d5ba7ff63f69` | `b77c25eedbf8974ded98424e9038e4703ca79b15` |
| `frontend/src/features/events/EventsFeature.tsx` | modified | Frontend | `77fb2fb96dff66678bd7663dadca2a8ffd3aa5e1` | `71ff2c7a6504be3d6531d4f81074b8a244a9e8a8` |
| `frontend/src/features/events/__tests__/EventsFeature.my-page.audit.test.tsx` | added | Frontend | `absent` | `d42061897aebbccfa12d48214c8489a4f5fb341d` |
| `frontend/src/features/events/components/EventsList.tsx` | modified | Frontend | `98eb33f8ea6cfb6ba0360e27e6115dd8be6c1e75` | `9f5ebd58fd0924e06f7596b55de0bede5b33db54` |
| `frontend/src/features/events/components/__tests__/EventsList.my-page.audit.test.tsx` | added | Frontend | `absent` | `e8eedef3f37f363baf2700da970b162171b83b73` |
| `frontend/src/features/news/components/__tests__/NewsHeader.ssr-i18n.audit.test.tsx` | added | Frontend | `absent` | `67f1392e127c0c5221b962247b9e7f30fa9f942e` |
| `frontend/src/hooks/__tests__/chatReplayCheckpoints.test.ts` | modified | Frontend | `f5c96f7067fa585c1576f4ebd31c035f506bd7c7` | `ed19ce2f3acbc44c8baf9bc5475549355d1c89b0` |
| `frontend/src/hooks/__tests__/useEventRegistration.my-qr.audit.test.tsx` | added | Frontend | `absent` | `6af8d0d456d682dcc82c9cc24b3aa5f19b39ac34` |
| `frontend/src/hooks/__tests__/useLessonNotes.persistence.audit.test.tsx` | added | Frontend | `absent` | `6dbd37f68a15da10576d7e17e0b365e1cfa61097` |
| `frontend/src/hooks/__tests__/useNewsInteraction.offline-fail-closed.audit.test.tsx` | added | Frontend | `absent` | `cf4d5049cd64dd825f35a98f5c3de7e219f3eca8` |
| `frontend/src/hooks/__tests__/useNewsInteraction.test.ts` | modified | Frontend | `280df90e1df7526df51fddec161de823f7ff4271` | `a8fc332eb1d98688a07ff770e783d5fe8499d860` |
| `frontend/src/hooks/auth/__tests__/useProfileSync.mutation-contract.test.tsx` | modified | Frontend | `8c69b58e28dae450a480cda3c230704460e3309b` | `71f824d7cfb6e93206d0a02160c0b026836fa107` |
| `frontend/src/hooks/chatReplayCheckpoints.ts` | modified | Frontend | `e30f63bb831c011f29e97385865f49ae36e7320c` | `17e763d02748a91d8d73f25707c02f3bf1c98871` |
| `frontend/src/hooks/features/__tests__/useMessengerController.branches.test.tsx` | modified | Frontend | `466bf073e4280109716ddf5258cb94c85516c10c` | `5ddf135fcb45fb10ee4109c39ce4ef8f576455de` |
| `frontend/src/hooks/features/__tests__/useMessengerController.rollback.integration.test.tsx` | added | Frontend | `absent` | `998d08eda4c3bb72beabacd320d1bdb6e394bd3c` |
| `frontend/src/hooks/features/useMessengerController.ts` | modified | Frontend | `645c196823350b11334648f6ae06763f1f53cedb` | `8d60f96a89c951c2eac4787008fa8aef0cd231e0` |
| `frontend/src/hooks/messengerProjection.ts` | added | Frontend | `absent` | `9bb0762cda23f2a75afb6b80c0ae5a8c5f92952b` |
| `frontend/src/hooks/useChatWebSocket.ts` | modified | Frontend | `d3397e5b5c7bbab8d37c4b8c0c4705cb427c9ee4` | `e6121cc5bc55f960be039f9a1397b1e7bcfc644f` |
| `frontend/src/hooks/useEventCardLogic.ts` | modified | Frontend | `ef29648d98c2425e698764c20fd48edc34f3758e` | `20b84c2c3c2a16f4ad05705ffb26ef469b744641` |
| `frontend/src/hooks/useEventRegistration.ts` | modified | Frontend | `6f739935d26569cccb295542d7836950df4cd0b5` | `9ffe15db2291a52a0a6b4d50a7d064904f5ab4e3` |
| `frontend/src/hooks/useLessonNotes.ts` | modified | Frontend | `17e840044c57b72533d394a7ba52854364935ea8` | `3b9874ce45438b7f5e3fa567b5473abda5361e83` |
| `frontend/src/hooks/useNewsInteraction.ts` | modified | Frontend | `a28df719b174ea2a7a51a1a076064cd614dd2b2a` | `cb4c97e23a045aa4310241548e56ceb1c08909f0` |
| `frontend/src/i18n/locales/en/news.json` | modified | Frontend | `19ef5d9566e6f19e473adb38ce1fa3aac8ddbbff` | `9e288eb745854bfa0b0dbab55edaf56a9aeab17a` |
| `frontend/src/i18n/locales/en/settings.json` | modified | Frontend | `f4f09edb966bb1424a82817b33eacda259089717` | `814cf97c78a2b66dcea9e77e37e0a630801dd55e` |
| `frontend/src/i18n/locales/ru/news.json` | modified | Frontend | `f9ca041cdb1fd4cb028c9587b9e06509d1965758` | `42385a1fb5a5fc848e8bf2164d5a9740f9be7ebf` |
| `frontend/src/i18n/locales/ru/settings.json` | modified | Frontend | `d5b5857f13ff6c6495e133c5aee739e83e08bec4` | `1096bf74eeacd0942209826b897f3fadba68d6fc` |
| `frontend/src/pages/NewsDetail.tsx` | modified | Frontend | `51ed749de5b281efbfbcbb7d143fa599571cbcfb` | `d0c3a2d05f05523f54c1b0c9f09198d24dd3db3a` |
| `frontend/src/pages/StoriesAdmin.tsx` | modified | Frontend | `e07603460955b50c2e57b4cc878220633a52b48c` | `f4e5023f954c801b95577eebb0855aa5e837a59e` |
| `frontend/src/pages/__tests__/NewsDetail.comments-pagination.audit.test.tsx` | added | Frontend | `absent` | `223b9751d1fb7f405c08dfc0c03c5eff91dfcc9d` |
| `frontend/src/pages/__tests__/NewsDetail.test.tsx` | modified | Frontend | `cf641577d89d7275c24f4660c97191e016a10859` | `b4903e97364de68564829bdab0be70cc679d9274` |
| `frontend/src/pages/__tests__/StoriesAdmin.test.tsx` | modified | Frontend | `a341236f0cfd9ca07e406e5e8da0fad3af20692d` | `6f957d78cced0e9e1f83ccc9f2b1de1efbfc0726` |
| `frontend/src/pages/settings/hooks/useCoverUpload.ts` | modified | Frontend | `8d519c1443777c6fd290b1f54d4dd3c6df0064b9` | `cde5809ff3090780e27d497422bdecb85c9e868a` |
| `frontend/src/pages/settings/hooks/useEmailMfa.test.tsx` | modified | Frontend | `a3740c03e46ebb2d099ab3f334098c99160cf971` | `cc7fa7055df72e48eb7ecc751cc45a84f4b3a7b7` |
| `frontend/src/pages/settings/hooks/useEmailMfa.ts` | modified | Frontend | `6ba91b1c4798f818c68d6ffbf1c258670cbb5511` | `a77cfb837ac64744470d1f154ca75b307778a099` |
| `frontend/src/pages/settings/hooks/useMediaUpload.closure.test.tsx` | modified | Frontend | `7c7e8726e59a48bf0220ec6cd339ebe9350650d3` | `ffd9f1ebb7384c39a2a20b5c6181bc5f4a70b80d` |
| `frontend/src/pages/settings/hooks/useSettingsSessionIsolation.test.tsx` | modified | Frontend | `6e12de8e413685b2aa18bd567b5aa99e945b66a3` | `744525cf976c10723a39c8d9b057bd69dd4208cc` |
| `frontend/src/routes/__root.tsx` | modified | Frontend | `9e67966abc14e8b44adfa4012e836402f2e10c17` | `e53560f637c7c3de43ebd6d39898e652d84b69c6` |
| `frontend/src/routes/__tests__/__root.activity-hydration.test.tsx` | modified | Frontend | `288c4f886940a963fd9b9b18c71bb6f9822f3517` | `4b8e81023c55207ae4c0182bab68e2ee085a11d2` |
| `frontend/src/routes/__tests__/__root.test.tsx` | modified | Frontend | `4676d09f13854d9aa560cfc6fcba6506190bd076` | `9cbf0a60b9705bac3db2b35395768f37e09522d2` |
| `frontend/src/routes/__tests__/_public.test.tsx` | modified | Frontend | `c48d984e863913e7500286c2470237aaff9cbe14` | `9f33a21d12b510b691aba0a165952cd5595b084d` |
| `frontend/src/routes/__tests__/aud147-297.head-output.test.tsx` | added | Frontend | `absent` | `5523e4ca55ca613a54e3e04b6d9eeeb1b4c52fcf` |
| `frontend/src/routes/_public.tsx` | modified | Frontend | `6159efa1b1e5b61b23a8afec460a557249f4f6c4` | `b7d85264a11ac1a9ea433d1c1df84f5d474a6bc4` |
| `frontend/src/sw/__tests__/audit375.legacy-safety.test.ts` | added | Frontend | `absent` | `6c05ff1ffe7256de98179d856f0eb4bcf6edf337` |
| `frontend/src/sw/__tests__/audit375.queue-serialization.test.ts` | added | Frontend | `absent` | `0f3f7dddd7da436396d562ecf099b2466877ec00` |
| `frontend/src/sw/__tests__/audit400.runtime-cache.test.ts` | added | Frontend | `absent` | `4125a9670742c446f0b66a176a382bf23a698f19` |
| `frontend/src/sw/__tests__/m1_offline_stress.test.tsx` | modified | Frontend | `a0eab70fc8a161b82846bda69e01c7ca75a285ec` | `0e23af0174525059f541119b729682e81a10f5a6` |
| `frontend/src/sw/__tests__/offline.test.ts` | modified | Frontend | `ec5cbf64c32098d0105484f02f3eec57e1af5984` | `e7bad16ec9fcf4b75a05ee7a1e4dff9e9f92c54b` |
| `frontend/src/sw/__tests__/offlineMutationQueue.closure.test.ts` | modified | Frontend | `4ab64399368268de1f4cadbd9a9b9f672b9ce6cd` | `c3896cda8e4ecc95d0dc20ea033535a5c66bfe1a` |
| `frontend/src/sw/__tests__/offlineUpgrade.test.ts` | modified | Frontend | `470c60de892e4981007d5d50f0bd1ced807bdef6` | `49de6846dd8b4f69ac0cef8e75b00e10493d5b1f` |
| `frontend/src/sw/__tests__/sw_offline.test.ts` | modified | Frontend | `cfb844fb3dc3f173a659d765a94d9b2f26549a89` | `b1f332296841d99e6710c7c3d9dc13709d2a5246` |
| `frontend/src/sw/offline.ts` | modified | Frontend | `b9724e87b49ee430bde9728e6f15a8e68b095c00` | `5ca11173e67992ab63b997c15c6a8019753e3991` |
| `frontend/src/tests/hooks/useChatWebSocket.test.tsx` | modified | Frontend | `da636c7cbb218078b6649fdca0b3f1c6fd6325c8` | `f39ab78a770a9186db7f326e96ad1d65d33d4852` |
| `frontend/src/tests/sw.test.ts` | modified | Frontend | `ee79707ee2c864868b6c7dd11b47b5d2de694094` | `845457197c3ea34e8c786bcb2de1a8ff5b3c49b6` |
| `frontend/src/utils/__tests__/activityExport.pdf-real.test.ts` | added | Frontend | `absent` | `497857d2b764d92713193bd085f92a5df8160ee4` |
| `frontend/tests/e2e-live/aud178-reset-referer-csp.live.spec.ts` | added | Frontend | `absent` | `e240e2252254ecef0512a4e8ea39c5f70eb03fb3` |
| `frontend/tests/e2e-live/live-ui-diagnostic.contract.test.mjs` | modified | Frontend | `1a6b6d6603ce799612aa6d8831f4a6a433bff2f2` | `68409ea6b1fd64a2985f162ba08ed63085a49de6` |
| `frontend/tests/e2e-live/password-reset-live.contract.test.mjs` | modified | Frontend | `b7535a9f3903cca9291235d679931701d13be072` | `657c3d95df8cd31cb1cbe75ac451ceeb5b884401` |
| `frontend/tests/e2e-live/password-reset-registration-action.ts` | modified | Frontend | `21cc25f8cb2534d65e9033e6948e85948c127b76` | `d9f053aeb9299d1129769a48cbaac6603f954bab` |
| `frontend/tests/e2e-live/password-reset.live.spec.ts` | modified | Frontend | `5a17e084de41d846d4c47906828f221224929caa` | `41a3098bf22067b27bdff096ef933ce24766cc93` |
| `frontend/tests/e2e-live/ssr-hydration-i18n.contract.test.mjs` | modified | Frontend | `3fc817f3c11ea2e85383737aa74206c2002d1387` | `816ce82ae6aaa929c709377581fa9002cb939fa6` |
| `frontend/tests/e2e-live/ssr-hydration-i18n.live.spec.ts` | modified | Frontend | `281b46440770839eeaf2e7c41180c07f0548f08e` | `be2572ed6d01e810f359d6a9c0d2131d08016ba2` |
| `frontend/tests/e2e-live/ssr-news-locale.d.mts` | added | Frontend | `absent` | `2c2d1a1b08b95b26893d5b48908a2218b4d82c6d` |
| `frontend/tests/e2e-live/ssr-news-locale.mjs` | added | Frontend | `absent` | `facacc00efc11b8f8187973a2d4f4f1714820e6e` |
| `frontend/tests/e2e-live/story-viewer-keyboard.live.spec.ts` | modified | Frontend | `4c9383071ff8acaa2319c28ea34a3e778613b302` | `2bd8a8bb4d2c042380993e8eb2cffc2de6c6e42c` |
| `frontend/tests/e2e/aud151-readiness.d.mts` | added | Frontend | `absent` | `c8b76801de7ce28149e293d1660ea175acdf4a4f` |
| `frontend/tests/e2e/aud151-readiness.mjs` | added | Frontend | `absent` | `dbc398ba89ad430db8415003945f8265b41ac6a8` |
| `frontend/tests/e2e/aud151-readiness.test.mjs` | added | Frontend | `absent` | `8d25f1f9d7c48b44f57951c5c77b3cf8965a752c` |
| `frontend/tests/e2e/aud304-dark-class-variant.spec.ts` | added | Frontend | `absent` | `0198adefabca6186531e88531d8900895c243328` |
| `frontend/tests/e2e/chat-realtime.spec.ts` | modified | Frontend | `6622a522d652c16fd765b693ee9bd7415237d27a` | `e2820cf6f914ed508e2d8ae0b6b033bdb240bbbc` |
| `frontend/tests/e2e/news-create-admin.spec.ts` | modified | Frontend | `fb7bc1ecc768d2ef6626a3e85044baaf45ce36ae` | `2ec30fc202488d52e5f0eb18bf6cdb733fa11db6` |
| `frontend/tests/e2e/rate-limit-ux.spec.ts` | modified | Frontend | `df4e4e8a27a5d1d70fd3be6235f64dd3bb5e2f0a` | `f75a2dda913a32886079735d1d253086099c407a` |
| `frontend/tests/e2e/sent-bubble-contrast.spec.ts` | added | Frontend | `absent` | `fe5f55db854880149ea86af4ac0326d5f97c11fb` |
| `frontend/vite.config.mts` | modified | Frontend | `814d28c2faef534941359dc39f08a59069f06cd8` | `44835bf854a99b63175014bce783e49a19273e92` |
| `native/rust_ext/src/lib.rs` | modified | Rust/WASM | `a7de3fa85c8b7834b82084797e8ee94ea8d1aa00` | `4081df2e847426253529e0daa30bce9cc4bef08c` |
| `quality/ci-check-catalog.json` | modified | Quality inventories | `3c67846c5e366d010327677257796d97f91a781f` | `9fd97b6fa5fc48ef91ed163320cc5c6f7b115201` |
| `scripts/chaos/run_chaos_loadtest.py` | modified | Repository tooling | `7742ddd8704ab4791a7c90a03c5567b804d19c62` | `97de1812fdad5e18096351017ae9cb311803e36f` |
| `scripts/check_route_dependency_inventory.py` | modified | Repository tooling | `e52d21349a203dd3455719881cf2801ccdbc752b` | `7c343cc3174489f9de0e2198532b0c12d2053d84` |
| `scripts/ci/inventory_go_binaries.py` | added | Repository tooling | `absent` | `1c47c85afb0a498fafa72b914b0bfb8955c8c803` |
| `scripts/live_stand.py` | modified | Repository tooling | `78fff2117738d2e818c3837ab96c717d9aa9da1e` | `fc0dc6682c2f6d35b9be471c6606a53147b57d08` |
| `scripts/owned_client_ip_probe.py` | added | Repository tooling | `absent` | `1494a28965a565672a257a404fe6c5eccc870ac7` |
| `scripts/quality/normalize_coverage_reports.py` | modified | Repository tooling | `03212324427c67b5c77ac3c2656a28783b332626` | `6eea9dcda6eff4c8c7f73a9b7dd9827c74fa51b5` |
| `scripts/quality/validate_quality_contract.py` | modified | Repository tooling | `9ac27e1ce8cca47153f78ba2176896a580987410` | `c63bb937f14e655599dc68dae191116e91d8f0df` |
| `scripts/quality/verify_dependency_review_scope.py` | modified | Repository tooling | `85537583350ad9956421e2896dd3660522fbebb4` | `33279c7d93f285026c909359792559fa6a43e696` |
| `scripts/seed_admin_data.py` | modified | Repository tooling | `26943321f6a29ea88443620d1ea43e00b42a8f97` | `a031a8f2a1ad94ee2cb40abf71df200e279c7be7` |
| `services/file-processor/cmd/file-processor/aud369_temporal_tls_test.go` | added | Go services | `absent` | `3bc3703c9534d4de1ddf2fcff3210a1d7ba0f6eb` |
| `services/ws-hub/internal/contract/cache_invalidation_provider_test.go` | modified | Go services | `c04ee04b310e65f01ec8d2d5af4452f9c22cbdea` | `5629f3a23a4f092b34cc991c04d26cf46c039438` |
| `services/ws-hub/pkg/hub/aud320_python_contract_test.go` | added | Go services | `absent` | `401501374eafae7966751529bc06733b9f6e7401` |
| `services/ws-hub/pkg/hub/aud334_broker_integration_test.go` | added | Go services | `absent` | `0eec3d98add7858f9384a1eb4ed4b2bd43ac94cd` |
| `services/ws-hub/pkg/hub/aud334_replay_error_backpressure_test.go` | added | Go services | `absent` | `0db11506270240a04f000a3b53faedb4fbaa49f1` |
| `services/ws-hub/pkg/hub/client.go` | modified | Go services | `d74d55167253f6e23d13a262abc242dded89c950` | `735fef71e08019f43c02ef5d18a3ac2d86021018` |
| `tests/contracts/pacts/ws-hub-university-backend.json` | modified | Python tests/contracts | `f031c2bdc25a7256fa86f0b35b9b1f248c30bab4` | `6a155e74ff13925e6bcb1dbf35ecace9acb7e808` |
| `tests/contracts/test_aud310_409_hooks.py` | added | Python tests/contracts | `absent` | `8db481a19452b9019f38eb58f1d87d52d631460e` |
| `tests/contracts/test_pact_artifacts.py` | modified | Python tests/contracts | `623bb7057c5605a86dd7cb1da9f3551c60394759` | `e9f49115a60d76e5ee1c908b067479fd2a32cd8f` |
| `tests/contracts/test_redis_key_contracts.py` | modified | Python tests/contracts | `05bd2974e1282325a8973b7e7d52deac0a15d548` | `764d0c1179ced87e9f88579945544a3506123b32` |
| `tests/contracts/test_ws_hub_contract.py` | modified | Python tests/contracts | `5e018be75f814d53c280bc5bcdf9175f7e90214f` | `7131e385d9d457f2298d7d377d4160cb09621c07` |
| `tests/contracts/test_ws_message_contract.py` | modified | Python tests/contracts | `73f47b575c93cc330601511522cd29c7c5873fb5` | `261eea2ad88002eb54e1233e4c202de16dcee4c4` |
| `tests/integration/test_aud277_360_450_tenant_rls_postgres.py` | added | Python integration tests | `absent` | `e0b2b1bde5f93bc0041ebe52d3e22b67cb921c26` |
| `tests/integration/test_aud327_348_433_migration_postgres.py` | added | Python integration tests | `absent` | `fef368f343ca43e203a6d45de1e1cd300279f0da` |
| `tests/integration/test_aud345_444_postgres.py` | added | Python integration tests | `absent` | `7ae19061971d14f7041cafd9b8774c9ec20f07dd` |
| `tests/integration/test_aud363_454_borrowed_session_postgres.py` | added | Python integration tests | `absent` | `ee330cb8038bf679f4739523eceaa84fb8ca7333` |
| `tests/integration/test_aud389_pgvector_startup_postgres.py` | added | Python integration tests | `absent` | `63ac35182416a3b9eddc3049c4c0f9ff8d0a6bbc` |
| `tests/integration/test_aud445_membership_retry_postgres.py` | added | Python integration tests | `absent` | `02c925c788f3c7410a07423046b75b806aa81b0b` |
| `tests/integration/test_postgres_integration.py` | modified | Python integration tests | `72af8833e298962d0fcd14a99b03292dc127b45b` | `96a7152119e5dd8cd0293f800f29919430080c0b` |
| `tests/services/test_chat_helpers.py` | modified | Python tests/contracts | `c4a5f8d1c03e65d4deb36e4065836de393e1310f` | `98bebe65dbe1e3aee24f385b9069c3052b419486` |
| `tests/test_aud169_188_189_networkpolicy_topology.py` | added | Python tests/contracts | `absent` | `c1a8828c60f84dc9581d7da81c576c9154b4c667` |
| `tests/test_aud260_attachment_prefilter.py` | added | Python tests/contracts | `absent` | `704a48f19367fb3ac698a0072fe9622453cca846` |
| `tests/test_aud260_my_events_bounds_freshness.py` | added | Python tests/contracts | `absent` | `d66b774908efee85e3a44c3c3bba993bec8a5941` |
| `tests/test_aud260_my_events_legacy_batches.py` | modified | Python tests/contracts | `2cd2435707e3fd6579f664b818dcc66e736c88e5` | `aa58866fe8d05400e847c4b98770add4c91bfa45` |
| `tests/test_aud271_393_historical_migrations.py` | added | Python tests/contracts | `absent` | `2d2df6e3c584a7f2d4f761f9eba699b017203100` |
| `tests/test_aud277_360_450_tenant_rls_contract.py` | added | Python tests/contracts | `absent` | `1ef323f2a84037003390da1bb220005564eb4c55` |
| `tests/test_aud316_371_scanner_contract.py` | added | Python tests/contracts | `absent` | `b693fb9517aa6bb5d22c8a3753294b3de22f9a6f` |
| `tests/test_aud327_348_433_migration_evidence.py` | added | Python tests/contracts | `absent` | `c6d62aaf26a959175264d1f51f5e8258bb634172` |
| `tests/test_aud327_348_433_postgres_guard.py` | added | Python tests/contracts | `absent` | `8d85457adb1175ca859cafb1c291866861b797b4` |
| `tests/test_aud337_route_heartbeat.py` | modified | Python tests/contracts | `aa6c7d52398a19f48b06a391f1ee6e210b99fd77` | `1c61ac3ba913f255efb61a18f1899c67e41054e0` |
| `tests/test_aud345_444_registration.py` | added | Python tests/contracts | `absent` | `a59909cdb8a854ad852856c07adf5a99094e231f` |
| `tests/test_aud363_454_pool_pressure.py` | added | Python tests/contracts | `absent` | `2e975a8565364ad72df0befb215d82c5748f3fa5` |
| `tests/test_aud363_borrowed_session_auth.py` | added | Python tests/contracts | `absent` | `ebf54bbd9dff19d24e0a6ef5e7d4c40b95048b72` |
| `tests/test_aud363_notification_pool_pressure.py` | added | Python tests/contracts | `absent` | `7a391703233900c993cfa6e08f4b53bc4be0a47e` |
| `tests/test_aud363_websocket_revalidation.py` | added | Python tests/contracts | `absent` | `6e022a96ebe3ec58285543aef9518cf751bf6e24` |
| `tests/test_aud365_access_audit_export.py` | added | Python tests/contracts | `absent` | `a84d4d143754e23932ee6ad3813525633fb6931e` |
| `tests/test_aud366_391_health_exposure.py` | added | Python tests/contracts | `absent` | `53011edfefeb4c4e2c8a63e65974a6f53fc291fd` |
| `tests/test_aud389_pgvector_startup.py` | added | Python tests/contracts | `absent` | `5a4637b7164823e00a6baca815c5c8710b94d5fe` |
| `tests/test_aud407_510_quality_contract.py` | added | Python tests/contracts | `absent` | `4cc3333ce7c88228bb5cd2076a55346a8c082bf3` |
| `tests/test_aud418_313_seed_guards.py` | added | Python tests/contracts | `absent` | `69cbe5859816a7b3938f4e62bccf1f6609baaa1b` |
| `tests/test_aud445_cache_outbox.py` | added | Python tests/contracts | `absent` | `1235e05bd5267275dbc26635b326b466609129a0` |
| `tests/test_aud445_chat_remove_cache_failure.py` | added | Python tests/contracts | `absent` | `6215fbe0e0984cd3631cb8f6005faa92d8393b4b` |
| `tests/test_aud445_presence_authority.py` | added | Python tests/contracts | `absent` | `650f30adf1a29ed98c90e9ff5279633da0e4984e` |
| `tests/test_aud445_strict_cache_adapters.py` | added | Python tests/contracts | `absent` | `2f279ba9af2c4aaa67d07bad32cd89f88070c62a` |
| `tests/test_aud447_auth_email_delivery.py` | added | Python tests/contracts | `absent` | `3d403412a4d6c3f7043edc9161c7d835a866b3ed` |
| `tests/test_aud454_websocket_membership_race.py` | added | Python tests/contracts | `absent` | `4b96a1667455624702eaded922f371c8a0defced` |
| `tests/test_aud479_480_483_484_485_487_scanner_evidence.py` | added | Python tests/contracts | `absent` | `fcebc6d87da95ef388996b7e609cd152cff31da3` |
| `tests/test_aud482_go_binary_inventory.py` | added | Python tests/contracts | `absent` | `65e156e06578a82d58c2194fdf8273e21c55165a` |
| `tests/test_auth_endpoints_coverage.py` | modified | Python tests/contracts | `f309d3a626bf7f86e6d682d1c5aafa3ba70a0e7f` | `9500ba8b694735917fd8fce7f064f459df6265af` |
| `tests/test_auth_login_tier0_closure.py` | modified | Python tests/contracts | `4da6e29ce8e5b23f0ff178b1a57b8db4e8afca21` | `c29330ea29ee5c51e6e7c46b5b46eb74d8b2ee01` |
| `tests/test_auth_security.py` | modified | Python tests/contracts | `78dbe32d7477d0dfafad557430ab108a5a675694` | `7c91c524f9e4237f89b71bb7e4b87cae45791928` |
| `tests/test_auth_service_password_reset_contracts.py` | modified | Python tests/contracts | `dbdf281a9f8d0183a0e179e1adc80a42e5d0c648` | `ea063f4e4343d1e732805d66ea5b24aba840dc75` |
| `tests/test_backend_api_runtime_contracts.py` | modified | Python tests/contracts | `c0d996839ab641b7e32031e3c936e026d4dbc550` | `b73a448bccf8b81ca369ce2848aa58a8a4daf913` |
| `tests/test_cache_warmup.py` | modified | Python tests/contracts | `ef37203ba303585ab52e1f1e96e6c94c04ec4e0b` | `1ebf1d9282b121aecd2acd549edc353b19fca245` |
| `tests/test_cache_warmup_closure.py` | modified | Python tests/contracts | `14e09d9f9efa9190bff496eb586f47d3bc174f62` | `1914cdc9be6d65e1e5ae38a077ec237057407dba` |
| `tests/test_cache_warmup_consumer.py` | added | Python tests/contracts | `absent` | `b2d0076214f15286109052395886c9f343de4f95` |
| `tests/test_chaos_runtime_contract.py` | modified | Python tests/contracts | `ea9d9758a0a4f4aa8558a371d3eae5837d804878` | `66a28ea1c1152ad3840e05da9c1998037bf8470b` |
| `tests/test_chat_command_branch_closure.py` | modified | Python tests/contracts | `885cb7e133fc9ec236846e47a14beb5e37b0640d` | `06dad2c8ccecd6af84e150a91da0dd25239b0cba` |
| `tests/test_chat_command_service.py` | modified | Python tests/contracts | `5a8964594c055960a2cb852e26c3b6ef8e86accf` | `99c873cd4651ccfa144f50f70cf8812785dcdc44` |
| `tests/test_chat_participant_cache_contract.py` | modified | Python tests/contracts | `9b0b4b2e427c52ee659c4e9e2fc1c1c98b6c4a04` | `b5ebf70b0d74e6c56281213c352c15825aa37483` |
| `tests/test_chat_typing.py` | modified | Python tests/contracts | `0e19f74bd523c76a1407f9aad9c63e3ec62c321d` | `fe47b8a13a4f3988f9bd506746eeaec37cd35282` |
| `tests/test_connection_manager_closure.py` | modified | Python tests/contracts | `8a8ffa9f028b5eab22f7b4e04a03ed65e371a166` | `37634a9dd903a0a7b4aed5ebbe7f94aeedc41a79` |
| `tests/test_connection_manager_final_closure.py` | modified | Python tests/contracts | `d023ec4e1b42190b5ff91e096a6db7dd736d8573` | `a3e4dffe05e84551c07c544e40fbbe11d7a56dd2` |
| `tests/test_docker_log_proxy_contract.py` | modified | Python tests/contracts | `2a79b56723d9db9430aad6c35148ed1fcef8e694` | `6b53070c26163a95f978862a334d19c8e792a44d` |
| `tests/test_email_task_async_redelivery_contract.py` | modified | Python tests/contracts | `f52d820f2796233f1077280a7e83eb85eeff522b` | `0b0b00e6d326a893d5a12d5287eb585300ea979f` |
| `tests/test_event_handlers_behavior_closure.py` | modified | Python tests/contracts | `63451962b45276106dee0472d05f46bc49ac0fb9` | `2fd68df646df6fd8a9fd1c776e937744a51b2d52` |
| `tests/test_events_localization.py` | modified | Python tests/contracts | `f209bfc9c2605f2fb7a7fdfb1311b6db07f24669` | `132e545d1732f4fadf663ce2ffacf85569ca31fe` |
| `tests/test_file_scanner.py` | modified | Python tests/contracts | `607b85accbeac5441e84f726bf882006d19715c4` | `164539be423002735305f3043e995395a25e8635` |
| `tests/test_file_scanner_faults.py` | modified | Python tests/contracts | `8a4f4d8cf7b744d9a48247291f9edf6717ac06cc` | `41beb52e2840430bed1e2fbd865351e18ae02e6d` |
| `tests/test_harness_hook_runtime.py` | modified | Python tests/contracts | `192c2b954d10363c2529c18188cf847f24d00a54` | `41b20f739a0f80f01dbbb545440c5b65e4a9bd55` |
| `tests/test_health_endpoint.py` | modified | Python tests/contracts | `9a00de318335fb6b34724e53745d4bd4dbad18a1` | `613d3ea86e8dd4ac961cddadbea05b88d081b774` |
| `tests/test_lifespan.py` | modified | Python tests/contracts | `c92ba18210c992dd8f531f4822299f385970b625` | `03f3afb237bad9284d820cb01acc83c3a580563f` |
| `tests/test_live_stand.py` | modified | Python tests/contracts | `ca4010b5feba2a76eb9fd59e8bddde2cdd6d6ce6` | `713c6476fe4044621367daded0ef235ee3191af1` |
| `tests/test_migration_148642dd1207_squawk_json_ci.py` | added | Python tests/contracts | `absent` | `79a2ac06a6d6183faf177de2a98c7bd91ef4a43e` |
| `tests/test_migration_reconcile_aud269_272_351.py` | added | Python tests/contracts | `absent` | `f2383ea4c1f8343938bf4904c29e2366861134b2` |
| `tests/test_owned_client_ip_probe.py` | added | Python tests/contracts | `absent` | `a91b75ae41a50bbda1874c42df024532a0216e2c` |
| `tests/test_presence_closure.py` | modified | Python tests/contracts | `7180edf6272984e86a6799180ec886a300c81935` | `bbc6f543db12ed04d1b45e8ccd7240c24eedf1fa` |
| `tests/test_route_dependency_inventory.py` | modified | Python tests/contracts | `afe2aed92803e1a520df5c31bafe2d585f26d99b` | `3648bd1b3f7489e37ebe707b13d2e81e1415a6fb` |
| `tests/test_security_hardening_workflow_contract.py` | modified | Python tests/contracts | `312b9b2f661b379e6baab919885fe0015b5db6ab` | `b7feba64fba1a76af174ac2ca7455c56f03e7294` |
| `tests/test_trivy_identity_before_diagnostic.py` | added | Python tests/contracts | `absent` | `11b0e6af62fdece327e4855feb83fa9e188bdb78` |
| `tests/test_websocket_api_coverage.py` | modified | Python tests/contracts | `085c539a303249918faef3a276183d781e60c25e` | `8fc2402b0c3568cb16acfcd213d67f2cdaa36baf` |
| `tests/test_websocket_broadcast_bridge.py` | modified | Python tests/contracts | `20b8504893cd10c0ecb7bf38674fe86bf869a328` | `12059179e37d5cea9b5b0a4a2bce6ca69dd2bcfc` |
| `tests/test_websocket_chat.py` | modified | Python tests/contracts | `6c84dbdd0521dc4076cbde71bfbf64eabd034d5b` | `22395ec6ea557d6998b7e483ecebe0cc8a11ddcf` |
| `tests/test_websocket_closure.py` | modified | Python tests/contracts | `278138d0b1b5230598113c3649ced0bb81a7f746` | `d6cd9edc1d83832d464a621c21c06ca71cc4a1af` |
| `tests/test_ws_connection_manager_closure.py` | modified | Python tests/contracts | `10134037ae2e6d6477f6739f8de1f13b0f06cde9` | `a2853f9a2d91d1a1ee448b2cb10c0f086324ad57` |
| `tests/test_ws_dispatcher_full.py` | modified | Python tests/contracts | `ab71a41daeb536694cc57dccf7da2351cfedf1fe` | `e6511dc47d3640cd3fba38b4e45d6f2790b815f9` |
| `tests/test_ws_presence_closure.py` | modified | Python tests/contracts | `d238a72d9641932ded6d1f9d63198e4278d9c398` | `b02a84921771d18c76d62273ce5328ec90f668c1` |
| `tests/test_ws_presence_full.py` | modified | Python tests/contracts | `d2816fe3c4d48a56af1646d64c57df4291427ae2` | `95821cc730990df56fcb3d3269248b2f6a2e52e2` |

## Appendix B. Remaining 135 IDs outside the evidence-ready packet

At the 351-ID published snapshot, these plus the 26 candidates above form all 161 unaccepted IDs. No additional readiness category or closure is inferred for the following IDs; their original registry criteria remain authoritative.

- AUD-030
- AUD-043
- AUD-045
- AUD-073
- AUD-137
- AUD-151
- AUD-154
- AUD-155
- AUD-164
- AUD-167
- AUD-169
- AUD-178
- AUD-188
- AUD-189
- AUD-192
- AUD-193
- AUD-208
- AUD-226
- AUD-231
- AUD-236
- AUD-244
- AUD-245
- AUD-247
- AUD-250
- AUD-251
- AUD-253
- AUD-258
- AUD-260
- AUD-262
- AUD-269
- AUD-270
- AUD-271
- AUD-272
- AUD-274
- AUD-275
- AUD-277
- AUD-278
- AUD-304
- AUD-308
- AUD-309
- AUD-310
- AUD-311
- AUD-313
- AUD-316
- AUD-317
- AUD-319
- AUD-320
- AUD-321
- AUD-322
- AUD-327
- AUD-332
- AUD-334
- AUD-340
- AUD-345
- AUD-346
- AUD-347
- AUD-348
- AUD-351
- AUD-360
- AUD-361
- AUD-363
- AUD-365
- AUD-366
- AUD-369
- AUD-370
- AUD-371
- AUD-373
- AUD-375
- AUD-378
- AUD-380
- AUD-381
- AUD-382
- AUD-383
- AUD-384
- AUD-385
- AUD-386
- AUD-389
- AUD-390
- AUD-391
- AUD-392
- AUD-393
- AUD-399
- AUD-400
- AUD-401
- AUD-406
- AUD-407
- AUD-409
- AUD-414
- AUD-416
- AUD-417
- AUD-418
- AUD-420
- AUD-422
- AUD-423
- AUD-425
- AUD-426
- AUD-427
- AUD-428
- AUD-429
- AUD-432
- AUD-433
- AUD-434
- AUD-436
- AUD-438
- AUD-444
- AUD-445
- AUD-447
- AUD-449
- AUD-450
- AUD-454
- AUD-455
- AUD-456
- AUD-462
- AUD-463
- AUD-474
- AUD-476
- AUD-477
- AUD-478
- AUD-479
- AUD-480
- AUD-482
- AUD-483
- AUD-484
- AUD-485
- AUD-486
- AUD-487
- AUD-489
- AUD-490
- AUD-495
- AUD-500
- AUD-501
- AUD-503
- AUD-506
- AUD-510
- AUD-512
