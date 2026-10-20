# UI lifecycle and transport reconciliation

Date: 2026-10-19 UTC. GitHub plugin only, branch egorribun, PR1306.

## Accepted original boundaries

AUD-078: current register-sw.ts compares controller identity, ignores initial/no-change events and reloads once on later replacement. All thirteen registerSw.test.ts cases pass on 19cae40, job 118362686823 at 23:26:39 UTC, including both ready/listener ordering cases. This is controlled callback/EventTarget evidence, not a deployed worker upgrade.

AUD-079: current Dashboard catches the decorative marker's quota write failure. All ten Dashboard.closure.test.tsx cases pass on 19cae40, job 118362686860 at 23:24:25 UTC. The original quota scenario asserts the specific write was attempted once and all three content cards remain mounted. Unrelated storage-access/getItem/removeItem SecurityError behavior is not accepted by this proof. Both findings enter ledger 72; no production changes are needed here.

## AUD-067 tests first

Original finding: clearing time in the lesson editor leaves the form valid. updateLessonTimeField serializes empty input as dateT:00, while isEditLessonFormValid checks nonempty strings. Add eight cases to the existing branch suite: start/end, bare/ISO input, helper and real dialog. Require disabled Save and no forced-submit PATCH/optimistic update/refresh; restoration must allow one valid request. Helper checks preserve input immutability and deterministic date selection; ISO dialog payload must keep 2026-01-15 rather than today's date. Use an end time later than the unchanged start for the positive restoration control.

Do not clear stored date context as a shortcut. A narrow displayed-time validation correction can retain existing date-bearing draft state; no broad timestamp/calendar redesign is implied. The transport spy records the actual form boundary but is not a backend persistence test. Production is unchanged until observed RED.

## AUD-077 tests first

Original finding: the ordinary Web Vitals reporter loses a metric when sendBeacon returns false. Add one false-beacon case requiring exactly one existing fetch fallback with the same serialized payload, POST JSON, keepalive true and credentials omit; retain a true-beacon control requiring no duplicate fetch. Use the actual registered reporter and typed metric data. Existing thrown/unavailable-beacon and rejected-fetch controls remain unchanged.

Production is unchanged until observed RED. The later minimal correction should return only when the browser accepts the beacon, preserving the existing fallback and exception boundary. This establishes transport attempt and serialization, not remote metrics delivery. No trusted-RUM/global SDK/configuration change is included.

## Other reviewed scope

AUD-061 scanner exclusion consistency, AUD-062 day rollover, AUD-063 rejected React.lazy recovery, AUD-066 calendar export, AUD-068 delayed search focus, AUD-069 late footer observation, AUD-071 Snackbar pointer hit-testing, AUD-074 print-media behavior, AUD-075 modified navigation clicks and AUD-080 group listbox semantics remain separate open items. AUD-065 has source improvements but still needs a displayed-target regression and source-bound execution reconciliation. None is accepted merely because tests exist.

## Observed AUD-067/077 RED and narrow corrections

80c0553 frontend job 118373599522 records eight expected new time-editor failures at helper line 331 and Save-disabled line 356; the other 2616 cases pass. Job 118373599628 records only the new false-beacon failure at line 172 (zero fetch calls), with 2339 other cases passing. Exact checkout a0527e2b54daaca915b4218af7d93d53544a0148/tree 004a4877fd815db7b2676a19f3ba90c1bba2e9bb is verified. No runtime/setup failure is substituted for these assertions.

Time validation now checks both displayed HH:MM values against bounded clock ranges after the subject guard. Getter parameter types require only the single time field they read, allowing the partial validator input without casts; runtime getter behavior and date-bearing serialization are unchanged. This validates displayed time, not an entire calendar timestamp. Existing tests retain exact original ISO dates and chronological positive controls. The test's two controlled suffix cases now use literal regex alternatives, resolving the security lint warning without suppression.

The ordinary Web Vitals reporter returns only when sendBeacon accepts the payload. False reaches the unchanged keepalive fetch path; exceptions and unavailable-browser controls remain unchanged. These corrections still require own-source GREEN and do not yet add AUD-067/077 to the ledger.

