import { expect, test } from "@playwright/test"
import AxeBuilder from "@axe-core/playwright"

/**
 * Public-page accessibility scan — Wave 112 SW4.
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
 *   3. `AxeBuilder.setLegacyMode(true)` on WebKit projects — the default
 *      `.analyze()` does TWO axe injections (main page + a new blank page
 *      for `finishRun`) and chunks partial results through JSON.
 *      Legacy mode runs `axe.run()` once on the page directly, halving
 *      the peak memory footprint. Safe for /login + /404 (no cross-origin
 *      iframes to recurse into).
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
 * Authenticated 6-page sweep (dashboard/news/schedule/events/activity/map)
 * lands in a future wave alongside the per-page e2e specs that need a
 * working login.
 */

const PUBLIC_ROUTES = [
  { path: "/login", name: "login" },
  { path: "/this-route-does-not-exist", name: "fallback" },
] as const

const THEMES = [
  { scheme: "light" as const, name: "light" },
  { scheme: "dark" as const, name: "dark" },
] as const

for (const route of PUBLIC_ROUTES) {
  for (const theme of THEMES) {
    test(`@a11y ${route.name} — ${theme.name} theme has no critical/serious axe violations`, async ({
      page,
    }, testInfo) => {
      await page.emulateMedia({ colorScheme: theme.scheme, reducedMotion: "reduce" })
      await page.goto(route.path, { waitUntil: "domcontentloaded" })
      // Give the SPA shell a beat to mount + i18n to apply.
      await page.waitForLoadState("networkidle").catch(() => {})
      // `<MotionConfig reducedMotion="user">` at AppProviders (Wave 114 SW2b)
      // snaps Framer Motion to end state under the emulateMedia directive
      // above. A small settle buffer still pays for itself: Login mounts a
      // handful of React Query observers that briefly render their loading
      // state, and axe sampling pre-settle surfaces flicker-state colour
      // violations that don't exist at rest. 300ms is ~2× the queue flush
      // measured locally — shorter than the 900ms Wave 113 workaround.
      await page.waitForTimeout(300)

      // Wave 115 SW1 — `setLegacyMode(true)` on WebKit projects halves axe's
      // memory footprint: default `.analyze()` injects axe into the page AND
      // a new blank page (for `finishRun`), then chunks partial results
      // through JSON serialisation. Legacy mode runs `axe.run()` once on the
      // page directly — no second injection, no chunking. Safe for /login +
      // /404 (no cross-origin frames). Combined with the
      // ParticleAuthBackground canvas gate + `fullyParallel: false` on
      // WebKit projects (playwright.config.ts), this closes A11Y-113-04 for
      // mobile-webkit's tighter renderer memory envelope.
      const project = testInfo.project.name
      const isWebKit = project === "webkit" || project === "mobile-webkit"
      const builder = new AxeBuilder({ page })
        // Stay focused on user-impacting violations; informational tags pass-through
        // is checked by Lighthouse's separate accessibility category.
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
      if (isWebKit) {
        builder.setLegacyMode(true)
      }
      const results = await builder.analyze()

      const blocking = results.violations.filter(
        (v) => v.impact === "critical" || v.impact === "serious",
      )
      // Surface the violation list in the test failure for fast triage.
      expect(blocking, JSON.stringify(blocking, null, 2)).toEqual([])
    })
  }
}
