# AUDIT — Wave 201 (Chromatic activation prep — drift-resilience + report-mode + runbook)

> **Status: CLOSED.** Post-campaign first wave (W200 closed the story-coverage arc at 212 stories). Chromatic is the payoff — it pixel-diffs every story on each PR. W201 makes the suite **activation-ready**: marks the 6 genuinely non-deterministic stories `disableSnapshot` so the first baseline is clean, strips the plaintext project token from the workflow comment (hygiene), and documents the activation runbook. **Report-mode** per user Q1 (`exitZeroOnChanges: true` stays — the enforce-flip is a documented post-baseline follow-up). 61st consecutive wave with brainstorming + Phase 1 Explore + Phase 3 verify-before-write + W141 anti-pattern discipline. 2 SW.

## Headline

- **6 of 212 stories marked `parameters.chromatic.disableSnapshot: true`** — the Phase-1 audit classified the candidate set; the other ~206 are deterministic (fixed-date fixtures / static / `pauseAnimationAtEnd` framer-motion springs that settle, incl. the 15 pre-existing `chromatic:` stories — all unchanged). The 6: WeatherParticles + MapLibreMap (canvas/WebGL), ParticleAuthBackground + MfaChallengeView (particle bg), EventCard (relative-time text), FlipCountdown (live clock).
- **chromatic.yml hygiene**: removed the plaintext `chpt_…` project token from the comment (0 `chpt_` now; value lives in the Secret / memory note) + refreshed the activation steps + documented the enforce-flip as a post-baseline follow-up. Behavior unchanged — `exitZeroOnChanges: true` (Report-mode) stays.
- **Bundle main JS BYTE-IDENTICAL × 3** to W134-SW3 → W200 `1bff1fd7…c97` — the 6 `.stories.tsx` are outside the app Vite graph + chromatic.yml is CI config → zero bundle impact. **≥59-wave LOCAL invariant extends to ≥60-wave.** server.js `bd4a3402…885` × 3 unchanged. build-storybook index **893 unchanged** (684 stories + 209 docs); all 6 disableSnapshot stories remain enumerated (disableSnapshot is a Chromatic-side flag — keeps dev/docs value, drops only the futile pixel-diff).
- **Activation is user-gated** (cannot be automated): set Secret `CHROMATIC_PROJECT_TOKEN` (reuse `chpt_48d051b3688a3e4` per Q2) + repo var `CHROMATIC_ENABLED=true`, then merge to main → `autoAcceptChanges` captures the first clean baseline. W201 delivers *readiness*, not the live baseline.

## Per-SW table

| SW | Commit | Work |
|----|--------|------|
| SW1 | `f145829cf` | 6 stories `disableSnapshot` (meta-level) + chromatic.yml comment hygiene (token removed, steps refreshed, report-mode kept) |
| SW2 | _(this)_ | audit + activation runbook + INDEX + CLAUDE.md row + NEW Gotcha + N+3 (W198→archive) + MEMORY.md + memory files |

## disableSnapshot classification (verify-before-write)

The Chromatic-determinism taxonomy that drove the 6-vs-rest split:
- **`pauseAnimationAtEnd` settles framer-motion springs** → Chromatic waits for the final frame, then snapshots → deterministic (15 stories; left unchanged).
- **`disableSnapshot` (the 6)** — three classes a paused spring CAN'T freeze: (1) **canvas `Math.random()` swarms** — no final frame (WeatherParticles, ParticleAuthBackground, MfaChallengeView's bg); (2) **WebGL + remote tiles** — GPU raster + network both vary run-to-run (MapLibreMap); (3) **live wall-clock text** — countdowns / relative-time recompute against real `now` every CI run, drifting day-over-day (FlipCountdown `new Date()`, EventCard `Date.now()`-relative `timeStatus` + relative-time text).
- **Safe as-is** (~206): fixed-argument date fixtures (`new Date("2026-…")`), `useId()` (stable per render tree), static content, deterministic SVG charts (ActivityTrend/BarChart settle via pauseAnimationAtEnd), and all backdrop/UI/list stories whose `new Date()` usage is metadata-only (not rendered as drifting text).

## Chromatic activation runbook (user-side, post-W201-merge)

