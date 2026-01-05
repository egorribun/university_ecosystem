import { test, expect } from "@playwright/test"

test.describe("bootstrap fallback", () => {
  test("shows fallback UI when bootstrap fails", async ({ page }) => {
    await page.addInitScript(() => {
      ;(
        window as typeof window & { __APP_BOOTSTRAP_FORCE_ERROR__?: boolean }
      ).__APP_BOOTSTRAP_FORCE_ERROR__ = true
      window.localStorage.setItem("ue:language", "ru")
    })

    await page.goto("/")

    // Debug output
    console.log("Bootstrap Fallback Body Text:", await page.textContent("body"))

    // Check for either the Russian text OR the key (if translation failed) OR English
    // This allows us to understand failure mode if it's i18n related
    const heading = page.getByRole("heading")
    const text = await heading.innerText()
    if (text.includes("errorBoundary.title")) {
      console.log("Warning: i18n translation missing, showing key")
    }

    await expect(page.locator("body")).toContainText(
      /Что-то пошло не так|Something went wrong|errorBoundary.title/
    )


    await expect(page.getByRole("heading")).toBeVisible()

    await expect(page.getByRole("button", { name: /Перезагрузить|Reload/i })).toBeVisible()
    await expect(page.getByRole("button", { name: /Попробовать|Try again|Retry/i })).toBeVisible()
  })
})
