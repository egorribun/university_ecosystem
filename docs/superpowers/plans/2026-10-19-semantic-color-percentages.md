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
