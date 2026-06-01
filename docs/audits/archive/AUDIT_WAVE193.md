# AUDIT — Wave 193 (Storybook glob widen + backdrop coverage full closure)

**Date**: 2026-05-28
**Branch**: `egorribun` · **PR**: [#1126](https://github.com/egorribun/university_ecosystem/pull/1126)
**Scope**: User-chosen B + E Storybook combo (Q0 options 2 + 4) → **E** widen the Storybook glob to track the `features/` migration + **B** write all 9 missing backdrop stories (full closure → 11/11). 53rd consecutive wave preserving brainstorming + Phase 1 Explore + Phase 3 Review + W141 anti-pattern discipline.

---

## Headline

W193 closes a **slow architectural drift**: over ~80 waves the codebase migrated whole features into `src/features/` (Activity W112, Events/News, Admin W164, Messenger W145), but the Storybook story glob stayed frozen at `src/components/**` since W115 — silently orphaning every feature-co-located story. SW1 **widens** the glob with a second explicit `../src/features/**` pattern (activating 6 dormant orphan stories for free + unblocking the 2 `features/`-scoped backdrops), and SW2–SW4 write the **9 missing backdrop stories**, bringing backdrop visual-regression coverage **2/11 → 11/11**.

Discoverable Storybook story files: **53 → 68** (53 active + 6 orphans + 9 new). `admin.stories.tsx` (a TanStack Router route file) stays excluded **by construction** — neither glob pattern touches `routes/`, zero negation needed.

**4 SW commits + this SW5 audit = 5 commits.** Bundle main JS **byte-identical** to W190/W192 (empirically verified). vitest **1270p/12s/0f** preserved exactly across all 5 commits.

---

## SW breakdown

### SW1 — `ffa668252` `feat(wave193-sw1-storybook-glob-widen)` (1 file, +14/-6)
- `.storybook/main.ts:15` → 2-element `stories` array: existing `../src/components/**/*.stories.@(...)` + NEW `../src/features/**/*.stories.@(...)`. Comment block 10-14 rewritten to document the W193 widen rationale (track features/ migration; routes/ excluded by construction).
- **Verified**: `build-storybook` succeeds (9.53s); `storybook-static/index.json` → **59 story files** (was 53), all 6 events/news orphans now activated; **0 routes/ leak** (`admin.stories.tsx` excluded). Risk A (dormant orphan breakage) did NOT materialize — all 6 orphans compile + appear in the index. Risk B (addon-vitest registering orphans) did NOT materialize — vitest **1270p/12s/0f** preserved exactly.
- **Gates**: tsc 0, lint 0, vitest 1270p/12s/0f.

### SW2 — `3c91ae8ba` `feat(wave193-sw2-features-backdrop-stories)` (2 files, +184)
- NEW `features/activity/components/ActivityBackdrop.stories.tsx` + `features/admin/components/AdminBackdrop.stories.tsx` — first co-located `features/` stories, discoverable only since SW1's widen → **proves the widen end-to-end**.
- **Phase 3 deviation from the MessengerBackdrop template** (documented): both backdrops' orb tokens are SCOPE-defined under `.activity-theme` / `.admin-theme` (tokens/activity.css:34/:123, tokens/admin.css:42/:121) — NOT `@property`-registered globals like the messenger orbs. So each story uses a `themed(dark)` decorator factory that nests `.dark` OUTSIDE the theme class — the correct ancestry for the `.dark .X-theme` descendant selector. Storybook nests story decorators INSIDE meta decorators, so the messenger "meta=theme + story=.dark" split would have inverted the order and silently rendered light orbs in the "DarkMode" variant.
- **Within-iter SAME-mechanism fix (W138 Lesson #1)**: the factory's returned arrow tripped `react/display-name`; restructured to a block-body factory with a justified `eslint-disable-next-line` (W112 SW1 sanctioned pattern — Storybook decorators are not render components). Both required props (`isNarrow` + `prefersReducedMotion`) passed explicitly.
- **Gates**: tsc 0, lint 0.

### SW3 — `b0d692b2e` `feat(wave193-sw3-3prop-backdrop-stories)` (3 files, +304)
- NEW `Auth` + `Profile` + `Settings` backdrop stories (components/ tree, 3-prop family: `isNarrow` + `isMobile` + `prefersReducedMotion`; `dropBlur = prefersReducedMotion || isMobile`). Each scoped to `.auth-theme` / `.profile-theme` / `.settings-theme` via the `themed(dark)` factory.
- **5 variants each** — Default / DarkMode / Narrow (tablet: narrow orbs, blur KEPT) / ReducedMotion / **Mobile** (phone: blur DROPPED via `isMobile`). The Narrow-vs-Mobile pair exercises the deliberate tablet-vs-phone GPU distinction the 3-prop family encodes.
- **Gates**: tsc 0, lint 0.

### SW4 — `dadfe70d5` `feat(wave193-sw4-2prop-backdrop-stories)` (4 files, +327)
- NEW `Events` + `News` + `Map` + `Footer` backdrop stories (2-prop family, no `isMobile` → 4 variants each).
- Events/News/Map scoped to `.events-theme` / `.news-theme` / `.map-theme`. **FooterBackdrop is the special case**: theme-agnostic always-dark, NO `.X-theme` scope — its orbs live in semantics.css `:root`/`.dark` (:308/:551), so its decorator wraps in `bg-footer` (not a theme class) + uses `--text-on-footer` (constant white) for the label. Map + News pass their required props explicitly.
- **Closes the backdrop coverage gap**: `build-storybook` reports **68 story files** (53 + 6 orphans + 9 new), all **11 backdrops** now have stories, 0 routes/ leak.
- **Gates**: tsc 0, lint 0, vitest **1270p/12s/0f** (baseline preserved exactly across all 9 new stories + the widen).

### SW5 — (this commit) audit + housekeeping
- NEW `docs/audits/AUDIT_WAVE193.md` (this file).
- N+3 rotation: `git mv docs/audits/AUDIT_WAVE190.md docs/audits/archive/AUDIT_WAVE190.md` → active waves **W191/W192/W193**.
- CLAUDE.md ## Audit Trail row + 2 NEW Gotchas (Storybook glob widen 2nd-pattern convention + Rolldown filename-hash-vs-content-sha distinction).
- `docs/audits/INDEX.md` updates (W193 → active, W190 → archive, rotation-history line).
- MEMORY.md compaction (W190 verbose → one-liner) + W193 row (`.claude` profile).
- NEW `memory/wave193_backlog.md` + `memory/wave194_opening_prompt.md` (`.claude` profile).

---

## Bundle (empirical, clean `rm -rf dist && npm run build`)

| Artifact | W193 | vs W190/W192 baseline |
| --- | --- | --- |
| main JS content | `index-B8BD2TjY.js` **180,273 b**, sha `1bff1fd7403b03e206534340bc89c53a37ce29d1240e923e83b4101c9c813c97` | **BYTE-IDENTICAL CONTENT** (sha EXACT MATCH `1bff1fd7…c97`) |
| main JS filename | `B8BD2TjY` | shifted from `CGBUMlAV` (cosmetic — see Gotcha) |
| server.js | **24,024 b**, sha `fb8a586026a2e6c17b0143b775d501909a284f31de69097f89d1d73132fa8631` | same SIZE; sha shifted (NEW W193 baseline) per `.stories.tsx` precedent |

- **Main JS byte-identical CONTENT confirms the structural argument EMPIRICALLY**: W193 touches only `.storybook/main.ts` (Storybook-only config, not read by `vite build`) + new `.stories.tsx` (never imported by `main.tsx` → outside the prod module graph). The W134-W192 ≥51-wave LOCAL-MACHINE BYTE-IDENTICAL invariant chain (on main-JS content) **EXTENDS through W193 → ≥52-wave invariant**.
- **Chunk filename shifted** (`CGBUMlAV` → `B8BD2TjY`) while content sha is identical: Rolldown's filename-hash folds in module-graph metadata, which the 9 new project files + glob change perturbed without altering emitted bytes. Cosmetic — same class as the server.js sha drift tracked since W189.
- **server.js sha shifted** (`cc187185…c19` W192 → `fb8a5860…8631` W193), size unchanged 24,024 b — the documented `.stories.tsx`-addition chunk-graph reshuffle; server-side code unchanged; NOT a regression.
- Build orchestrated cleanly ("no Windows hang, no watch+kill required").

---

## Gates (end-of-wave)

| Gate | Result |
| --- | --- |
| tsc `--noEmit` | **0 errors** (every SW) |
| eslint `--max-warnings=0` | **0** (every SW; `npm run lint` scopes src+tests) |
| vitest `run` | **1270 passed / 12 skipped / 0 failed** (W192 baseline preserved EXACTLY — stories are not registered as default vitest tests) |
| `build-storybook` | **success** — 68 story files, 11/11 backdrops covered, 0 routes/ leak |
| main JS content | **byte-identical** to W190/W192 (sha `1bff1fd7…c97`) |
| Storybook story files | 53 → **68** (+6 orphans activated, +9 new backdrops) |
| husky pre-commit chain | clean × 4 SW commits (lint-staged + detect-secrets + Python 2 except check) — NO `--no-verify` |

---

## §Honesty probe

- **§Honesty trajectory: 0-2 OPEN → 1-2 OPEN at wave-close → 0-2 OPEN after polish-v1** (the 1 NEW caveat below was CLOSED in polish-v1 — see the Polish-v1 section).
  - **Delivered (not §Honesty closures — net-positive scope)**: E glob widen (resolved the orphan + features/-discoverability drift) + B backdrop coverage 2/11 → 11/11.
  - **1 NEW W193-surfaced caveat**: committing `.storybook/main.ts` (SW1) surfaced a **pre-existing** eslint *parsing error* in lint-staged — "`.storybook/main.ts` was not found by the project service". `.storybook/` isn't in eslint's typed-lint tsconfig, so the typed parser can't resolve it. **Non-blocking** (the commit completed; `tsc` 0; build OK) and **pre-existing** (surfaces on any `.storybook/*.ts` commit — W123/W125 hit it too). CI is unaffected (`npm run lint` only scans `src`+`tests`). W194 ~15 min candidate: add `.storybook/` to eslint's tsconfig project service OR scope it out of lint-staged's eslint task.
  - **2 structural carry-forward (unchanged, by-design)**: W134 §H#2 bundle delta recording-only; W134 §H#10 /messenger Phase 5 SSR by-design (W161 SW2 deliberate defer).
- **NOT §Honesty caveats (documented observations)**: the Rolldown filename shift (content byte-identical) + the server.js sha drift — both documented build-pipeline behaviors, not defects.

---

## W141 anti-pattern compliance

- **#1 STRICT 1-iter per SW**: 4 SW each landed in 1 iter (SW2's `react/display-name` fix was a within-iter SAME-mechanism sub-fix per W138 Lesson #1 — NOT a mechanism pivot). Vindications **#100-#103** (cumulative ≥99 pre-W193).
- **#3 Phase 3 Review verify-before-write**: vindications **#113-#116** — Phase 3 corrected Agent 1's "52 active" → 53 (off by one); caught the E-B coupling the agents missed (2 backdrops under `features/` need the widen); caught the scope-defined-token vs `@property`-global distinction (forced the `themed(dark)` factory + correct `.dark` ancestry); caught MEMORY.md headroom drift (opening prompt "~22-23 KB / 1.4-2.4 KB headroom" was stale; actual 24,288 b / 112 b headroom).
- **#4 closures-after-empirical-verification**: vindication **#47** — backdrop coverage closure attributed AFTER `build-storybook` index.json showed 68 files + 11/11; bundle invariant attributed AFTER empirical sha match (not just structural argument).
- **#15 (ARCHIVED W159 SW4)**: preserved **85th-88th consecutive waves** — all 4 W193 SW commits fired the W156 SW4 husky pre-commit chain cleanly. NO `--no-verify`.

---

## (z) discoveries

**0 NEW (z) from W193 SW execution proper.** Extends the low-(z) streak (W145-W193). The SW2 `react/display-name` factory lint was a within-iter SAME-mechanism fix (W138 Lesson #1), not a (z). The `.storybook/main.ts` lint-staged parsing error is a pre-existing tooling gap surfaced (logged as a §Honesty caveat / W194 candidate), not a W193-introduced (z).

---

## Gotchas added (CLAUDE.md ## Gotchas)

1. **Storybook glob widen 2nd-pattern convention** — to make a `src/features/**`-co-located story discoverable, the `.storybook/main.ts` `stories` array carries a 2nd explicit pattern `../src/features/**/*.stories.@(...)`; `routes/` is never matched, so `admin.stories.tsx` (route file) stays excluded by construction. Scope-defined theme-token backdrops (activity/admin/auth/profile/settings/events/news/map) need a `themed(dark)` decorator factory that nests `.dark` OUTSIDE the `.X-theme` class (`.dark .X-theme` is a descendant selector; Storybook nests story decorators inside meta decorators, so a meta=theme + story=.dark split inverts the order).
2. **Rolldown filename-hash ≠ content-sha** — a prod build can shift `dist/client/assets/index-<hash>.js` filename while `sha256sum` proves the content is byte-identical (Rolldown's filename-hash folds in module-graph metadata that unbundled file additions perturb). Verify the bundle invariant via content `sha256sum`, NOT the filename. Same class as the server.js sha drift tracked since W189.

---

## W194+ candidates

- **A** — Maintenance mode (CANONICAL DEFAULT per W171 Lesson #1) — no real trigger; next wave fires on a real trigger or user-chosen scope.
- **B** — Continue D scope: remaining non-backdrop story candidates (MessageInput Blob-URL + SVG-rejection + FormData mock; Map markers × 3 MapLibre-GL mock; Profile Header+Editor; Auth LoginCredentialForm + MfaChallengeView; Activity visualizations × 3 ActivityTrendChart/BarChart/Heatmap; Navbar; Mobile menu). HARD tier (mocks).
- **C** — Path E XL messenger backend wave (~6-10h — backend EMPIRICALLY NOT READY per W190 pre-flight: `read_status: bool` only, no `read_at`/`Reaction` table/`voice_message_url`).
- **D** — Lighthouse #17021 next monitoring tick at the W196-W200 window (off-cadence now).
- **E** — ✅ DONE in polish-v1 (`.storybook` added to eslint `ignores` + `--no-warn-ignored` on lint-staged eslint task).
- **F** — Visual verification: review the Chromatic build post-push for the 15 new story baselines (9 backdrops + 6 orphans) — expected auto-accepted as new baselines, 0 regressions on existing.

---

## Polish-v1 (post «безупречно?» probe, 2026-05-28)

The probe surfaced 3 gaps against the project's own standard; polish-v1 closed 2 of 3 (the 3rd, CI, is external + was confirmed shortly after).

1. **Build reproducibility upgraded × 1 → × 3 EMPIRICAL.** Wave-close did Build × 1; polish-v1 ran 2 more clean `rm -rf dist && npm run build`. All 3: main JS sha `1bff1fd7403b03e206534340bc89c53a37ce29d1240e923e83b4101c9c813c97` (= W190/W192 baseline) + server.js sha `fb8a586026a2e6c17b0143b775d501909a284f31de69097f89d1d73132fa8631` — **BYTE-IDENTICAL × 3**. The ≥52-wave LOCAL-MACHINE invariant is now confirmed empirically × 3, not × 1.
2. **`.storybook/*.ts` lint-staged eslint parsing-error gap CLOSED** (was the 1 NEW W193 §Honesty caveat). Fix: added `".storybook"` to `eslint.config.mjs` `ignores` (line 17) — exactly mirroring the pre-existing `vite.config.mts` entry (both are build-config files outside the typed-lint tsconfig `projectService`) — plus `--no-warn-ignored` on the lint-staged eslint task (`frontend/package.json`). Verified: `npx eslint .storybook/main.ts` was a **parsing error (exit 1)** → now an ignored-file warning (exit 0); with `--no-warn-ignored` it is **fully silent (exit 0)**. `npm run lint` (src+tests scope) unaffected = 0. Both changes are dev-tooling only — NOT in the prod bundle (main JS stays byte-identical).
3. **CI Matrix Expansion** — the only pending wave-close item; confirmed green after the long-pole matrix finished (Chromatic + Wave189 Smoke + Go Lint + Dependency Review all green at wave-close).

**§Honesty post-polish-v1: 0-2 OPEN** (the lint-staged gap CLOSED; only the 2 W134 structural non-goals carry forward — W134 §H#2 bundle delta recording-only + W134 §H#10 /messenger Phase 5 SSR by-design). **W141 #4** vindicated: the «безупречно?» probe correctly drove a self-audit, not reassurance — 2 real gaps fixed + 1 confirmed. Polish-v1 commit touches `eslint.config.mjs` + `package.json` (dev-tooling) + docs; bundle invariant preserved (main JS sha `1bff1fd7...c97` unchanged across the Build × 3).
