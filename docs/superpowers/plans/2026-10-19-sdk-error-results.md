# Generated-client HTTP error results

Date: 2026-10-19. GitHub plugin only, branch egorribun, PR1306.

## Observed RED on source ccc8

The generated SDK defaults to returning an error result instead of rejecting. Consumers that await a mutation can therefore continue through their success path after an HTTP failure.

[Mutation job 118247350088](https://github.com/egorribun/university_ecosystem/actions/runs/39306435037/job/118247350088) observes all seven exact requests and then fails the rejection assertion for deleteNews, createStory, updateStory, deleteStory, markNotificationRead, markAllNotificationsRead and clearNotifications. It reports 7 FAIL / 2233 PASS at 19:11:02 UTC. HTTP 422 responses use a controlled MSW handler, real wrappers, generated SDK and Axios; there are no generated-client mocks in these regressions.

[Stories job 118247350042](https://github.com/egorribun/university_ecosystem/actions/runs/39306435037/job/118247350042) fails the real QueryClient HTTP 422 rejection assertion at 19:08:58 UTC after its request-shape guard passes. The query incorrectly resolves to an empty successful feed. The neighboring direct-wrapper 304 and cached-query compatibility control passes. Job totals are 1 FAIL / 2346 PASS.

## Narrow correction

- [x] Observe intended assertion RED before production changes.
- [x] Add endpoint-local throwOnError:true to the seven demonstrated mutations.
- [x] Add the same local error policy to fetchStories, explicitly accepting HTTP 304 alongside 2xx; remove its unnecessary double type assertion.
- [x] Retain the new real-client regression files unchanged. Strengthen older exact-call mocks to require the error flag and validate the accepted status boundary.
- [ ] Verify all nine new cases and existing consumer/API tests, typecheck, formatting and full frontend CI on the corrected source.
- [ ] Reconcile AUD-035 only after verified evidence and a final scope review.

Do not modify generated code or global SDK defaults. Upload wrappers are not part of these seven false-success mutations: they already validate missing response data and reject. This proves frontend HTTP/query behavior with controlled transport responses, not deployed authentication, CSRF, persistence or every possible SDK endpoint.
