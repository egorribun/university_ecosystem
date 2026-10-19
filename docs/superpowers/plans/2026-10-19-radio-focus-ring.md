# Radio focus-indicator sibling boundary

Date: 2026-10-19. GitHub plugin only, branch egorribun, PR1306.

AUD-060 places peer-focus-visible classes on a span nested beneath the input's sibling, where the peer sibling selector cannot match it. Existing settings tests cover selection but not this selector relationship.

- [x] Review actual RadioGroup, Storybook htmlFor labels and Settings wrapping FormControlLabel consumers.
- [x] Add a two-item actual DOM regression requiring labeled focusable radios, a per-item 44px hit target and its 24px following-sibling peer indicator.
- [x] Observe intended same-parent assertion RED after focus/accessibility guards on c94d9be, job 118310084855, line 44.
- [x] Correct only the DOM relationship, preserving disabled/checked/name/ref behavior and accessible label composition.
- [ ] Verify new and existing form/radio contracts before reconciliation.

Do not nest the native input under the current aria-hidden outer span: decorative hiding must stay off the input's ancestors. Existing primitive tests may need equivalent DOM selectors while preserving their visual-state, geometry and animation assertions. The structural test does not claim browser paint or physical-keyboard acceptance.

## Actual browser computed-style acceptance

The new settings-radio-focus.live.spec.ts uses the existing synthetic student and disposable Core fixtures. It opens Theme without selecting a radio, asserts native keyboard focus and :focus-visible, then observes computed boxShadow change and restoration on Tab/Shift+Tab. Both existing projects run it through the fixed smoke tuple. Source/selection/security contracts preserve metadata-only diagnostics and disabled trace/screenshot/video capture. This observes browser computed styles, not screenshots or physical hardware. Actual execution/cleanup is still required before accepting AUD-060.

## Live CSS counterexample and narrow follow-up

On exact 73ff704 tree, Core run 39328611496 / job 118320769222 passed 22 existing cases but failed both new desktop/mobile cases at line 46: native focus and :focus-visible guards passed, computed boxShadow did not change. Two existing skips remain. Checkout 3330fda26d679108e01b76ef762c29decc1cf0ac has tree 475e1befa97ff48b0cd17ce4dbc883bc3952029a. Owned services stopped at 21:51:43 UTC; metadata receipt artifact 12223953793 has sha256:1b4abde48eec227280aca8656f8c947b7f25d056fb1aeda57c68ad6dd0052bf6.

The next candidate replaces only the indicator's peer focus effect with the existing shadow-focus utility. Its raw focus token uses valid page/brand colors, avoiding the unitless opacity variables used by the old ring/glass color-mix composition. Source inspection supports this explanation, but actual GREEN is still required. Equivalent class-selector changes preserve the same own-item sibling/geometry checks and every browser focus/shadow-change/restoration/checked assertion. No global token cleanup or acceptance of AUD-060 is included.
