import { expect, test } from "@playwright/test"
import { useMockApi } from "./utils/mockApi"

test.describe("Visual regression tests", () => {
  // Restrict to chromium to prevent minor font/layout rendering variations between browser engines
  test.skip(({ browserName }) => browserName !== "chromium", "Visual tests are chromium-only")
  test.skip(
    process.platform !== "win32",
    "Visual baselines are currently checked in for Windows only"
  )

  test.beforeEach(async ({ page }) => {
    // Freeze time to Saturday, June 27, 2026, matching the baseline creation date
    await page.clock.install({ time: new Date("2026-06-27T10:00:00Z") })
  })

  test("dashboard page matches snapshot", async ({ page }) => {
    const { login } = await useMockApi(page)
    await login(page)

    // Wait for page load and animations to settle
    await page.waitForLoadState("networkidle")
    await page.waitForTimeout(1500)

    await expect(page).toHaveScreenshot("dashboard.png", {
      maxDiffPixelRatio: 0.005, // 0.5% threshold
      animations: "disabled",
    })
  })

  test("news page matches snapshot", async ({ page }) => {
    const { login } = await useMockApi(page)
    await login(page)

    await page.goto("/news")
    await page.waitForURL(/\/news$/)
    await page.waitForLoadState("networkidle")
    await page.waitForTimeout(1500)

    await expect(page).toHaveScreenshot("news-list.png", {
      maxDiffPixelRatio: 0.005, // 0.5% threshold
      animations: "disabled",
    })
  })

  test("schedule page matches snapshot", async ({ page }) => {
    const { login } = await useMockApi(page)
    await login(page)

    await page.goto("/schedule")
    await page.waitForURL(/\/schedule$/)
    await page.waitForLoadState("networkidle")
    await page.waitForTimeout(1500)

    await expect(page).toHaveScreenshot("schedule.png", {
      maxDiffPixelRatio: 0.005, // 0.5% threshold
      animations: "disabled",
    })
  })
})