## Next bounded tests

- AUD-075: seven additive integrated TanStack Link/memory-router cases cover Ctrl/Meta/Shift/Alt, middle/secondary click and pre-cancelled events; the two ordinary same-target controls gain explicit cancellation and one-scroll assertions. React or Link composition can already suppress secondary/pre-cancelled callbacks, so those are preservation controls, not independent proof of a source guard. No native tab/window opening is claimed from jsdom. Production navigation is unchanged before RED.
- AUD-080: direct/group/direct listbox regression requires true multiselect semantics only in group mode, two retained selected rows and the original direct-selection callback. Absent or false in direct mode is accepted equivalently. Production accessibility markup is unchanged before RED.
- AUD-065: add actual static digit and accessible-label assertions immediately after changing the target from 600 to 601, then after one second. Keep the existing hidden-to-visible wall-clock catch-up and interval tests. Production source is unchanged; new hosted execution is needed before accepting the original finding.
- AUD-061: scanRepository fixture includes valid App, invalid excluded test/generated/vendor files and an invalid ordinary production control. Require inventory exclusions and actual files/references/errors to agree, with production errors still blocking. The existing Node suite is appended after the existing scanner CLI and translation-parity test in i18n:check because no prior hosted command selected it. No workflow or scope-policy exclusion is added; scanner production is unchanged before RED. Temporary fixture cleanup is limited to its own mkdtemp path.

## Corrected-source GREEN and next observed boundaries

Exact source 68a29ba97ecdf26b1b6d4291ce3f3698dd3d90c6; hosted checkout debeed2c51a68e6631d1bd84443c48f94ba8d1da has identical tree 2c10b87c3cb1e1f8f60b70cff51d7cf9eee12be9.

- AUD-065: all fifteen FlipCountdown cases pass in job 118379988574 at 00:17:03 UTC, including existing hidden-to-visible wall-clock catch-up and new immediate displayed-target/static-digit assertions. Production was already corrected. The target change updates accessible label and actual static digits without advancing time, then continues ticking.
- AUD-067: all twenty-one EditLessonDialog branch cases pass in job 118379988739 at 00:17:46 UTC, including eight previous REDs. Clearing either field invalidates helper/form and prevents forced-submit transport; restoration retains the original ISO date and permits one request. This validates displayed HH:MM, not full calendar timestamps or backend persistence.
- AUD-077: all twenty-eight ordinary Web Vitals cases pass in job 118379988715 at 00:21:23 UTC. False-beacon now invokes exactly one existing keepalive fetch with unchanged payload; accepted beacons do not duplicate transport. Remote delivery is not claimed.

Ledger is now 75. Original scope limitations remain in force.

Static job 118379988451 passes TypeScript, ESLint, Prettier, message-contract and knip. Its only failure is AUD-061: twenty-eight existing Node tests pass, but excluded __tests__, generated and vendor files emit missing-key errors in both locales at fixture line 435. The production scanner CLI and eighteen translation-parity tests pass. Job 118379988739 observes five AUD-075 failures for Ctrl/Meta/Shift/Alt/middle-button cancellation; secondary/pre-cancelled and ordinary controls pass. Job 118379988715 observes AUD-080 missing aria-multiselectable=true at line 376.

Apply existing isScopeExcluded policy to actual scan candidates without changing inventory or exclusions; preserve default modified-click behavior; mark only group listboxes multiselectable. Keep all regression assertions unchanged and require own GREEN before accepting those three findings.

## AUD-062 stable-data rollover tests first

AUD-062 adds two tests first for today/week rollover across Istanbul midnight while UTC remains the previous day. Keep the same array, query object and zone; advance only the clock sixty seconds. Assert old-day removal, next-day inclusion and moving week edge, without rerender, post-transition scope clicks or network prefetch. Unmount before restoring timers. Production stays unchanged before observed RED; a later minute ticker must preserve current half-open eight-day week, cap, ordering and null-zone behavior. No immediate background-resume guarantee is claimed.

