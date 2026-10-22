# Activity and event evidence plan

Date: 2026-10-19. GitHub plugin only, egorribun, PR1306.

## AUD-013 incomplete boundary day

- [x] Trace producer row caps and current inclusive heatmap coverage.
- [x] Add a realistic mocked-summary counterexample: six records, five returned on one day; complete attendance daily totals do not certify the sampled heatmap.
- [x] Observe intended assertion RED on8d5 job118218720402: April20 instead of April21;2170 other PASS.
- [x] Move complete coverage beyond the potentially incomplete day after RED and correct the two old cutoff assertions/comments. Preserve malformed-date legacy behavior with finite/round-trip guards and neighboring tests.
- [x] Verify exact regression, neighboring complete-history behavior and all frontend checks.

This does not claim complete historical activity accounting or unique-event counting.

## AUD-016 list/count parity

- [x] Add ten real DB cases for translated type/location, hidden rows, active/archive boundary, combinations and empty results.
- [x] Extend the existing PostgreSQL-selected FTS test with eight parity cases, preserving its marker and ordering assertions. No new skip.
- [x] Verify named SQLite cases, existing service total/cursor cases, and actual PostgreSQL execution.
- [x] Reconcile only the demonstrated scope. Vector semantic search is not exercised; positive PG type/archive cases remain outside this fixture.

## Historical reconciliation

AUD-010 is accepted narrowly for single-scale denominator selection and separate rendering, not mixed-scale rejection or GPA-range validation. AUD-009 awaits five existing named cache regressions. AUD-017 needs disposition against the explicit start-date ordering criterion; do not call creation-date ordering implemented.

8d5 backend and PG jobs were skipped after static failures, so AUD-009/016 are not accepted. The PostgreSQL parity extension is moved into an EOF helper, preserving original reviewed fixture credential coordinates and the committed baseline. All original ordering assertions and the existing PostgreSQL marker remain.

## Source 84bf verification

Actual job 118230433646 has all five AUD-009 cases, ten list/count cases and two service cases PASS. PostgreSQL job 118230433856 executes the extended FTS test successfully and reports 202 PASS / 9 existing SKIP. Frontend job 118230934590 has all 29 hook tests PASS, including the unchanged capped-day counterexample. The four frontend shards total 9363 PASS, and frontend static gates pass. The earlier skipped-job hold above is superseded only for these demonstrated scopes. AUD-009/013/016 are reconciled in the 61-ID checkpoint; full CI is not accepted.
