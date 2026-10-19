# Activity and event evidence plan

Date: 2026-10-19. GitHub plugin only, egorribun, PR1306.

## AUD-013 incomplete boundary day

- [x] Trace producer row caps and current inclusive heatmap coverage.
- [x] Add a realistic mocked-summary counterexample: six records, five returned on one day; complete attendance daily totals do not certify the sampled heatmap.
- [ ] Observe intended assertion RED with current production logic and old assertions unchanged.
- [ ] Conservatively move complete coverage beyond the potentially incomplete day, correcting the two old cutoff assertions/comments only after RED.
- [ ] Verify exact regression, neighboring complete-history behavior and all frontend checks.

This does not claim complete historical activity accounting or unique-event counting.

## AUD-016 list/count parity

- [x] Add ten real DB cases for translated type/location, hidden rows, active/archive boundary, combinations and empty results.
- [x] Extend the existing PostgreSQL-selected FTS test with eight parity cases, preserving its marker and ordering assertions. No new skip.
- [ ] Verify named SQLite cases, existing service total/cursor cases, and actual PostgreSQL execution.
- [ ] Reconcile only the demonstrated scope. Vector semantic search is not exercised; positive PG type/archive cases remain outside this fixture.

## Historical reconciliation

AUD-010 is accepted narrowly for single-scale denominator selection and separate rendering, not mixed-scale rejection or GPA-range validation. AUD-009 awaits five existing named cache regressions. AUD-017 needs disposition against the explicit start-date ordering criterion; do not call creation-date ordering implemented.
