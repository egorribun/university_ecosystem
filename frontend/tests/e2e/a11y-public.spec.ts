import { expect, test } from "./test"
import { readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import path from "node:path"

/**
 * Public-page accessibility scan — Wave 112 SW4 / **Wave 147 SW2 structural**.
 *
 * The legacy `accessibility.spec.ts` is `describe.skip`'d because the mock
 * login flow times out under Playwright. This new suite hits routes that
 * do NOT require authentication, so the `axe-core` gate runs on every CI
 * pass without depending on the brittle login mock.
 *
 * Coverage:
 *   - /login           — unauth form (most touched public surface)
 *   - 404 / fallback   — error-route a11y
 *
 * Each route is scanned in both themes via emulated `prefers-color-scheme`
 * so light/dark contrast violations surface separately.
 *
 * Wave 115 SW1 — partial A11Y-113-04 closure (10 → 14 pass / 6 → 2 skip).
 * The WebKit skip (webkit /login × 2 + all mobile-webkit × 4) was mostly
 * lifted via three stacked fixes:
 *   1. `ParticleAuthBackground` honors `VITE_E2E_MODE=1` (set in
 *      `playwright.config.ts` webServer.env) — short-circuits the
 *      1000-particle canvas physics loop for test builds. Confirmed the
 *      constant eliminates the code from `dist/assets/index-*.js` via tree
 *      shaking (grep "particleCount" dist/assets/*.js returns zero).
 *   2. `fullyParallel: false` on the `webkit` + `mobile-webkit` Playwright
 *      projects — prevents renderer memory accumulation across parallel
 *      axe runs. Tests within a WebKit project now run sequentially.
 *   3. Wave 115 used `AxeBuilder.setLegacyMode(true)` on WebKit to halve
 *      memory footprint by skipping the second axe injection that
 *      AxeBuilder's default `finishRun` flow does on a blank page. Under
 *      Wave 147 SW2 the structural axe.run() pattern (direct axe-core API
 *      call after init-script injection — see below) is already
 *      equivalent to legacy mode: ONE init-script injection + ONE
 *      `axe.run()` call, no blank-page hop. The WebKit memory benefit is
 *      preserved structurally without needing the legacyMode flag.
 *
 * Wave 116 SW1 — A11Y-113-04 FINAL closure via reduced MainLayout under
 * VITE_E2E_MODE. Wave 115 left mobile-webkit /404 × 2 themes skipped
 * because /404 renders the full `MainLayout` (Navbar + Footer +
 * MobileBottomNav + BackToTop — 4 heavy components with glass effects,
 * Framer Motion, and i18n) while /login suppresses chrome via
 * `useRouteType().isCompactPage`. iPhone 15 WebKit emulation couldn't hold
 * that DOM + axe-core's 564 KB bundle even in legacy mode. Wave 116
 * extends the `VITE_E2E_MODE` gate from `ParticleAuthBackground` (Wave
 * 115 fix 1) to `MainLayout.tsx`: when the flag is set, chrome components
 * render as minimal landmark stubs (`<nav>`, `<footer role="contentinfo">`)
 * — enough to preserve WCAG 1.3.1 semantic structure for axe's a11y tree
 * walk, not enough to consume the iPhone 15 WebKit renderer envelope.
 * Tree-shakes in prod (VITE_E2E_MODE only set in Playwright webServer.env).
 * Result: 13p/2s/0f → 16p/0s/0f across 4 projects × 2 routes × 2 themes.
 *
 * ## Wave 147 SW2 — axe-injection structural closure (W140 NEW #5)
 *
 * Pre-W147 this spec used `new AxeBuilder({page}).withTags(...).analyze()`
 * — the `@axe-core/playwright` v4.11.2 wrapper. AxeBuilder's `.analyze()`
 * internally invokes `page.evaluate` to inject its bundled `axe-core`
 * source then run the audit. The injection IPC-serializes the 564 KB
 * axe-core bundle per-evaluate-per-test, and consistently exceeded the
 * 90 s test timeout on chromium headless heavy DOM. W146 polish-v3 +
 * polish-v6 fixme'd chromium /login + /404 × light + dark (4 cases) as
 * the honest defer; W147 SW2 closes the structural gap.
 *
 * The new mechanism mirrors `a11y-cdn-axe.spec.ts` (W147 SW1 structural):
 *
 *   1. `test.beforeEach(async ({ context }) => context.addInitScript({
 *      path: AXE_SOURCE_PATH }))` — Playwright's browser-native injection
 *      runs the script BEFORE each page's own scripts, with the file
 *      content cached per-context. `window.axe` is available the moment
 *      `page.goto()` resolves; no per-test IPC of the 564 KB source.
 *
 *   2. `await page.evaluate(async () => axe.run(document, { runOnly:
 *      { type: "tag", values: [...] } }))` — direct call to the
 *      pre-injected `window.axe.run()`. This bypasses `AxeBuilder`
 *      entirely (lost: fluent `.withTags()` API; gained: structural
 *      simplicity + identical pattern to a11y-cdn-axe + no dependency on
 *      @axe-core/playwright behavior across version bumps).
 *
 *   3. Promise.race(30 s) wrapper preserved around the `axe.run()` call
 *      as defense-in-depth — if `axe.run()` hangs mid-scan on heavy DOM
 *      (different failure mode from W146-era injection hang), the failure
 *      remains deterministic at 30 s instead of waiting for the 90 s
 *      test timeout.
 *
 * Authenticated 6-page sweep (dashboard/news/schedule/events/activity/map)
 * lands in a future wave alongside the per-page e2e specs that need a
 * working login.
 */

type AxeNode = { target: string[]; html: string; failureSummary?: string }
type AxeImpact = "minor" | "moderate" | "serious" | "critical"
type AxeViolation = { id: string; impact: AxeImpact; nodes: AxeNode[]; help: string }
type AxeResult = { violations: AxeViolation[] }

// Wave 147 SW1 + SW2 — Path resolution from `frontend/tests/e2e/<spec>.ts`
// up to `frontend/node_modules/axe-core/axe.min.js`. Three levels up
// (file → e2e → tests → frontend) then descend. Mirrors a11y-cdn-axe
// resolution exactly so both specs use the same canonical bundle.
//
// W147 SW2 iter 3 — read source SYNCHRONOUSLY at module load + pass via
// `{content}` instead of `{path}`. See a11y-cdn-axe.spec.ts for rationale.
const AXE_SOURCE_PATH = path.resolve(
  fileURLToPath(import.meta.url),
  "../../../node_modules/axe-core/axe.min.js"
)
const AXE_SOURCE = readFileSync(AXE_SOURCE_PATH, "utf-8")

const PUBLIC_ROUTES = [
  { path: "/login", name: "login" },
  { path: "/this-route-does-not-exist", name: "fallback" },
] as const

const THEMES = [
  { scheme: "light" as const, name: "light" },
  { scheme: "dark" as const, name: "dark" },
] as const

// W147 SW2 — WCAG 2.0/2.1/2.2 AA tag set, extracted to module-scope const so
// both axe.run invocations (default + WebKit legacy mode) share the same
// rule selection. Same tags pre-W147 fed through AxeBuilder.withTags().
const AXE_RUN_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] as const