## Day-rollover RED and next UI lifecycle tests

On d8682a6, frontend reports 9407 PASS / 2 intended AUD-062 FAIL across 779 files. Job 118385971433 records both stable-data rollover failures at line 899: today retains the old campus day and week retains the outgoing item instead of the incoming edge. All twenty-seven navigation cases pass in that job. Job 118385971362 passes all seventeen group-listbox mutation cases. Static job 118385971284 passes all twenty-nine scanner Node cases, scanner CLI and translation parity, plus TypeScript, ESLint, knip and message contract; its only failure is formatting in the scanner predicate and new EventsCard test.

The follow-up uses existing useMinuteClock and campus-day memo dependencies without changing data, order, cap, time-zone null handling or half-open week boundaries. Scanner formatting collapses its 100-character arrow line; the test obtains list/buttons through short local bindings with equivalent assertions. No lint suppression or regression weakening is added. AUD-061/075/080 have behavioral GREEN but remain outside ledger 75 until corrected static checks are verified; AUD-062 requires its own corrected-source GREEN.

Next tests-first cases:

- AUD-063: keep actual lazy/Suspense/WidgetErrorBoundary, reject one controlled load, preserve the same imported module through unmount and reopening, and require a fresh activation load plus stable loaded-child lifecycle. Mock reporting sinks only; React caught-error callback checks expected identity and cardinality is asserted explicitly. No console policy, loader cache or retry UI changes.
- AUD-068: real LazyMotion/AnimatePresence wait-mode transitions must first demonstrate the old header remains while the input is absent, then require focus on delayed attachment/reopen. Also cover chat becoming available with search intent already true and query-only rerenders not stealing focus. Production remains unchanged before RED; do not substitute animation setup failures for the intended assertions.
- AUD-069: real memory router, useRouteType, MainLayout and BackToTop retain the same button through messenger/dashboard/schedule/news. Require each new footer observed, prior observer disconnected, offset reset, stale callback ignored and final cleanup. Only unrelated chrome/footer markup is stubbed. No new prop or production behavior is applied before RED; a future narrow layout visibility prop can reuse the existing route authority without global MutationObserver polling.

## Observed lazy/focus/footer RED and narrow corrections

Frontend 965a82d reports 9410 PASS / 5 intended FAIL across 782 files. EventsCard passes all twenty-seven cases in job 118392005528, including both stable-data campus rollover regressions. All existing frontend cases remain passing. New job 118392005604 exposes the exact next boundaries: MapFeature retry line 164 observes one loader call instead of two after actual unmount/reopen; ChatArea lines 153/180 lose focus after both real wait-mode transitions and chat availability; MainLayout footer line 152 observes no IntersectionObserver after the first real route transition. The chat query-only focus-preservation control passes. No setup/animation/router failure is substituted for these assertions.

The corrections scope lazy identity to a mounted MapFeature instance, observe actual search-input attachment in the cancellable focus effect, and pass existing layout footer visibility to BackToTop. Footer transitions reset offset, disconnect observers and ignore queued stale callbacks; no global MutationObserver or new router dependency is added to BackToTop. The existing ChatArea mutation mock now caches motion component identities, matching real m.* identity without altering assertions. New regressions remain unchanged.

Static job 118392005513 passes types, ESLint, scanner/translation checks, message contract and knip. The only remaining formatter warning names EventsCard.test.tsx. The follow-up collapses its first two-element expected-label array, whose combined form is exactly the configured 100-character width; its own formatter result is pending. Other formatter changes, including the scanner predicate, pass. Ledger remains 75 until corrected static checks and own corrected-source cases are reconciled.

## AUD-066 first-lesson calendar preparation tests first

AUD-066 tests first retain actual Schedule, Settings, ExportDropdown, generator, campus provider and store. Existing settings controls select the next campus week and hide Monday; reversed fixture order must still prepare the earliest eligible Tuesday lesson with title, teacher, room, date/time, localized type and timezone. A second case requires no opening for an empty group. The current handler opens only a bare calendar week despite its documented first-lesson intent.

