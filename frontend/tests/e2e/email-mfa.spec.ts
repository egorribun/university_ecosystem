import type { MfaMethodChallenge, MfaVerifyPayload, PendingMfaResponse } from "@/types/Mfa"
import { expect, test, type Page } from "./test"
import { useMockApi as setupMockApi } from "./utils/mockApi"

// Browser contract coverage with a stateful API double, not SMTP delivery evidence.
const EMAIL = "email-mfa@example.com"
const DELIVERY_HINT = "e***@example.com"
const INITIAL_TOKEN = "email-challenge-initial-32-characters-long"
const ROTATED_TOKEN = "email-challenge-rotated-32-characters-long"
const NOW = new Date("2026-09-22T12:00:00Z")
const COOLDOWN_MS = 60_000

const locales = {
  ru: {
    title: "Код из письма",
    sentTo: `Мы отправили 6-значный код на ${DELIVERY_HINT}.`,
    resend: "Отправить новый код",
    cooldown: /Повторная отправка через \d+ с/,
    firstTick: "Повторная отправка через 59 с",
    lastSecond: "Повторная отправка через 1 с",
    invalid: "Неверный код подтверждения",
    verify: "Подтвердить",
    recovery: "Использовать резервный код",
    recoveryInput: "Резервный код",
    useOtp: "Использовать обычный код подтверждения",
  },
  en: {
    title: "Email verification code",
    sentTo: `We sent a 6-digit code to ${DELIVERY_HINT}.`,
    resend: "Send a new code",
    cooldown: /Send again in \d+s/,
    firstTick: "Send again in 59s",
    lastSecond: "Send again in 1s",
    invalid: "Invalid verification code",
    verify: "Verify",
    recovery: "Use a recovery code",
    recoveryInput: "Recovery code",
    useOtp: "Use a regular verification code",
  },
} as const

type Locale = keyof typeof locales

async function setupEmailMfaApi(page: Page, locale: Locale, baseURL: string) {
  await setupMockApi(page, { authenticated: false })
  // The app's pre-paint language selection prefers this SSR cookie over the
  // shared fixture's Russian localStorage default; no init-script ordering race.
  await page.context().addCookies([{ name: "ue:language", value: locale, url: baseURL }])
  // Let hydration run normally, then pause both Date and timers before login.
  // A fixed Date with live timers can strand the one-shot resend timer when
  // its first callback writes the same timestamp back into React state.
  await page.clock.install({ time: new Date(NOW.getTime() - 60 * 60_000) })

  const verificationRequests: MfaVerifyPayload[] = []
  const resendRequests: { challenge_token: string }[] = []
  let challenge: MfaMethodChallenge = {
    method: "email_otp",
    challenge_token: INITIAL_TOKEN,
    challenge_expires_at: new Date(NOW.getTime() + 10 * 60_000).toISOString(),
    delivery_hint: DELIVERY_HINT,
    resend_available_at: new Date(NOW.getTime() + COOLDOWN_MS).toISOString(),
    revision: 1,
  }

  await page.route("**/auth/login", async (route) => {
    const credentials = new URLSearchParams(route.request().postData() ?? "")
    expect(credentials.get("username")).toBe(EMAIL)
    const pending: PendingMfaResponse = {
      status: "mfa_required",
      user_id: "11111111-1111-4111-8111-111111111111",
      session_id: "22222222-2222-4222-8222-222222222222",
      default_method: "email_otp",
      methods: [challenge],
    }
    await route.fulfill({ status: 202, json: pending })
  })

  await page.route("**/auth/mfa/email/resend", async (route) => {
    const body = route.request().postDataJSON() as { challenge_token: string }
    resendRequests.push(body)
    expect(body).toEqual({ challenge_token: challenge.challenge_token })
    const browserNow = await page.evaluate(() => Date.now())
    challenge = {
      ...challenge,
      challenge_token: ROTATED_TOKEN,
      resend_available_at: new Date(browserNow + COOLDOWN_MS).toISOString(),
      revision: 2,
    }
    await route.fulfill({ status: 200, json: challenge })
  })

  await page.route("**/auth/mfa/verify", async (route) => {
    const body = route.request().postDataJSON() as MfaVerifyPayload
    verificationRequests.push(body)
    expect(body.method).toBe("email_otp")
    expect(body.challenge_token).toBe(challenge.challenge_token)
    if (body.code !== "123456") {
      await route.fulfill({ status: 400, json: { detail: locales[locale].invalid } })
      return
    }
    // Keep the shared fixture's successful authentication/profile contract.
    await route.fallback()
  })

  return { verificationRequests, resendRequests }
}

