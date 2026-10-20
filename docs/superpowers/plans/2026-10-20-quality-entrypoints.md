# Audit quality entrypoint contracts

## Accepted artifact stability

AUD-086 has named, source-bound behavioral proof in job 118415281373, not merely aggregate job success. Seven paired shell/server stability cases pass at 2026-10-20 02:13:08 UTC; source aa7ea4265ec21ed9d88fc253785d0bc9660adb72 and test ce5227820d601c7412d7788f36431d287ab192b3 remain unchanged. The bounded sampling claim does not imply producer completion, full asset stability or general process-tree quiescence.

## AUD-082 tests first

The existing frontend quality-contract Node suite parses the real VS Code JSONC with the installed TypeScript parser, requires pytest enabled and the intended tests directory, and checks a known tracked test file. Current root/tests should fail the explicit path assertion before filesystem lookup. No settings change is included yet. A later single-value correction proves discovery configuration, not a physical VS Code session.

## AUD-083 tests first

Four automatically selected Contract Tests execute a copy of the actual Makefile using official runner GNU make and Python, through the existing bounded private collector. Each fixture owns synthetic app and npm files under tmp_path, an explicit fixture-only PATH, and a synthetic tracked-schema stand-in. Actual application startup, dependency downloads and actual SDK generation cannot run in this fixture.

Require successful export/normalization/generation ordering and retained schema; exporter failure must reach the synthetic application and preserve previous schema; normalization/generation failures must return nonzero at their intended recorded stages. Nonzero make alone is insufficient proof. The current split heredoc should fail before the synthetic application, exposing four meaningful assertions.

The actual frontend/openapi.json is tracked. After observed RED, replace only the broken recipe with canonical UTF-8/indent/sorted-key/newline export, normal frontend Prettier normalization and the existing quoted generate:api prefix. Remove the rm recipe rather than deleting the tracked schema. Do not add global .ONESHELL. These contracts prove recipe execution/order and preservation, not actual Prettier/SDK parity or transactional rollback; existing OpenAPI/MSW drift jobs remain authoritative.

## AUD-087 tests first

Five subprocess cases execute the unchanged icon-generator body in a temporary scripts/public layout, resolving only sharp to its real installed module. A small raw-pixel PNG avoids external inputs. Child execution has an explicit empty environment, a 30-second timeout and a 64-KiB output bound; finally removes the temporary tree. No tracked icon can be touched.

Success and missing-input behavior are preservation controls. Directory collisions at the first PNG, favicon only or all six output paths require nonzero exit while preserving best-effort attempts and successful outputs. Do not claim RED before hosted execution. Favicon's pre-existing PNG-format bytes are explicitly outside this exit-status correction. The tests extend the already-selected frontend quality-contract suite without new dependencies or selection scripts.

## AUD-088 named rendered-configuration proof

Current frontend/gateway templates already render zero minimums and complementary daytime cron, while hibernation remains disabled by default. Select the three existing tests/test_helm_keda_hibernation.py cases by extending only existing focused workflow line 155. Required redis and nats chart archives are already tracked; these tests use helm template --dependency-update=false with synthetic CLI overrides and do not install/apply or alter values.

The focused command precedes the later pinned Helm setup. Acceptance requires three explicit PASSED node IDs, not aggregate success, because the unchanged helper can skip if preinstalled Helm is absent. No skip is added or hidden. Passing proves the original positive-minimum configuration defect only, not live scaler behavior, cron timing, zeroing/wake readiness or availability. No operational enablement is requested or performed. Workflow split-line count and baseline coordinates remain unchanged.

## Observed entrypoint RED and narrow corrections

Contract job 118441928877 has four intended failures: make exits 2 on the success path, the synthetic application is never reached in the export-failure case, and both downstream cases record no stage. Node job 118442417955 exposes root/tests versus tests and exit 0 versus 1 in all three blocked-output icon cases. Success/missing-source icon controls pass. These are actual child-process/configuration assertions, not inferred source defects.

AUD-082 changes only the intended pytest discovery path and restores the file's terminal newline. AUD-083 replaces the split heredoc with one continued Python command, retains canonical UTF-8/sorted/indented/newline export, normalizes the tracked schema, and leaves SDK/MSW generation in its existing command. The tracked schema is no longer removed. npm exec --no declines implicit installation when Prettier is missing; the synthetic npm argument oracle gains that exact safety flag, with all behavior assertions preserved. The original Make target's physical span is retained through readable continuations and explanatory comments; protected baseline line 188 is byte-identical and the baseline itself is untouched.

AUD-087 sets process.exitCode=1 in each existing output-error catch while continuing all later attempts. Logging, success, missing-source behavior and favicon byte format are unchanged. All corrected-source execution is pending; these three IDs are not yet accepted.

## AUD-088 rendered contract accepted

AUD-088 is accepted as the original rendered frontend/gateway positive-minimum defect. The two off-peak/daytime cases pass at 03:50:21/22 UTC and the disabled-state case at 03:50:23 in job 118442456006. They execute Helm against the tracked chart/dependency archives with synthetic CLI overrides and no dependency update or cluster contact. Hibernation remains disabled by default; no replicas, schedules or deployment settings change. This does not prove real KEDA zeroing, wake readiness, cron execution or availability. The verified lower bound becomes 87/512; other new findings remain open until their own corrected-source GREEN.

## Corrected entrypoints accepted

Source 1ed440f88de239971ce9e4e6900a41ed6adad7c3 and hosted checkout 8bbbd09fc76189c0caa6993acfb008728a2d367b have identical tree 07c72b763fa54ec77bd1bcc6e435b06d76ec8579. Contract job 118448021392 passes all four Make cases and totals 129 PASS. Node job 118448485714 passes all 596 cases, including JSONC discovery and all five real icon subprocess oracles. AUD-082/083/087 now have their own corrected-source GREEN and are accepted within the scopes above; no formatter, generator, baseline or security gate is bypassed.

