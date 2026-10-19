# Complete registration analytics and explicit delta units

Date: 2026-10-19. Source inspected: bd4fd6f0f6cb6435978764f0ca4107ac4d031def.
Scope: AUD-011, AUD-012 and AUD-014; only egorribun through GitHub plugin. Tests execute in hosted Actions.

## Established behavior and defect boundaries

Attendance means registration, not verified physical presence. The existing summary denominator already counts all active events in the selected half-open window and must remain unchanged. Its current/previous-window comparison is correct. The capped five-item recent feed cannot establish daily registration percentages or an exact streak.

## Delivery order

Publish one reviewed tests-first batch for daily aggregates, card units and the owner-confirmed streak contract. They share the attendance response boundary, so a single coherent regression batch avoids repeating full CI solely for sequential field additions. Each behavioral change still requires its own observed RED; implementation, review and full-source acceptance remain mandatory.

## Required output

Keep recent as a bounded feed. Add complete daily aggregates for the selected current window, each with an explicit calendar date, registered count and total eligible active-event count. Include event-days with zero registrations; omit days with zero eligible events. Preserve the existing active-event population, user-specific left join, half-open instant boundaries and period cache isolation. Group starts_at into dates using the authoritative settings.campus_timezone. Keep rolling half-open UTC instant bounds unchanged, so the first and current campus dates can be partial buckets; do not silently switch to midnight-aligned windows. Calendar grouping must not depend on database/browser host timezone. New response fields must survive actual summary response validation and cache round trips. The existing async_client five-SQL-query GET budget is part of acceptance; do not increase or bypass it to add daily and streak data. Prefer a coherent attendance query/result contract over extra per-day or per-history queries.

Frontend must use the complete aggregates rather than reconstruct denominator from recent rows. Absent/malformed aggregate data must not fabricate a 100% series from recent. The chart's formatDate callback must also treat YYYY-MM-DD as a calendar key, not shift UTC midnight into the browser's previous day. Test this with a bounded native-formatter default-zone shim, not process TZ mutation. Existing timestamp feed and heatmap behavior is a separate boundary and must not regress.

## Owner-confirmed current streak

On 2026-10-19 03:19 UTC the owner approved consecutive calendar dates of events for which the user registered, deduplicating multiple events per day, a current run ending today or yesterday, campus timezone dates, and independence from the 30/90/180-day display filter. Grades and other non-registration activity are not part of this streak. A gap ends the run; an older run not reaching yesterday yields zero. The result cannot be capped by the five-item feed or selected period. Preserve existing active/past-event eligibility; do not count future event instants as completed activity.

Return authoritative backend streak_days computed for the response's current campus date, using the same now instant as the window calculation but without the selected-window lower bound. Preserve the existing bounded statistics cache policy; this is a cached snapshot, not a real-time counter. Map it to an optional frontend streakDays; a missing signal must not be inferred from feed row order. Keep the existing UI badge threshold of more than two days. Validate stale cached payload compatibility and ordinary cache expiry/invalidation without changing permissions or claiming instantaneous rollover freshness.

## Trend units

Preserve numeric backend deltas. Attendance is percentage points, grades are score points on the reported scale, and participation is an event-count difference. Each card supplies an explicit unit; localize English/Russian copy and numerical formatting. Do not label any of these deltas a relative percent. Missing/nonfinite values do not create misleading badges. Registration copy must not imply measured attendance.

## Verification before implementation

Publish behavioral regressions against existing code and observe exact hosted assertion RED. Cover complete daily population including zero-registration event-days, user isolation, inactive/exact-window exclusions, over-five history, timezone midnight, absent aggregate fallback, each card's unit, duplicate event dates, gaps, today/yesterday anchoring, stale historical runs and period independence. Preserve existing aggregate denominator and cache tests. Review API schema/DTO and actual PostgreSQL compatibility as well as frontend parsing/locale behavior.

A bounded early shard-zero regression run may surface these two backend test files before the long full shard. It uses the existing locked environment, isolated temporary test state and no coverage output. The service/window contract file also runs in the existing isolated PostgreSQL integration job, using its current explicit test-database reset guard and per-test cleanup. HTTP payload/query-budget assertions remain in the ordinary unit lane. PostgreSQL authentication/session setup adds RLS control statements to that generic HTTP budget; do not weaken the budget or change RLS to make a new cross-database HTTP case pass. PostgreSQL evidence here is for service/query behavior, not a new full HTTP/auth-stack acceptance. No new service, account, role or connection is introduced. Every original integration test, full unit shard, coverage/provenance artifact and aggregate gate remains mandatory after success; focused and cross-database duplicate executions are not added to the unique unit-suite count.

No production implementation until relevant RED. No new exclusions, baseline identities, scanner dispositions, workflow weakening, main changes, merge or deployment. Own full CI, source-bound live cleanup and exact required gates remain mandatory before closure.
