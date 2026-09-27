/**
 * Wave 11 — E2E: Profile / Settings page flows.
 *
 * WHY: Settings pages contain critical user-data flows (password change,
 * notification prefs, avatar upload). These smoke tests confirm the shell
 * renders without crashes before a user even authenticates, catching bundler
 * regressions that would otherwise only surface in production.
 */
import { test, expect } from "./test"

test.describe("Profile Settings — Wave 11", () => {
  test("settings route resolves to settings or login (no crash)", async ({ page }) => {
    const errors: string[] = []
    page.on("pageerror", (err) => {
      if (!err.message.includes("ResizeObserver")) errors.push(err.message)
    })

    await page.goto("/settings", { waitUntil: "domcontentloaded" })
    await expect(page).toHaveURL(/settings|profile|login|\/$/)
    expect(errors).toHaveLength(0)
  })

  test("anonymous settings navigation reaches a usable login and preserves its destination", async ({
    page,
  }) => {
    const destination = "/settings?tab=2"
    await page.goto(destination, { waitUntil: "domcontentloaded" })

    await expect(page).toHaveURL(
      (url) => url.pathname === "/login" && url.searchParams.get("redirect") === destination
    )
    const email = page.getByRole("textbox", { name: /^e-?mail$/i })
    const password = page.getByLabel(/^(пароль|password)$/i)
    await expect(email).toBeVisible()
    await expect(email).toBeEnabled()
    await expect(password).toBeVisible()
    await expect(password).toBeEnabled()
  })

  test("settings page body has rendered content", async ({ page }) => {
    await page.goto("/settings")
    await expect(page.locator("body")).toBeVisible()
    const text = await page.locator("body").innerText()
    expect(text.trim().length).toBeGreaterThan(0)
  })

  test("profile route resolves without uncaught errors", async ({ page }) => {
    const errors: string[] = []
    page.on("pageerror", (err) => {
      if (
        !err.message.includes("ResizeObserver") &&
        !err.message.includes("AbortError") &&
        !err.message.includes("NetworkError")
      ) {
        errors.push(err.message)
      }
    })
    await page.goto("/profile", { waitUntil: "domcontentloaded" })
    expect(errors).toHaveLength(0)
  })
})