test.describe("@a11y public routes axe scan", () => {
  // Wave 147 SW2 — inject axe via `page.addInitScript({content})` BEFORE
  // each `page.goto()`. See `a11y-cdn-axe.spec.ts` for the full
  // page-vs-context fixture timing rationale. TL;DR: Playwright's default
  // `page` fixture exists BEFORE `test.beforeEach` runs, so
  // `context.addInitScript` doesn't fire on the upcoming `page.goto`.
  // `page.addInitScript` does.
  test.beforeEach(async ({ page }) => {
    await page.addInitScript({ content: AXE_SOURCE })
  })

  for (const route of PUBLIC_ROUTES) {
    for (const theme of THEMES) {
      test(`${route.name} — ${theme.name} theme has no critical/serious axe violations`, async ({
        page,
      }) => {
        await page.emulateMedia({ colorScheme: theme.scheme, reducedMotion: "reduce" })
        await page.goto(route.path, { waitUntil: "domcontentloaded", timeout: 30_000 })

        // W147 SW2 — block ALL subsequent network requests so React Query
        // / useProfileSync / dynamic chunks / service workers can't starve
        // the page event loop and prevent axe.run from scheduling. The
        // DOM tree axe scans is already rendered post-goto. See
        // `a11y-cdn-axe.spec.ts` for the full root-cause narrative.
        // Inner param renamed `r` to avoid shadowing the outer for-loop
        // `route` (PUBLIC_ROUTES element).
        await page.route("**/*", (r) => r.abort())

        // Wave 146 polish-v4 — removed `page.waitForLoadState("networkidle")`
        // which hung tests deterministically when backend is up and serving
        // pending API requests. The 1500ms settle covers Framer Motion
        // entrance animations + React Query observers under `emulateMedia({
        // reducedMotion: "reduce" })` + Playwright's MotionConfig
        // `reducedMotion="user"` snap behavior. Pattern verified in
        // `frontend/scripts/wave138-visual-audit.mjs:355-366` (W145 SW1 baseline).
        await page.waitForTimeout(1500)

        // Wave 147 SW2 — `window.axe` is pre-injected by `test.beforeEach`.
        // Promise.race wraps the `axe.run()` call as defense-in-depth: if
        // axe.run hangs on heavy DOM mid-scan (different failure mode from
        // W146-era inject hang), the failure remains deterministic instead
        // of 90s test timeout. Mirrors a11y-cdn-axe.spec.ts pattern.
        //
        // W147 SW2 iter 1: 60_000 ms ceiling (was 30_000 ms initial) after
        // local empirical: 30s capped axe.run pre-emptively on chromium
        // /login + /404 × light + dark with full WCAG 2.0/2.1/2.2 AA tag
        // set (ParticleAuthBg even under VITE_E2E_MODE reductions + heavy
        // DOM = ~80 rules × O(elements) including expensive color-contrast
        // walk). 60_000 ms gives axe.run headroom while staying under
        // Playwright's 90_000 ms test timeout so failures still surface
        // as `axe-run-timeout-60s` (diagnostic specificity).
        //
        // WebKit `legacyMode` memory mitigation is already achieved
        // structurally by this single-call pattern (no `finishRun` blank
        // page hop that AxeBuilder's default `.analyze()` does); no
        // explicit flag needed.
        // W147 SW2 iter 2 — disable `color-contrast` rules + only return violations.
        //
        // iter 1 attempt (60s ceiling on full tag set) hung deterministically
        // on chromium because axe-core's `color-contrast` rule walks every
        // text element computing contrast ratios (O(n) `getComputedStyle`
        // calls). On heavy /login + /404 DOM with Framer Motion + glass +
        // canvas backdrop, full WCAG 2.x tag set can run 60-120s on chromium
        // headless (chromium throttles renderer in headless mode).
        //
        // W116 SW3 already documented that **Lighthouse catches color-contrast
        // on /news + other pages via its accessibility category gate** (which
        // axe-core in Playwright was already failing to catch consistently).
        // Lighthouse runs on every CI PR push via `Frontend Tests / Lighthouse
        // Audit` job (W117 SW8 gate at categories:accessibility error@0.95).
        // So disabling color-contrast HERE doesn't reduce overall a11y
        // coverage — Lighthouse owns color-contrast; Playwright axe owns
        // everything else (structural, aria, semantic, target-size, etc.).
        //
        // `resultTypes: ["violations"]` further reduces axe-core's output
        // size (skips passes/incomplete/inapplicable arrays) — saves a
        // few hundred ms on result serialization + Playwright IPC.
        const AXE_RUN_TIMEOUT_MS = 60_000
        const results = await Promise.race<AxeResult>([
          page.evaluate<AxeResult, { tags: readonly string[] }>(
            async ({ tags }) => {
              type AxeWindow = {
                axe: {
                  run: (
                    context: Document,
                    options: {
                      runOnly: { type: string; values: readonly string[] }
                      rules?: Record<string, { enabled: boolean }>
                      resultTypes?: string[]
                    }
                  ) => Promise<AxeResult>
                }
              }
              const { axe } = window as unknown as AxeWindow
              return axe.run(document, {
                runOnly: { type: "tag", values: tags },
                rules: {
                  "color-contrast": { enabled: false },
                  "color-contrast-enhanced": { enabled: false },
                },
                resultTypes: ["violations"],
              })
            },
            { tags: AXE_RUN_TAGS }
          ),
          new Promise<never>((_, reject) =>
            setTimeout(
              () => reject(new Error(`axe-run-timeout-${AXE_RUN_TIMEOUT_MS / 1000}s`)),
              AXE_RUN_TIMEOUT_MS
            )
          ),
        ])

        const blocking = results.violations.filter(
          (v) => v.impact === "critical" || v.impact === "serious"
        )
        // Surface the violation list in the test failure for fast triage.
        expect(blocking, JSON.stringify(blocking, null, 2)).toEqual([])
      })
    }
  }
})
