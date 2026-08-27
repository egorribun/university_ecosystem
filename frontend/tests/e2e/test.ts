import { mkdir, writeFile } from "node:fs/promises"
import { dirname } from "node:path"
import { expect, test as base, devices, type Page } from "@playwright/test"

// Playwright exposes JavaScript coverage only for Chromium. Keep collection
// opt-in so normal E2E and the Firefox/WebKit stabilization matrix have no
// coverage overhead or behavioral dependency on this diagnostic path.
const collectCoverage = process.env.E2E_COVERAGE === "true"

export const test = base.extend({
  page: async ({ page, browserName }, runFixture, testInfo) => {
    const shouldCollect = collectCoverage && browserName === "chromium"
    if (!shouldCollect) {
      await runFixture(page)
      return
    }

    await page.coverage.startJSCoverage({
      resetOnNavigation: false,
      reportAnonymousScripts: false,
    })
    try {
      await runFixture(page)
    } finally {
      const coverage = await page.coverage.stopJSCoverage()
      const outputPath = testInfo.outputPath("playwright-coverage.json")
      await mkdir(dirname(outputPath), { recursive: true })
      await writeFile(outputPath, JSON.stringify(coverage), "utf8")
    }
  },
})

/**
 * Quiesce background activity without aborting application code or assets.
 *
 * Accessibility/visual audits need a stable DOM, but aborting every request
 * also cancels lazy JavaScript chunks that may still be loading on a busy CI
 * runner.  Keep document, script, style, image, and font requests alive; only
 * stop the unbounded API/realtime classes that can starve axe's scheduler.
 */
export async function blockBackgroundNetwork(page: Page): Promise<void> {
  const backgroundTypes = new Set(["fetch", "xhr", "websocket", "eventsource"])
  await page.route("**/*", (route) => {
    if (backgroundTypes.has(route.request().resourceType())) {
      return route.abort()
    }
    return route.continue()
  })
}

export { devices, expect }
export type { BrowserContext, Page, Route } from "@playwright/test"
