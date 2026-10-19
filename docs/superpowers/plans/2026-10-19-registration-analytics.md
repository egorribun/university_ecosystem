# Registration Analytics Implementation Plan

**Goal:** Resolve AUD-011 daily denominator, AUD-012 trend units and AUD-014 current streak without changing existing aggregate metrics or deriving completeness from recent samples.

**Spec:** ../specs/2026-10-19-registration-analytics.md.
**Tests:** frontend/src/features/activity/__tests__/parsers.closure.test.ts (supplemental helper cases); tests/test_user_analytics_window_contracts.py; tests/test_stats_api.py; frontend/src/hooks/__tests__/useActivityData.test.tsx; frontend/src/features/activity/components/__tests__/ActivityTrendUnits.test.tsx; frontend/src/features/activity/components/__tests__/ActivityMotivation.closure.test.tsx; frontend/src/features/activity/components/__tests__/TrendChip.closure.test.tsx.

**Implementation boundaries:** app/repositories/user_stats_repository.py; app/services/user/analytics_service.py; frontend/src/features/activity/types.ts and parsers.ts; frontend/src/hooks/useActivityData.ts; ActivityMotivation, TrendChip, AttendanceCard, GradesCard and ParticipationCard; EN/RU activity locale files. Changes outside these boundaries require a concrete related defect, not speculative cleanup.

**Source:** f8545c8ddead5fdd88ac9a336f1fb083f752168a. Only egorribun via GitHub plugin. Root owns Git; hosted Actions only.

## Task 1: Publish reviewed RED contracts

- [x] Review six test files against actual service/HTTP/card behavior and existing fixtures.
- [x] Keep the correct backend aggregate denominator assertions; add daily expectations, not replacement ratios.
- [x] Test complete campus-day aggregation, other-user registration, zero-registration days, inactive and exact-now exclusion, period boundaries and more-than-five history.
- [x] Require real cards and real TrendChip for EN/RU unit assertions; reduced-motion fixtures must preserve real DOM behavior.
- [x] Correct the old frontend synthetic-absence chart assertion, retaining grade and heatmap coverage.
- [x] Refresh only existing baseline line references: six in test_stats_api.py and two in reusable-backend-tests.yml. Retain all 319 identities, timestamps, flags, plugins and filters.
- [x] Add a bounded shard-zero early run of the two analytics regression files after locked dependency sync/frozen-RC contracts. Use a unique temporary basetemp, exact cleanup and no coverage output; retain every full-shard, provenance and aggregate coverage step unchanged.
- [x] Include tests/test_user_analytics_window_contracts.py in the existing dedicated PostgreSQL integration argument list, preserving all existing tests and reset-safety/cleanup fixtures. HTTP/query-budget assertions remain in the unit lane. This adds no service, context or waiver and must produce its own PostgreSQL service/query assertion evidence; do not bypass authentication/RLS overhead accounting.
- [x] Independently review the focused gate's isolation, time budget and unchanged full-suite requirement; it is fast feedback, not replacement evidence or a new required context.
- [x] Publish tests/spec/plan and truthful audit/status after current schedule verification reaches its checkpoint.
- [x] Observe exact hosted assertions before production implementation; setup or formatter errors are not RED.

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

- [x] Obtain genuine RED for unique consecutive current dates, duplicates, gaps, stale history, period independence, campus midnight, inactive/future/other-user exclusions and missing-authority frontend behavior.
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

## Execution record and rulings

- Tests-first source e3f8fbe produced 18 actual frontend assertion failures; a separate Ruff layout error blocked backend. Formatter-only 4249718 passed both pre-commit gates.
- On 424, early backend job 117894232677 produced 21 failures and 15 passes in 12.22s, including the unmodified summary query budget of seven statements versus five. The full shard was skipped afterward. PostgreSQL job 117894232644 reached the daily equality regression and stopped with one failure, 162 passes and nine skips; this is not complete PostgreSQL acceptance.
- Frontend 424 jobs 117893116177/117893116133 reconfirmed the 18 behavioral failures. Job 117893116090 independently exposed all three non-finite TrendChip assertions (2240 passes); only after reading those failures was the finite guard included in the publication candidate. Shard three job 117893116126 passed 2338 tests.
- Ruling: the formatter correction could supersede ordinary Matrix CI while the separately serialized owned-live run finished unchanged. Its cancel-in-progress:false guard was read from exact source, old cleanup was tracked to success, and no old receipt substitutes for new-source evidence. Cost: old Matrix's cancelled shards cannot supply complete results.
- Ruling: grade and participation current/previous populations must be fetched once each and partitioned at the same UTC boundary. The observed summary budget failure makes this a necessary part of the fix, not an optional budget waiver. Authentication and RLS remain unchanged.
- Ruling: keep the existing green/upward icon for a displayed zero trend rather than redesign unrelated presentation. The corrected signed text must not show negative rounded zero. No neutral-icon redesign is claimed.
- Supplemental parser/date/plural cases cover the implemented helper boundaries and preserve all original behavioral assertions. They are not represented as separate independently observed pre-implementation helper-level RED.
- All-source acceptance remains pending. The unrelated 424 light smoke build hit its unchanged RSS watchdog before browser assertions; the implementation SHA must pass its own light/dark smoke without raising resource limits or bypassing guards.

- Implementation candidate review: attendance's disjoint UNION ALL preserves one actual-event scalar row and avoids a global historical left-join OR. Both empty-input and recent ordering contracts were checked; a draft aggregate/head/rank variant was rejected before publication because it violated them.
- The complete user's eligible history is required for an unbounded current streak; comparison-window rows and user-history scalar rows are materialized. No arbitrary cutoff, N+1 query or performance benchmark claim is introduced.
- Exact source metadata: none of the implementation or supplemental-test paths has a baseline record, so the existing 319-identity baseline needs no further line-reference changes.
- Both tests-first owned-live runs completed cleanup. Current 424 receipt 12164102527 binds synthetic checkout bbb69e1ae2bfc04eb8de4dda0dd453e71179117c to exact tree d30ea09eb294191f8ff702b10adc068a24ab86bc. This does not replace implementation-source acceptance.

- Ruling after actual 1e8 live preflight RED: include frontend/tests/e2e-live/activity-dashboard.live.spec.ts, activity-summary.live.spec.ts and activity-dashboard.contract.test.mjs in scope. Two contracts failed before startup because old attendance labels and the old separate grade-window call no longer matched the implementation. Synchronize exact labels and verify both disjoint user-scoped SQL populations; retain all real-metric, wrong-value, read-only, reload, geometry and empty-state assertions. No runtime acceptance or successful cleanup is inferred from the skipped receipt.

- Correct the observed static i18n failure by restoring EN status.absent without reverting registration wording or changing the finite key registry. Fresh cache-transition test data now includes explicit daily aggregates; original assertions remain, and a supplemental real-QueryClient test covers legacy missing fields until cache update. This adds the existing cache test and EN catalog key correction to the narrow follow-up scope.
