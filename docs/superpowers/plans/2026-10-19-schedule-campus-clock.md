# Schedule Campus Clock Implementation Plan

> **For agentic workers:** Use test-driven development and independent review. Root owns all Git writes; execute checks through hosted Actions only.

**Goal:** Correct AUD-003 description escaping, AUD-004 adjacent next lessons and AUD-006 campus-clock coherence.

**Architecture:** Preserve the existing provider and query/storage boundaries. Share an actual ticking instant across schedule selection, derive campus calendar/clock parts in a pure utility, and retain standalone useScheduleTime compatibility.

**Tech Stack:** React, TypeScript, Intl, Vitest/Testing Library, Python/pytest.

**Spec:** [Schedule calendar and campus-clock corrections](../specs/2026-10-19-schedule-campus-clock.md).

## Global Constraints

- Only egorribun through the GitHub plugin; no local repository execution, merge or deployment.
- Production changes follow observed hosted assertion RED.
- No fake shifted Date, process TZ mutation, new skip, waiver or coverage exclusion.
- Keep Sunday todayIdx -1, ISO-week parity, manual parity lifetime, existing query keys and cache/storage behavior.
- Preserve existing null-zone fallback without claiming unknown-zone correctness.

## Review Focus

- Async timezone resolution must update automatic selection without overriding a manual choice.
- Choosing the already active parity is still an explicit choice.
- Queued functional setters must each see the latest effective previous value.
- Hidden date rollover must refresh even at the same hour/minute after a full day.
- Countdown visibility and its actual seconds must use the same zone, including quarter-hour offsets.

## Accepted implementation checkpoint

Implementation bd4fd6f and formatter correction f8545c8 completed their own final-source CI at f8545c8: Matrix 39194937435, 23 terminal workflows (21 success/two skips), 136 check runs, all 78 exact required pairs present (77 success/one neutral Checkov comparison uncertainty). Python 16417 PASS/174 SKIP, frontend 9318 PASS/771 files, PostgreSQL 178 PASS/9 SKIP; quality contract/artifacts/checksum and 4459-line diff coverage passed. Owned Live stop/receipt/upload passed and its checkout tree equals f854. See STATUS and AUDIT supplements for exact source links, artifacts and limits. Quiet backend logs establish a successful full cohort, not an individually printed ICS PASS. No release/main/bootstrap/merge/deploy is claimed.

The supplemental helper tests are not represented as an independently observed pre-implementation helper-level RED; the published f4 behavioral regressions drove the implementation. Independent formatter failures were tracked separately from those genuine assertions.

## Historical RED evidence

Hosted f4dfcbe Matrix 39190366176 establishes frontend assertion RED (10 failures / 9295 passes) and exact ICS RED (job117862849856: 1 failure / 5584 passes / 33 skips). Owned Live stop/receipt is successful and source-tree bound. Minimal implementation and supplemental helper/lifecycle tests received independent static review; their final-source CI is now accepted as recorded above. The separate cache-test blank-line formatter defect is corrected without removing RED assertions. No finding is declared closed by static review alone.

## Task 1: Publish precise failing regressions

**Files:** tests/test_ical.py; frontend/src/hooks/__tests__/useScheduleTime.test.tsx; frontend/src/hooks/__tests__/useScheduleData.cache.test.tsx; frontend/src/components/schedule/__tests__/ScheduleHeader.behavior.test.tsx; frontend/src/components/schedule/__tests__/FlipCountdown.test.tsx; frontend/src/pages/__tests__/Schedule.behavior.test.tsx.

- [x] Review the six test-only diffs against current source and fixture contracts.
- [x] Keep Date/timer/visibility restoration exact; leave real timeouts where asynchronous waitFor is used.
- [x] Publish tests with this spec/plan and truthful audit/status evidence, after the previous source reaches its CI checkpoint.
- [x] Observe exact hosted assertion failures for escaping, adjacent selection and campus time. Distinguish setup/type/format gate errors from behavioral RED; fix independent formatting defects without treating them as behavioral evidence.

## Task 2: Correct ICS and adjacent selection

**Files:** app/services/ical.py; frontend/src/hooks/useScheduleTime.ts.

- [x] Join description fields with real newlines before the existing _escape call; retain the escaping implementation.
- [x] Allow a valid next lesson starting at the current lesson's end, retaining half-open current intervals and invalid-bound rejection.
- [x] Verify the exact new regressions and all existing related tests in hosted CI.

## Task 3: Share the campus calendar and effective instant

**Files:** frontend/src/utils/campusTimezone.ts; frontend/src/utils/scheduleUtils.ts; frontend/src/hooks/useScheduleClock.ts (new); frontend/src/hooks/useScheduleTime.ts; frontend/src/hooks/useScheduleData.ts.

**Interfaces:**
- getCampusClockParts(input, timeZone) returns null without a usable zone/instant, otherwise campus dateKey, weekday (Sunday zero), hour, minute and second.
- useScheduleClock(enabled = true): Date owns the existing minute-granular ticker/visibility lifecycle.
- useScheduleTime(todayLessons, hasToday, nowTick?) retains existing two-argument callers and return shape; an external tick disables its internal ticker.
- Existing nowParity/isoWeekNumber retain their default local semantics and gain an optional campus-zone input.

- [x] Add supplemental utility regressions for calendar/ISO boundaries and clock parts alongside the minimal helpers driven by the observed hosted behavioral RED.
- [x] Use Gregorian/latn/h23 Intl parts and UTC calendar arithmetic, never host getters for known campus-zone dates.
- [x] Extract the existing ticker with epoch-minute equality; keep exactly one enabled schedule ticker in orchestration and correct cleanup.
- [x] Have useScheduleData obtain the shared instant before deriving weekday/parity and pass it to time calculations.
- [x] Replace fixed initial parity with derived automatic parity plus nullable manual override. Preserve React Dispatch/SetStateAction, explicit same-value choices and queued updaters.
- [x] Keep the returned nowTick as the actual instant and all query/storage behavior unchanged.
- [x] Verify null resolution, manual choice, current/next selection and midnight/full-day resume contracts.

## Task 4: Reconcile visible consumers with that clock

**Files:** frontend/src/pages/Schedule.tsx; frontend/src/components/schedule/ScheduleHeader.tsx; frontend/src/components/schedule/FlipCountdown.tsx.

- [x] Derive past-filter and countdown-window minutes from the same campus utility and supplied actual instant.
- [x] Keep getSecondsUntilTarget's existing two-argument fallback; allow its caller to provide the campus zone.
- [x] Recompute actual countdown seconds when zone/target changes and on each visible second tick. Keep hidden ticks paused and the existing callback policy.
- [x] Verify Header with the real countdown, quarter-hour zone changes and first-visible-tick catch-up. Keep page-filter proof explicitly scoped to its mocked hook boundary.
- [x] Do not change unrelated calendar month navigation, selected-week behavior or other countdown product semantics.

## Task 5: Validate and record the corrected source

- [x] Obtain independent review of the narrow implementation and compatibility paths.
- [x] Before publication, reconcile affected source catalogs and baseline line metadata while preserving all identities and gates. The six test-only paths currently have no baseline entries.
- [x] Require full backend/frontend/quality/security CI on the implemented SHA; focused results are not a full verdict.
- [x] Verify owned-live stop/receipt and exact source-tree provenance before superseding a run.
- [x] Update the three AUD IDs with precise proof limits; retain other open findings and the unknown aggregate closure percentage.
