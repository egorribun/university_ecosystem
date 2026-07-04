import { expect, test } from "@playwright/test"
import { useMockApi } from "./utils/mockApi"

test.describe("MFA Lost Recovery Flows", () => {
  test("completes login flow using backup recovery codes", async ({ page }) => {
    await useMockApi(page)

    await page.goto("/login")
    await page.waitForURL(/\/login$/)

    // Trigger MFA challenge by entering mfa@example.com
    await page.locator('input[name="email"]').fill("mfa@example.com")
    await page.locator('input[name="password"]').fill("Password123")
    await page.locator('button[type="submit"]').click()

    // Assert that the MFA verification screen is shown
    await expect(page.getByText(/Verify it's you|Подтвердите личность/i).first()).toBeVisible()

    // Click on Use backup recovery code button
    const toggleBtn = page.locator("#use-recovery-code-toggle")
    await expect(toggleBtn).toBeVisible()
    await toggleBtn.click()

    // Assert recovery input UI is now displayed
    await expect(page.getByLabel("MFA recovery code")).toBeVisible()

    // Try an invalid recovery code
    await page.getByLabel("MFA recovery code").fill("INVALID-RECOVERY")
    await page.getByRole("button", { name: /Подтвердить код|Verify/i }).click()

    // Assert warning text appears
    await expect(page.getByText("Неверный код")).toBeVisible({ timeout: 10000 })

    // Use a valid recovery code
    await page.getByLabel("MFA recovery code").fill("VALID-RECOVERY")
    await page.getByRole("button", { name: /Подтвердить код|Verify/i }).click()

    // Verify successful login redirect to dashboard
    await expect(page).toHaveURL(/\/dashboard$/, { timeout: 15000 })
  })
})
