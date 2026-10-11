import { randomUUID } from "node:crypto"
import type { Locator, Page, Request, Response, TestInfo } from "@playwright/test"
import { reportLiveHttpStatus } from "./http-status-diagnostic"
import {
  awaitMail,
  expect,
  freshPassword,
  loginAs,
  loginWith,
  mailFor,
  mailText,
  stubBreachedPasswordLookup,
  test,
} from "./fixtures"

const EMAIL_CODE = /(?:Verification code|Код подтверждения):\s*(\d{6})/iu

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

async function enterCode(inputs: Locator, code: string) {
  await expect(inputs).toHaveCount(6)
  for (const [index, digit] of Array.from(code).entries()) {
    await inputs.nth(index).fill(digit)
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

  await stubBreachedPasswordLookup(page)

  try {
    const registrationResponse = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname.endsWith("/auth/register")
    )
    await page.goto("/register")
    await page.locator("#full_name").fill(fullName)
    await page.locator("#email").fill(address)
    await page.locator("#password").fill(password)
    await page.locator("#confirmPassword").fill(password)
    await page.locator("#register-submit").click()

    const registered = await registrationResponse
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
    const rejected = await rejectedResponse
    reportLiveHttpStatus(
      testInfo.project.name,
      "email-otp-verification-wrong-code",
      rejected.status()
    )
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
