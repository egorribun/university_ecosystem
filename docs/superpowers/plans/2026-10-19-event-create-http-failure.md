# Event-create HTTP failure regression plan

Date: 2026-10-19. Original finding: AUD-022. Work only through GitHub plugin on egorribun and PR1306.

## Verified source path

The event wrapper calls the generated create endpoint without throwOnError and returns data. Axios rejects HTTP500, but the generated client's outer catch returns an error value. A resolved undefined result reaches EventFormDialog's success callback and EventCreateDialog's reset/close path. Existing rejection-only component mocks do not cover this boundary. The intended hosted RED and own-source GREEN are recorded below.

## Tests-first contract

- Keep the real createEvent wrapper, generated client, production Axios/interceptors, EventFormDialog, EventCreateDialog and UTC provider.
- Use a controlled MSW HTTP500 and require the exact POST/body to have been observed, so preflight/setup rejection cannot count as defect evidence.
- Require the wrapper promise to reject with HTTP500.
- Require the composed form to retain title, location and both dates, display an error, and call neither success nor close.
- Animation/i18n/expected logging mocks are permitted; do not mock the API or either dialog. This is not authentication, CSRF, focus or live-storage acceptance.

## Execution

- [x] Add two real-boundary regressions without changing production frontend behavior.
- [x] Observe assertion RED:630 job118171264522, two intended failures after verified HTTP500 POST/body,2609 other tests pass.
- [x] Apply the minimal create-only throwOnError correction; preserve upload validation, successful creation and post-create refresh behavior. Do not edit generated code or global client defaults.
- [x] Update the existing generated-call expectation to require the corrected create contract without weakening other assertions.
- [x] Verify both new cases, existing API/dialog cases and all frontend shards plus lint/typechecks on1d995:9357 PASS across773 files. Full CI is not green: the unrelated intentional NATS workflow capability failure remains explicit.
- [x] Reconcile AUD-022 after own-source regression GREEN, with the jsdom/HTTP-mock boundary stated.

The two unchanged real-client tests PASS in job118180350816 on run39287160560. Existing API5, create-dialog48 and form-dialog3 cases and frontend lint/typechecks also pass. Checkout19bf6ab49b31c92bd68b4d4e1f335ab3f2659e66 matches source1d995 tree9622298dc8628e8eab36b1ab33863c3d77e20b75. AUD-022 is accepted at this scoped frontend boundary, not as deployment or full CI acceptance. No global SDK setting or generated file is modified.
