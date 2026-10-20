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
