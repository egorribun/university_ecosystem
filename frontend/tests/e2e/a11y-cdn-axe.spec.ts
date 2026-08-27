import { blockBackgroundNetwork, expect, test } from "./test"
import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import path from "node:path"

/**
 * Local-injected `axe-core` regression test — Wave 115 SW3 / Wave 146 SW1 / **Wave 147 SW1 structural**.
 *
 * `@axe-core/playwright@4.11.2` bundles `axe-core@4.11.3` internally (see
 * `node_modules/@axe-core/playwright/dist/index.mjs` — it imports the
 * transitive `axe-core` peer). During Wave 114 polish-v2, a full-WCAG
 * audit via `axe.min.js@4.11.2` loaded directly in a running dev preview
 * consistently reported a WCAG 2.5.8 `target-size` violation on
 * `<a href="/forgot-password">` in the `LoginCredentialForm`. Three
 * consecutive runs at Playwright's 1280×720 viewport all surfaced it
 * (19 × 105 px inline link < 24 × 24 px minimum). The same tag-set through
 * `@axe-core/playwright`'s bundled scanner on the same e2e harness did
 * NOT catch it — rule-engine delta between 4.11.2 and 4.11.3 or a
 * Playwright-specific rendering quirk, not instrumented further.
 *
 * ## Injection mechanism evolution + real root-cause discovery
 *
 *   - **Wave 115 SW3 (origin)**: loaded `axe-core@4.11.2` from jsdelivr CDN
 *     via `page.addScriptTag` → production CSP `script-src 'self' 'strict-dynamic'`
 *     (see `app/core/policies/csp.py:39`) silently blocked the CDN URL since
 *     Playwright's `addScriptTag` can't attach a per-request nonce → `load`
 *     event never fired → 90 s test timeout.
 *
 *   - **Wave 146 SW1 (eval pivot)**: replaced CDN with npm-bundled
 *     `axe-core@4.11.2` injected via `page.evaluate((src) => eval(src), AXE_SOURCE)`.
 *     CSP-agnostic (no `<script>` tag = no `script-src` evaluation). Hung
 *     deterministically — initial hypothesis (W145 SW1 Promise.race(30s)
 *     diagnostic) was 564 KB AXE_SOURCE IPC-serialized per-evaluate.
 *
 *   - **Wave 147 SW1 (THIS — structural closure)**: switched to
 *     `page.addInitScript({ content: AXE_SOURCE })` via `test.beforeEach`.
 *     Init-script runs BEFORE each page's own scripts (browser-native
 *     injection, no IPC marshalling of 564 KB per-test). `window.axe`
 *     available immediately on `page.goto()` resolution.
 *
 *     **CRITICAL EMPIRICAL DISCOVERY (W147 SW1 iter 4-5 diagnostic)**:
 *     init-script alone DIDN'T fix the hang. Diagnostic confirmed
 *     `window.axe` WAS pre-injected (init-script works), yet `axe.run()`
 *     still hung 60s+ EVEN ON INSTANT RULES like `html-has-lang`. The
 *     ACTUAL root cause was BROWSER EVENT LOOP STARVATION: /login mounts
 *     `useProfileSync` which fires `/users/me`, that errors (500/401),
 *     React Query retry semantics + dynamic-chunk lazy-loads + service
 *     worker workbox loops kept the JS event loop saturated → axe-core's
 *     internal `requestIdleCallback` / `setTimeout` scheduler never got
 *     a yield slot → axe.run never resolved.
 *
 *     Fix: quiesce background API/realtime traffic AFTER `page.goto` while
 *     allowing document, script, style, image, and font requests to finish.
 *     The page settles in its post-goto static state (DOM tree unchanged,
 *     axe-auditable), while unbounded background loops stop competing for the
 *     event loop. axe.run completes in ~1-2s. Closes W140 NEW #5 chronic since
 *     Wave 140 —
 *     this was the SAME failure class W113-W116 + W144-W146 wrestled
 *     with under various injection mechanisms (CDN, eval, AxeBuilder).
 *     The injection was a red herring; event-loop starvation was the
 *     real bug.
 *
 * The Promise.race wrapper from W145 SW1 is preserved around the
 * `axe.run()` call as defense-in-depth: if axe.run hangs for a
 * different reason (e.g. some future browser quirk), the failure
 * remains deterministic at 60s instead of waiting for the 90s test
 * timeout.
 *
 * Chromium-only — WebKit projects already have memory-envelope constraints
 * from `a11y-public.spec.ts` Wave 115 SW1 legacy-mode handling, and the
 * pre-injected init-script doesn't change WebKit's memory footprint
 * meaningfully (564 KB still has to land in the page's JS heap once).
 */