The planned scope is one lesson of the filtered selected week, not whole-schedule synchronization or the current mobile panel. Existing PNG/PDF, backend group ICS and mobile active-day state stay unchanged. Later wiring can reuse the existing Google TEMPLATE helper with explicit campus date/timezone and accurate labels. The current parity calculation is based on now rather than selected week; export must intersect visible lessons with actual occurrence parity, not silently substitute hidden raw lessons or claim to fix that separate scheduling boundary. Additional invalid-time, parity, year-boundary and live-state tests remain required before acceptance. No production calendar change is included yet.

## Seven original UI/scanner boundaries accepted

Source 19a2f8a25509fe385df2a9dbaf60af18b5e9a154 is bound to hosted checkout 889f77d4b3da091d88f77b448de4741311175523 and exact tree 60b3ec1ffae6d211acd7fe95abd6427c8afcf9c4. Frontend reports 9415 PASS / 2 intended AUD-066 FAIL across 783 files; static job 118398422550 passes every gate, including Prettier and all twenty-nine scanner Node cases.

- AUD-061: actual scanner exclusions and inventory agree; the production-error negative control remains blocking. All twenty-nine Node cases pass in static job 118398422550. No exclusion policy was added.
- AUD-062: all twenty-seven EventsCard cases pass in job 118398422504 at 01:14:43 UTC, including stable-array today/week rollover. Update is at the next running minute tick, not an immediate background-resume guarantee.
- AUD-075: all twenty-seven NavbarPieces cases pass in the same job at 01:15:04 UTC, preserving modified-click default behavior and ordinary same-target scrolling. This is real Link/memory-router evidence, not native tab/window opening.
- AUD-080: all seventeen NewChatModal mutation cases pass in job 118398422677 at 01:20:17 UTC, including direct/group/direct multiselect semantics and selection callbacks.
- AUD-063: actual lazy/Suspense/error-boundary failure, unmount, reopening and successful activation pass in job 118398422677 at 01:21:38 UTC. Loaded-child identity remains stable on ordinary rerenders. Loader behavior is controlled; real WebGL cleanup and recovery from every browser module-evaluation failure are not claimed.
- AUD-069: actual memory-router/MainLayout/BackToTop repeated route transitions pass in job 118398422677 at 01:21:49 UTC. The same button observes each new footer, resets geometry, disconnects the old observer and ignores stale callbacks. Intersection geometry is controlled, not a physical-browser layout measurement.
- AUD-068: all four real-motion search-focus cases pass in job 118398422677 at 01:21:58 UTC. Wait-mode delayed attachment, reopening, later chat availability and query-only focus preservation are covered. No animation/focus implementation is replaced in that cohort.

Ledger advances from 75 to 82. AUD-066 is still open. Job 118398422738 observes exactly the two real-path failures: line 229 opens /calendar/r/week instead of /calendar/r/eventedit, and line 248 opens a window for an empty schedule. The next calendar correction is being prepared separately; it must preserve the documented single-lesson intent, selected campus week, filters, group provenance and explicit timezone, not claim full schedule synchronization or change backend ICS.

## AUD-066 correction after real-path RED

The handler now prepares a Google TEMPLATE draft for the first eligible lesson of the filtered selected campus week. The selector uses explicit group, campus date/timezone, visible weekdays and actual occurrence parity; it never substitutes raw hidden lessons. Deterministic order is weekday, normalized start time and ID. Empty/unready inputs, contradictory explicit group metadata, invalid first time ranges and unrepresentable date offsets disable export instead of silently selecting another lesson. Legacy lessons without group metadata retain the existing group-keyed query provenance.

Schedule forwards the prepared URL and localized disabled reason through Settings. ExportDropdown preserves PNG/PDF and existing enabled-item keyboard navigation. Its missing-URL guard prevents opening; the disabled item has a localized accessible description outside the menu and a title. English/Russian labels explicitly identify the first filtered-week lesson. Existing Date-based URL calls keep their old serialization without ctz; the new explicit occurrence adds campus ctz.

