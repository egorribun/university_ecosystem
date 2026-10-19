# SearchDialog native keyboard acceptance

Date: 2026-10-19. GitHub plugin only, branch egorribun, PR1306.

AUD-053 concerns SearchDialog, not StoryViewer. Existing source uses the real focus-trap hook with returnFocus enabled; mocked hook wiring and jsdom keydown assertions do not prove native browser Tab navigation.

## Scope and proof

- [x] Verify the original finding, current SearchDialog implementation and existing disposable Core live fixtures.
- [x] Add a real Playwright case using the existing seeded student, dashboard and deferred-overlay readiness event.
- [x] Focus the exact navbar logo link before Control+K, then require native Tab and Shift+Tab to wrap through the input and clear button. A one-character query reveals the second control without enabling the search request.
- [x] Require Escape to close the dialog and restore the exact original focused navbar element.
- [x] Select the new spec in Core smoke for both existing desktop and mobile Chromium projects, with no new skip, retry or service.
- [x] Update exact smoke-list contracts, diagnostic filename allowlist membership and fixture-frame indexing; keep metadata-only redaction and artifact policy unchanged.
- [ ] Run the source contracts and actual browser case on both projects, and verify owned stand cleanup/receipt provenance before reconciliation.

This does not add an application search button or change the application's focus implementation. It does not test search-result navigation or a physical mobile keyboard. The live fixture uses a fresh browser context and removes only its own recent-search storage. No new credential, account, backend endpoint or external environment is created. Existing ordinary cleanup remains mandatory; no NATS outage is enabled.
