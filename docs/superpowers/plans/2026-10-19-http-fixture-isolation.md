# HTTP test-client isolation

Date: 2026-10-19. GitHub plugin only, branch egorribun, existing PR1306.

## Observed failure

On source 84bf, [Go integration job 118230433137](https://github.com/egorribun/university_ecosystem/actions/runs/39301611872/job/118230433137) runs Go 1.26.9 with integration tags and the race detector. TestResponseHeadersErrorsAndInvalidPayloads fails at main_test.go:400: a loopback ping request reports a transport connection broken by CloseIdleConnections.

The fixture file is unchanged at source ccc8. Nine httptest-backed requests use the global client. Several tests run in parallel and close independent httptest servers. The [Go 1.26.9 implementation](https://github.com/golang/go/blob/go1.26.9/src/net/http/httptest/server.go) shows Server.Close closing the global default transport's idle connections as well as its own client's transport.

## Tests-first sequence

- [x] Trace the observed failure, exact toolchain and shared resource.
- [x] Independently review a deterministic connection-reuse oracle.
- [x] Route existing httptest requests through a test-only client helper, initially preserving the global-client behavior.
- [x] Add a regression that fully drains/closes a target response, closes an unrelated httptest server, then requires the target's second connection to be reused. Observe the intended assertion RED, not setup failure.
- [x] Change only the helper to return the target server's own client. Do not disable parallel tests or add retries.
- [ ] Verify the regression, old response-header/error controls, race/integration tests, formatting and lint on the new source.

Use httptrace.GotConn with atomic.Bool for the reuse observation. Both response bodies must be drained and closed. Do not close the target fixture between requests. The manual-listener shutdown test has an active response until teardown and is a separate path. This is test transport isolation, not a change to product proxy behavior or a new accepted AUD ID.

Observed intended RED on ab1b: run 39310016686 / job 118258426196 fails the reuse assertion at main_test.go:1029, 19:24:12 UTC. Both request setup and response drain succeed. The correction changes only the helper parameter and return value to server.Client(); all nine mapped request sites and the new regression remain unchanged. Independent review found no lifecycle/keepalive blocker. Corrected-source execution remains pending.
