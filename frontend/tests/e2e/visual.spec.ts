import { expect, test } from "@playwright/test"
import { useMockApi } from "./utils/mockApi"

test.describe("Visual regression tests", () => {
  // Restrict to chromium to prevent minor font/layout rendering variations between browser engines
  test.skip(({ browserName }) => browserName !== "chromium", "Visual tests are chromium-only")

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
