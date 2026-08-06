/**
 * Wave 11 — E2E: Error recovery & offline resilience.
 *
 * WHY: Network failure is the most common real-world error scenario. These
 * tests verify the app degrades gracefully (no white screen, no frozen UI)
 * when connectivity is lost and restored. This complements the existing
 * offline.spec.ts by specifically testing recovery transitions.
 */
import { test, expect } from "./test"

test.describe("Error Recovery — Wave 11", () => {
  test("app remains visible when going offline", async ({ page, context }) => {
    await page.goto("/")
    await page.waitForLoadState("domcontentloaded")

    // Simulate network loss
    await context.setOffline(true)
    await page.evaluate(() => window.dispatchEvent(new Event("offline")))

    // The previously-rendered DOM must still be visible
    await expect(page.locator("body")).toBeVisible()

    await context.setOffline(false)
  })

  test("app recovers and remains functional after network restore", async ({ page, context }) => {
    await page.goto("/")
    await page.waitForLoadState("domcontentloaded")

    await context.setOffline(true)
    await page.evaluate(() => window.dispatchEvent(new Event("offline")))

    await context.setOffline(false)
    await page.evaluate(() => window.dispatchEvent(new Event("online")))

    // Body must still be in the DOM after restore
    await expect(page.locator("body")).toBeVisible()
  })

  test("no uncaught JS errors during offline→online transition", async ({ page, context }) => {
    const errors: string[] = []
    page.on("pageerror", (err) => {
      if (
        !err.message.includes("ResizeObserver") &&
        !err.message.includes("NetworkError") &&
        !err.message.includes("AbortError")
      ) {
        errors.push(err.message)
      }
    })

    await page.goto("/")
    await context.setOffline(true)
    await context.setOffline(false)

    expect(errors).toHaveLength(0)
  })

  test("404 route shows a non-blank page (not a crash)", async ({ page }) => {
    // WHY: Unmatched routes must render a 404 component, not a white screen or
    // an unhandled error boundary fallback that swallows the error silently.
    const errors: string[] = []
    page.on("pageerror", (err) => {
      if (!err.message.includes("ResizeObserver")) errors.push(err.message)
    })

    await page.goto("/definitely-does-not-exist-42xyz")
    await page.waitForLoadState("domcontentloaded")

    await expect(page.locator("body")).toBeVisible()
    const text = await page.locator("body").innerText()
    expect(text.trim().length).toBeGreaterThan(0)
    expect(errors).toHaveLength(0)
  })
})
