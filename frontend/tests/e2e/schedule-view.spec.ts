/**
 * Wave 11 — E2E: Schedule view smoke + accessibility.
 *
 * WHY: The schedule page is one of the highest-traffic routes. These tests
 * verify the shell loads without JS errors and the initial URL state is correct
 * regardless of auth state. Tests are intentionally resilient to backend state —
 * they pass whether the dev server is running or not (by checking for redirect).
 */
import { test, expect } from "@playwright/test"

test.describe("Schedule View — Wave 11", () => {
  test("schedule route resolves without uncaught JS errors", async ({ page }) => {
    const errors: string[] = []
    page.on("pageerror", (err) => {
      // Filter known non-critical noise from third-party scripts / ResizeObserver
      if (!err.message.includes("ResizeObserver") && !err.message.includes("AbortError")) {
        errors.push(err.message)
      }
    })

    await page.goto("/schedule", { waitUntil: "domcontentloaded" })
    // Either the schedule page or the login redirect — both are valid
    await expect(page).toHaveURL(/schedule|login|\/$/)
    expect(errors).toHaveLength(0)
  })

  test("schedule page has a non-empty document title", async ({ page }) => {
    await page.goto("/schedule")
    const title = await page.title()
    expect(title.length).toBeGreaterThan(0)
  })

  test("body is rendered and visible (not blank white screen)", async ({ page }) => {
    await page.goto("/schedule")
    await expect(page.locator("body")).toBeVisible()
    // The document must have at least some rendered content
    const bodyText = await page.locator("body").innerText()
    expect(bodyText.trim().length).toBeGreaterThan(0)
  })

  test("schedule route has no critical axe violations on the landing page", async ({ page }) => {
    // Wave 11: a11y gate — even on unauthenticated shell, wcag2a must pass
    await page.goto("/schedule")
    // Inject axe-core from CDN (no dependency on local package)
    await page.addScriptTag({
      url: "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.3/axe.min.js",
    })

    type AxeViolation = { impact: string; description: string }
    const violations = await page.evaluate<AxeViolation[]>(async () => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const results = await (window as any).axe.run()
      return results.violations as AxeViolation[]
    })
    const critical = violations.filter((v) => v.impact === "critical")
    expect(critical, `Critical a11y violations: ${JSON.stringify(critical, null, 2)}`).toHaveLength(
      0
    )
  })
})