async function openEmailChallenge(page: Page, locale: Locale) {
  await page.goto("/login")
  await page.waitForFunction(() => window.__APP_HYDRATED === true)
  await expect(page.locator("html")).toHaveAttribute("lang", locale)
  await page.locator('input[name="email"]').fill(EMAIL)
  await page.locator('input[name="password"]').fill("Password123")
  await page.clock.pauseAt(NOW)
  await page.locator('button[type="submit"]').click()
  await expect(page.getByRole("heading", { name: locales[locale].title, level: 2 })).toBeVisible()
  await expect(page.getByText(locales[locale].sentTo, { exact: true })).toBeVisible()
  await expect(page.getByRole("textbox", { name: /digit \d/ })).toHaveCount(6)
}

async function fillCode(page: Page, code: string) {
  const inputs = page.getByRole("textbox", { name: /digit \d/ })
  for (const [index, digit] of [...code].entries()) await inputs.nth(index).fill(digit)
}

for (const locale of ["ru", "en"] as const) {
  test.describe(`Email MFA browser contract (${locale})`, () => {
    test("shows the masked delivery hint and completes email-only login", async ({
      page,
      baseURL,
    }) => {
      const api = await setupEmailMfaApi(page, locale, baseURL!)
      await openEmailChallenge(page, locale)
      await expect(page.getByRole("button", { name: locales[locale].cooldown })).toBeDisabled()

      await fillCode(page, "123456")

      await expect(page).toHaveURL(/\/dashboard$/)
      expect(api.verificationRequests).toEqual([
        { method: "email_otp", challenge_token: INITIAL_TOKEN, code: "123456" },
      ])
      expect(api.resendRequests).toEqual([])
    })

    test("enforces resend cooldown, rotates the token, and retries a wrong code", async ({
      page,
      baseURL,
    }) => {
      const api = await setupEmailMfaApi(page, locale, baseURL!)
      await openEmailChallenge(page, locale)
      const copy = locales[locale]

      // Exercise a slow test/client: let the first timeout fire before jumping
      // to the boundary. Date must advance with it so the next tick is armed.
      await page.clock.runFor(1000)
      await expect(page.getByRole("button", { name: copy.firstTick, exact: true })).toBeDisabled()
      // Jump over the middle of the cooldown, then wait for React to commit
      // the timer update and schedule the final tick before advancing again.
      await page.clock.fastForward(COOLDOWN_MS - 2000)
      await expect(page.getByRole("button", { name: copy.lastSecond, exact: true })).toBeDisabled()
      await page.clock.runFor(999)
      expect(await page.evaluate(() => Date.now())).toBe(NOW.getTime() + COOLDOWN_MS - 1)
      await expect(page.getByRole("button", { name: copy.lastSecond, exact: true })).toBeDisabled()
      expect(api.resendRequests).toEqual([])
      await page.clock.runFor(1)
      expect(await page.evaluate(() => Date.now())).toBe(NOW.getTime() + COOLDOWN_MS)
      const resend = page.getByRole("button", { name: copy.resend, exact: true })
      await expect(resend).toBeEnabled()
      await resend.click()
      await expect(page.getByRole("button", { name: copy.cooldown })).toBeDisabled()
      expect(api.resendRequests).toEqual([{ challenge_token: INITIAL_TOKEN }])

      await fillCode(page, "000000")
      await expect(page.getByText(copy.invalid, { exact: true })).toBeVisible()
      await expect(page).toHaveURL(/\/login$/)
      const inputs = page.getByRole("textbox", { name: /digit \d/ })
      for (let index = 0; index < 6; index++) await expect(inputs.nth(index)).toHaveValue("")

      await fillCode(page, "123456")
      await page.getByRole("button", { name: copy.verify, exact: true }).click()
      await expect(page).toHaveURL(/\/dashboard$/)
      expect(api.verificationRequests).toEqual([
        { method: "email_otp", challenge_token: ROTATED_TOKEN, code: "000000" },
        { method: "email_otp", challenge_token: ROTATED_TOKEN, code: "123456" },
      ])
    })

    test("can return from recovery-code entry to the email challenge", async ({
      page,
      baseURL,
    }) => {
      const api = await setupEmailMfaApi(page, locale, baseURL!)
      await openEmailChallenge(page, locale)
      const copy = locales[locale]
      await page.getByRole("button", { name: copy.recovery, exact: true }).click()
      await expect(
        page.getByRole("textbox", { name: copy.recoveryInput, exact: true })
      ).toBeVisible()
      await expect(page.getByRole("textbox", { name: /digit \d/ })).toHaveCount(0)
      await page.getByRole("button", { name: copy.useOtp, exact: true }).click()
      await expect(page.getByText(copy.sentTo, { exact: true })).toBeVisible()
      expect(api.verificationRequests).toEqual([])

      await fillCode(page, "123456")
      await expect(page).toHaveURL(/\/dashboard$/)
      expect(api.verificationRequests).toEqual([
        { method: "email_otp", challenge_token: INITIAL_TOKEN, code: "123456" },
      ])
    })
  })
}