The two observed real-path assertions are preserved. A third same-mounted group transition keeps schedule/configuration/date/filter identities stable, rejects explicitly contradictory old-group metadata and restores export after switching back. Ten utility cases cover filtering, nonmutation, query-group compatibility, invalid times, ISO time fields, parity/year boundaries, overflow-before-shift, unavailable inputs and legacy URL bytes. Existing dropdown tests use a complete supplied URL; two additional cases cover disabled-item navigation and all-disabled safety.

Hosted lint/types/format and all new runtime assertions are pending for this correction. AUD-066 remains open and ledger stays 82/512. This prepares one event, not remote saving or whole-schedule synchronization. Mobile active-day selection, display parity behavior, backend ICS and DST gap/fold resolution are not changed or claimed as fixed.

## AUD-066 corrected-source acceptance

Source 3258d715ffad0b1c2d9e5b4404819d8386bc478b is bound to hosted checkout 76493104d65dba3ec9630927a438c38ee4442dc6 and identical tree 29342be1a3aa759aab40fb85f12d44b8639344cd. Frontend completes 9430 PASS / 784 files with no failures. Static job 118409926012 passes all gates, including types, lint, formatting, message contract, knip and scanner29; production build 118409925971 passes.

AUD-066 is accepted for preparing one Google Calendar event draft from the first eligible lesson of the filtered selected campus week. Real Schedule/Settings/Dropdown/provider/store cases pass all three assertions in job 118409926141 at 01:55:16 UTC, including both prior failures and same-mounted group switching. Ten selector/serialization cases pass in job 118409926038 at 02:00:14; all twenty-four dropdown branch cases pass there at 01:59:31, and three dropdown unit cases pass in job 118409926187 at 02:00:41. Payload, dates, timezone, filters, explicit group contradictions, invalid inputs, parity/year boundaries, legacy Date URL and disabled keyboard behavior are covered.

This is draft preparation, not saving into a remote Google account, whole-schedule synchronization, mobile active-day selection or DST gap/fold resolution. Existing schedule-display parity behavior and backend ICS are unchanged. Focused backend 118409909542 remains 736 PASS / one existing disabled-outage hold in 193.93 seconds; this is not full-CI acceptance.

## AUD-071 real pointer-hit regression first

The affected component is settings/ui/Feedback Snackbar, not the separate ui/Snackbar. Existing standalone Alert fireEvent tests do not prove browser hit testing through the pointer-events-none ancestor. The next test uses the real Profile email button, which opens local feedback without clipboard access, profile writes or navigation. It is appended to the already-selected settings-radio-focus live UI carrier; no smoke selection changes are made.

Install the browser clock before navigation, keep it running through authentication/readiness, then pause immediately before opening feedback. Require a visible, enabled close button with positive area and viewport center, verify elementFromPoint resolves to that button or its descendant, and use an ordinary unforced click. Disappearance must occur with unchanged paused time, excluding automatic dismissal. Always resume the clock before fixture cleanup. No CSS injection, DOM substitute, synthetic click or duration change is introduced. Production remains unchanged until the intended hit-target RED is observed.

## AUD-071 observed browser RED and narrow correction

On a71c6d7, Core run 39357053154 / job 118414135257 reports 26 PASS / 2 FAIL / 2 existing SKIP. Both desktop and mobile failures reach the browser hit-target assertion at settings-radio-focus.live.spec.ts:291 after profile readiness, feedback visibility and close-button checks. Production Snackbar's pointer-events-none ancestor prevents that assertion. No synthetic click or auto-dismiss result is used.

The correction restores pointer events only on direct Snackbar content with the existing Tailwind child variant, retaining the outer pass-through positioning wrapper and existing DOM structure. Alert and timers are unchanged. The same browser assertions remain intact. Static job 118415281486 reports only a Prettier warning in that new live test; its 98-character centerInsideViewport expression is collapsed without changing behavior. Own corrected-source browser and formatter GREEN remain required; AUD-071 stays open.

