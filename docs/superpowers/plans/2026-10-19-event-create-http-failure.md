# Event-create HTTP failure regression plan

Date: 2026-10-19. Original finding: AUD-022. Work only through GitHub plugin on egorribun and PR1306.

## Verified source path

The event wrapper calls the generated create endpoint without throwOnError and returns data. Axios rejects HTTP500, but the generated client's outer catch returns an error value. A resolved undefined result reaches EventFormDialog's success callback and EventCreateDialog's reset/close path. Existing rejection-only component mocks do not cover this boundary. Hosted reproduction is still required.

## Tests-first contract

- Keep the real createEvent wrapper, generated client, production Axios/interceptors, EventFormDialog, EventCreateDialog and UTC provider.
- Use a controlled MSW HTTP500 and require the exact POST/body to have been observed, so preflight/setup rejection cannot count as defect evidence.
- Require the wrapper promise to reject with HTTP500.
- Require the composed form to retain title, location and both dates, display an error, and call neither success nor close.
- Animation/i18n/expected logging mocks are permitted; do not mock the API or either dialog. This is not authentication, CSRF, focus or live-storage acceptance.

## Execution

- [x] Add two real-boundary regressions without changing production frontend behavior.
- [ ] Observe assertion RED on hosted CI, not setup/import/contract errors.
- [ ] Apply the minimal create-only throwOnError correction; preserve upload validation, successful creation and post-create refresh behavior. Do not edit generated code or global client defaults.
- [ ] Update the existing generated-call expectation to require the corrected create contract without weakening other assertions.
- [ ] Verify both new cases, existing API/dialog cases, lint/typechecks and full applicable CI. Retain any unrelated intentional NATS workflow failure explicitly.
- [ ] Reconcile AUD-022 only after own-source regression GREEN, with the jsdom/HTTP-mock boundary stated.
