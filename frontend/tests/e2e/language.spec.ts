import { expect, test } from "./test"
import { useMockApi } from "./utils/mockApi"
import { gotoWithTransientRetry } from "./utils/navigation"

const storageKey = "ue:language"

test.describe("Language switching and document metadata", () => {
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

    await page.getByRole("button", { name: /Язык интерфейса/ }).click()
    const english = page.getByRole("radio", { name: "Английский" })
    await english.focus()
    await page.keyboard.press("Space")
    await expect(english).toBeChecked()
    await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible()
    await expect(page.locator("html")).toHaveAttribute("lang", "en")
    await expect(page.locator("html")).toHaveAttribute("dir", "ltr")

    const russian = page.getByRole("radio", { name: "Russian" })
    await russian.focus()
    await page.keyboard.press("Space")
    await expect(russian).toBeChecked()
    await expect(page.getByRole("heading", { name: "Настройки" })).toBeVisible()
    await expect(page.locator("html")).toHaveAttribute("lang", "ru")
    await expect(page.locator("html")).toHaveAttribute("dir", "ltr")

    const skipLink = page.locator(".skip-link")
    await skipLink.focus()
    await expect(skipLink).toBeFocused()
    await page.keyboard.press("Enter")
    await expect(page.getByRole("main")).toBeFocused()
  })
})