Owned stop and receipt finish at 02:22:24 UTC; artifact 12235089831 has SHA-256 d8828cdf1c1606ccda4fa5f0cc843571b10c4c27f8d0bfda2ca46a531bddd71d. This failed regression run still cleaned up its owned containers.

## Snackbar corrected-source acceptance

Source 4f64cdad18186e3c8634505f11931dd99de5ccda is bound to hosted checkout ac85a98a815cd2c6d5aa17f363b73323bb3a4bcc and identical tree 77fa13ecba7ed054a4b6b8f452a1a73316729ba3. Frontend finishes 9430 PASS across 784 files. Static job 118436013198 and production build 118436013233 pass. Focused backend job 118435856906 reports 837 PASS / one existing disabled-outage hold in 220.14 seconds, including all fifty-two daemon request/decode cases.

AUD-071 is accepted: Core run 39363500028 / job 118434859608 passes 28 browser cases with two existing skips at 03:33:51 UTC. The unchanged paused-clock hit-target and ordinary-click assertions now pass on desktop and mobile. Pointer events are restored only for Snackbar content; outer positioning, Alert markup and dismissal timing remain unchanged. Owned stop and receipt finish at 03:34:13; artifact 12238472787 has SHA-256 f795e14acd6f54805ffb4791aca20c6aa4439f72df490713b6401a12e82c8024.

AUD-086 is accepted for paired-artifact stability debounce. Earlier source a71c6d7 and checkout fbb400bb797ed0fd683515f19da1d9275c483953 have identical tree e164ddb9bbe0550e010832adead33404763a552d. Job 118415281373 explicitly passes all seven behavioral cases at 02:13:08 UTC: unchanged fresh samples, same-metadata content changes, either output changing despite restored mtime, disappearance/reappearance, stale outputs, missing client assets and continuous churn. Its Node cohort totals 590 PASS / zero FAIL/SKIP. Source blob aa7ea4265ec21ed9d88fc253785d0bc9660adb72 and test blob ce5227820d601c7412d7788f36431d287ab192b3 are unchanged in 4f64. This establishes sampled shell/server stability, not producer completion, stability of every client asset or universally safe producer termination.

The lower bound advances from 84 to 86 original AUD IDs. None of these results enables outage, replaces full-CI acceptance or establishes deployment readiness.

## Pending-input and settings-selection tests first

AUD-089 adds three numeric-fraction counterexamples to the real settings schema, plus three controls preserving existing parseInt string compatibility. A real-schema-to-Settings conditional-rendering case requires exactly the General panel and selected tab. Its router/tab/panel dependencies retain the existing mocks: this is not a full-router or real tab ARIA integration claim. Production remains unchanged before observed RED; a future integer check must not silently rewrite string-coercion compatibility.

AUD-090 adds repeated Enter while isRenaming is rendered true, retention of the editing draft, exactly one trimmed submission after settled rerender, and submit/pending/reopen behavior. Each repeated press requeries the actual textbox. Existing mouse-disabled, Escape, blank/undefined and happy-path assertions remain unchanged. Production stays unchanged before RED. A later pending guard would cover rendered pending state, not every same-tick race before the parent updates its prop.

## Numeric-tab and pending-rename RED corrections

On 2c85f95, job 118442418080 observes all three numeric fraction failures and both pending-Enter duplication failures; Settings container job 118442418051 cannot find the selected tab after validating 1.5. Total frontend is 9433 PASS / six intended FAIL across 784 files.

The schema adds only an integer check after finite validation, preserving union/parseInt compatibility, range checks, fallback and Spotify values. saveRename returns immediately when isRenaming is rendered true, before trimming, callbacks or editing-state changes. Existing draft, Escape, blank/undefined and normal-save behaviors remain untouched. All new regression assertions are unchanged. Own corrected-source GREEN is pending; no claim covers every pre-render same-tick race or a physical full-router integration.

## Fractional tabs and pending rename accepted

