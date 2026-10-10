import { createHmac, randomUUID } from "node:crypto"
import type { Browser, BrowserContext, Page, TestInfo } from "@playwright/test"
import {
  expect,
  freshPassword,
  loginAs,
  stubBreachedPasswordLookup,
  submitLogin,
  test,
} from "./fixtures"

const TOTP_PERIOD_MS = 30_000
const TOTP_DIGITS = 6
const TOTP_SECRET_INPUT = "#totp-manual-code"
const OTP_INPUTS = 'input[inputmode="numeric"][maxlength="1"]'
const RECOVERY_INPUT = 'input[placeholder="XXXX-XXXX-XXXX-XXXX"]'

test.use({ trace: "off", screenshot: "off", video: "off" })

function decodeBase32(value: string): Buffer {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" // pragma: allowlist secret -- public TOTP test alphabet
  const normalized = value.replace(/\s+/gu, "").replace(/=+$/u, "").toUpperCase()
  const bytes: number[] = []
  let accumulator = 0
  let bits = 0

  for (const character of normalized) {
    const digit = alphabet.indexOf(character)
    if (digit < 0) throw new Error("Authenticator seed was not valid base32")
    accumulator = (accumulator << 5) | digit
    bits += 5
    if (bits >= 8) {
      bits -= 8
      bytes.push((accumulator >> bits) & 0xff)
      accumulator &= (1 << bits) - 1
    }
  }

  if (bytes.length === 0) throw new Error("Authenticator seed was empty")
  return Buffer.from(bytes)
}

function totpAt(secret: string, timestampMs: number): string {
  const counter = BigInt(Math.floor(timestampMs / TOTP_PERIOD_MS))
  const counterBytes = Buffer.alloc(8)
  counterBytes.writeBigUInt64BE(counter)
  const digest = createHmac("sha1", decodeBase32(secret)).update(counterBytes).digest()
  const offset = digest[digest.length - 1]! & 0x0f
  const binary =
    (((digest[offset]! & 0x7f) << 24) |
      ((digest[offset + 1]! & 0xff) << 16) |
      ((digest[offset + 2]! & 0xff) << 8) |
      (digest[offset + 3]! & 0xff)) >>>
    0

  return String(binary % 10 ** TOTP_DIGITS).padStart(TOTP_DIGITS, "0")
}

async function waitForTotpCode(secret: string, minimumStep: number | null = null) {
  for (;;) {
    const now = Date.now()
    const step = Math.floor(now / TOTP_PERIOD_MS)
    const remainingMs = (step + 1) * TOTP_PERIOD_MS - now
    if ((minimumStep === null || step > minimumStep) && remainingMs >= 8_000) {
      return { code: totpAt(secret, now), step }
    }

    const waitMs = remainingMs > 0 ? Math.min(remainingMs + 100, 1_000) : 100
    await new Promise((resolve) => setTimeout(resolve, waitMs))
  }
}

function isApiResponse(suffix: string) {
  return (response: { request(): { method(): string }; url(): string }) =>
    response.request().method() === "POST" && new URL(response.url()).pathname.endsWith(suffix)
}

async function fillOtpInputs(page: Page, code: string) {
  const inputs = page.locator(OTP_INPUTS)
  await expect(inputs).toHaveCount(6)
  for (const [index, digit] of Array.from(code).entries()) {
    await inputs.nth(index).fill(digit)
  }
}

