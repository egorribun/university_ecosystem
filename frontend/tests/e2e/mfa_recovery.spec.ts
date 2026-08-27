import { expect, test } from "./test"
import { useMockApi } from "./utils/mockApi"

test.describe("MFA Lost Recovery Flows", () => {
  test("completes login flow using backup recovery codes", async ({ page }) => {
    await useMockApi(page, { authenticated: false })

    await page.goto("/login")
    await page.waitForURL(/\/login$/)
    await page.waitForLoadState("networkidle")

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

    // The label is localized by the auth namespace (RU is the deterministic
    // mock locale, while EN is used by browser smoke runs). Query the
    // accessible role/name contract instead of a single-language label.
    const recoveryCodeInput = page.getByRole("textbox", {
      name: /Recovery code|Резервный код/i,
    })
    const verifyRecoveryButton = page.getByRole("button", {
      name: /Verify(?: recovery code)?|Подтвердить(?: резервный)? код/i,
    })
    await expect(recoveryCodeInput).toBeVisible()

    // Try an invalid recovery code
    await recoveryCodeInput.fill("INVALID-RECOVERY")
    await verifyRecoveryButton.click()

    // Assert warning text appears
    await expect(page.getByText(/Неверный код|Invalid code/i)).toBeVisible({ timeout: 10000 })

    // Use a valid recovery code
    await recoveryCodeInput.fill("VALID-RECOVERY")
    await verifyRecoveryButton.click()

    // Verify successful login redirect to dashboard
    await expect(page).toHaveURL(/\/dashboard$/, { timeout: 15000 })
  })
})
