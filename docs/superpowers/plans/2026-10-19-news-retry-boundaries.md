# News retry boundary regression plan

Date: 2026-10-19. GitHub plugin only, branch egorribun, PR1306.

## Scope

AUD-033 source inspection finds automatic complete-dataset fetching can restart after retry exhaustion; NewsList has an independent sentinel path lacking an error guard. Anonymous Retry additionally invalidates the authenticated list prefix instead of the active anonymous key. This last mismatch is not covered by AUD-032's accepted error-rendering scope.

## Tests first

- [x] Add authenticated real QueryClient/API/feature regression with controlled HTTP failures, finite notification flushing and a held third-request safety gate.
- [x] Add independent cached-list sentinel error regression plus positive control after the error clears.
- [x] Add anonymous real-fetch Retry-button regression, asserting the exact query transitions to fetching and preserving credentials:omit.
- [ ] Observe intended hosted assertion RED, not type/lint/setup failure.
- [ ] Apply minimal production guards and correct active-query invalidation after RED.
- [ ] Verify regression GREEN, neighboring behavior, all frontend checks and documentation.

Presentation-only mocks and controlled MSW responses do not establish deployed networking. Cleanup restores auth/language/global scheduler state, cancels queries and releases held responses. No production news implementation changes are included in the first slice. Do not accept AUD-033 until its own GREEN; do not silently broaden AUD-032.
