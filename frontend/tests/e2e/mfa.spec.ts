import { expect, test } from "@playwright/test"
import { useMockApi } from "./utils/mockApi"

const matchTotpAddButton = /Set up authenticator app|Настроить приложение/i
const matchTotpVerifyButton = /Verify|Подтвердить/i

test.describe("Multi-factor authentication flows", () => {
  test("allows enabling TOTP in settings", async ({ page }) => {
    const mock = await useMockApi(page)
    await mock.login(page)

    await page.goto("/settings")
    await page.waitForURL(/\/settings$/)

    await page.getByRole("button", { name: matchTotpAddButton }).click()
    await expect(page.getByText(/Finish setup|Завершите настройку/i)).toBeVisible()

    await page.getByLabel(/Authenticator code|Код из приложения/i).fill("123456")
    await page.getByRole("button", { name: matchTotpVerifyButton }).click()

    await expect(
      page.getByText(/Authenticator app connected|Приложение-аутентификатор подключено/i)
    ).toBeVisible()
    await expect(page.getByText(/Authenticator 1|Аутентификатор 1/i)).toBeVisible()
  })

  test("completes login when an OTP challenge is returned", async ({ page }) => {
    await useMockApi(page)

    await page.goto("/login")
    await page.waitForURL(/\/login$/)

    await page.locator('input[name="username"]').fill("mfa@example.com")
    await page.locator('input[name="password"]').fill("Password123")
    await page.locator('button[type="submit"]').click()

    await expect(page.getByText(/Verify it's you|Подтвердите свою личность/i)).toBeVisible()

    await page.getByLabel(/Authenticator code|Код из приложения/i).fill("123456")
    await page.getByRole("button", { name: matchTotpVerifyButton }).click()

    await expect(page).toHaveURL(/\/dashboard$/)
  })

  test("shows an error for invalid OTP attempts and allows retry", async ({ page }) => {
    await useMockApi(page)

    await page.goto("/login")
    await page.waitForURL(/\/login$/)

    await page.locator('input[name="username"]').fill("mfa@example.com")
    await page.locator('input[name="password"]').fill("Password123")
    await page.locator('button[type="submit"]').click()

    await expect(page.getByText(/Verify it's you|Подтвердите свою личность/i)).toBeVisible()

    const otpInput = page.getByLabel(/Authenticator code|Код из приложения/i)
    await otpInput.fill("000000")
    await page.getByRole("button", { name: matchTotpVerifyButton }).click()

    await expect(page.getByText(/Invalid verification code|Неверный код/i)).toBeVisible()

    await otpInput.fill("123456")
    await page.getByRole("button", { name: matchTotpVerifyButton }).click()

    await expect(page).toHaveURL(/\/dashboard$/)
  })
})