type AxeNode = { target: string[]; html: string; failureSummary?: string }
type AxeViolation = { id: string; impact: string; nodes: AxeNode[]; help: string }
type AxeResult = { violations: AxeViolation[] }

// W146 SW1 — Path resolution from `frontend/tests/e2e/a11y-cdn-axe.spec.ts`
// up to `frontend/node_modules/axe-core/axe.min.js`. Three levels up
// (file → e2e → tests → frontend) then descend. Mirrors
// `authenticated-visual-audit.mjs` resolution pattern (which goes two
// levels because that script is in `frontend/scripts/`).
//
// W147 SW1 iter 3 — read source SYNCHRONOUSLY at module load + pass via
// `{content}` instead of `{path}`. Empirical: `{path}` variant injection
// hung axe.run deterministically on chromium even with single-rule scope,
// suggesting Playwright's path handling on Windows (backslash normalization
// or async file-resolution timing) wasn't actually injecting axe-core
// before page.goto resolution. `{content}` eliminates the path-resolution
// variable: file is read by Node at module load, content is passed inline
// to Playwright's `context.addInitScript`. Module-scope sync read is fine
// — single 564 KB read at test file load, negligible vs test runtime.
const AXE_SOURCE_PATH = path.resolve(
  fileURLToPath(import.meta.url),
  "../../../node_modules/axe-core/axe.min.js"
)
const AXE_SOURCE = readFileSync(AXE_SOURCE_PATH, "utf-8")

