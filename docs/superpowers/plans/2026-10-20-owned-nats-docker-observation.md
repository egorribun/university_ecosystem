# Bounded Docker observation prerequisites

## Scope

Runtime observation, coordinator/CLI wiring and outage remain disabled. Prepared requests and supplied bytes do not establish actual Docker execution, executable/config/socket provenance, trusted daemon identity, complete inventory, health, image trust or mount admission.

## No-I/O Compose projection extraction

Extract the existing parsed-project body into _compose_resource_evidence_from_project; the legacy wrapper retains project validation, current process invocation/environment, JSON decoding and exact error behavior. The extraction adds no subprocess call or waiver. The existing projection body stays byte-for-byte unchanged.

Twenty-one additive tests compare the wrapper and extracted helper against independent canonical/evidence expectations: full/Core/legacy resource retention, dependency closure, port names rather than numeric values, Unicode mount changes, malformed models, selection errors and pre-projection wrapper failures. The only fake process accepts one exact command and kwargs, without a real-process fallback. Fixed synthetic models are checked for nonmutation; this is not a general purity promise. Existing resolution can append link/network-mode dependencies to a list-valued depends_on, which remains unchanged for compatibility.

These six test functions are explicitly selected on the existing focused workflow command line. Hosted execution remains pending.

## Explicit daemon request and supplied-result tests first

New owned_nats_docker contains unavailable no-I/O preparation/decode seams. DockerReadPins requires explicit executable, local endpoint, config directory, working directory, immutable environment pairs and expected daemon fingerprint. Private fields are excluded from repr. The scaffold returns None/NOT_READY and never invokes the collector.

Fifty-two additive cases live in the already-selected transport test file. Six positive cases are expected to expose unavailable preparation or decoding: two exact requests, three daemon line endings and the shared-deadline preparation control. Negative cases cover representative unsupported pins/environments, process outcomes, return codes, cleanup uncertainty, private stderr, malformed/oversized output, fingerprint mismatch and unusable/finally-expired deadlines. Guards record attempted process execution; they cover specified entry points, not every possible I/O mechanism. No expected RED is claimed until hosted observation.

After RED, preparation must use only a fixed read-only info argv, explicit empty/locale-only environment, bounded output and the supplied Deadline. Decoding accepts only confirmed EXITED/exact-zero results with bounded bytes and empty stderr, strips at most one accepted line ending, hashes the opaque daemon ID and compares the supplied expected fingerprint. It must recheck the same deadline, never learn its expected pin from the same response. No RuntimeEvidence or ContainerSnapshot is produced by this slice.

## Existing preflight deadline proof

Original AUD-084 concerns bounded return when an exited parent leaves inherited stdout open. Current source and both existing test blobs match e150, but inspected aggregate logs do not expose named execution. Select both existing suites in the same verbose focused command. Real Linux inherited-pipe evidence is the acceptance target; Windows API simulations are not physical Windows execution, and bounded return does not mean every detached descendant is terminated.

Only existing workflow line 155 is extended. The 631 split-line layout and baseline coordinates 396/406 remain byte-identical; baseline 319, dispositions 263, required contexts and security gates are unchanged.

## Named projection and preflight evidence

Source a71c6d7c756c53bd31ea661053a9974ee9fdc497 is bound to checkout fbb400bb797ed0fd683515f19da1d9275c483953 and identical tree e164ddb9bbe0550e010832adead33404763a552d. Focused job 118415057333 reports 831 PASS / 7 FAIL in 212.74 seconds: six intended unavailable daemon request/decode assertions and the existing disabled-outage workflow hold. All twenty-one Compose projection cases and all twenty-eight existing preflight cases pass.

AUD-084 is accepted narrowly for bounded runner return when an exited parent leaves inherited output pipes open. The real Linux regression test_run_check_deadline_when_descendant_inherits_output_pipes passes at 02:16:19 UTC. Source was already corrected and is unchanged; adding named selection supplies the missing source-bound proof. Windows drain cases are simulated API controls, not physical Windows execution. Bounded return does not claim termination of every detached descendant.

## Observed daemon RED and bounded implementation

The six positive assertions fail on a71c6d7 because preparation returns None and decoding returns NOT_READY. The other forty-six new cases pass. The corrected source now validates explicit lexical paths, local Unix endpoint and immutable locale-only environment before creating one fixed bounded request. Supplied process results require exact enum identity, integer zero, confirmed cleanup, bounded bytes, empty stderr, strict UTF-8 and a matching pinned fingerprint. Both operations recheck the original Deadline and perform no process or filesystem invocation.

Paths and endpoint checks are deliberately restricted capabilities, not existence/provenance checks. Root is supported for directory pins only; ambiguous endpoint query, fragment, percent encoding and backslashes are rejected. Ordinary malformed-data/deadline failures remain private; BaseException is not newly swallowed. Extra defensive shape/Unicode/path branches exceed the representative fifty-two-case cohort and are not claimed as exhaustively tested.

Own corrected-source GREEN is pending. No collector invocation, RuntimeEvidence, container inventory, coordinator/CLI wiring or outage is enabled.

## Request/decode GREEN and collector composition tests first

