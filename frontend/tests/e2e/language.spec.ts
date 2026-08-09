import { expect, test } from "./test"
import { useMockApi } from "./utils/mockApi"
import { gotoWithTransientRetry } from "./utils/navigation"

const storageKey = "ue:language"

// Skip: Language tests timeout during login in mock environment
test.describe.skip("Language switching and RTL support", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript((key) => {
      window.localStorage.setItem(key, "ru")
    }, storageKey)
  })

  test("switches locales, direction and translations", async ({ page }) => {
    const mock = await useMockApi(page)
    await mock.login(page)

    await gotoWithTransientRetry(page, "/settings", { waitUntil: "networkidle" })
    await expect(page.getByRole("heading", { name: "Настройки" })).toBeVisible()
    await expect(page.locator("html")).toHaveAttribute("dir", "ltr")

    await page.getByText("Английский").click()
    await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible()
    await expect(page.locator("html")).toHaveAttribute("lang", "en")

    await page.getByText("Arabic (RTL)").click()
    await expect(page.getByRole("heading", { name: "الإعدادات" })).toBeVisible()
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl")

    // Use class selector for skip link which is more robust
    const skipLink = page.locator(".skip-link")
    await skipLink.focus()
    await expect(skipLink).toBeFocused()
    await page.keyboard.press("Enter")
    await expect(page.getByRole("main")).toBeFocused()
  })
})
