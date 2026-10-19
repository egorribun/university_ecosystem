# Spotlight MotionValue coordinates

Date: 2026-10-19. GitHub plugin only, branch egorribun, PR1306.

AUD-059 names direct MotionValue interpolation into CSS. The current component builds a primitive gradient string with object coordinates. Framer Motion is locked to 14.0.0; its real MotionValue has no numeric toString conversion. Existing local mocks define one and do not establish live style subscription.

- [x] Review original finding, actual component, locked Motion source and test setup.
- [x] Add a standalone actual Motion/LazyMotion component test without a MotionValue mock.
- [x] Observe intended gradient assertion RED after the wrapper event guard passes.
- [x] Apply the smallest useMotionTemplate correction, preserving the real regression and existing assertions.
- [x] Verify both numeric pointer positions on the corrected component source.
- [ ] Verify the narrow snapshot-mock TypeScript correction restores the complete static gate before AUD-059 acceptance.

Only timer-backed RAF and bounding rectangle are controlled. The test drives the actual wrapper, real MotionValue/style serialization and DOM CSS parser. It checks coordinates, not visual hover opacity, pixel rendering or physical mouse hardware. No component implementation change is included before RED.

Observed 2caf407 RED: job 118288718037 at 20:36:20 UTC reports 2336 PASS / 1 FAIL. The actual style contains object-stringified coordinates rather than 30px 50px. The correction changes only the derived gradient binding; hook/event logic, classes and stops remain. The survivor-contract mock receives a snapshot-only serializer, not simulated live subscription. Corrected-source execution and the second-position assertion remain pending.

On 0aa309f, the unchanged actual Motion test passes at 20:52:42 UTC in job 118296921885. Existing survivor contracts also pass all 11 cases. Static TS2532 flags the mock's indexed value lookup; optional access with an empty trailing fragment fixes that test-helper typing without touching component behavior or suppressing the checker. Own-source static GREEN remains pending.
