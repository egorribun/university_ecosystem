# Radio focus-indicator sibling boundary

Date: 2026-10-19. GitHub plugin only, branch egorribun, PR1306.

AUD-060 places peer-focus-visible classes on a span nested beneath the input's sibling, where the peer sibling selector cannot match it. Existing settings tests cover selection but not this selector relationship.

- [x] Review actual RadioGroup, Storybook htmlFor labels and Settings wrapping FormControlLabel consumers.
- [x] Add a two-item actual DOM regression requiring labeled focusable radios, a per-item 44px hit target and its 24px following-sibling peer indicator.
- [ ] Observe intended same-parent assertion RED after focus/accessibility guards.
- [ ] Correct only the DOM relationship, preserving disabled/checked/name/ref behavior and accessible label composition.
- [ ] Verify new and existing form/radio contracts before reconciliation.

Do not nest the native input under the current aria-hidden outer span: decorative hiding must stay off the input's ancestors. Existing primitive tests may need equivalent DOM selectors while preserving their visual-state, geometry and animation assertions. The structural test does not claim browser paint or physical-keyboard acceptance.
