import { randomUUID } from "node:crypto"
import type { Browser, BrowserContext, Page, Response, TestInfo } from "@playwright/test"
import {
  expect,
  freshPassword,
  loginAs,
  mailFor,
  mailText,
  stubBreachedPasswordLookup,
  submitLogin,
  test,
} from "./fixtures"

const EMAIL_CODE = /(?:Verification code|Код подтверждения):\s*(\d{6})/iu
const OTP_INPUTS = 'input[inputmode="numeric"][maxlength="1"]'

test.use({ trace: "off", screenshot: "off", video: "off" })

function isApiResponse(suffix: string) {
  return (response: Response) =>
    response.request().method() === "POST" && new URL(response.url()).pathname.endsWith(suffix)
}

function isProfileResponse(response: Response) {
  return (
    response.request().method() === "GET" &&
    new URL(response.url()).pathname.endsWith("/users/me") &&
    response.ok()
  )
}

async function enterCode(page: Page, code: string) {
  const inputs = page.locator(OTP_INPUTS)
  await expect(inputs).toHaveCount(6)
  for (const [index, digit] of Array.from(code).entries()) {
    await inputs.nth(index).fill(digit)
  }
}

async function awaitNewCode(address: string, previousMessageIds: Set<string>): Promise<string> {
  let receivedCode: string | undefined
  await expect
    .poll(
      async () => {
        for (const message of await mailFor(address)) {
          if (previousMessageIds.has(message.ID)) continue
          const match = (await mailText(message.ID)).match(EMAIL_CODE)
          if (match?.[1]) {
            receivedCode = match[1]
            return true
          }
        }
        return false
      },
      { message: "no new email OTP arrived for the current challenge", timeout: 30_000 }
    )
    .toBe(true)
  if (!receivedCode) throw new Error("New email OTP message had no usable code")
  return receivedCode
}

async function createIsolatedPage(
  browser: Browser,
  sourcePage: Page,
  testInfo: TestInfo
): Promise<{ context: BrowserContext; page: Page }> {
  const isMobile = testInfo.project.name.toLowerCase().includes("mobile")
  const context = await browser.newContext({
    baseURL: process.env.LIVE_BASE_URL,
    ignoreHTTPSErrors: true,
    locale: "ru-RU",
    viewport: sourcePage.viewportSize() ?? { width: 1280, height: 800 },
    isMobile,
    hasTouch: isMobile,
  })
  return { context, page: await context.newPage() }
}

async function deleteOwnedAccount(browser: Browser, userId: string) {
  const context = await browser.newContext({
    baseURL: process.env.LIVE_BASE_URL,
    ignoreHTTPSErrors: true,
    locale: "ru-RU",
  })
  try {
    const page = await context.newPage()
    await loginAs(page, "admin")
    const status = await page.evaluate(async (createdId) => {
      const csrfCookie = document.cookie
        .split(";")
        .map((part) => part.trim())
        .find((part) => part.startsWith("csrf_token="))
      if (!csrfCookie) return 0

      const response = await fetch(`/api/v1/users/${encodeURIComponent(createdId)}`, {
        method: "DELETE",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "X-CSRF-Token": decodeURIComponent(csrfCookie.slice("csrf_token=".length)),
          "X-Requested-With": "XMLHttpRequest",
        },
      })
      return response.status
    }, userId)
    expect(status).toBe(200)
  } finally {
    await context.close()
  }
}

