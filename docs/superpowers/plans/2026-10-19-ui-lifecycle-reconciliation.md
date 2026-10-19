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
