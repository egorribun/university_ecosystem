# Clearing persisted English news translations

Date: 2026-10-19. GitHub plugin only, branch egorribun, PR1306.

AUD-031 originally concerns clearing existing English translations in the card editor. Current code sends explicit null for blank fields; NewsUpdate preserves explicit null, repository update assigns it, and the service commits. Existing tests cover blank initial fields or replacing a translation with another nonempty value, not the full missing case.

## Proof additions

- [x] Trace current editor/schema/service/repository behavior without changing it.
- [x] Add an editor test starting with both English fields populated, clear both through user-event, and require exactly one PATCH with both null and unchanged Russian/image values.
- [x] Add a real DB service test that confirms nonempty English values in one fresh session, clears both through NewsService, then reads in a different fresh session and requires persisted null with Russian values intact.
- [x] Select the persistence regression in the existing early backend command without adding workflow lines or changing baseline coordinates.
- [x] Observe actual frontend and DB execution on the new source.
- [x] Reconcile AUD-031 at this scope only after PASS.

The UI request is mocked and the service/DB persistence check is separate. This is not a single deployed browser-to-database acceptance run. No implementation, baseline, allowlist or skip changes are needed for this proof addition.

Source ab1b proof: backend job 118258426422 executes the fresh-session case successfully at 19:26:47 UTC; frontend job 118258509289 has all 22 editor tests PASS at 19:26:43 UTC. Scope remains two separate verified boundaries, not a browser-to-database test. Reconciled in the 64-ID checkpoint.
