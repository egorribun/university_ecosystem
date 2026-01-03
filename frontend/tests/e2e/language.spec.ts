import { expect, test } from "@playwright/test"
import { useMockApi } from "./utils/mockApi"

const storageKey = "ue:language"

test.describe("Language switching and RTL support", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript((key) => {
      window.localStorage.setItem(key, "ru")
    }, storageKey)
  })

  test("switches locales, direction and translations", async ({ page }) => {
    const mock = await useMockApi(page)
    await mock.login(page)

    await page.goto("/settings", { waitUntil: "networkidle" })
    await expect(page.getByRole("heading", { name: "Настройки" })).toBeVisible()
    await expect(page.locator("html")).toHaveAttribute("dir", "ltr")

    await page.getByRole("radio", { name: "English" }).click()
    await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible()
    await expect(page.locator("html")).toHaveAttribute("lang", "en")

    await page.getByRole("radio", { name: "العربية" }).click()
    await expect(page.getByRole("heading", { name: "الإعدادات" })).toBeVisible()
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl")

    const skipLink = page.getByRole("link", { name: "تجاوز إلى المحتوى" })
    await skipLink.focus()
    await expect(skipLink).toBeFocused()
    await page.keyboard.press("Enter")
    await expect(page.getByRole("main")).toBeFocused()
  })
})
