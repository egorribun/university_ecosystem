import { expect, test } from "@playwright/test"
import { useMockApi } from "./utils/mockApi"

test.describe("Visual regression tests", () => {
  test("dashboard page matches snapshot", async ({ page }) => {
    const { login } = await useMockApi(page)
    await login(page)

    // Wait for animations to settle
    await page.waitForTimeout(1000)

    await expect(page).toHaveScreenshot("dashboard.png", {
      maxDiffPixelRatio: 0.1,
      animations: "disabled",
    })
  })

  test("news page matches snapshot", async ({ page }) => {
    const { login } = await useMockApi(page)
    await login(page)

    await page.goto("/news")
    await page.waitForURL(/\/news$/)
    await page.waitForLoadState("networkidle")
    await page.waitForTimeout(1000)

    await expect(page).toHaveScreenshot("news-list.png", {
      maxDiffPixelRatio: 0.1,
      animations: "disabled",
    })
  })

  test("schedule page matches snapshot", async ({ page }) => {
    const { login } = await useMockApi(page)
    await login(page)

    await page.goto("/schedule")
    await page.waitForURL(/\/schedule$/)
    await page.waitForLoadState("networkidle")
    await page.waitForTimeout(1000)

    await expect(page).toHaveScreenshot("schedule.png", {
      maxDiffPixelRatio: 0.1,
      animations: "disabled",
    })
  })
})
