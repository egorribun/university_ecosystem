import { expect, test } from "@playwright/test"
import { useMockApi } from "./utils/mockApi"

const matchTotpAddButton = /Подключить приложение|Set up authenticator app/i
const matchTotpVerifyButton = /Подтвердить|Verify|Confirm/i

test.describe("Multi-factor authentication flows", () => {
  test("allows enabling TOTP in settings", async ({ page }) => {
    const mock = await useMockApi(page)
    await mock.login(page)

    await page.goto("/settings")
    await page.waitForURL(/\/settings$/)

    await page.getByRole("button", { name: matchTotpAddButton }).click()
    await expect(page.getByText(/Завершите настройку|Finish setup/i)).toBeVisible()

    const otpInput = page.getByLabel(/Код из приложения|Authenticator code/i).first()
    await otpInput.click()
    await page.keyboard.type("123456", { delay: 50 })

    const verifyBtn = page.getByRole("button", { name: matchTotpVerifyButton })
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

    await page.locator('input[name="username"]').fill("mfa@example.com")
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

    await page.locator('input[name="username"]').fill("mfa@example.com")
    await page.locator('input[name="password"]').fill("Password123")
    await page.locator('button[type="submit"]').click()

    await expect(page.getByText(/Подтвердите личность|Verify it's you/i)).toBeVisible()

    const otpInput = page.getByLabel(/Код из приложения|Authenticator code/i).first()
    await otpInput.click()
    await page.keyboard.type("000000", { delay: 50 })

    await expect(page.getByText(/Неверный код|Invalid verification code/i)).toBeVisible()

    await otpInput.click()
    await page.keyboard.type("123456", { delay: 50 })

    await expect(page).toHaveURL(/\/dashboard$/, { timeout: 10000 })
  })
})
