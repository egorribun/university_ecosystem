import { randomUUID } from "node:crypto"
import { Locator, Page, Request, Response, TestInfo } from "@playwright/test"
import { reportAuthRegistrationFailure } from "./auth-notification-diagnostic"
import {
  parseLiveRateLimitRetryAfterForDiagnostic,
  reportLiveHttpStatus,
  reportLiveRateLimitRetry,
} from "./http-status-diagnostic"
import {
  withLiveRegistrationAdmission,
  awaitMail,
  assessLiveRateLimitRetry,
  expect,
  freshPassword,
  loginAs,
  loginWith,
  liveDeadlineBoundedTimeoutMs,
  mailFor,
  mailText,
  parseLiveRateLimitRetryAfter,
  stubBreachedPasswordLookup,
  waitForLiveRateLimitRetry,
  test,
} from "./fixtures"

const EMAIL_CODE = /(?:Verification code|Код подтверждения):\s*(\d{6})/iu
const OTP_RETRY_REQUEST_BUDGET_MS = 20_000
const OTP_RETRY_ACTION_TIMEOUT_MS = 15_000
const OTP_RETRY_MAIL_WAIT_BUDGET_MS = 30_000
const OTP_RETRY_FINAL_RESERVE_MS = 20_000

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

function retryActionTimeout(deadlineAtMs: number): number {
  const timeoutMs = liveDeadlineBoundedTimeoutMs(deadlineAtMs, OTP_RETRY_ACTION_TIMEOUT_MS)
  if (timeoutMs === null) throw new Error("Email OTP retry action deadline exhausted")
  return timeoutMs
}

async function enterCode(inputs: Locator, code: string, actionDeadlineAtMs?: number) {
  const actionOptions = () =>
    actionDeadlineAtMs === undefined
      ? undefined
      : { timeout: retryActionTimeout(actionDeadlineAtMs) }
  await expect(inputs).toHaveCount(6, actionOptions())
  for (const [index, digit] of Array.from(code).entries()) {
    await inputs.nth(index).fill(digit, actionOptions())
  }
}

async function waitUntilResendAvailable(resendAvailableAt: string) {
  const availableAt = Date.parse(resendAvailableAt)
  if (!Number.isFinite(availableAt)) {
    throw new Error("Email OTP challenge had no valid resend time")
  }
  const waitMs = availableAt - Date.now() + 500
  if (waitMs > 0) await new Promise((resolve) => setTimeout(resolve, waitMs))
}

async function awaitNewMail(address: string, previousMessageIds: Set<string>): Promise<string> {
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
      { message: "no new verification message arrived after resend", timeout: 30_000 }
    )
    .toBe(true)
  if (!receivedCode) throw new Error("New Mailpit verification message had no code")
  return receivedCode
}