Source 1ed440f88de239971ce9e4e6900a41ed6adad7c3 has 9439 frontend PASS across 784 files in jobs 118448485907, 118448485830, 118448485880 and 118448485741. All use checkout 8bbbd09fc76189c0caa6993acfb008728a2d367b with identical source tree 07c72b763fa54ec77bd1bcc6e435b06d76ec8579. The 27 schema cases, six actual Settings closure cases and 41 GroupInfoPanel branch cases pass. Static checks and production build also succeed.

AUD-089 accepts integer-only numeric tabs with General fallback while preserving historical string parsing and valid indices. The selected General panel is tested through the real schema and Settings conditional rendering, not the full router or browser ARIA surface. AUD-090 accepts suppression of rename callbacks while the pending prop is true, draft retention and one settled submission; it does not claim every same-tick race before a parent update is eliminated.

Owned Core run 39367414064 / job 118447292623 finishes 28 browser PASS / two existing SKIP at 04:20:48 UTC on the same verified checkout/tree. Owned containers stop and the metadata receipt completes at 04:21:10, with upload at 04:21:11. Artifact 12241160221 has SHA-256 f4eaf7e8131cf21cfb7a512b4eae2c39155c4c77b3665c8157ebb9fe7719a502. This is the owned Core cohort, not the full 59-spec acceptance or an outage run.

## AUD-100 IndexedDB version accepted

The shared version-four constant is used by both page and worker. Unchanged 41-case page suite and two-case actual worker migration suite pass in source-bound jobs 118448485830 / 118448485741. Page cases cover worker-shaped existing stores, version-three data retention and page-first store creation; worker cases use fake-indexeddb to exercise initOfflineQueue. This closes the original version mismatch, not real-browser cross-tab upgrade blocking or sync delivery.

## AUD-097 provider-commit timing tests first

Eleven new entrypoint cases separate bootstrap start, the existing real ue:app-hydrated publisher and deferred telemetry clocks. They cover both arrival orders, repeated publication, missing/stale markers, a commit emitted during the mocked render call, disabled/import/init-failed telemetry, independent observability failure and LHCI omission. Test-owned event listeners are tracked and removed after assertions, not during leak assertions. The old telemetry-clock fixture remains unchanged until actual RED.

The intended metric remains APP_TTI for wire compatibility but denotes bootstrap-to-provider-tree commit, not standardized browser interactivity, router/data readiness or completion of every Suspense subtree. Preserve the ten-second deferral and certification reporter's LCP/INP/CLS whitelist. Do not fabricate an endpoint from hydrateRoot return, telemetry readiness or an already-true boolean marker. No production telemetry change is included yet.

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

## 2026-10-20 08:34 UTC — search proof and native-focus diagnosis

ce03 SearchDialog behavior has 23 PASS in job 118524020061 (2263 PASS overall). Core job 118522672667 has 34 PASS / two FAIL / two existing SKIP, with both failures confined to the compact-navbar declaration; all six controlled search instances pass. The regular helper's non-React useMockApi import is aliased setupMockApi to satisfy hook naming without suppression; AUD-105 awaits corrected static proof.

AUD-104's diagnostic frames establish native forward Tab scrolls out of compact state. Re-establish compact mode while settings retains focus before independently testing reverse Tab; do not require traversal to preserve scroll. No production behavior, manual blur, prevented scroll or conditional success is introduced. Both projects must pass the corrected test before closure.

AUD-107 has two actual first-shortcut failures and two passing controls in job 118524019167 (2284 PASS / two FAIL). Preserve real lazy loading and the normal mounted toggle owner while addressing queued opening intent. No corrected-source acceptance yet.

The correction queues store-local opening intent until the lazy dialog subscribes, then leaves shortcut toggles to the existing dialog handler. Escape and final cleanup clear pending intent; no event replay or module-global flag is introduced. Current four regressions do not establish deterministic cold-import/unmount race coverage.

## 2026-10-20 09:00 UTC — native keyboard and strict search verified

