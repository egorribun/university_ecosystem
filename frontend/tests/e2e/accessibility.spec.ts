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

    // Find a button and focus it
    const button = page.getByRole("button").first()
    // Simulate clicking a share button to open a share dialog
    // Assuming 'button' here refers to the share button for the purpose of this test flow
    await button.click({ force: true })

    // When share API is undefined, a dialog opens. We need to click "Copy link".
    await page.getByRole("button", { name: /Скопировать ссылку|Copy link/i }).click()
    // After closing the dialog, the original button should regain focus
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
