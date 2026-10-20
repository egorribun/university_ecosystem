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
