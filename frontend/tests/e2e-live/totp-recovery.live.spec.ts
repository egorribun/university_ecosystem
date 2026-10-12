import { createHmac, randomUUID } from "node:crypto"
import { Browser, BrowserContext, Page, Request, Response, TestInfo } from "@playwright/test"
import {
  withLiveRegistrationAdmission,
  expect,
  freshPassword,
  loginAs,
  stubBreachedPasswordLookup,
  submitLogin,
  test,
} from "./fixtures"
import {
  reportAuthHttpStatus,
  reportAuthRegistrationFailure,
  reportAuthUiFailure,
} from "./auth-notification-diagnostic"

const TOTP_PERIOD_MS = 30_000
const TOTP_DIGITS = 6
const TOTP_SECRET_INPUT = "#totp-manual-code"
const OTP_INPUTS = 'input[inputmode="numeric"][maxlength="1"]'
const RECOVERY_INPUT = 'input[placeholder="XXXX-XXXX-XXXX-XXXX"]'

const diagnosticProject = (projectName: string): "desktop" | "mobile" =>
  projectName.toLowerCase().includes("mobile") ? "mobile" : "desktop"

async function readFailureDetail(response: { json(): Promise<unknown> }): Promise<unknown> {
  try {
    const body = await response.json()
    return body && typeof body === "object" && "detail" in body
      ? (body as { detail?: unknown }).detail
      : undefined
  } catch {
    return undefined
  }
}

async function inspectAlertState(page: Page) {
  const alerts = page.getByRole("alert")
  const rawCount = await alerts.count().catch(() => 0)
  let visible = false
  for (let index = 0; index < Math.min(rawCount, 8); index += 1) {
    if (
      await alerts
        .nth(index)
        .isVisible()
        .catch(() => false)
    )
      visible = true
  }
  return { count: Math.min(rawCount, 8), capped: rawCount > 8, visible }
}

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

