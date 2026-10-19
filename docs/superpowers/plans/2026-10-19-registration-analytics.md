# Registration Analytics Implementation Plan

**Goal:** Resolve AUD-011 daily denominator, AUD-012 trend units and AUD-014 current streak without changing existing aggregate metrics or deriving completeness from recent samples.

**Spec:** ../specs/2026-10-19-registration-analytics.md.
**Tests:** tests/test_user_analytics_window_contracts.py; tests/test_stats_api.py; frontend/src/hooks/__tests__/useActivityData.test.tsx; frontend/src/features/activity/components/__tests__/ActivityTrendUnits.test.tsx; frontend/src/features/activity/components/__tests__/ActivityMotivation.closure.test.tsx; frontend/src/features/activity/components/__tests__/TrendChip.closure.test.tsx.

**Implementation boundaries:** app/repositories/user_stats_repository.py; app/services/user/analytics_service.py; frontend/src/features/activity/types.ts and parsers.ts; frontend/src/hooks/useActivityData.ts; ActivityMotivation, TrendChip, AttendanceCard, GradesCard and ParticipationCard; EN/RU activity locale files. Changes outside these boundaries require a concrete related defect, not speculative cleanup.

**Source:** f8545c8ddead5fdd88ac9a336f1fb083f752168a. Only egorribun via GitHub plugin. Root owns Git; hosted Actions only.

## Task 1: Publish reviewed RED contracts

- [ ] Review six test files against actual service/HTTP/card behavior and existing fixtures.
- [ ] Keep the correct backend aggregate denominator assertions; add daily expectations, not replacement ratios.
- [ ] Test complete campus-day aggregation, other-user registration, zero-registration days, inactive and exact-now exclusion, period boundaries and more-than-five history.
- [ ] Require real cards and real TrendChip for EN/RU unit assertions; reduced-motion fixtures must preserve real DOM behavior.
- [ ] Correct the old frontend synthetic-absence chart assertion, retaining grade and heatmap coverage.
- [ ] Refresh only existing baseline line references: six in test_stats_api.py and two in reusable-backend-tests.yml. Retain all 319 identities, timestamps, flags, plugins and filters.
- [ ] Add a bounded shard-zero early run of the two analytics regression files after locked dependency sync/frozen-RC contracts. Use a unique temporary basetemp, exact cleanup and no coverage output; retain every full-shard, provenance and aggregate coverage step unchanged.
- [ ] Include tests/test_user_analytics_window_contracts.py in the existing dedicated PostgreSQL integration argument list, preserving all existing tests and reset-safety/cleanup fixtures. HTTP/query-budget assertions remain in the unit lane. This adds no service, context or waiver and must produce its own PostgreSQL service/query assertion evidence; do not bypass authentication/RLS overhead accounting.
- [ ] Independently review the focused gate's isolation, time budget and unchanged full-suite requirement; it is fast feedback, not replacement evidence or a new required context.
- [ ] Publish tests/spec/plan and truthful audit/status after current schedule verification reaches its checkpoint.
- [ ] Observe exact hosted assertions before production implementation; setup or formatter errors are not RED.

## Task 2: Provide complete daily aggregates

- [ ] Repository/service return daily [{date, registered, total}] from the existing active-event population and exact current half-open window.
- [ ] Preserve the existing five-SQL-query GET budget for /stats/summary. Daily and complete streak data must not be bolted on as extra sequential queries that exceed the current contract. Keep aggregation/query design portable and verify it on both SQLite and PostgreSQL without weakening the budget.
- [ ] Use validated campus timezone for calendar dates, with explicit aware/naive normalization compatible with the database contracts.
- [ ] Include zero-registration event-days and omit zero-event days; return ascending dates without the recent cap.
- [ ] Preserve existing aggregate/previous-window values and recent feed behavior.
- [ ] Retain summary/attendance endpoint propagation, authentication, user/period cache isolation, bypass and invalidation.
- [ ] Inspect cache transition: cached older payloads cannot fabricate percentages; missing daily remains unavailable until refreshed.
- [ ] Verify related service, repository and HTTP tests on hosted CI.

## Task 3: Render truthful chart values and metric units

- [ ] Extend response/domain types and parser contracts for complete daily data; missing/invalid data cannot become a recent-derived 100% chart.
- [ ] Preserve campus date keys and sort valid series; format date-only chart labels without shifting UTC midnight into the browser's prior day. Preserve existing timestamp feed formatting.
- [ ] Pass explicit percentage-point, score-point or event-count units from real cards.
- [ ] Localize numerical formatting, signs, unit/plural strings in EN/RU; do not display negative rounded zero.
- [ ] Preserve intended generic TrendChip compatibility where used outside the three cards and update direct tests consistently with the chosen explicit API.
- [ ] Reconcile adjacent registration labels without claiming physical attendance.
- [ ] Verify all frontend regression/static/translation/build gates.

## Task 4: Compute the owner-confirmed streak

- [ ] Obtain genuine RED for unique consecutive current dates, duplicates, gaps, stale history, period independence, campus midnight, inactive/future/other-user exclusions and missing-authority frontend behavior.
- [ ] Compute streak_days from complete user registration history for eligible active events strictly before now, in campus calendar dates.
- [ ] Count only a run ending today or yesterday; keep history independent of period and recent cap.
- [ ] Keep response/cache as the existing bounded snapshot and preserve cache invalidation; do not claim a real-time day-rollover counter.
- [ ] Map authoritative count to optional streakDays and preserve the more-than-two-days badge threshold; never infer a count from capped recent rows.
- [ ] Preserve unrelated motivation-message priority and loading behavior.
- [ ] Verify all related backend/API/frontend regressions.

## Task 5: Own full-source acceptance

- [ ] Independent implementation review, including malformed/empty datasets, exact time boundaries, localization and cache paths.
- [ ] Reconcile source metadata without adding scanner exceptions, baselines, skips or lowering thresholds.
- [ ] Full backend/frontend/quality/security CI on the implementation SHA, exact 78 required context/app pairs, and source-tree-bound owned-live cleanup.
- [ ] Record precise AUD-011/AUD-012/AUD-014 evidence only after their corresponding hosted proof.

No main update, RC selection, merge or deployment. No aggregate closure percentage inferred from these findings.