On 4f64cdad, all fifty-two request/decode cases pass in job 118435856906; its aggregate is 837 PASS / one existing disabled-outage hold. This remains request/supplied-data validation, not an actual observed daemon or complete inventory.

The next observe_daemon_metadata seam is unavailable and returns NOT_READY. Twenty-one additive cases in the already-selected transport suite require one exact request and identical Deadline, no collection for rejected pins/deadlines, decode refusal after one collection, postcollection expiry, original exception identity, retained precollection fingerprint despite callback mutation, and no fresh deadline/retry. Fourteen positive integration oracles are expected to fail initially; seven admission controls should pass. No execution is claimed before hosted observation.

Tests replace only the existing collector boundary and retain direct process guards. The future implementation must capture the admitted expected fingerprint before calling the collector and decode against that retained value. Callback mutation intentionally bypasses frozen-dataclass protection; the proof is expectation retention, not continuing authenticity of a mutated object. No collector import, runtime caller, inventory, coordinator/CLI wiring or outage enablement is introduced by this scaffold.

## Collector composition after observed RED

On 2c85f95 / job 118442456006, fourteen composition cases fail at required one-call or exception-propagation assertions and all seven admission controls pass. The entire focused job is 847 PASS / 15 FAIL, including the existing disabled-outage hold.

The implementation uses existing preparation, refuses without collection when it returns None, retains the admitted fingerprint before the callback, invokes the existing private collector exactly once with the same Deadline, and decodes against that retained fingerprint. Unexpected exceptions and interrupts propagate unchanged. No fresh budget, retry, direct subprocess call or suppression is added.

Preparation/decoding still perform no transport I/O. Composition can invoke the existing collector when explicitly called; current tests replace that boundary and no coordinator/CLI/runtime caller is connected. Module documentation reflects this distinction. Own composition GREEN remains pending; complete inventory, executable/config/socket provenance, daemon authenticity, health admission and outage remain unproved.

## Collector composition GREEN

Source 1ed440f88de239971ce9e4e6900a41ed6adad7c3 and hosted checkout 8bbbd09fc76189c0caa6993acfb008728a2d367b share tree 07c72b763fa54ec77bd1bcc6e435b06d76ec8579. Job 118448423252 passes all twenty-one observation-composition cases at 04:12:46–51 UTC, with aggregate 861 PASS / one existing disabled-outage hold in 246.72 seconds. Exact request/deadline identity, one collection, refusal before collection, result rejection, postcollection expiry, exception/interrupt identity and retained precollection fingerprint are covered.

The tests substitute the existing collector boundary. No runtime caller, coordinator, CLI, complete inventory or actual outage is enabled. Next work is explicit in-place Core Compose request preparation and private supplied-JSON projection under the original deadline, before any inventory or transport composition is accepted. Caller-owned signature/key/lease/source and Docker/plugin/config provenance remain preconditions, not facts established by this helper.

## In-place Compose boundaries: tests first

The actual owned Core workflow uses --in-place; its reviewed layout is repository docker-compose.full.yml, repository docker-compose.live.yml and owned-state docker-compose.live-state.yml, with an explicit owned-state .env.docker. New unavailable prepare/decode seams introduce only private types and NOT_READY results, not collection or runtime callers.

Thirty-two additive cases require an exact explicit Docker/Compose request, immutable owner/pin admission, deterministic locale/control environment, bounded bytes, strict unambiguous JSON, an independently constructed Core resource projection and the same original Deadline. Every seam invocation is guarded against named filesystem/process/legacy calls, ambient environment reads and fresh deadlines. Two positive assertions are expected RED; thirty refusal controls preserve fail-closed behavior. This is not an exhaustive I/O sandbox.

Supplied private labels/environment are deliberately excluded from the existing resource fingerprint. Matching that fingerprint does not establish effective environment, image identity, label admission, daemon authenticity, source/transitive env-file provenance or retained signature/key/lease ownership. The fixture's dictionary dependencies avoid the existing list-mutation path; no general projector purity claim is made. Existing seventy-three daemon request/decode/composition cases are retained unchanged.

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

## 2026-10-20 08:34 UTC — composition RED and bounded correction

On ce03, focused job 118523935315 executes all sixteen new observation cases: twelve unavailable-stub failures and four passing admission controls. Overall 964 PASS / fifteen FAIL in 273.91 seconds includes two documentation failures and the intentional outage hold. The correction snapshots the owner, prepares once, calls existing run_private_process once with the identical Deadline, and decodes against that snapshot. No caller or outage is enabled. Require all sixteen corrected-source passes before accepting this boundary; it does not establish real daemon inventory or provenance. Sentinel approval remains pending; baseline and dispositions are unchanged.

## 2026-10-20 09:00 UTC — composition verified, runtime still disabled

Source 3cc49cd and identical-tree checkout 257a3d35: focused job 118535985402 passes all sixteen named Compose observation cases at 08:47:01–05 UTC. Overall 978 PASS / one intentional outage hold in 267.37 seconds. The previous 48 preparation/decode and 73 daemon contracts remain selected. This does not establish real daemon provenance or authorize runtime admission. No coordinator/CLI/outage activation, baseline/disposition edit or new process waiver occurs. Public-sentinel approval remains pending.