async function expectOwnedProfileIdentityReady(page: Page, fullName: string, isMobile: boolean) {
  if (isMobile) {
    const profileAction = page.getByRole("button", { name: "Открыть профиль", exact: true })
    await expect(profileAction).toHaveCount(1)
    await expect(profileAction).toBeVisible()
    await expect(profileAction).toBeEnabled()
    await expect(profileAction.locator("img")).toHaveAttribute(
      "alt",
      `Аватар пользователя ${fullName}`
    )
    return
  }

  const profileAction = page.getByRole("button", {
    name: `Открыть профиль: ${fullName}`,
    exact: true,
    includeHidden: true,
  })
  await expect(profileAction).toHaveCount(1)
  await expect(profileAction).toBeEnabled()
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

async function verifyRecoveryCodeOnLogin(
  page: Page,
  recoveryCode: string,
  expectedStatus: number,
  diagnostic?: {
    project: "desktop" | "mobile"
    operation: "totp_recovery_accept" | "totp_recovery_replay"
  }
) {
  await page.locator("#use-recovery-code-toggle").click()
  const input = page.locator(RECOVERY_INPUT)
  await expect(input).toBeVisible()
  const verifyPromise = page.waitForResponse(isApiResponse("/auth/mfa/verify"))
  await input.fill(recoveryCode)
  await input.press("Enter")
  const response = await verifyPromise
  if (diagnostic) reportAuthHttpStatus(diagnostic.project, diagnostic.operation, response.status())
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
  const identity = randomUUID()
  const email = `live-totp-${identity}@university.dev`
  const password = freshPassword()
  const fullName = `Live TOTP recovery acceptance ${testInfo.project.name} ${identity}`
  let createdUserId: string | null = null
  let registrationAttempted = false
  let registrationCompleted = false
  let registrationFormValid = false
  let registrationSubmitEnabled = false
  let registrationRequestObserved = false
  let registrationStatus: number | null = null
  let registrationPhase: "before-submit" | "response-wait" | "response-received" | "navigation" =
    "before-submit"
  const isRegistrationRequest = (request: Request) =>
    request.method() === "POST" && new URL(request.url()).pathname.endsWith("/auth/register")
  const observeRegistrationRequest = (request: Request) => {
    if (isRegistrationRequest(request)) registrationRequestObserved = true
  }
  const observeRegistrationResponse = (response: Response) => {
    if (!isRegistrationRequest(response.request())) return
    registrationRequestObserved = true
    registrationStatus = response.status()
    registrationPhase = "response-received"
  }
  const ownedContexts: BrowserContext[] = []

  await stubBreachedPasswordLookup(page)

  try {
    page.on("request", observeRegistrationRequest)
    page.on("response", observeRegistrationResponse)
    await page.goto("/register")
    await page.locator("#full_name").fill(fullName)
    await page.locator("#email").fill(email)
    await page.locator("#password").fill(password)
    await page.locator("#confirmPassword").fill(password)
    const registerButton = page.locator("#register-submit")
    registrationFormValid = await page
      .locator("form")
      .first()
      .evaluate((form) => form.matches(":valid"))
    registrationSubmitEnabled = await registerButton.isEnabled()
    const registered = await withLiveRegistrationAdmission(page, 1, async () => {
      registrationAttempted = true
      registrationPhase = "response-wait"
      const registrationResponsePromise = page.waitForResponse(isApiResponse("/auth/register"))
      const [registrationClick, registrationResponse] = await Promise.allSettled([
        registerButton.click(),
        registrationResponsePromise,
      ])
      if (registrationClick.status === "rejected") throw registrationClick.reason
      if (registrationResponse.status === "rejected") throw registrationResponse.reason
      return registrationResponse.value
    })
    registrationStatus = registered.status()
    registrationRequestObserved = true
    registrationPhase = "response-received"
    reportAuthHttpStatus(testInfo.project.name, "totp_register", registered.status())
    expect(registered.ok()).toBe(true)
    const registrationBody = (await registered.json()) as { id?: unknown }
    if (typeof registrationBody.id !== "string" || registrationBody.id.length === 0) {
      throw new Error("Synthetic account registration returned no account id")
    }
    createdUserId = registrationBody.id
    registrationCompleted = true

    await submitLogin(page, email, password)
    await expect(page).toHaveURL(/\/dashboard$/u)

    await page.goto("/settings?tab=2")
    await expectOwnedProfileIdentityReady(
      page,
      fullName,
      testInfo.project.name.toLowerCase().includes("mobile")
    )
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
    await expect(addAuthenticator).toBeVisible()
    await expect(addAuthenticator).toBeEnabled()
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
    await verifyRecoveryCodeOnLogin(recoveryLogin.page, recoveryCode, 200, {
      project: diagnosticProject(testInfo.project.name),
      operation: "totp_recovery_accept",
    })
    await expect(recoveryLogin.page).toHaveURL(/\/dashboard$/u)
    checkRecoveryLoginPageErrors()

    const replayLogin = await createIsolatedPage(browser, page, testInfo)
    ownedContexts.push(replayLogin.context)
    let replayPageErrorOccurred = false
    replayLogin.page.on("pageerror", () => {
      replayPageErrorOccurred = true
    })
    const checkReplayLoginPageErrors = await loginToMfaChallenge(replayLogin.page, email, password)
    const replayResponse = await verifyRecoveryCodeOnLogin(replayLogin.page, recoveryCode, 400, {
      project: diagnosticProject(testInfo.project.name),
      operation: "totp_recovery_replay",
    })
    const replayErrorAlert = replayLogin.page.getByRole("alert").filter({ hasText: /\S/u })
    try {
      await expect(replayErrorAlert).toHaveCount(1)
      await expect(replayErrorAlert).toBeVisible()
      checkReplayLoginPageErrors()
    } catch (error) {
      try {
        const alertState = await inspectAlertState(replayLogin.page)
        const loginChallenge = await replayLogin.page
          .locator(RECOVERY_INPUT)
          .isVisible()
          .catch(() => false)
        reportAuthUiFailure({
          project: diagnosticProject(testInfo.project.name),
          scenario: "totp_recovery_replay",
          status: replayResponse.status(),
          detail: await readFailureDetail(replayResponse),
          alertCount: alertState.count,
          alertCountCapped: alertState.capped,
          alertVisible: alertState.visible,
          currentFieldInvalid: null,
          loginChallenge,
          pageError: replayPageErrorOccurred,
        })
      } catch {
        // Telemetry is best-effort; retain the original assertion failure.
      }
      throw error
    }

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
  } catch (error) {
    if (registrationAttempted && !registrationCompleted) {
      reportAuthRegistrationFailure(diagnosticProject(testInfo.project.name), "totp", {
        phase: registrationPhase,
        formValid: registrationFormValid,
        submitEnabled: registrationSubmitEnabled,
        requestObserved: registrationRequestObserved,
        status: registrationStatus,
      })
    }
    throw error
  } finally {
    page.off("request", observeRegistrationRequest)
    page.off("response", observeRegistrationResponse)
    for (const context of ownedContexts) await context.close()
    if (createdUserId) await deleteOwnedAccount(browser, createdUserId)
  }
})
