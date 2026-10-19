# News retry boundary regression plan

Date: 2026-10-19. GitHub plugin only, branch egorribun, PR1306.

## Scope

AUD-033 source inspection finds automatic complete-dataset fetching can restart after retry exhaustion; NewsList has an independent sentinel path lacking an error guard. Anonymous Retry additionally invalidates the authenticated list prefix instead of the active anonymous key. This last mismatch is not covered by AUD-032's accepted error-rendering scope.

## Tests first

- [x] Add authenticated real QueryClient/API/feature regression with controlled HTTP failures, finite notification flushing and a held third-request safety gate.
- [x] Add independent cached-list sentinel error regression plus positive control after the error clears.
- [x] Add anonymous real-fetch Retry-button regression, asserting the exact query transitions to fetching and preserving credentials:omit.
- [x] Observe intended hosted RED for authenticated exhaustion and independent sentinel on dc21, jobs118197976374 and118197977733.
- [x] Observe intended anonymous Retry RED on6605 job118209082842: first request/options verified, Retry does not start the anonymous query.
- [x] Apply only the two automatic error guards after their own RED; no Retry invalidation change yet.
- [x] Correct active-query invalidation after intended RED, using returned queryKey with exact:true and preserving ETag reset.
- [ ] Verify regression GREEN, neighboring behavior, all frontend checks and documentation.

Presentation-only mocks and controlled MSW responses do not establish deployed networking. Cleanup restores auth/language/global scheduler state, cancels queries and releases held responses. No production news implementation changes are included in the first slice. Do not accept AUD-033 until its own GREEN; do not silently broaden AUD-032.

The two new feature test bodies now use named async callbacks to simplify formatting, preserving their request/query/UI assertions. Prettier must pass on the corrected source. The anonymous handler-side credentials assertion failed before request counting; checking the real fetch init through a non-mocking spy preserves credentials:omit/cache:no-store proof. This is a test-boundary correction, not a production credential fix.

On6605 the authenticated retry-exhaustion regression and independent sentinel are GREEN. Authenticated test formatting still fails; the short pages array is compacted without changing the oracle. Anonymous regression is unchanged during its production fix. Full frontend checks and own-source GREEN remain required; AUD-033 is not yet accepted.
