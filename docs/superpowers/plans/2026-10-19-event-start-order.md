# Main event-feed start-date ordering

Date: 2026-10-19. GitHub plugin only, branch egorribun, PR1306.

At 21:02:56 UTC the owner approved «Ближайшие» ascending and «Поздние сначала» descending by starts_at. The existing internal newest token remains a UI compatibility identifier, not publication-date semantics. Its English visible label becomes Later dates first. Popular remains unchanged.

## Scope and design

The original AUD-017 row concerns EventsFeature and the main /events feed, not /events/my/page. Current main pagination is ASC date/ID, or rank-first for search; client-only reversal of a partial page is not global DESC. Automatically loading every page for the default view would introduce unbounded fetching, so use an optional typed server order.

- Omitted API order preserves current legacy behavior and cursors.
- Explicit starts_at_asc/starts_at_desc uses date-primary order and matching ID tie-break/keyset direction, including search-filtered results.
- New cursors must bind direction and relevant query context; an ASC cursor cannot silently become DESC. /my/page remains untouched.
- Include order in frontend query/ETag/cache identities; never treat an orderless legacy cached array as complete DESC provenance.
- Regenerate normal OpenAPI/SDK/MSW artifacts through existing hosted generation. The unchanged Verify OpenAPI Types job already emits a generation diff, which can be reconstructed and then checked by another unchanged regeneration run. Do not hand-author generated files or change SDK-wide defaults.

## Tests first

- [x] Add standalone HTTP tests with shuffled insertion, tied dates crossing pages, raw response ordering and wrong-direction HTTP 400 assertions.
- [x] Add controlled frontend mode/label, query/ETag/cache identity and legacy-placeholder rejection tests.
- [ ] Observe intended assertions RED before implementing event behavior.
- [ ] Add a PostgreSQL search/rank counterexample proving explicit date order is primary, while omitted-order behavior remains compatible.
- [ ] Implement narrow API/repository/cursor behavior and perform ordinary generation.
- [ ] Implement UI binding and order-aware cached data with explicit provenance/completeness semantics.
- [ ] Verify all regression, generation, static and browser-relevant gates before AUD-017 reconciliation.

The existing test_event_time_constraints.py contains a baseline identity at line 283; the new HTTP test is separate so that coordinate stays unchanged. Tests use a synthetic viewer and generated per-test password, not live credentials. No event behavior is changed in this tests-first slice.