async function issueOneRecoveryCode(page: Page): Promise<string> {
  const result = await page.evaluate(async () => {
    const csrfCookie = document.cookie
      .split(";")
      .map((part) => part.trim())
      .find((part) => part.startsWith("csrf_token="))
    if (!csrfCookie) return { status: 0, code: null }

    const response = await fetch("/api/v1/auth/mfa/recovery-codes", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "X-CSRF-Token": decodeURIComponent(csrfCookie.slice("csrf_token=".length)),
        "X-Requested-With": "XMLHttpRequest",
      },
    })
    const payload: unknown = await response.json().catch(() => null)
    const codes =
      payload && typeof payload === "object" && "codes" in payload
        ? (payload as { codes?: unknown }).codes
        : null
    const candidate = Array.isArray(codes) ? codes[0] : null
    const separators = [4, 9, 14]
    const hasRecoveryCodeShape =
      typeof candidate === "string" &&
      candidate.length === 19 &&
      separators.every((index) => candidate[index] === "-") &&
      Array.from(candidate).every(
        (character, index) => separators.includes(index) || "ABCDEF0123456789".includes(character)
      )

    // Return only the single code this test needs. It remains in process
    // memory and is never attached to a report or written to browser storage.
    return {
      status: response.status,
      code: hasRecoveryCodeShape && typeof candidate === "string" ? candidate : null,
    }
  })

  if (result.status !== 200) {
    throw new Error(`Recovery-code generation returned status ${result.status}`)
  }
  if (!result.code) throw new Error("Recovery-code generation returned no usable code")
  return result.code
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

async function loginToMfaChallenge(page: Page, email: string, password: string) {
  let pageError = false
  page.on("pageerror", () => {
    pageError = true
  })

  const loginResponsePromise = page.waitForResponse(isApiResponse("/auth/login"))
  await submitLogin(page, email, password)
  const response = await loginResponsePromise
  expect(response.status()).toBe(202)

  const challenge = (await response.json()) as { methods?: Array<{ method?: unknown }> }
  expect(
    Array.isArray(challenge.methods) && challenge.methods.some((item) => item.method === "totp")
  ).toBe(true)
  await expect(page.locator(OTP_INPUTS)).toHaveCount(6)
  await expect(page.locator("#use-recovery-code-toggle")).toBeVisible()

  return () => {
    if (pageError) throw new Error("MFA browser flow raised an uncaught page exception")
  }
}

async function verifyTotpOnLogin(page: Page, code: string) {
  const verifyPromise = page.waitForResponse(isApiResponse("/auth/mfa/verify"))
  await fillOtpInputs(page, code)
  const response = await verifyPromise
  expect(response.status()).toBe(200)
  await expect(page).toHaveURL(/\/dashboard$/u)
}

