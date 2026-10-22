# Schedule calendar and campus-clock corrections

Date: 2026-10-19 (Europe/Istanbul). Scope: AUD-003, AUD-004 and AUD-006 from the October audit. Source review: 7b340e78c397cc908ecd0eafe0d4c2c5cd7fd168. Tests-first work on egorribun through GitHub only; implementation and hosted acceptance remain separate.

## Outcomes

- AUD-003: join human-readable iCalendar description fields with real newlines before the existing escaping function serializes them exactly once. Preserve field escaping and campus recurrence/date behavior.
- AUD-004: an upcoming lesson starting exactly when the current lesson ends remains the next lesson. Preserve malformed-bound rejection and current-lesson half-open intervals.
- AUD-006: when the existing authoritative campus timezone is available, automatic ISO parity, weekday, current/next lesson, past-lesson filtering and actual visible countdown use that same campus calendar/clock, not the browser zone.

The root route already supplies CampusTimezoneProvider for SSR/client. Do not add another config fetch, rewire that provider, change query keys/cache persistence, or replace the ISO-week convention with a semester anchor. Sunday remains todayIdx -1, not a seventh displayed schedule day.

## Campus clock and manual selection

Use the existing campus date/time utilities as the integration point for pure calendar/clock conversion. Include seconds for the actual FlipCountdown, not only its parent visibility condition. Calendar arithmetic for ISO week and weekday must be independent of host getters. Keep nowTick as an actual instant, not a fake Date whose timezone has been shifted. The countdown recalculates from the actual instant on each visible one-second tick and when its zone/target changes, so hidden elapsed time is not lost; retain the existing completion callback policy.

Derive all orchestrator day/parity/time calculations from one effective ticking instant. Preserve minute-granular scheduling, hidden-tab suspension, visibility-resume refresh and cleanup. Compare epoch minutes rather than only wall-clock hour/minute so resuming after a full day cannot keep yesterday's state. Do not create duplicate active schedule tickers when sharing the instant.

Preserve existing local fallback while the campus zone is unavailable; recompute automatic fields when the provider resolves. This fallback is not proof that an unknown campus zone is correct. An explicit parity selection persists for the component lifetime. Preserve the existing React Dispatch/SetStateAction setter semantics, including choosing the currently active value and queued functional updaters. URL/store hydration currently synchronizes only week offset w and must not become a manual parity action.

The full calendar-dot/month-navigation algorithm is outside this bounded correction. Do not change manual selected week behavior, API payloads, recurrence policy, data storage, permissions or unrelated countdown product semantics.

## Regression evidence

Before implementation, require hosted assertion RED for:
- exact single escaping of generated ICS description newlines, with a deterministic campus-date fixture;
- adjacent lessons where next.start equals current.end;
- UTC versus Moscow at 2026-10-18T21:30Z, where ISO week/day differ;
- actual Monday current/next lesson selection in Moscow;
- null-to-known provider refresh and an explicit manual parity choice;
- campus-midnight rollover on visibility resume;
- page filtering of past/current lessons in two explicit campus zones;
- real Header plus FlipCountdown showing thirty minutes, a mounted countdown recalculating when its campus zone changes, and catch-up on the first visible tick after a hidden interval.

Use real hook/provider logic with existing API/auth/storage fixture boundaries. The page filter test deliberately supplies mocked hook data and projects child props, so it proves the page filtering boundary, not browser end-to-end acceptance. Header/countdown tests must exercise the real countdown, not mock its value. No process-wide TZ mutation or new skips.

## Verification and boundaries

Keep all existing tests, coverage floors and required contexts. Add focused helper/lifecycle edge cases as needed for complete changed-code coverage without exclusions. Verify imports, formatting, timer restoration and all source-bound metadata before publishing; a tooling/fixture failure does not count as behavioral RED.

After the minimal correction, require each new assertion to pass, full frontend/backend and quality gates on the corrected SHA, and normal owned-live cleanup. Record scoped evidence and remaining limitations in AUDIT/STATUS. Do not label the full audit complete, select a release candidate, merge, deploy, or modify main.
