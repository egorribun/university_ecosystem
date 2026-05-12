# Wave 146 — Full structural fix for 4 chronic CI failures on PR #1114

**Date**: 2026-05-12
**Branch**: `egorribun` (HEAD `9d03c69d7`)
**Scope** (user-approved via 3-question AskUserQuestion W134-W145 convention): Full structural fix (~5-7h) → all 4 chronic CI failures, E2E first, open-ended absorption iter ceiling (8th consecutive wave)
**Cross-refs**: [memory/wave122_chromatic_upstream.md](../../memory/wave122_chromatic_upstream.md) (W122-W123 Chromatic diagnostic history), [memory/wave145_backlog.md](../../memory/wave145_backlog.md) (W145 close-status), W145 SW1 commit [2201fb8bd](https://github.com/egorribun/university_ecosystem/commit/2201fb8bd) (Promise.race injection wrapper template)

---

## Context

W145 closed cleanly: 2 §Honesty caveats CLOSED at runtime (W144 NEW (z) #21 axe injection 24-min hang RESOLVED via 30s fast-fail + Tier 5 12-wave carry-forward RETIRED) + **0 NEW (z) discoveries** (sharp departure from W139-W144 pattern 9/8/6/6/3/6). W145 polish-v2 surfaced **4 chronic CI failures on PR #1114** that ALL pre-date W145 (none are W145 regressions):

| Check | Status | Root cause |
|---|---|---|
| Chromatic Visual Regression | ❌ FAIL (2m6s) | `validateFiles` at `chromaui/action@v16.9.1:register.cjs:2388:870` rejects build because **`iframe.html` is missing** in `storybook-static/`. Storybook 10.2.13 + Vite 8/Rolldown + `@chromatic-com/storybook` 4.1.3 produces incomplete output |
| E2E Tests / E2E Tests (chromium) | ❌ FAIL (20m17s) | `tests/e2e/a11y-cdn-axe.spec.ts:51-53` hits 90s timeout — production CSP `script-src 'self' 'strict-dynamic'` blocks `page.addScriptTag(CDN_URL)` injection |
| Frontend Tests / Lighthouse Audit | ❌ FAIL (5m37s) | `LighthouseError: Lighthouse was unable to reliably load the URL you requested because the page stopped responding` on `http://localhost:40341/` — chronic flake family (W128/W139 NO_FCP) |
| CI Success (aggregate) | ❌ FAIL (3s) | Auto-aggregates above 3; will auto-green when underlying pass |

**Empirical findings** (Phase 1 verification at plan-write time per W141 anti-pattern #3 SEXTUPLE-vindicated discipline):

1. **iframe.html confirmed MISSING locally**: `find storybook-static -name "iframe*"` returns 0 matches; recursive deep find confirms not in any subdir.
2. **PWA artifacts confirmed LEAKING**: `manifest.webmanifest`, `sw.js`, `offline.html`, `icon-192.png`, `icon-512.png`, `maskable-icon-192.png`, `maskable-icon-512.png`, `static-shell-i18n.js` ALL present in `storybook-static/` despite W120 SW8 PWA-plugin filter in `.storybook/main.ts:34-45`.
3. **Package version gap**: `@chromatic-com/storybook@^4.1.3` installed; `5.1.2` is latest on npm (one major behind). Storybook 10.2.13 + Vite 8 + Rolldown stack.
4. **Chromatic CI log evidence**: "Storybook built in 34 seconds" (`exitCode: 0`) BUT "Invalid Storybook build at /tmp/chromatic--4549-KMHT5bc2mxHP". Build succeeds; output incomplete.
5. **E2E target line confirmed**: `tests/e2e/a11y-cdn-axe.spec.ts:51-53` is the exact `page.addScriptTag({ url: "https://cdn.jsdelivr.net/npm/axe-core@4.11.2/axe.min.js" })` to replace with W145 SW1 pattern.
6. **W145 SW1 pattern source verified**: `frontend/scripts/wave138-visual-audit.mjs:401-433` — `Promise.race([page.evaluate((src) => eval(src), AXE_SOURCE), setTimeout-reject(30s)])`. `frontend/node_modules/axe-core/axe.min.js` present (npm-pinned 4.11.2).

---

## Recommended approach

**7 SWs (plus optional SW4) with built-in honest-defer triggers per W140 anti-pattern #1 (2-3 CI iter cap; deviation → defer to W147+)**.

### SW0 — Design doc commit (this doc; ~5-10 min)

### SW1 — E2E `a11y-cdn-axe.spec.ts` fix (~10-20 min)

Apply W145 SW1 pattern verbatim from `wave138-visual-audit.mjs:401-433`:
- Module-scope `AXE_SOURCE = await readFile(require_.resolve("axe-core/axe.min.js"), "utf-8")`
- Replace `page.addScriptTag(CDN_URL)` with `page.evaluate((src) => eval(src), AXE_SOURCE)` wrapped in `Promise.race(30s)` defensive ceiling
- Eliminates CSP-block failure mode definitively (eval inside browser-context page.evaluate is CSP-agnostic — no `<script>` tag created)

**Commit**: `fix(wave146-sw1-e2e-csp-block): replace CDN page.addScriptTag with eval(npm-bundled axe) + Promise.race(30s)`

### SW2 — Lighthouse Audit investigation (~30 min - 1.5 h)

3-phase decision tree:
- **Phase A** (~15-20 min): local `npm run lhci:windows LHCI_URLS=,` reproduction + HAR capture
- **Phase B** (~10-20 min): hypothesis-verify `InstallPrompt` push-panel gate (W119 SW1) still trips
- **Phase C** (~10-30 min): one of c1=gate-fix, c2=throttling tune, c3=`continue-on-error` accept

**Honest defer**: if Phase A doesn't reproduce locally (CI-runner-only flake), defer to W147+ as "CI runner pressure unrelated".

### SW3 — Chromatic Path B Storybook structural fix (~2-5 h)

Priority-ordered hypothesis cascade (cheapest-first):

| # | Hypothesis | Action | Time |
|---|---|---|---|
| A | `@chromatic-com/storybook` 4.1.3 → 5.1.2 (PRIMARY — most plausible per major-bump signal) | `npm install --save-dev @chromatic-com/storybook@^5` + rebuild + find iframe.html | ~10-30 min |
| B | vite-plugin-pwa static-asset side-effect (`public/sw.js` + `public/manifest.webmanifest` collide with Storybook 10's iframe.html generation logic) | Temporarily move PWA artifacts out of `public/` + rebuild | ~30-60 min |
| C | TanStack Start filter over-aggression (`virtual-client-entry` filter at `.storybook/main.ts:73` may overshoot) | Inspect plugin chain + selectively remove filter entries | ~30-60 min |
| D | Storybook 10 PWA-mode auto-emission (detects `public/manifest.webmanifest` + switches to single-page emission) | Grep `node_modules/@storybook/builder-vite/dist/*.mjs` for PWA-detection logic | ~30-60 min |
| E | Storybook 10 build-storybook command flag drift (new required flag) | `npx storybook build --help` for `--no-pwa` or similar | ~10-20 min |

**Iter cap**: 2 attempts per hypothesis × 5 hypotheses = 6 max. Honest defer at iter 6 → user takes Path A (Chromatic disable repo variable) per `chromatic.yml:71` `if: ${{ vars.CHROMATIC_ENABLED == 'true' }}`.

**Commits** (per-hypothesis split):
- `fix(wave146-sw3-chromatic-storybook): <hypothesis name>` IF Path B succeeds, OR
- Audit doc honest-document defer + user takes Path A

### SW4 — Optional Tier 5 new scope decision (~30 min - 2 h, ONLY if SW1-3 leave budget)

Tier 5 retired in W145; W146-W148 candidates: `/admin`, `/map` polish round 2, `/events`, `/news`, etc. **Honest defer**: may stay deferred — Tier 1 CI closure is the W146 headline.

### SW5 — §Honesty caveats re-measurement (~15-20 min)

Re-measure all gates: tsc 0, lint 0, vitest 1052p/12s/0f, npm audit 0, Cargo.lock idempotent, bundle size invariant. Re-check `gh pr checks 1114` per commit.

**Target §Honesty trajectory**: 3-10 pre-W146 → ≤6 post-W146.

### SW6 — Bundle reproducibility verification (~5-10 min)

W145 baseline preservation: `index-BxOLtIf2.js` 139,808 bytes BYTE-IDENTICAL SIZE. Tree-shake invariants (no `lhci-mock-user`, no `data-e2e-stub` in PROD dist). SW IIFE invariant (`head -c 25 dist/client/sw.js` → `"use strict";(()=>{`). Cargo.lock no drift (≥35 waves idempotent).

### SW7 — Audit + memory + N+3 rotation (~30-45 min)

- NEW `docs/audits/AUDIT_WAVE146.md` (~400-500 lines)
- UPDATE `CLAUDE.md ## Audit Trail` row (concise per W134 SW3 convention)
- NEW `memory/wave146_backlog.md`, NEW `memory/wave147_opening_prompt.md`, UPDATE `memory/MEMORY.md`
- N+3 rotation: `git mv docs/audits/AUDIT_WAVE143.md docs/audits/archive/AUDIT_WAVE143.md` (active waves W144/W145/W146)
- UPDATE `docs/audits/INDEX.md`

---

## Hypothesis matrix justification

**Why Hypothesis A first (cheapest + most likely)**:
- Major version bump 4.x → 5.x typically signals breaking API contract (Storybook addon ecosystem follows semver-major for compat shifts)
- W123 SW1 already documented Storybook 10 + Vite 8 integration as fragile (`strictExecutionOrder` workaround was needed) — addon compat is plausible next breakage point
- ~10-30 min investment; if iframe.html appears post-install, ~3-4h budget saved vs Hypothesis B-E investigation

**Why iter cap matters**:
- W140 anti-pattern #1: "2-3 CI iter cap on SW1" — applied per SW here
- W141 polish-A3 + W143 SW3 honest-defer precedents — cascade investigation can yak-shave deeper than scope allows
- Path A user-action fallback is the safety valve: 5-min repo-settings flip closes the CI failure even if Path B doesn't resolve

**Why E2E first**:
- Concrete + mechanical (W145 SW1 pattern verified working in current codebase)
- Highest-certainty closure → builds momentum into uncertain SW2 + SW3
- No CSP-block hypotheses to test; the W145 SW1 pattern is the canonical CSP-agnostic injection method

---

## Verification gates (post-W146)

| Gate | Target |
|---|---|
| Frontend Tests / Lint & Format | ✅ preserved (W145 polish-v2 baseline) |
| Trivy Image Scan | ✅ preserved (W145 polish-v2 baseline) |
| Chromatic Visual Regression | ✅ green via Hypothesis A-E OR skip via Path A user-action |
| E2E Tests (chromium) | ✅ green via SW1 W145 SW1 pattern |
| Frontend Tests / Lighthouse Audit | ✅ green via SW2 fix OR `continue-on-error` |
| CI Success (aggregate) | ✅ auto-greens when above 3 pass |
| Other 44 checks | ✅ preserved green |
| §Honesty caveats | ≤6 (4 closed minus 1-2 NEW from Path B partial closure) |
| tsc 0 + lint 0 + vitest 1052p/12s/0f + npm audit 0 | ✅ preserved exactly |
| Bundle `index-*.js` BYTE-IDENTICAL SIZE 139,808 bytes | ✅ preserved (SW1 is test-only; SW3 hypothesis fixes touch package.json + .storybook/main.ts — neither affects prod bundle) |
| Tree-shake + SW IIFE invariants | ✅ preserved |
| Cargo.lock no drift (≥35 waves) | ✅ preserved |
| Docker temporal + file-processor (healthy) | ✅ preserved (post-W144 SW2 baseline) |

---

## Plan deviation triggers (per W141 anti-pattern #1+#4)

1. **SW1 CI iter 3+** → defer to W147+ as "W144 NEW (z) #21 analogue"
2. **SW2 Phase A doesn't reproduce locally** → defer to W147+ as "CI runner pressure unrelated"
3. **SW3 hypothesis cascade exceeds 6 iter** → defer to W147+ via Path A user-action + document deeper W148+ investigation
4. **(z) cascade > 5 NEW discoveries** → pause + reassess scope per W143 SW3-6 honest-defer precedent
5. **Mid-wave time spent > 7h** → close at current SW + defer remaining (open-ended absorption is generous, but 7h is the soft ceiling per W140 polish-A3 history)

---

## W147+ candidates surfaced (per design discipline)

If SW3 takes Path A user-action fallback (Chromatic disable):
- Storybook 10 + Vite 8/Rolldown iframe.html structural investigation as own focused W148 scope (~3-5h)
- Filed upstream issue or PR if Storybook 10 PWA-mode emission is the bug

If SW1 fixes hit unforeseen depth:
- W140 NEW #5 axe coverage 0/10 closure via `page.addInitScript()` alternative (already W146+ candidate per W145 backlog)

Tier 5 scope decision (post-W145 retirement):
- /admin polish arc — long-deferred since W134
- /map polish round 2 — last major work W108-W111