1. **Set the Secret** `CHROMATIC_PROJECT_TOKEN` = `chpt_48d051b3688a3e4` (reused per Q2; value in `memory/wave122_chromatic_upstream.md` / your Chromatic dashboard — no longer in the workflow comment).
2. **Set the repo variable** `CHROMATIC_ENABLED=true` (the `chromatic.yml` job is `if: vars.CHROMATIC_ENABLED == 'true'` — skips cleanly until then).
3. **Merge a `frontend/**` change to `main`** → the workflow runs with `autoAcceptChanges` (already `github.ref == 'refs/heads/main'`) → captures the **first baseline** for all snapshot'd stories. The 6 disableSnapshot stories are intentionally skipped → no perpetual-red pollution.
4. **Review** the baseline in the Chromatic dashboard.
5. **Subsequent PRs surface visual diffs** (Report-mode — visible in the Chromatic check + dashboard, but `exitZeroOnChanges: true` means they don't block merge).
6. **(Optional follow-up)** once the baseline is trusted, flip `exitZeroOnChanges: true → false` in `chromatic.yml` to **block PRs on un-accepted diffs** (full enforcement). 1-line change; deliberately deferred from W201 so the W201 PR's own Chromatic check (no baseline yet) can't fail.

## Verification (wave-close gates)

- SW1: `npx tsc --noEmit` 0 + `npx eslint <6 stories> --max-warnings=0` 0 + chromatic.yml valid YAML + `grep -c chpt_ chromatic.yml` = 0 + husky chain clean (lint-staged, detect-secrets **Passed**, Python 2 except Passed; NO `--no-verify`).
- `npm run build-storybook` **SUCCESS**; index **893** (684 stories + 209 docs + 211 importPaths) — unchanged from W200; all 6 disableSnapshot stories still enumerated (6/6).
- **Build × 3** main JS sha `1bff1fd7403b03e206534340bc89c53a37ce29d1240e923e83b4101c9c813c97` × 3 (BYTE-IDENTICAL to W134-SW3 → W200; ≥60-wave); server.js `bd4a3402…885` × 3. Tree-shake invariant holds; Cargo.lock no drift.
- `npm audit --omit=dev` **0** (preserved — W201 has no dependency changes). i18n parity 18/18 (no new keys).
- Runtime smoke deliberately SKIPPED — `parameters.chromatic.*` is never read by Storybook's renderer; the 6 stories render byte-identically to W199/W200 where they passed smoke (structurally unnecessary per `feedback_perfectionism.md`).

## §Honesty probe

1. **The live Chromatic baseline + diffs are NOT verifiable in W201** — they require the user-side Secret + flag + a merge to main. W201 delivers activation-*readiness* (drift-resilient stories + clean workflow + runbook); the user completes activation. The CI Chromatic job skips cleanly (`if: vars.CHROMATIC_ENABLED == 'true'`) until the flag is set — so the W201 PR's Chromatic check reports success-by-skip, not success-by-snapshot. Honest scope boundary.
2. **MfaChallengeView loses snapshot coverage of its glass-card MFA UI** — it renders the live ParticleAuthBackground canvas, which `disableSnapshot` skips entirely. Accepted vs a perpetual false-positive; the story remains for dev/docs. A future option: conditionally render a static bg under a Storybook flag to restore card coverage (not W201 scope).
3. **Token reused, not rotated** (user Q2) — `chpt_48d051b3688a3e4` stays in git history + the memory note. Removed from the active workflow comment (hygiene). Chromatic project tokens are low-sensitivity (upload-only to one project); rotation remains available in the dashboard if the repo is public.
4. Carry-forward structural non-goals (NOT W201 scope): **W134 §H#2** bundle-delta recording-only, **W134 §H#10** /messenger Phase 5 SSR by-design (W161 SW2).

## (z) discoveries + anti-patterns

- **0 NEW (z) discoveries.** The 6-vs-rest classification was decided by Phase 1 verify-before-write reads of all candidate stories BEFORE writing — the discipline working as designed. The chromatic.yml plaintext-token finding (W121-era) was surfaced by reading the workflow, not a W201-introduced issue.
- **0 NEW anti-patterns** (14-pattern register stable post-W159 #15 archival).
- **W141 compliance**: #1 (SW1 landed 1-iter), #3 (Phase 1 classified all candidate stories from source + verified exact insertion points before editing — never trusted the grep superset), #4 (Build × 3 sha + build-storybook index captured BEFORE the audit's bundle claim), #15 ARCHIVED preserved (SW1 + SW2 fired the husky chain cleanly, NO `--no-verify`).

## NEW Gotcha (added to CLAUDE.md ## Gotchas)

**Chromatic enforce-readiness** (W201): a story is snapshot-deterministic only if its rendered pixels are identical between two CI runs of the same code. `pauseAnimationAtEnd: true` achieves that for framer-motion springs (settle → snapshot final frame), but NOT for three classes that need `parameters.chromatic.disableSnapshot: true`: (1) canvas `Math.random()` swarms (no final frame), (2) WebGL + remote tiles (GPU raster + network vary run-to-run), (3) live wall-clock text — countdowns / `Date.now()`-relative `timeStatus` / relative-time strings (recompute against real `now`, drift day-over-day). Mark these `disableSnapshot` BEFORE the first baseline, else a baseline polluted with perpetually-red stories trains the team to ignore Chromatic. `disableSnapshot` keeps the story in the Storybook index (dev/docs intact) — it only skips the Chromatic snapshot.

## Campaign / W202

The story-coverage campaign stays closed (212 stories). W201 turns that breadth into activation-ready visual-regression infrastructure. **W202+ = maintenance mode** (W171 Lesson #1) until a real trigger — OR, once the user sets the token+flag + reviews the first baseline, an **enforce-flip follow-up** (`exitZeroOnChanges: false`) to make visual diffs block PRs. Either fires on a real signal, not a schedule.

Memory references (`.claude` profile only): `memory/wave201_backlog.md`, `memory/wave202_opening_prompt.md`, `memory/wave122_chromatic_upstream.md` (token value + upstream diagnosis).
