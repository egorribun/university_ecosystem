import type { Page } from "@playwright/test"
import { expect, test } from "./test"
import { useMockApi } from "./utils/mockApi"

const matchTotpAddButton = /Подключить приложение|Set up authenticator app/i
const matchTotpSection = /^Приложение-аутентификатор|^Authenticator app/i
const matchTotpVerifyButton = /Подтвердить|Verify|Confirm/i

const fillOtp = async (page: Page, code: string) => {
  const inputs = page.getByRole("textbox", { name: /digit \d/i })
  await expect(inputs).toHaveCount(6)
  for (const [index, digit] of [...code].entries()) {
    await inputs.nth(index).fill(digit)
  }
}

test.describe("Multi-factor authentication flows", () => {
  test("keeps remember-email separate from explicit trusted-device consent", async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem("auth:trustDevice", JSON.stringify("1"))
    })
    await useMockApi(page, { authenticated: false })

    await page.goto("/login")
    await page.waitForFunction(() => window.__APP_HYDRATED === true)

    const rememberEmail = page.getByRole("checkbox", { name: /Remember email|Запомнить email/i })
    const trustDevice = page.getByRole("checkbox", {
      name: /Trust this device for 30 days|Доверять этому устройству 30 дней/i,
    })
    await expect(rememberEmail).not.toBeChecked()
    await expect(trustDevice).not.toBeChecked()
    await expect(page.getByText(/skip MFA for 30 days|обходиться без MFA 30 дней/i)).toBeVisible()

    await page.getByText(/^(Remember email|Запомнить email)$/i).click()
    await expect(rememberEmail).toBeChecked()
    await page.locator('input[name="email"]').fill("mfa@example.com")
    await page.locator('input[name="password"]').fill("Password123")
    const loginRequest = page.waitForRequest(
      (request) => request.url().includes("/auth/login") && request.method() === "POST"
    )
    await page.locator('button[type="submit"]').click()

    const request = await loginRequest
    const params = new URLSearchParams(request.postData() ?? "")
    expect(params.get("trust_device")).toBeNull()
    await expect
      .poll(() => page.evaluate(() => window.localStorage.getItem("auth:lastEmail")))
      .toContain("mfa@example.com")
  })

  test("allows enabling TOTP in settings", async ({ page }) => {
    const mock = await useMockApi(page)
    await mock.login(page)

    await page.goto("/settings")
    await expect(page.getByRole("heading", { name: /Settings|Настройки/i })).toBeVisible()

    await page.getByRole("tab", { name: /Security|Безопасность/i }).click()
    await expect(
      page.getByRole("heading", { name: /Security & MFA|Безопасность и MFA/i })
    ).toBeVisible()

    const totpSection = page.getByRole("button", { name: matchTotpSection })
    await totpSection.click()
    await expect(totpSection).toHaveAttribute("aria-expanded", "true")

    const addBtn = page.getByRole("button", { name: matchTotpAddButton })
    await expect(addBtn).toBeVisible()

    const startPromise = page.waitForResponse(
      (r) => r.url().includes("auth/mfa/totp/start") && r.status() === 200
    )
    await addBtn.click()
    await startPromise
    await expect(
      page.getByText(/Завершите настройку|Finish setup|Confirm setup|Scan|QR/i).first()
    ).toBeVisible()

    await fillOtp(page, "123456")

    await expect(
      page.getByText(/Приложение-аутентификатор подключено|Authenticator app connected/i)
    ).toBeVisible()
    await expect(page.getByText(/Приложение \d|Authenticator \d/i)).toBeVisible()
  })

  test("completes login when an OTP challenge is returned", async ({ page }) => {
    await useMockApi(page, { authenticated: false })

    await page.goto("/login")
    await page.waitForURL(/\/login$/)
    await page.waitForFunction(() => window.__APP_HYDRATED === true)

    await page.locator('input[name="email"]').fill("mfa@example.com")
    await page.locator('input[name="password"]').fill("Password123")
    await page.locator('button[type="submit"]').click()

    await expect(page.getByText(/Подтвердите личность|Verify it's you/i)).toBeVisible()

    await fillOtp(page, "123456")

    await expect(page).toHaveURL(/\/dashboard$/, { timeout: 10000 })
  })

  test("shows an error for invalid OTP attempts and allows retry", async ({ page }) => {
    await useMockApi(page, { authenticated: false })

    await page.goto("/login")
    await page.waitForURL(/\/login$/)
    await page.waitForFunction(() => window.__APP_HYDRATED === true)

    await page.locator('input[name="email"]').fill("mfa@example.com")
    await page.locator('input[name="password"]').fill("Password123")
    await page.locator('button[type="submit"]').click()

    await expect(page.getByText(/Подтвердите личность|Verify it's you/i)).toBeVisible()

    await fillOtp(page, "000000")

    const errorMsg = page.getByText(/Неверный код|Invalid verification code/i).first()
    await expect(errorMsg).toBeVisible()
    await expect(errorMsg).toHaveText(/Неверный код|Invalid verification code/i)

    await fillOtp(page, "123456")
    await page.getByRole("button", { name: matchTotpVerifyButton }).click()

    await expect(page).toHaveURL(/\/dashboard$/, { timeout: 10000 })
  })
})
