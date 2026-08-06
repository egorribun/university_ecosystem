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

  test("settings page reaches network-idle without indefinite hanging", async ({ page }) => {
    // WHY: Prevents regressions where a bad fetch hangs the page forever.
    await page.goto("/settings")
    await page.waitForLoadState("networkidle", { timeout: 15_000 })
    // If we reach here, the page did not hang
    expect(true).toBe(true)
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