Source 3cc49cd / checkout 257a3d35 share tree eaf9ec9857c808adb96a3888e1e404584c48befe. Core job 118535048190 has 36 PASS / two fixed SKIP, successful cleanup, receipt 12251734381 and digest 010b1a9fe601740208d87897c3462d7850da6e7e30cd7f3e54dec34497a0d982. AUD-104 and AUD-105 enter the ledger: compact traversal is tested with independent valid forward/reverse preconditions, and six shared strict search instances pass. SearchDialog has 23 behavior plus three focus-trap passes; regular-helper TypeScript/ESLint passes. This is not the whole nightly suite or service-worker search proof.

AUD-107 has four real-dialog and eighteen existing lifecycle passes in job 118536398994 (2286 PASS). Six new store ownership/cleanup controls remain unexecuted; keep it outside the ledger until checked. No deterministic cold-import/native race claim.

Next tests-first cases cover AUD-110's actual serialized motion collector, AUD-112's actual regular diagnostic classifier, AUD-113 cache updates/removal, and AUD-114 dirty same-item refresh with reset controls. Existing behavior is retained before RED; preserve pristine refresh and all source/image cleanup controls. Motion collection uses root plus descendants and actual JSDOM styles without changing Core's inventory. Latest verified lower bound: 109/512.

## 2026-10-20 09:33 UTC — search lifecycle verified, remaining UI RED reproduced

AUD-107 enters the ledger at 110/512: f06 job 118546333989 passes 24 lifecycle and four real-dialog cases (2292 PASS overall). Core job 118545359975 has 36 PASS / two fixed SKIP, successful cleanup and receipt 12253583196, digest f9a48fb8344754f23fa07169bb61ed6377134a63d275d332ff264dcfd1322891. Cold-import/native races are not newly proven.

Actual selected RED: AUD-110 five collector failures, AUD-112 six minified-code failures (job 118546333829); AUD-113 three update/removal failures (118546333924); AUD-114 one dirty-refresh failure (118546334084). Preservation controls pass. Corrections inspect every duration component, recognize exact code tokens, subscribe through stable reference snapshots, and preserve session-scoped edits while resetting images at session boundaries. Three cache and six English/image/abort controls supplement the existing regressions. Corrected-source GREEN remains required; no native reduced-motion/full-nightly or in-flight save-session claim.

## 2026-10-20 10:02 UTC — collector and classifier accepted

On 44a9d818 / checkout ba478d71 (identical tree 160ddba4), frontend job 118561272734 passes fourteen motion collector cases and thirty-two hydration classifier cases at 09:47:25–26 UTC, totaling 2672 PASS. AUD-110 and AUD-112 enter the ledger for these bounded helpers, not native reduced-motion or hydration recovery. Job 118561272774 passes all twenty-six News mutation-contract cases (2272 PASS overall), but AUD-114 waits for exact formatter cleanup. Job 118561272679 passes all ninety event branch cases (2297 PASS overall); AUD-113 is accepted for unchanged-ID navigation tracking list updates/removals, with three original RED cases and three supplementary controls passing. Ordering/filtering/deduplication and invalid-session behavior are preserved. Existing abort handling and session-reset behavior remain intact; in-flight save completion across session changes is not claimed fixed.

## 2026-10-20 10:24 UTC — formatter cleanup and next DOM regressions

9cface Node job 118572527812 obtains exact installed-Prettier output for the News mutation-contract fixture; apply it and remove the temporary diagnostic/imports completely. Its other 617 cases pass, and static job 118572527938 flags only that News fixture. Clean-source verification remains required for AUD-106/114. Core job 118570418071 has 36 PASS / two fixed SKIP plus successful cleanup and receipt 12256873702, digest fb48be7fd1efb05e81362264bffbd9ab5547db49bef36afdf389567f4744e0c1.

AUD-119 adds two real standalone local-midnight cases and a separate parent forwarding/selected-month control before a clock correction. AUD-124 adds five accessible-name regressions through real settings Dialog/providers and two EventCreate preservation controls. The original row's location list is truncated; the five-target reconstruction is documented rather than claimed as recovered coordinates. Mocked LessonDetails wrappers are not naming evidence. Existing assertions stay unchanged, and no native-browser/screen-reader or DST proof is claimed. Previously accepted UI findings remain unchanged; latest overall ledger is 117/512.
