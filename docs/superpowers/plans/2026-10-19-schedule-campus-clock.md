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

## Task 1: Publish precise failing regressions

**Files:** tests/test_ical.py; frontend/src/hooks/__tests__/useScheduleTime.test.tsx; frontend/src/hooks/__tests__/useScheduleData.cache.test.tsx; frontend/src/components/schedule/__tests__/ScheduleHeader.behavior.test.tsx; frontend/src/components/schedule/__tests__/FlipCountdown.test.tsx; frontend/src/pages/__tests__/Schedule.behavior.test.tsx.

- [ ] Review the six test-only diffs against current source and fixture contracts.
- [ ] Keep Date/timer/visibility restoration exact; leave real timeouts where asynchronous waitFor is used.
- [ ] Publish tests with this spec/plan and truthful audit/status evidence, after the previous source reaches its CI checkpoint.
- [ ] Observe exact hosted assertion failures for escaping, adjacent selection and campus time. Fix any setup/type/format failure before counting RED.

## Task 2: Correct ICS and adjacent selection

**Files:** app/services/ical.py; frontend/src/hooks/useScheduleTime.ts.

- [ ] Join description fields with real newlines before the existing _escape call; retain the escaping implementation.
- [ ] Allow a valid next lesson starting at the current lesson's end, retaining half-open current intervals and invalid-bound rejection.
- [ ] Verify the exact new regressions and all existing related tests in hosted CI.

## Task 3: Share the campus calendar and effective instant

**Files:** frontend/src/utils/campusTimezone.ts; frontend/src/utils/scheduleUtils.ts; frontend/src/hooks/useScheduleClock.ts (new); frontend/src/hooks/useScheduleTime.ts; frontend/src/hooks/useScheduleData.ts.

**Interfaces:**
- getCampusClockParts(input, timeZone) returns null without a usable zone/instant, otherwise campus dateKey, weekday (Sunday zero), hour, minute and second.
- useScheduleClock(enabled = true): Date owns the existing minute-granular ticker/visibility lifecycle.
- useScheduleTime(todayLessons, hasToday, nowTick?) retains existing two-argument callers and return shape; an external tick disables its internal ticker.
- Existing nowParity/isoWeekNumber retain their default local semantics and gain an optional campus-zone input.

- [ ] Add pure utility regressions for calendar/ISO boundaries and clock parts before implementing those helpers.
- [ ] Use Gregorian/latn/h23 Intl parts and UTC calendar arithmetic, never host getters for known campus-zone dates.
- [ ] Extract the existing ticker with epoch-minute equality; keep exactly one enabled schedule ticker in orchestration and correct cleanup.
- [ ] Have useScheduleData obtain the shared instant before deriving weekday/parity and pass it to time calculations.
- [ ] Replace fixed initial parity with derived automatic parity plus nullable manual override. Preserve React Dispatch/SetStateAction, explicit same-value choices and queued updaters.
- [ ] Keep the returned nowTick as the actual instant and all query/storage behavior unchanged.
- [ ] Verify null resolution, manual choice, current/next selection and midnight/full-day resume contracts.

## Task 4: Reconcile visible consumers with that clock

**Files:** frontend/src/pages/Schedule.tsx; frontend/src/components/schedule/ScheduleHeader.tsx; frontend/src/components/schedule/FlipCountdown.tsx.

- [ ] Derive past-filter and countdown-window minutes from the same campus utility and supplied actual instant.
- [ ] Keep getSecondsUntilTarget's existing two-argument fallback; allow its caller to provide the campus zone.
- [ ] Recompute actual countdown seconds when zone/target changes and on each visible second tick. Keep hidden ticks paused and the existing callback policy.
- [ ] Verify Header with the real countdown, quarter-hour zone changes and first-visible-tick catch-up. Keep page-filter proof explicitly scoped to its mocked hook boundary.
- [ ] Do not change unrelated calendar month navigation, selected-week behavior or other countdown product semantics.

## Task 5: Validate and record the corrected source

- [ ] Obtain independent review of the narrow implementation and compatibility paths.
- [ ] Before publication, reconcile affected source catalogs and baseline line metadata while preserving all identities and gates. The six test-only paths currently have no baseline entries.
- [ ] Require full backend/frontend/quality/security CI on the implemented SHA; focused results are not a full verdict.
- [ ] Verify owned-live stop/receipt and exact source-tree provenance before superseding a run.
- [ ] Update the three AUD IDs with precise proof limits; retain other open findings and the unknown aggregate closure percentage.