test("email verification retries, rotates its code on resend, and rejects replay", async ({
  browser,
  page,
}, testInfo: TestInfo) => {
  test.setTimeout(150_000)
  const identity = randomUUID()
  const address = `live-email-otp-${identity}@university.dev`
  const fullName = `Live email OTP acceptance ${testInfo.project.name} ${identity}`
  const password = freshPassword()
  let createdUserId: string | null = null
  let registrationAttempted = false
  let registrationRequestObserved = false
  let registrationStatus: number | null = null
  let registrationPhase: "before-submit" | "submit-click" | "response-wait" | "response-received" =
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

  await stubBreachedPasswordLookup(page)

  try {
    page.on("request", observeRegistrationRequest)
    page.on("response", observeRegistrationResponse)
    await page.goto("/register")
    await page.locator("#full_name").fill(fullName)
    await page.locator("#email").fill(address)
    await page.locator("#password").fill(password)
    await page.locator("#confirmPassword").fill(password)
    const registerButton = page.locator("#register-submit")
    const registrationFormValid = await page
      .locator("form")
      .first()
      .evaluate((form) => form.matches(":valid"))
    const registrationSubmitEnabled = await registerButton.isEnabled()
    let registered: Response
    try {
      registered = await withLiveRegistrationAdmission(page, 1, async () => {
        registrationAttempted = true
        registrationPhase = "submit-click"
        const registrationResponsePromise = page.waitForResponse((response) =>
          isRegistrationRequest(response.request())
        )
        const [registrationClick, registrationResponse] = await Promise.allSettled([
          registerButton.click(),
          registrationResponsePromise,
        ])
        if (registrationResponse.status === "fulfilled") {
          registrationRequestObserved = true
          registrationStatus = registrationResponse.value.status()
        }
        if (registrationClick.status === "rejected") {
          registrationPhase = "submit-click"
          throw registrationClick.reason
        }
        if (registrationResponse.status === "rejected") {
          registrationPhase = "response-wait"
          throw registrationResponse.reason
        }
        registrationPhase = "response-received"
        return registrationResponse.value
      })
    } catch (error) {
      if (registrationAttempted) {
        try {
          reportAuthRegistrationFailure(
            testInfo.project.name.toLowerCase().includes("mobile") ? "mobile" : "desktop",
            "email-otp",
            {
              phase: registrationPhase,
              formValid: registrationFormValid,
              submitEnabled: registrationSubmitEnabled,
              requestObserved: registrationRequestObserved,
              status: registrationStatus,
            }
          )
        } catch {
          // Diagnostics are best-effort and must preserve the original failure.
        }
      }
      throw error
    }
    reportLiveHttpStatus(testInfo.project.name, "email-otp-register", registered.status())
    expect(registered.ok()).toBe(true)
    const registrationBody = (await registered.json()) as { id?: unknown }
    if (typeof registrationBody.id !== "string" || registrationBody.id.length === 0) {
      throw new Error("Synthetic account registration returned no account id")
    }
    // This id came from this test's unique synthetic account registration and
    // is retained only so the finally block can remove that exact account.
    createdUserId = registrationBody.id

    await loginWith(page, address, password)
    await page.goto("/settings?tab=2")
    await expectOwnedProfileIdentityReady(
      page,
      fullName,
      testInfo.project.name.toLowerCase().includes("mobile")
    )
    await page.getByRole("button", { name: /Коды по электронной почте/iu }).click()
    const verifyEmailButton = page.getByRole("button", {
      name: /Verify email first|Сначала подтвердить почту/iu,
    })
    await expect(verifyEmailButton).toBeVisible()
    await expect(verifyEmailButton).toBeEnabled()
    const [started] = await Promise.all([
      page.waitForResponse(
        (response) =>
          response.request().method() === "POST" &&
          new URL(response.url()).pathname.endsWith("/auth/mfa/email/verification/start")
      ),
      verifyEmailButton.click(),
    ])
    reportLiveHttpStatus(testInfo.project.name, "email-otp-verification-start", started.status())
    expect(started.status()).toBe(200)
    const initialChallenge = (await started.json()) as {
      challenge_token?: unknown
      resend_available_at?: unknown
      revision?: unknown
    }
    if (
      typeof initialChallenge.challenge_token !== "string" ||
      typeof initialChallenge.resend_available_at !== "string" ||
      typeof initialChallenge.revision !== "number"
    ) {
      throw new Error("Email verification challenge omitted resend state")
    }

    const mailMatch = await awaitMail(address, EMAIL_CODE)
    const firstCode = mailMatch[1]
    if (!firstCode) throw new Error("Mailpit verification message had no code")
    const previousMessageIds = new Set((await mailFor(address)).map((message) => message.ID))
    const inputs = page.locator('input[inputmode="numeric"]')
    const wrongCode = `${firstCode[0] === "9" ? "8" : "9"}${firstCode.slice(1)}`
    const verifyRequest = (request: Request) =>
      request.method() === "POST" && new URL(request.url()).pathname.endsWith("/auth/mfa/verify")
    const verifyResponse = (response: Response) => verifyRequest(response.request())

    const rejectedResponse = page.waitForResponse(verifyResponse)
    await enterCode(inputs, wrongCode)
    let rejected = await rejectedResponse
    reportLiveHttpStatus(
      testInfo.project.name,
      "email-otp-verification-wrong-code",
      rejected.status()
    )
    let retryDecision: "retry" | "declined-header" | "declined-deadline" | null = null
    if (rejected.status() === 429) {
      await expect(inputs.first()).toHaveValue("")
      const retryAfter = parseLiveRateLimitRetryAfter(rejected.headers()["retry-after"])
      const resendAvailableAtMs = Date.parse(initialChallenge.resend_available_at)
      const remainingResendWaitMs = Number.isFinite(resendAvailableAtMs)
        ? Math.max(0, resendAvailableAtMs - Date.now() + 500)
        : OTP_RETRY_FINAL_RESERVE_MS
      const retryTailBudgetMs =
        remainingResendWaitMs + OTP_RETRY_MAIL_WAIT_BUDGET_MS + OTP_RETRY_FINAL_RESERVE_MS
      const initialDecision = assessLiveRateLimitRetry(
        testInfo,
        retryAfter,
        OTP_RETRY_REQUEST_BUDGET_MS,
        retryTailBudgetMs
      )
      retryDecision = initialDecision.decision
      let retryDeadlineAtMs = initialDecision.deadlineAtMs

      if (initialDecision.decision === "retry" && retryAfter !== null) {
        await waitForLiveRateLimitRetry(retryAfter)
        const afterWait = assessLiveRateLimitRetry(
          testInfo,
          0,
          OTP_RETRY_REQUEST_BUDGET_MS,
          retryTailBudgetMs
        )
        retryDecision = afterWait.decision
        retryDeadlineAtMs = afterWait.deadlineAtMs

        if (afterWait.decision === "retry" && afterWait.deadlineAtMs !== null) {
          const requestDeadlineAtMs = afterWait.deadlineAtMs - retryTailBudgetMs
          const responseTimeoutMs = liveDeadlineBoundedTimeoutMs(
            requestDeadlineAtMs,
            OTP_RETRY_REQUEST_BUDGET_MS
          )
          const retryActionDeadlineAtMs = Math.min(
            requestDeadlineAtMs,
            performance.now() + OTP_RETRY_ACTION_TIMEOUT_MS
          )
          const actionBudgetMs = liveDeadlineBoundedTimeoutMs(
            retryActionDeadlineAtMs,
            OTP_RETRY_ACTION_TIMEOUT_MS
          )
          if (responseTimeoutMs !== null && actionBudgetMs !== null) {
            const verifyButton = page.getByRole("button", {
              name: /^(?:Verify|Подтвердить)$/iu,
            })
            const retryResponse = page.waitForResponse(verifyResponse, {
              timeout: responseTimeoutMs,
            })
            const retryAction = (async () => {
              await enterCode(inputs, wrongCode, retryActionDeadlineAtMs)
              await expect(verifyButton).toBeEnabled({
                timeout: retryActionTimeout(retryActionDeadlineAtMs),
              })
              await verifyButton.click({
                timeout: retryActionTimeout(retryActionDeadlineAtMs),
              })
            })()
            const [responseOutcome, actionOutcome] = await Promise.allSettled([
              retryResponse,
              retryAction,
            ])
            if (responseOutcome.status === "rejected") throw responseOutcome.reason
            if (actionOutcome.status === "rejected") throw actionOutcome.reason
            rejected = responseOutcome.value
            retryDecision = "retry"
            reportLiveHttpStatus(
              testInfo.project.name,
              "email-otp-verification-wrong-code",
              rejected.status()
            )
          } else {
            retryDecision = "declined-deadline"
          }
        }
      }

      reportLiveRateLimitRetry(
        testInfo.project.name,
        "email-otp-verification-wrong-code",
        retryAfter,
        retryDecision,
        retryDeadlineAtMs === null
          ? 0
          : Math.max(0, Math.min(60_000, Math.floor(retryDeadlineAtMs - performance.now())))
      )
    }
    expect(rejected.status()).toBe(400)
    await expect(inputs.first()).toHaveValue("")

    await waitUntilResendAvailable(initialChallenge.resend_available_at)
    const resendResponse = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname.endsWith("/auth/mfa/email/resend")
    )
    await page.getByRole("button", { name: /Отправить новый код|Send a new code/iu }).click()
    const resent = await resendResponse
    reportLiveHttpStatus(testInfo.project.name, "email-otp-verification-resend", resent.status())
    expect(resent.status()).toBe(200)
    const rotatedChallenge = (await resent.json()) as {
      challenge_token?: unknown
      revision?: unknown
    }
    if (
      typeof rotatedChallenge.challenge_token !== "string" ||
      typeof rotatedChallenge.revision !== "number"
    ) {
      throw new Error("Email OTP resend omitted rotated challenge state")
    }
    expect(rotatedChallenge.revision).toBeGreaterThan(initialChallenge.revision)
    expect(rotatedChallenge.challenge_token === initialChallenge.challenge_token).toBe(false)

    const rotatedCode = await awaitNewMail(address, previousMessageIds)
    // A random six-digit OTP can coincide by chance. The challenge token and
    // revision still prove rotation, but there is no distinct old value to try.
    let staleCodeWasRejected = false
    if (rotatedCode !== firstCode) {
      const staleCodeResponse = page.waitForResponse(verifyResponse)
      await enterCode(inputs, firstCode)
      const staleCodeRejected = await staleCodeResponse
      reportLiveHttpStatus(
        testInfo.project.name,
        "email-otp-verification-stale-code",
        staleCodeRejected.status()
      )
      if (staleCodeRejected.status() === 429) {
        reportLiveRateLimitRetry(
          testInfo.project.name,
          "email-otp-verification-stale-code",
          parseLiveRateLimitRetryAfterForDiagnostic(staleCodeRejected.headers()["retry-after"]),
          "not-retried",
          Math.max(0, Math.min(60_000, Math.floor(testInfo.timeout - testInfo.duration)))
        )
      }
      expect(staleCodeRejected.status()).toBe(400)
      await expect(inputs.first()).toHaveValue("")
      staleCodeWasRejected = true
    }

    const acceptedRequest = page.waitForRequest(verifyRequest)
    const verifiedResponse = page.waitForResponse(verifyResponse)
    const refreshedProfile = page.waitForResponse(
      (response) =>
        response.request().method() === "GET" &&
        new URL(response.url()).pathname.endsWith("/users/me") &&
        response.ok()
    )
    await enterCode(inputs, rotatedCode)
    if (staleCodeWasRejected) {
      // Server errors suppress auto-submit; a fresh code is retried with the explicit Verify action.
      const verifyButton = page.getByRole("button", { name: /^(?:Verify|Подтвердить)$/iu })
      await expect(verifyButton).toBeEnabled()
      await verifyButton.click()
    }
    const [accepted, verified, profileResponse] = await Promise.all([
      acceptedRequest,
      verifiedResponse,
      refreshedProfile,
    ])
    reportLiveHttpStatus(testInfo.project.name, "email-otp-verification-accept", verified.status())
    expect(verified.status()).toBe(200)

    const profile = (await profileResponse.json()) as { email_verified_at?: string | null }
    expect(profile.email_verified_at).toBeTruthy()

    const acceptedBody = accepted.postData()
    if (!acceptedBody) throw new Error("Email verification request had no body")
    const replayed = await page.evaluate(
      async ({ path, body }) => {
        const csrfCookie = document.cookie
          .split(";")
          .map((part) => part.trim())
          .find((part) => part.startsWith("csrf_token="))
        if (!csrfCookie) return { status: 0 }

        const response = await fetch(path, {
          method: "POST",
          credentials: "same-origin",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
            "X-CSRF-Token": decodeURIComponent(csrfCookie.slice("csrf_token=".length)),
            "X-Requested-With": "XMLHttpRequest",
          },
          body,
        })
        return { status: response.status }
      },
      { path: new URL(accepted.url()).pathname, body: acceptedBody }
    )
    expect(replayed.status).toBe(400)
  } finally {
    page.off("request", observeRegistrationRequest)
    page.off("response", observeRegistrationResponse)
    if (createdUserId) {
      const cleanupContext = await browser.newContext({
        baseURL: process.env.LIVE_BASE_URL,
        ignoreHTTPSErrors: true,
        locale: "ru-RU",
      })
      try {
        const cleanupPage = await cleanupContext.newPage()
        await loginAs(cleanupPage, "admin")
        const cleanup = await cleanupPage.evaluate(async (userId) => {
          const csrfCookie = document.cookie
            .split(";")
            .map((part) => part.trim())
            .find((part) => part.startsWith("csrf_token="))
          if (!csrfCookie) return { status: 0 }

          const response = await fetch(`/api/v1/users/${encodeURIComponent(userId)}`, {
            method: "DELETE",
            credentials: "same-origin",
            headers: {
              Accept: "application/json",
              "X-CSRF-Token": decodeURIComponent(csrfCookie.slice("csrf_token=".length)),
              "X-Requested-With": "XMLHttpRequest",
            },
          })
          return { status: response.status }
        }, createdUserId)
        expect(cleanup.status).toBe(200)
      } finally {
        await cleanupContext.close()
      }
    }
  }
})
