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
- [x] Run the source contracts and actual browser case on both projects, and verify owned stand cleanup/receipt provenance before reconciliation.

This does not add an application search button or change the application's focus implementation. It does not test search-result navigation or a physical mobile keyboard. The live fixture uses a fresh browser context and removes only its own recent-search storage. No new credential, account, backend endpoint or external environment is created. Existing ordinary cleanup remains mandatory; no NATS outage is enabled.

Actual Live run 39310016261 / job 118256863070 selects the new spec and reports 22 PASS / 2 existing SKIP at 19:34:37 UTC, with successful owned cleanup and receipt upload. Exact source/tree and receipt digest are recorded in the 64-ID checkpoint. Node source contracts pass; the separate ESLint gate requires an explicit node:url import, added without weakening the rule. The three existing Python runner-selection/redaction/inventory contracts are also selected early for subsequent-source verification.

Source 052 revalidates the actual browser case in Live 39312764119 with 22 PASS / 2 existing SKIP, successful owned cleanup and receipt upload. Frontend static job 118268538527 passes after the explicit URL import. All 21 selected runner-selection, strict failure-location and tracked-source inventory cases pass in early backend job 118267989692. No redaction assertion or artifact policy was relaxed.
