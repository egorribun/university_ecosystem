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
      // WebKit renderer crashes during axe-core .analyze() — heavy DOM
      // (ParticleAuthBackground canvas, Framer Motion, glass shadows) +
      // large axe ruleset exhaust the renderer process. Wave 114 SW2a
      // attempted three rescues — narrowing axe scope to meaningful
      // landmarks, disabling color-contrast + color-contrast-enhanced on
      // WebKit only, and upgrading @axe-core/playwright 4.10.0 → 4.11.2
      // — none of which unlocked the crashing cases (webkit /login × 2 +
      // all mobile-webkit × 4). The OOM fires before axe's scope filter
      // runs; root cause is DOM weight + full ruleset injection. Wave 115
      // SW2a-remainder: minimize the injected axe bundle via page.evaluate,
      // or conditionally render a reduced auth page when
      // `process.env.NODE_ENV === "test"`. Using project name (not
      // browserName) because mobile-webkit and webkit share the same
      // browser binary.
      const project = testInfo.project.name
      test.skip(
        (project === "webkit" && route.path === "/login") ||
          project === "mobile-webkit",
        "axe-core .analyze() crashes WebKit renderer — Wave 115 SW2a-remainder",
      )
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
