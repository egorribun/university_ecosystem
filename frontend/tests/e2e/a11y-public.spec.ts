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
    }) => {
      await page.emulateMedia({ colorScheme: theme.scheme })
      await page.goto(route.path, { waitUntil: "domcontentloaded" })
      // Give the SPA shell a beat to mount + i18n to apply.
      await page.waitForLoadState("networkidle").catch(() => {})

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
