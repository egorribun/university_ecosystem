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