async function verifyRecoveryCodeOnLogin(page: Page, recoveryCode: string, expectedStatus: number) {
  await page.locator("#use-recovery-code-toggle").click()
  const input = page.locator(RECOVERY_INPUT)
  await expect(input).toBeVisible()
  const verifyPromise = page.waitForResponse(isApiResponse("/auth/mfa/verify"))
  await input.fill(recoveryCode)
  await input.press("Enter")
  const response = await verifyPromise
  expect(response.status()).toBe(expectedStatus)
  return response
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

test("TOTP enrollment enables login and recovery codes are single-use", async ({
  browser,
  page,
}, testInfo) => {
  test.setTimeout(180_000)
  const email = `live-totp-${randomUUID()}@university.dev`
  const password = freshPassword()
  let createdUserId: string | null = null
  const ownedContexts: BrowserContext[] = []

  await stubBreachedPasswordLookup(page)

  try {
    const registrationResponsePromise = page.waitForResponse(isApiResponse("/auth/register"))
    await page.goto("/register")
    await page.locator("#full_name").fill("Live TOTP recovery acceptance")
    await page.locator("#email").fill(email)
    await page.locator("#password").fill(password)
    await page.locator("#confirmPassword").fill(password)
    await page.locator("#register-submit").click()

    const registered = await registrationResponsePromise
    expect(registered.ok()).toBe(true)
    const registrationBody = (await registered.json()) as { id?: unknown }
    if (typeof registrationBody.id !== "string" || registrationBody.id.length === 0) {
      throw new Error("Synthetic account registration returned no account id")
    }
    createdUserId = registrationBody.id

    await submitLogin(page, email, password)
    await expect(page).toHaveURL(/\/dashboard$/u)

    await page.goto("/settings?tab=2")
    const authenticatorAccordion = page.getByRole("button", {
      name: /^(?:Приложение-аутентификатор|Authenticator app)/iu,
    })
    if ((await authenticatorAccordion.getAttribute("aria-expanded")) !== "true") {
      await authenticatorAccordion.click()
    }
    await expect(authenticatorAccordion).toHaveAttribute("aria-expanded", "true")
    const addAuthenticator = page.getByRole("button", {
      name: /Подключить приложение|Set up authenticator app/iu,
    })
    const enrollmentStartPromise = page.waitForResponse(isApiResponse("/auth/mfa/totp/start"))
    await addAuthenticator.click()
    const enrollmentStart = await enrollmentStartPromise
    expect(enrollmentStart.status()).toBe(200)
    const seedInput = page.locator(TOTP_SECRET_INPUT)
    await expect(seedInput).toBeVisible()
    const authenticatorSecret = await seedInput.inputValue()
    if (!authenticatorSecret) throw new Error("TOTP enrollment UI did not expose its one-time seed")

    const enrollmentTotp = await waitForTotpCode(authenticatorSecret)
    const enrollmentConfirmationPromise = page.waitForResponse(
      isApiResponse("/auth/mfa/totp/confirm")
    )
    await fillOtpInputs(page, enrollmentTotp.code)
    const enrollmentConfirmation = await enrollmentConfirmationPromise
    expect(enrollmentConfirmation.status()).toBe(200)
    await expect(
      page.getByText(/Приложение-аутентификатор подключено|Authenticator app connected/iu)
    ).toBeVisible()

    const recoveryCode = await issueOneRecoveryCode(page)
    const minimumLoginTotpStep = enrollmentTotp.step

    const totpLogin = await createIsolatedPage(browser, page, testInfo)
    ownedContexts.push(totpLogin.context)
    const checkTotpLoginPageErrors = await loginToMfaChallenge(totpLogin.page, email, password)
    const loginTotp = await waitForTotpCode(authenticatorSecret, minimumLoginTotpStep)
    await verifyTotpOnLogin(totpLogin.page, loginTotp.code)
    checkTotpLoginPageErrors()

    const recoveryLogin = await createIsolatedPage(browser, page, testInfo)
    ownedContexts.push(recoveryLogin.context)
    const checkRecoveryLoginPageErrors = await loginToMfaChallenge(
      recoveryLogin.page,
      email,
      password
    )
    await verifyRecoveryCodeOnLogin(recoveryLogin.page, recoveryCode, 200)
    await expect(recoveryLogin.page).toHaveURL(/\/dashboard$/u)
    checkRecoveryLoginPageErrors()

    const replayLogin = await createIsolatedPage(browser, page, testInfo)
    ownedContexts.push(replayLogin.context)
    const checkReplayLoginPageErrors = await loginToMfaChallenge(replayLogin.page, email, password)
    await verifyRecoveryCodeOnLogin(replayLogin.page, recoveryCode, 400)
    await expect(replayLogin.page.getByRole("alert")).toBeVisible()
    checkReplayLoginPageErrors()

    const postReplayTotpLogin = await createIsolatedPage(browser, page, testInfo)
    ownedContexts.push(postReplayTotpLogin.context)
    const checkPostReplayTotpLoginPageErrors = await loginToMfaChallenge(
      postReplayTotpLogin.page,
      email,
      password
    )
    const postReplayTotp = await waitForTotpCode(authenticatorSecret, loginTotp.step)
    await verifyTotpOnLogin(postReplayTotpLogin.page, postReplayTotp.code)
    checkPostReplayTotpLoginPageErrors()
  } finally {
    for (const context of ownedContexts) await context.close()
    if (createdUserId) await deleteOwnedAccount(browser, createdUserId)
  }
})
