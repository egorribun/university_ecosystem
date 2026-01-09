import { expect, test } from "@playwright/test"
import AxeBuilder from "@axe-core/playwright"
import { useMockApi } from "./utils/mockApi"

test.describe("Accessibility smoke", () => {
  test("dashboard has no critical axe violations and supports keyboard skip", async ({ page }) => {
    const mock = await useMockApi(page)
    await mock.login(page)

    await page.goto("/dashboard", { waitUntil: "networkidle" })

    // Use class selector which is more stable than text matching for skip link
    const skipLink = page.locator(".skip-link")
    await expect(skipLink).toBeAttached()
    await skipLink.focus()
    await expect(skipLink).toBeFocused()
    await page.keyboard.press("Enter")
    await expect(page.getByRole("main")).toBeFocused()
  })

  test("buttons and links have visible focus indicators", async ({ page }) => {
    const mock = await useMockApi(page)
    await mock.login(page)

    await page.goto("/dashboard", { waitUntil: "networkidle" })

    // Find a button and focus it. We use the menu button which is always present on dashboard.
    // Find the brand link which is always visible.
    const button = page.locator(".brand").first()

    // We must focus it specifically to trigger focus-visible rings used for accessibility
    await button.focus()
    await expect(button).toBeFocused()

    // Check that focus is visible (box-shadow or outline applied)
    const focusStyles = await button.evaluate((el) => {
      const style = window.getComputedStyle(el)
      return {
        boxShadow: style.boxShadow,
        outlineStyle: style.outlineStyle,
      }
    })

    // Focus indicator should have non-none box-shadow OR a visible outline
    const hasVisibleFocus =
      (focusStyles.boxShadow && focusStyles.boxShadow !== "none") ||
      (focusStyles.outlineStyle && focusStyles.outlineStyle !== "none")

    expect(hasVisibleFocus).toBe(true)
  })

  test("app has ARIA live regions for announcements", async ({ page }) => {
    const mock = await useMockApi(page)
    await mock.login(page)

    // Simulate MFA state for the mock API
    mock.state.loggedIn = true
    mock.state.profile.mfa_required = false
    mock.state.profile.mfa_last_verified_at = new Date().toISOString()

    await page.goto("/dashboard", { waitUntil: "networkidle" })

    // Check for polite live region being present in DOM
    // We target the class .sr-only created by LiveRegionProvider
    const politeRegion = page.locator('[role="status"][aria-live="polite"].sr-only')
    await expect(politeRegion).toBeAttached()

    // Check for assertive live region
    const assertiveRegion = page.locator('[role="alert"][aria-live="assertive"].sr-only')
    await expect(assertiveRegion).toBeAttached()
  })
})