test("verified email OTP MFA is required and completes a fresh browser login", async ({
  browser,
  page,
}, testInfo) => {
  test.setTimeout(180_000)
  const email = `live-email-mfa-${randomUUID()}@university.dev`
  const password = freshPassword()
  let createdUserId: string | null = null
  let loginContext: BrowserContext | null = null

  await stubBreachedPasswordLookup(page)

  try {
    const registrationResponsePromise = page.waitForResponse(isApiResponse("/auth/register"))
    await page.goto("/register")
    await page.locator("#full_name").fill("Live email MFA login acceptance")
    await page.locator("#email").fill(email)
    await page.locator("#password").fill(password)
    await page.locator("#confirmPassword").fill(password)
    await page.locator("#register-submit").click()

    const registrationResponse = await registrationResponsePromise
    expect(registrationResponse.ok()).toBe(true)
    const registrationBody = (await registrationResponse.json()) as { id?: unknown }
    if (typeof registrationBody.id !== "string" || registrationBody.id.length === 0) {
      throw new Error("Synthetic account registration returned no account id")
    }
    createdUserId = registrationBody.id

    await submitLogin(page, email, password)
    await expect(page).toHaveURL(/\/dashboard$/u)
    await page.goto("/settings?tab=2")

    const emailOtpAccordion = page.getByRole("button", {
      name: /Коды по электронной почте|Email verification codes/iu,
    })
    if ((await emailOtpAccordion.getAttribute("aria-expanded")) !== "true") {
      await emailOtpAccordion.click()
    }
    await expect(emailOtpAccordion).toHaveAttribute("aria-expanded", "true")

    const priorVerificationMessages = new Set((await mailFor(email)).map((message) => message.ID))
    const verificationStartPromise = page.waitForResponse(
      isApiResponse("/auth/mfa/email/verification/start")
    )
    await page
      .getByRole("button", { name: /Сначала подтвердить почту|Verify email first/iu })
      .click()
    expect((await verificationStartPromise).status()).toBe(200)

    const verificationCode = await awaitNewCode(email, priorVerificationMessages)
    const verificationPromise = page.waitForResponse(isApiResponse("/auth/mfa/verify"))
    const verifiedProfilePromise = page.waitForResponse(isProfileResponse)
    await enterCode(page, verificationCode)
    const [emailVerification, verifiedProfileResponse] = await Promise.all([
      verificationPromise,
      verifiedProfilePromise,
    ])
    expect(emailVerification.status()).toBe(200)
    const verifiedProfile = (await verifiedProfileResponse.json()) as {
      email_verified_at?: string | null
    }
    expect(verifiedProfile.email_verified_at).toBeTruthy()

    await expect(
      page.getByRole("button", { name: /Включить коды по почте|Enable email codes/iu })
    ).toBeVisible()
    const priorEnablementMessages = new Set((await mailFor(email)).map((message) => message.ID))
    const enablementStartPromise = page.waitForResponse(isApiResponse("/auth/mfa/email/enable"))
    await page.getByRole("button", { name: /Включить коды по почте|Enable email codes/iu }).click()
    expect((await enablementStartPromise).status()).toBe(200)

    const enablementCode = await awaitNewCode(email, priorEnablementMessages)
    const enablementVerifyPromise = page.waitForResponse(isApiResponse("/auth/mfa/verify"))
    const enabledProfilePromise = page.waitForResponse(isProfileResponse)
    await enterCode(page, enablementCode)
    const [enablementVerification, enabledProfileResponse] = await Promise.all([
      enablementVerifyPromise,
      enabledProfilePromise,
    ])
    expect(enablementVerification.status()).toBe(200)
    const enabledProfile = (await enabledProfileResponse.json()) as {
      email_mfa_enabled_at?: string | null
    }
    expect(enabledProfile.email_mfa_enabled_at).toBeTruthy()

    const login = await createIsolatedPage(browser, page, testInfo)
    loginContext = login.context
    let pageError = false
    login.page.on("pageerror", () => {
      pageError = true
    })

    const priorLoginMessages = new Set((await mailFor(email)).map((message) => message.ID))
    const loginResponsePromise = login.page.waitForResponse(isApiResponse("/auth/login"))
    await submitLogin(login.page, email, password)
    const loginResponse = await loginResponsePromise
    expect(loginResponse.status()).toBe(202)
    const pendingChallenge = (await loginResponse.json()) as {
      methods?: Array<{ method?: unknown }>
    }
    if (
      !Array.isArray(pendingChallenge.methods) ||
      !pendingChallenge.methods.some((method) => method.method === "email_otp")
    ) {
      throw new Error("Login did not offer the enabled email OTP factor")
    }
    await expect(login.page.locator(OTP_INPUTS)).toHaveCount(6)
    await expect(
      login.page.getByRole("heading", { name: /Код из письма|Email code/iu })
    ).toBeVisible()

    const loginCode = await awaitNewCode(email, priorLoginMessages)
    const loginVerificationPromise = login.page.waitForResponse(isApiResponse("/auth/mfa/verify"))
    await enterCode(login.page, loginCode)
    expect((await loginVerificationPromise).status()).toBe(200)
    await expect(login.page).toHaveURL(/\/dashboard$/u)
    if (pageError) throw new Error("Email MFA login raised an uncaught page exception")
  } finally {
    if (loginContext) await loginContext.close()
    if (createdUserId) await deleteOwnedAccount(browser, createdUserId)
  }
})
