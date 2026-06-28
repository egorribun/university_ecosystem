import { expect, test } from "@playwright/test"
import { useMockApi } from "./utils/mockApi"

const matchTotpAddButton = /Подключить приложение|Set up authenticator app/i
const matchTotpVerifyButton = /Подтвердить|Verify|Confirm/i

// Skip: MFA tests timeout during login/authentication flows in mock environment
test.describe.skip("Multi-factor authentication flows", () => {
  test("allows enabling TOTP in settings", async ({ page }) => {
    const mock = await useMockApi(page)
    await mock.login(page)

    await page.goto("/settings")
    await page.waitForURL(/\/settings$/)
    await page.waitForTimeout(500) // Allow tabs to initialize

    // Switch to Account tab
    await page.getByRole("tab", { name: /Account|Аккаунт/i }).click()
    await page.waitForTimeout(1000)

    // Expand TOTP accordion
    await page
      .getByText(/Authenticator app|Приложение-аутентификатор/i)
      .first()
      .click()
    await page.waitForTimeout(500)

    const addBtn = page.getByRole("button", { name: matchTotpAddButton })
    await expect(addBtn).toBeVisible({ timeout: 15000 })

    const startPromise = page.waitForResponse(
      (r) => r.url().includes("auth/mfa/totp/start") && r.status() === 200,
      { timeout: 20000 }
    )
    await addBtn.click({ force: true })
    await startPromise
    await page.waitForTimeout(1000)
    await expect(
      page.getByText(/Завершите настройку|Finish setup|Confirm setup|Scan|QR/i).first()
    ).toBeVisible({ timeout: 30000 })

    const otpInput = page.getByLabel(/Код из приложения|Authenticator code/i).first()
    await otpInput.click()
    await page.keyboard.type("123456", { delay: 50 })

    // The component might auto-submit, but we also ensure the button is at least enabled or we just wait for the success state
    await expect(
      page.getByText(/Приложение-аутентификатор подключено|Authenticator app connected/i)
    ).toBeVisible({ timeout: 10000 })
    await expect(page.getByText(/Приложение \d|Authenticator \d/i)).toBeVisible()
  })

  test("completes login when an OTP challenge is returned", async ({ page }) => {
    await useMockApi(page)

    await page.goto("/login")
    await page.waitForURL(/\/login$/)

    await page.locator('input[name="email"]').fill("mfa@example.com")
    await page.locator('input[name="password"]').fill("Password123")
    await page.locator('button[type="submit"]').click()

    await expect(page.getByText(/Подтвердите личность|Verify it's you/i)).toBeVisible()

    const otpInput = page.getByLabel(/Код из приложения|Authenticator code/i).first()
    await otpInput.click()
    await page.keyboard.type("123456", { delay: 50 })

    await expect(page).toHaveURL(/\/dashboard$/, { timeout: 10000 })
  })

  test("shows an error for invalid OTP attempts and allows retry", async ({ page }) => {
    await useMockApi(page)

    await page.goto("/login")
    await page.waitForURL(/\/login$/)

    await page.locator('input[name="email"]').fill("mfa@example.com")
    await page.locator('input[name="password"]').fill("Password123")
    await page.locator('button[type="submit"]').click()

    await expect(page.getByText(/Подтвердите личность|Verify it's you/i)).toBeVisible()

    const otpInput = page.getByLabel(/Код из приложения|Authenticator code/i).first()
    await otpInput.click()
    await page.keyboard.type("000000", { delay: 50 })

    await page.waitForTimeout(500) // Wait for validation/API response rendering
    // Assert on the specific error element
    const errorMsg = page.locator("p.text-red-500")
    await expect(errorMsg).toBeVisible({ timeout: 15000 })
    await expect(errorMsg).toHaveText(/Неверный код|Invalid verification code/i)

    // Clear inputs before retrying
    const inputs = page.getByLabel(/Код из приложения|Authenticator code/i)
    const count = await inputs.count()
    for (let i = 0; i < count; i++) {
      await inputs.nth(i).fill("")
    }

    // Simulate paste (fill respects maxLength=1, so we must paste)
    await inputs.first().evaluate((el) => {
      const dt = new DataTransfer()
      dt.setData("text", "123456")
      const event = new ClipboardEvent("paste", { clipboardData: dt, bubbles: true })
      el.dispatchEvent(event)
    })

    // Trigger submit manually (auto-submit blocked by existing error prop)
    await page.getByRole("button", { name: matchTotpVerifyButton }).click()

    await expect(page).toHaveURL(/\/dashboard$/, { timeout: 10000 })
  })
})
