# Semantic color percentage probes

Date: 2026-10-19. GitHub plugin only, branch egorribun, PR1306.

Original AUD-072 (P2) concerns unitless numbers in color-mix percentage positions. AUD-085 utility registration and AUD-073 contrast remain separate; neither is accepted here. Keep unitless primitive opacity values unchanged because ordinary opacity consumers require fractions.

## Bounded tests-first scope

- Extend the existing Vite/Tailwind pipeline test only to confirm that real compiled CSS retains the observed semantic tokens and both panel themes. Parser success is not computed-value validity.
- Add a separate case to the already selected settings-radio-focus live file. Use actual production CSS, the synthetic student, System theme and OS color-scheme emulation, with html/body theme guards and no test-induced saved preference change.
- Transient div probes compare panel background to an independent 70% mix, glass/glow shadows to independent 20% mixes, in both themes. Ordinary opacity must remain 0.2, and the known-valid focus token is a positive control. Remove every probe in finally.
- Keep the existing AUD-060 radio case and its keyboard/computed-style oracle unchanged. Preserve trace/screenshot/video restrictions and metadata-only diagnostics; no mocks, substitute stylesheet or token overrides.
- Observe intended value assertions RED before touching semantic declarations. Login, hydration, theme or expected-value control failures are setup failures, not AUD-072 evidence.

Only tests are added in this slice. Candidate correction later concerns demonstrated percentage positions in semantics.css, not a global primitive conversion. Other semantic mixes, malformed single-color gradients and direct CSS/Tailwind arbitrary-alpha consumers require their own evidence before whole AUD-072 reconciliation. No visual redesign, global quality infrastructure or acceptance is included.

## Observed RED and first bounded correction

On 0869fab, Core run 39334270376 / job 118341811931 reports 24 PASS / 2 FAIL / 2 existing SKIP. Both desktop/mobile failures are the new semantic probe's panel, glass and glow soft assertions (source lines 134-136); preceding stylesheet/theme/opacity/focus controls do not fail. Checkout 50fe49b46269c185ad4515edd4dc417d20f078cd has exact tree 593798f0c6793c0845b3dfc7978d098913da0130. Owned cleanup completes at 22:43:12 UTC; metadata receipt artifact 12225844407 has SHA-256 87cf83345887cb72d8104fed8c425fe7ef9b673cd66e217d25409feb7dde0d30.

The next source changes only four declarations: both panel theme values, raw-shadow-glass and shadow-glow-primary now convert the existing unitless opacity to a percentage with calc(value * 100%). Primitive values, independent browser assertions, focus behavior and all other mix consumers remain unchanged. A formatting-only collapse of the exactly 100-character glassExpected expression fixes the remaining Prettier complaint; no assertion is removed or weakened. Own GREEN remains pending and whole AUD-072 remains open.

## Four-declaration GREEN and next twelve-token probes

Actual Core run 39338265824 / job 118353627557 on 933e4c9 passes 26 browser cases with two existing skips at 23:14:00 UTC, including all original panel/glass/glow assertions in light and dark. Cleanup 23:14:22 and artifact 12228950317 are verified; SHA-256 066388381d4f8b68e4ef9da294db4dbb6f7bab6294ee49e01951b3ba51ed0b4f. Exact checkout f0762f69d338cea6875e84842ba47232fedd2a40/tree c6562b921b1a3616bf85f54a6e0acf7f15a01f02 is verified. Frontend static also passes on 47f35bf.

The next tests-only cohort preserves every existing oracle and probes twelve additional tokens: surface tint, error background, matte-card/hover multi-shadows, raw small/inner shadows, low glass background, glass sheen and news gradients, message header, glass border and tint3. Expected references use independent literal percentages, original geometries and explicit theme overrides. Valid-reference guards precede soft actual/reference comparisons; gradients and shadows must not resolve to none. Unitless primitives remain untouched.

Read-only scope inventory identifies 48 remaining semantic declarations across 38 names, including two malformed one-color mixes. The new cohort deliberately excludes shadow-glass/strong and nav/footer aliases that collide with @theme declarations until winning cascade is separately established. Direct CSS/Tailwind consumers, dashboard light-only gradients and ErrorBoundary's literal in_srgb inline syntax remain later evidence. Correct percentage syntax does not establish AUD-085 utility emission or AUD-073 contrast. No additional production CSS change or whole AUD-072 acceptance is included.

## Expanded cohort RED and seventeen-declaration correction

On 19cae40, Core run 39340683386 / job 118364584960 reports 24 PASS / 2 FAIL / 2 existing SKIP at 23:40:52 UTC. Desktop and mobile both identify only comparison frame 229 in the new loop; reference guards and original panel/glass/glow comparisons have no failure frame. Metadata-only diagnostics intentionally do not expose per-token details, so no individual failure count is inferred. Checkout 26e011393946e5d4220925f5a607f7e84493a392/tree 3e31b70b5d3ff60a09601a136383dffa083e89de is verified. Cleanup completes at 23:41:13; receipt artifact 12229821929 has SHA-256 6064d4803a197d1797332214e9adbe259455507deb9cb5eeec81ea46105ce994.

Source inspection maps the twelve probes to seventeen declarations, including explicit dark overrides. The correction applies calc(fraction * 100%) only to their opacity/glass-alpha percentage arguments. Original geometries, color bases, both theme weights, unitless primitives and every behavioral assertion remain unchanged. It excludes collided aliases, malformed one-color mixes and other direct CSS/utility consumers. Own computed-value GREEN is required before accepting this slice; whole AUD-072 stays open.
