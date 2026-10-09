import { randomUUID } from "node:crypto"
import type { Browser, BrowserContext, Page, Response, TestInfo } from "@playwright/test"
import {
  expect,
  freshPassword,
  loginAs,
  loginWith,
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

type ActiveSessionSummary = { id: string; is_current: boolean }

type SiblingRevocationSocketProbe = {
  socket: WebSocket
  opened: boolean
  closed: boolean
  closeCode: number | null
  revokedReason: boolean
  closeSignal: Promise<void>
}

type SiblingRevocationProbeWindow = Window & {
  __liveMfaSiblingRevocationProbe?: SiblingRevocationSocketProbe
}

async function readActiveSessions(page: Page): Promise<ActiveSessionSummary[]> {
  const response = await page.request.get("/api/v1/auth/sessions")
  if (response.status() !== 200) {
    throw new Error("Authenticated session listing did not return HTTP 200")
  }

  const payload: unknown = await response.json()
  if (!Array.isArray(payload)) {
    throw new Error("Authenticated session listing returned an invalid response")
  }

  const sessions: ActiveSessionSummary[] = []
  for (const item of payload) {
    if (typeof item !== "object" || item === null) {
      throw new Error("Authenticated session listing returned an invalid row")
    }
    const record = item as { id?: unknown; is_current?: unknown }
    if (typeof record.id !== "string" || typeof record.is_current !== "boolean") {
      throw new Error("Authenticated session listing returned an invalid row")
    }
    sessions.push({ id: record.id, is_current: record.is_current })
  }
  return sessions
}

function uniqueCurrentSessionId(sessions: ActiveSessionSummary[]): string {
  const currentIds = sessions.filter((session) => session.is_current).map((session) => session.id)
  if (currentIds.length !== 1) {
    throw new Error("Expected exactly one current session in the authenticated context")
  }
  return currentIds[0]!
}

async function openSiblingRevocationSocket(page: Page): Promise<void> {
  const opened = await page.evaluate(async () => {
    const target = window as SiblingRevocationProbeWindow
    if (target.__liveMfaSiblingRevocationProbe) return false

    const csrfCookie = document.cookie
      .split(";")
      .map((part) => part.trim())
      .find((part) => part.startsWith("csrf_token="))
    if (!csrfCookie) return false

    let csrfToken: string
    try {
      csrfToken = decodeURIComponent(csrfCookie.slice("csrf_token=".length))
    } catch {
      return false
    }

    let payload: unknown
    const ticketController = new AbortController()
    const ticketTimeout = window.setTimeout(() => ticketController.abort(), 5_000)
    try {
      const ticketResponse = await fetch("/ws/ticket", {
        method: "POST",
        credentials: "same-origin",
        signal: ticketController.signal,
        headers: {
          Accept: "application/json",
          "X-CSRF-Token": csrfToken,
          "X-Requested-With": "XMLHttpRequest",
        },
      })
      if (ticketResponse.status !== 201) return false
      payload = await ticketResponse.json()
    } catch {
      return false
    } finally {
      window.clearTimeout(ticketTimeout)
    }
    if (
      typeof payload !== "object" ||
      payload === null ||
      typeof (payload as { ticket?: unknown }).ticket !== "string"
    ) {
      return false
    }
    const ticket = (payload as { ticket: string }).ticket
    if (!/^[a-f0-9]{64}$/u.test(ticket)) return false

    try {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
      const socket = new WebSocket(
        `${protocol}//${window.location.host}/ws/chat?ticket=${encodeURIComponent(ticket)}`
      )
      let resolveClose!: () => void
      const closeSignal = new Promise<void>((resolve) => {
        resolveClose = resolve
      })
      const probe: SiblingRevocationSocketProbe = {
        socket,
        opened: false,
        closed: false,
        closeCode: null,
        revokedReason: false,
        closeSignal,
      }
      target.__liveMfaSiblingRevocationProbe = probe

      const didOpen = await new Promise<boolean>((resolve) => {
        let settled = false
        const timeout = window.setTimeout(() => finish(false), 8_000)
        const finish = (didOpen: boolean) => {
          if (settled) return
          settled = true
          window.clearTimeout(timeout)
          resolve(didOpen)
        }

        socket.addEventListener(
          "open",
          () => {
            probe.opened = true
            finish(true)
          },
          { once: true }
        )
        socket.addEventListener(
          "close",
          (event) => {
            probe.closed = true
            probe.closeCode = event.code
            probe.revokedReason = event.reason === "Session revoked"
            resolveClose()
            finish(false)
          },
          { once: true }
        )
        socket.addEventListener("error", () => finish(false), { once: true })
      })
      return didOpen && socket.readyState === WebSocket.OPEN
    } catch {
      return false
    }
  })

  if (!opened) throw new Error("Sibling session could not open its authenticated WebSocket")
}

async function expectSiblingRevocationSocketOpen(page: Page): Promise<void> {
  const open = await page.evaluate(() => {
    const probe = (window as SiblingRevocationProbeWindow).__liveMfaSiblingRevocationProbe
    return Boolean(probe?.opened && !probe.closed && probe.socket.readyState === WebSocket.OPEN)
  })

  if (!open) throw new Error("Sibling WebSocket closed before MFA verification")
}

async function expectSiblingRevocationSocketClosed(page: Page): Promise<void> {
  const result = await page.evaluate(async (timeoutMs) => {
    const probe = (window as SiblingRevocationProbeWindow).__liveMfaSiblingRevocationProbe
    if (!probe?.opened) {
      return { opened: false, closed: false, closeCode: null, revokedReason: false }
    }

    if (!probe.closed) {
      let timeout: number | undefined
      await Promise.race([
        probe.closeSignal,
        new Promise<void>((resolve) => {
          timeout = window.setTimeout(resolve, timeoutMs)
        }),
      ])
      if (timeout !== undefined) window.clearTimeout(timeout)
    }

    return {
      opened: probe.opened,
      closed: probe.closed,
      closeCode: probe.closeCode,
      revokedReason: probe.revokedReason,
    }
  }, 12_000)

  if (!result.opened || !result.closed || result.closeCode !== 4401 || !result.revokedReason) {
    throw new Error("Email MFA did not revoke the sibling WebSocket session")
  }
}

async function closeSiblingRevocationSocket(page: Page): Promise<void> {
  const closed = await page.evaluate(async () => {
    const target = window as SiblingRevocationProbeWindow
    const probe = target.__liveMfaSiblingRevocationProbe
    if (!probe) return true

    if (probe.socket.readyState !== WebSocket.CLOSED) {
      try {
        probe.socket.close(1000, "test cleanup")
      } catch {
        return false
      }
    }
    if (!probe.closed) {
      let timeout: number | undefined
      await Promise.race([
        probe.closeSignal,
        new Promise<void>((resolve) => {
          timeout = window.setTimeout(resolve, 3_000)
        }),
      ])
      if (timeout !== undefined) window.clearTimeout(timeout)
    }

    const didClose = probe.closed && probe.socket.readyState === WebSocket.CLOSED
    if (didClose) delete target.__liveMfaSiblingRevocationProbe
    return didClose
  })

  if (!closed) throw new Error("Owned sibling WebSocket cleanup did not complete")
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
  try {
    return { context, page: await context.newPage() }
  } catch (error) {
    try {
      await context.close()
    } catch {
      testInfo.annotations.push({
        type: "cleanup-failed",
        description: "Isolated browser context cleanup failed after page creation error",
      })
    }
    throw error
  }
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
  let siblingContext: BrowserContext | null = null
  let siblingPageForCleanup: Page | null = null
  let testFailed = false
  let testFailure: unknown

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

    const initiatingSessionId = uniqueCurrentSessionId(await readActiveSessions(page))
    const sibling = await createIsolatedPage(browser, page, testInfo)
    siblingContext = sibling.context
    const siblingPage = sibling.page
    siblingPageForCleanup = siblingPage
    await loginWith(siblingPage, email, password)
    const siblingSessionId = uniqueCurrentSessionId(await readActiveSessions(siblingPage))
    if (siblingSessionId === initiatingSessionId) {
      throw new Error("Separate browser contexts did not establish distinct sessions")
    }

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
    await openSiblingRevocationSocket(siblingPage)

    await expect(
      page.getByRole("button", { name: /Включить коды по почте|Enable email codes/iu })
    ).toBeVisible()
    const priorEnablementMessages = new Set((await mailFor(email)).map((message) => message.ID))
    const enablementStartPromise = page.waitForResponse(isApiResponse("/auth/mfa/email/enable"))
    await page.getByRole("button", { name: /Включить коды по почте|Enable email codes/iu }).click()
    expect((await enablementStartPromise).status()).toBe(200)
    await expectSiblingRevocationSocketOpen(siblingPage)

    const enablementCode = await awaitNewCode(email, priorEnablementMessages)
    const enablementVerifyPromise = page.waitForResponse(isApiResponse("/auth/mfa/verify"))
    const enabledProfilePromise = page.waitForResponse(isProfileResponse)
    await enterCode(page, enablementCode)
    const [enablementVerification, enabledProfileResponse] = await Promise.all([
      enablementVerifyPromise,
      enabledProfilePromise,
    ])
    expect(enablementVerification.status()).toBe(200)
    await expectSiblingRevocationSocketClosed(siblingPage)
    const enabledProfile = (await enabledProfileResponse.json()) as {
      email_mfa_enabled_at?: string | null
    }
    expect(enabledProfile.email_mfa_enabled_at).toBeTruthy()

    const sessionsAfterEnablement = await readActiveSessions(page)
    const currentSessionRows = sessionsAfterEnablement.filter((session) => session.is_current)
    const initiatingSessionPreserved = currentSessionRows.some(
      (session) => session.id === initiatingSessionId
    )
    const siblingSessionAbsent = sessionsAfterEnablement.every(
      (session) => session.id !== siblingSessionId
    )
    if (currentSessionRows.length !== 1 || !initiatingSessionPreserved || !siblingSessionAbsent) {
      throw new Error("Email MFA enablement did not preserve only the initiating session")
    }

    const siblingProfileResponse = await siblingPage.request.get("/api/v1/users/me")
    expect(
      siblingProfileResponse.status(),
      "the pre-existing sibling session is rejected after email MFA enablement"
    ).toBe(401)

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
      methods?: Array<{
        method?: unknown
        challenge_token?: unknown
        resend_available_at?: unknown
      }>
    }
    if (
      !Array.isArray(pendingChallenge.methods) ||
      !pendingChallenge.methods.some((method) => method.method === "email_otp")
    ) {
      throw new Error("Login did not offer the enabled email OTP factor")
    }
    const emailLoginChallenge = pendingChallenge.methods.find(
      (method) => method.method === "email_otp"
    )
    if (
      !emailLoginChallenge ||
      typeof emailLoginChallenge.challenge_token !== "string" ||
      typeof emailLoginChallenge.resend_available_at !== "string"
    ) {
      throw new Error("Login did not return the email OTP resend challenge fields")
    }
    await expect(login.page.locator(OTP_INPUTS)).toHaveCount(6)
    await expect(
      login.page.getByRole("heading", { name: /Код из письма|Email code/iu })
    ).toBeVisible()

    const resendAvailableAt = Date.parse(emailLoginChallenge.resend_available_at)
    if (!Number.isFinite(resendAvailableAt) || resendAvailableAt <= Date.now()) {
      throw new Error("The email OTP resend cooldown was not active for the fresh challenge")
    }
    const earlyResendResponsePromise = login.page.waitForResponse(
      isApiResponse("/auth/mfa/email/resend")
    )
    await login.page.evaluate(async (challengeToken) => {
      const csrfCookie = document.cookie
        .split(";")
        .map((part) => part.trim())
        .find((part) => part.startsWith("csrf_token="))
      if (!csrfCookie) throw new Error("CSRF cookie was unavailable for the resend request")

      await fetch("/api/v1/auth/mfa/email/resend", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRF-Token": decodeURIComponent(csrfCookie.slice("csrf_token=".length)),
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify({ challenge_token: challengeToken }),
      })
    }, emailLoginChallenge.challenge_token)
    const earlyResendResponse = await earlyResendResponsePromise
    expect(earlyResendResponse.status()).toBe(429)
    expect(earlyResendResponse.headers()["retry-after"]).toBeUndefined()

    const loginCode = await awaitNewCode(email, priorLoginMessages)
    const loginVerificationPromise = login.page.waitForResponse(isApiResponse("/auth/mfa/verify"))
    await enterCode(login.page, loginCode)
    expect((await loginVerificationPromise).status()).toBe(200)
    await expect(login.page).toHaveURL(/\/dashboard$/u)
    if (pageError) throw new Error("Email MFA login raised an uncaught page exception")
  } catch (error) {
    testFailed = true
    testFailure = error
  }

  let cleanupFailed = false
  if (siblingPageForCleanup) {
    try {
      await closeSiblingRevocationSocket(siblingPageForCleanup)
    } catch {
      cleanupFailed = true
    }
  }
  for (const context of [loginContext, siblingContext]) {
    if (!context) continue
    try {
      await context.close()
    } catch {
      cleanupFailed = true
    }
  }
  if (createdUserId) {
    try {
      await deleteOwnedAccount(browser, createdUserId)
    } catch {
      cleanupFailed = true
    }
  }
  if (cleanupFailed) {
    testInfo.annotations.push({
      type: "cleanup-failed",
      description: "Owned email-MFA browser or account cleanup did not complete",
    })
  }

  if (testFailed) throw testFailure
  if (cleanupFailed) throw new Error("Owned email-MFA test cleanup did not complete")
})