test.describe("@a11y local-injected axe-core regression", () => {
  // Wave 147 SW1 structural — inject axe via `page.addInitScript({content})`
  // BEFORE `page.goto()` in each test.
  //
  // ## Why `page.addInitScript`, NOT `context.addInitScript`
  //
  // Playwright's default `page` fixture creates the page BEFORE
  // `test.beforeEach({ context })` runs (fixtures resolve before
  // beforeEach hooks). So `context.addInitScript` attaches scripts to
  // FUTURE pages only — the current test's page already exists, the
  // upcoming `page.goto` does NOT trigger the context-level init-script.
  // This was the bug in W147 SW1 iter 1+2 (~30s + ~60s timeouts both
  // fired because `window.axe` was never defined when `axe.run()` was
  // called — `page.evaluate` hung trying to access undefined `axe`).
  //
  // `page.addInitScript` attached to the existing page registers a
  // script to run on the NEXT navigation. The `page.goto()` inside the
  // test body triggers it. `window.axe` is defined the moment
  // `page.goto()` resolves; the subsequent `axe.run()` page.evaluate
  // works as designed.
  //
  // No IPC marshalling of 564 KB per-test: Playwright passes the script
  // content to the browser ONCE via CDP `Page.addScriptToEvaluateOnNewDocument`
  // and the browser caches it. Per-test overhead is constant-time.
  test.beforeEach(async ({ page }) => {
    await page.addInitScript({ content: AXE_SOURCE })
  })

  test("/login — no WCAG 2.2 AA target-size violations", async ({ page }, testInfo) => {
    // Wave 115 polish — standardised on `testInfo.project.name` across both
    // `a11y-public.spec.ts` and this spec so skip conditions stay consistent
    // (per Wave 113 convention: `browserName` returns "webkit" for both the
    // `webkit` and `mobile-webkit` Playwright projects because they share
    // the same browser binary — only `project.name` distinguishes them).
    test.skip(
      testInfo.project.name !== "chromium",
      "axe injection compounds WebKit memory pressure — Chromium only (Wave 115 SW1 gates WebKit via legacy mode)"
    )

    await page.emulateMedia({ reducedMotion: "reduce" })
    await page.goto("/login", { waitUntil: "domcontentloaded", timeout: 30_000 })

    // W147 SW1 — quiesce background API/realtime traffic so React Query +
    // useProfileSync + service workers can't starve the event loop, while
    // keeping application code/assets available for any pending lazy import.
    //
    // ROOT CAUSE (empirically identified in iter 4-5 via diagnostic logs):
    // Pre-W147, `axe.run()` on chromium hung deterministically even on
    // instant rules like `html-has-lang`. Diagnostic confirmed
    // `window.axe` WAS correctly pre-injected (init-script works), so the
    // hang wasn't injection-related. It was the BROWSER EVENT LOOP being
    // saturated by useProfileSync's `/users/me` API call retry loop on
    // /login (and dynamic-chunk lazy-loads, telemetry init, etc.) —
    // axe-core's internal `requestIdleCallback` / `setTimeout` scheduler
    // never got a yield slot.
    //
    // Aborting only background traffic leaves the page in a static state
    // post-goto. The DOM tree axe scans is unchanged (page rendered enough to
    // be auditable post-goto + waitForTimeout settle), but background loops
    // stop competing for the event loop while lazy assets still finish.
    // axe.run completes in ~1-2s.
    //
    // This is the SAME failure class W113-W116 + W144-W146 wrestled with
    // under various injection mechanisms (CDN script-tag, eval inject,
    // AxeBuilder.analyze). Injection wasn't the issue — event-loop
    // starvation was. W147 SW1 closes the real root cause.
    await blockBackgroundNetwork(page)
    // Wave 146 polish-v2 — removed `page.waitForLoadState("networkidle")` which
    // hung the test under W146 SW1 CSP-block elimination. The 1500ms settle
    // covers Framer Motion entrance animations + React Query observers under
    // `emulateMedia({ reducedMotion: "reduce" })` + Playwright's MotionConfig
    // `reducedMotion="user"` snap behavior. Pattern verified in
    // `frontend/scripts/authenticated-visual-audit.mjs` baseline.
    await page.waitForTimeout(1500)

    // Wave 147 SW1 — `window.axe` is pre-injected by `test.beforeEach` above
    // (browser-native init-script — no IPC marshalling of source per-test).
    // Promise.race wraps the `axe.run()` call itself as defense-in-depth: if
    // axe.run hangs on heavy DOM mid-scan (different failure mode from
    // W146-era inject hang), the failure remains deterministic instead of
    // 90s test timeout.
    //
    // W147 SW1 iter 1: 60_000 ms ceiling (was 30_000 ms initial) after
    // local empirical: 30s capped axe.run pre-emptively on chromium with
    // full WCAG 2.0/2.1/2.2 AA tag set against /login DOM (ParticleAuthBg
    // even under VITE_E2E_MODE reductions + Framer Motion glass effects =
    // ~80 rules × O(elements) including expensive color-contrast walk).
    // 60_000 ms gives axe.run the headroom it needs while staying under
    // Playwright's 90_000 ms test timeout so failures still surface as
    // `axe-run-timeout-60s` (diagnostic specificity) rather than the
    // ambiguous test timeout.
    // W147 SW1 iter 2 — narrow to `target-size` rule only.
    //
    // This spec exists for ONE reason (per the W114 polish-v2 + W115 SW3
    // origin docstring above): catch WCAG 2.5.8 `target-size` regressions
    // on /login. We don't need full WCAG 2.0/2.1/2.2 AA coverage here —
    // `a11y-public.spec.ts` covers that broader scope; this spec is a
    // targeted regression guard.
    //
    // iter 1 attempt (60s ceiling on full tag set) hung deterministically
    // on chromium because axe-core's `color-contrast` rule walks every
    // text element computing contrast ratios (O(n) `getComputedStyle`
    // calls). On heavy /login DOM with Framer Motion + glass + canvas
    // backdrop, full WCAG 2.x tag set can run 60-120s on chromium headless
    // (chromium throttles renderer in headless). Narrowing to a single
    // rule eliminates the bottleneck.
    //
    // `resultTypes: ["violations"]` further reduces axe-core's output size
    // (skips passes/incomplete/inapplicable arrays) — saves a few hundred
    // ms on result serialization + Playwright IPC marshalling.
    const AXE_RUN_TIMEOUT_MS = 60_000
    const results = await Promise.race<AxeResult>([
      page.evaluate<AxeResult>(async () => {
        type AxeWindow = {
          axe: {
            run: (
              context: Document,
              options: {
                runOnly: { type: string; values: string[] }
                resultTypes?: string[]
              }
            ) => Promise<AxeResult>
          }
        }
        const { axe } = window as unknown as AxeWindow
        return axe.run(document, {
          runOnly: { type: "rule", values: ["target-size"] },
          resultTypes: ["violations"],
        })
      }),
      new Promise<never>((_, reject) =>
        setTimeout(
          () => reject(new Error(`axe-run-timeout-${AXE_RUN_TIMEOUT_MS / 1000}s`)),
          AXE_RUN_TIMEOUT_MS
        )
      ),
    ])

    const targetSize = results.violations.filter((v) => v.id === "target-size")
    // `toEqual([])` surfaces the node[] array in the test failure message for
    // fast triage of which specific link regressed.
    expect(targetSize, JSON.stringify(targetSize, null, 2)).toEqual([])
  })
})
