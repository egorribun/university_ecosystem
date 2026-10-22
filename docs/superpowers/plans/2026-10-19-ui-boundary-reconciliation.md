# Media query, StoryList and swipe boundaries

Date: 2026-10-19. GitHub plugin only, branch egorribun, PR1306.

AUD-048 and AUD-052 are reconciled at their demonstrated hook/component boundaries in the 66-ID audit checkpoint. Implementations/tests are byte-identical between ab1b and 052; named tests pass on both sources. MediaQueryList, ResizeObserver and layout inputs are controlled, not real browser/API timing.

At the 66-ID checkpoint AUD-058 was not yet counted; the later execution below resolves that hold. Existing real-hook tests return to the exact start, whereas the original finding names reversal past it. Two additive cases now move beyond the close threshold, reverse one pixel past the origin and end the gesture in each direction, requiring zero offset and no close callback. Keep all old exact-origin and positive-close tests unchanged.

- [x] Review all three original criteria, current source and existing tests.
- [x] Verify AUD-048 file 13 PASS and AUD-052 file 22 PASS against exact unchanged blobs.
- [x] Add the missing two AUD-058 real-hook counterexamples without changing implementation.
- [x] Observe actual execution of both new cases and reconcile only that scope.

No new skip, allowlist or production behavior change is introduced.

## AUD-058 execution

Source 834984b / job 118282802962 verifies all 14 real-hook cases at 20:17:08 UTC, including both new past-origin reversals. Synthetic handler events, not physical hardware, establish the original cancellation criterion. AUD-058 joins the 67-ID checkpoint.
