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

    await page.getByLabelText(/Authenticator code|Код из приложения/i).fill("123456")
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
    await page.getByRole("button", { name: /Sign in|Войти/i }).click()

    await expect(page.getByText(/Verify it's you|Подтвердите свою личность/i)).toBeVisible()

    await page.getByLabelText(/Authenticator code|Код из приложения/i).fill("123456")
    await page.getByRole("button", { name: matchTotpVerifyButton }).click()

    await expect(page).toHaveURL(/\/dashboard$/)
  })

  test("shows an error for invalid OTP attempts and allows retry", async ({ page }) => {
    await useMockApi(page)

    await page.goto("/login")
    await page.waitForURL(/\/login$/)

    await page.locator('input[name="username"]').fill("mfa@example.com")
    await page.locator('input[name="password"]').fill("Password123")
    await page.getByRole("button", { name: /Sign in|Войти/i }).click()

    await expect(page.getByText(/Verify it's you|Подтвердите свою личность/i)).toBeVisible()

    const otpInput = page.getByLabelText(/Authenticator code|Код из приложения/i)
    await otpInput.fill("000000")
    await page.getByRole("button", { name: matchTotpVerifyButton }).click()

    await expect(page.getByText(/Invalid verification code|Неверный код/i)).toBeVisible()

    await otpInput.fill("123456")
    await page.getByRole("button", { name: matchTotpVerifyButton }).click()

    await expect(page).toHaveURL(/\/dashboard$/)
  })

  test("allows logging in with a WebAuthn challenge", async ({ page }) => {
    await page.addInitScript(() => {
      const credentialResponse = {
        id: "credential-id",
        rawId: Uint8Array.from([1, 2, 3]).buffer,
        response: {
          clientDataJSON: Uint8Array.from([4, 5]).buffer,
          authenticatorData: Uint8Array.from([6, 7]).buffer,
          signature: Uint8Array.from([8, 9]).buffer,
          userHandle: null,
        },
        type: "public-key",
        authenticatorAttachment: "platform",
        clientExtensionResults: () => ({}),
        toJSON() {
          return {
            id: "credential-id",
            rawId: "AQID",
            response: {
              clientDataJSON: "BAU=",
              authenticatorData: "Bgc=",
              signature: "CAk=",
              userHandle: null,
            },
            type: "public-key",
            clientExtensionResults: {},
            authenticatorAttachment: "platform",
          }
        },
      }

      Object.defineProperty(window, "PublicKeyCredential", {
        value: class PublicKeyCredential {
          static isUserVerifyingPlatformAuthenticatorAvailable() {
            return Promise.resolve(true)
          }
        },
      })

      Object.defineProperty(navigator, "credentials", {
        value: {
          get: async () => credentialResponse,
        },
        configurable: true,
      })
    })

    await useMockApi(page)

    await page.goto("/login")
    await page.waitForURL(/\/login$/)

    await page.locator('input[name="username"]').fill("webauthn@example.com")
    await page.locator('input[name="password"]').fill("Password123")
    await page.getByRole("button", { name: /Sign in|Войти/i }).click()

    await expect(page.getByText(/Use your security key|Используйте ключ безопасности/i)).toBeVisible()

    await expect(page).toHaveURL(/\/dashboard$/)
  })
})