## AUD-098 diagnostic IPC tests first

Two real Node subprocess cases preload the unchanged trace agent with IPC and an explicit environment. One leaves IPC open and requires natural successful exit without a dump/exit request; the other keeps a real timer active and requires the existing dump reply. The latter proves message delivery must survive any future channel unref. Readiness, exit, reply and cleanup waits are bounded; cleanup targets only the direct owned child, awaits close, then removes its temporary directory. The natural-exit case is expected to fail until observed otherwise. It does not prove real Vite producer completion or general process-tree cleanup.

## AUD-099 actual Spectral tests first

The existing spectral-lint job gains a bounded synthetic-fixture step after its existing pinned enforcement command. The checker extracts and requires the same immutable image from both existing commands; no image literal, dependency or pull is added. Docker uses --pull=never, --network=none and read-only mounts. The exact container ID comes from Docker's CID file; bounded cleanup preserves original failure and makes cleanup failure observable. Runner loss or unresponsive Docker can still leave cleanup unproven.

The fixture exercises 200-only/default-only/400/4XX across the five existing selected verbs, plus excluded HEAD/OPTIONS/TRACE controls. Acceptance requires ten response-rule warnings at the expected operation.responses paths, no such warnings for the positive/excluded controls, and preserved PII/OAS diagnostics. The production ruleset is unchanged for this first run, so missing warnings are expected; the actual pinned tool must establish RED and diagnostic locations before any rule correction. Runtime checks raise explicit errors rather than optimization-sensitive asserts. Unit guards validate checker failure handling but are not a substitute for actual Spectral execution.

## Spectral behavioral RED and scoped rule correction

Source 52db76bcd4b1287f67a497032ccb9a8a0bfbabff and checkout 88a46c6ce6f9c3aa9ef8f22ce864035e5e450805 have identical tree 9d04c284e64bf713bd528a8936f4eb58aa647afb. Actual pinned Spectral job 118461862364 produces zero response-rule diagnostics and the expected PII property warning at 04:57:08 UTC; the checker fails for exactly ten missing 200/default warnings. The owned fixture container is removed by its exact CID before the step reports failure.

The responses schema now rejects maps with no explicit 400–499 or 4XX key. Existing object/required checks, five-verb selector, warning severity, OAS extension and PII rule remain unchanged. AUD-099 is not accepted until corrected-source execution proves the diagnostic paths and preservation controls. A separate exact formatter join in the Gateway source-contract assertion removes the lint blocker without changing its expected text or behavior. The verified ledger remains 95/512.

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

## 2026-10-20 08:34 UTC — actual selection verified

AUD-103 is now accepted: ce03 Contract job 118523150422 executes twenty named generator guards (174 PASS total), completing the previously verified real Promtool and producer layers. AUD-106 remains open: ce03 Node/WASM job's 598 PASS omitted eslint-architecture.test.mjs. Add that existing suite exactly once to test:wasm and protect its selection; do not change the ESLint exemptions before observing its RED. Two existing formatter warnings are corrected without changing assertions. AUD-109's two defaults cases fail while both explicit 5/5 controls pass; correct the bilingual defaults and narrow the test parser to the defaults bullet, then require new GREEN. Latest verified audit lower bound is 106/512; e150 remains the last fully accepted CI source.

## 2026-10-20 09:00 UTC — path-rule RED and documentation GREEN

AUD-109 enters the ledger after all four named bilingual defaults/override controls pass in 3cc49cd job 118535985402. AUD-106 remains open: selected Node job 118536398799 has 613 PASS / three untranslated-JSX failures, with all six exemption controls passing. Correct only the three moved-component paths; the warning-array extraction retains every assertion and needs formatter verification. Current static job passes TypeScript/ESLint/i18n/Knip but still flags only the architecture-test file's formatting.

A private, bounded pinned-Playwright --list contract is prepared in the already-selected live security suite. It checks exact reviewed-file coverage for desktop/mobile, no executed results and finite unique instances, then reports only source SHA and integer counts after owned temporary cleanup. It does not prove runtime skips or descendant containment. Keep the historical 190/eight gate unchanged until evidence supports reconciliation. Latest verified ledger: 109/512; no full-green or release claim.

## 2026-10-20 09:33 UTC — measured inventory and exact formatting diagnosis

f06 Node job 118546333849 passes all 617 cases, including nine corrected ESLint path cases and actual pinned Playwright collection: 216 instances, 61 files, 108 per project. Eight unchanged skip identities imply a configured target of 208 PASS/eight SKIP, not observed runtime acceptance. e150-to-f06 adds sixteen instances; two further instances are pre-existing drift against the historical 198 gate. Keep those evidence boundaries explicit.

Eight additive pure acceptance/index cases and a measured-count/source-constant check precede any production count change. They preserve exact identities and finite source/reporter validation. A mismatch intentionally stops the owned preflight before Docker. Do not turn it into a skip or lower-bound gate.

Static checks expose collection regex-space/unsafe-finally issues and two formatter warnings. Fix cleanup error propagation without suppressing cleanup failures. A temporary diagnostic obtains bounded exact installed-Prettier output for the one fixed public architecture fixture; remove it and its imports after applying the result. AUD-106 remains uncounted until that cleanup is verified. Next named cohorts cover CLI smoke target, real tiered Redis-wrapper metrics and existing Elasticsearch SDK fallback evidence. Latest ledger: 110/512.
