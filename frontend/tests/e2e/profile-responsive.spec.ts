import { expect, test } from "./test"
import { useMockApi } from "./utils/mockApi"

test("profile grid remains responsive at mobile, tablet, and desktop widths", async ({ page }) => {
  const { login } = await useMockApi(page)
  await login(page)

  await page.goto("/profile")
  await page.waitForURL(/\/profile$/)
  await page.waitForLoadState("networkidle")

  const profileGrid = page.locator(
    '[data-testid="profile-root"] > .container-fluid-responsive > div > .grid.grid-cols-1'
  )
  await expect(profileGrid).toHaveCount(1)
  const columns = profileGrid.locator(":scope > div")
  await expect(columns).toHaveCount(2)

  for (const { width, layout } of [
    { width: 390, layout: "stacked" },
    { width: 768, layout: "stacked" },
    { width: 1440, layout: "columns" },
  ] as const) {
    await page.setViewportSize({ width, height: 900 })
    await expect
      .poll(async () => {
        const left = await columns.nth(0).boundingBox()
        const right = await columns.nth(1).boundingBox()
        const viewportWidth = await page.evaluate(() => document.documentElement.clientWidth)
        if (!left || !right) return false

        const fitsViewport =
          left.x >= -1 &&
          right.x >= -1 &&
          left.x + left.width <= viewportWidth + 1 &&
          right.x + right.width <= viewportWidth + 1
        const matchesLayout =
          layout === "stacked"
            ? Math.abs(left.x - right.x) <= 1 && right.y >= left.y + left.height - 1
            : right.x >= left.x + left.width - 1 && Math.abs(left.y - right.y) <= 1

        return fitsViewport && matchesLayout
      })
      .toBe(true)
  }
})
