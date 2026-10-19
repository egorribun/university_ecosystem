# Spotlight MotionValue coordinates

Date: 2026-10-19. GitHub plugin only, branch egorribun, PR1306.

AUD-059 names direct MotionValue interpolation into CSS. The current component builds a primitive gradient string with object coordinates. Framer Motion is locked to 14.0.0; its real MotionValue has no numeric toString conversion. Existing local mocks define one and do not establish live style subscription.

- [x] Review original finding, actual component, locked Motion source and test setup.
- [x] Add a standalone actual Motion/LazyMotion component test without a MotionValue mock.
- [ ] Observe intended gradient assertion RED after the wrapper event guard passes.
- [ ] Apply the smallest reactive-template correction, preserving existing tests.
- [ ] Verify numeric coordinates and a second pointer position on the corrected source.

Only timer-backed RAF and bounding rectangle are controlled. The test drives the actual wrapper, real MotionValue/style serialization and DOM CSS parser. It checks coordinates, not visual hover opacity, pixel rendering or physical mouse hardware. No component implementation change is included before RED.
