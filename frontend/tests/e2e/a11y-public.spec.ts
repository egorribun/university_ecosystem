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
 * Authenticated 6-page sweep (dashboard/news/schedule/events/activity/map)
 * lands in SW6 alongside the per-page e2e specs that need a working login.
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
      // WebKit renderer crashes during axe-core .analyze() — heavy DOM (Particle canvas,
      // Framer Motion, glass shadows) + large axe ruleset exhaust the renderer process.
      // Desktop WebKit crashes only on /login; mobile-webkit (lower memory envelope) crashes
      // on both routes. Wave 114 followup: narrow axe scope via .include() or upgrade
      // @axe-core/playwright (A11Y-113-04). Using project name (not browserName) because
      // mobile-webkit and webkit share the same browser binary.
      const project = testInfo.project.name
      test.skip(
        (project === "webkit" && route.path === "/login") || project === "mobile-webkit",
        "axe-core .analyze() crashes WebKit renderer — Wave 114 followup",
      )
      await page.emulateMedia({ colorScheme: theme.scheme, reducedMotion: "reduce" })
      await page.goto(route.path, { waitUntil: "domcontentloaded" })
      // Give the SPA shell a beat to mount + i18n to apply.
      await page.waitForLoadState("networkidle").catch(() => {})
      // Framer Motion FadeIn animations take up to ~750ms (0.45s duration + 0.3s max delay).
      // Wait for the resting state so axe-core samples final colors, not mid-animation opacity
      // blends. Wave 114 followup: wire MotionConfig reducedMotion="user" at AppProviders so
      // emulateMedia({ reducedMotion }) alone is enough (A11Y-113-03).
      await page.waitForTimeout(900)

      const results = await new AxeBuilder({ page })
        // Stay focused on user-impacting violations; informational tags pass-through
        // is checked by Lighthouse's separate accessibility category.
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
        .analyze()

      const blocking = results.violations.filter(
        (v) => v.impact === "critical" || v.impact === "serious",
      )
      // Surface the violation list in the test failure for fast triage.
      expect(blocking, JSON.stringify(blocking, null, 2)).toEqual([])
    })
  }
}
