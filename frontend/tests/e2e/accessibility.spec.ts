import { expect, test } from "@playwright/test"
import AxeBuilder from "@axe-core/playwright"
import { useMockApi } from "./utils/mockApi"

test.describe("Accessibility smoke", () => {
  test("dashboard has no critical axe violations and supports keyboard skip", async ({ page }) => {
    const mock = await useMockApi(page)
    await mock.login(page)

    await page.goto("/dashboard", { waitUntil: "networkidle" })
    const skipLink = page.getByRole("link", { name: /content/i })
    await skipLink.focus()
    await expect(skipLink).toBeFocused()
    await page.keyboard.press("Enter")
    await expect(page.getByRole("main")).toBeFocused()

    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()

    expect(results.violations).toEqual([])
  })

  test("buttons and links have visible focus indicators", async ({ page }) => {
    const mock = await useMockApi(page)
    await mock.login(page)

    await page.goto("/dashboard", { waitUntil: "networkidle" })

    // Find a button and focus it
    const button = page.getByRole("button").first()
    await button.focus()
    await expect(button).toBeFocused()

    // Check that focus is visible (box-shadow applied)
    const boxShadow = await button.evaluate((el) => {
      return window.getComputedStyle(el).boxShadow
    })

    // Focus indicator should have non-none box-shadow
    expect(boxShadow).not.toBe("none")
  })

  test("app has ARIA live regions for announcements", async ({ page }) => {
    const mock = await useMockApi(page)
    await mock.login(page)

    await page.goto("/dashboard", { waitUntil: "networkidle" })

    // Check for polite live region
    const politeRegion = page.locator('[role="status"][aria-live="polite"]')
    await expect(politeRegion).toBeAttached()

    // Check for assertive live region
    const assertiveRegion = page.locator('[role="alert"][aria-live="assertive"]')
    await expect(assertiveRegion).toBeAttached()
  })
})
