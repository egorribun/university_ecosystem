import { randomUUID } from "node:crypto"
import type { BrowserContext, Page, Request, TestInfo } from "@playwright/test"
import {
  expect,
  freshPassword,
  liveDeadlineBoundedTimeoutMs,
  liveTestSlotDeadlineAtMs,
  loginAs,
  loginWith,
  ownedSessionOrigin,
  registerOwnedSessionCleanup,
  stubBreachedPasswordLookup,
  test,
  withLiveRegistrationAdmission,
} from "./fixtures"
import {
  createOwnedResetAccount,
  findOwnedResetUserId,
  readOwnedResetUserId,
} from "./password-reset-account-identity"
import {
  isOpaqueRegistrationReceipt,
  waitForRegistrationCompletion,
  withRegistrationDetach,
} from "./register-double-submit-lifecycle.mjs"

type RegistrationLanguage = "ru" | "en"

const COPY = {
  ru: { heading: "Регистрация", student: "Студент" },
  en: { heading: "Sign up", student: "Student" },
} as const

function isRegistrationPost(request: Request): boolean {
  const url = new URL(request.url())
  return (
    request.method() === "POST" &&
    url.origin === ownedSessionOrigin() &&
    url.pathname === "/api/v1/auth/register"
  )
}

function boundedTimeout(deadlineAtMs: number): number {
  const timeoutMs = liveDeadlineBoundedTimeoutMs(deadlineAtMs, 5_000)
  if (timeoutMs === null) throw new Error("Owned registration cleanup deadline exhausted")
  return timeoutMs
}

async function runRegistration(
  page: Page,
  context: BrowserContext,
  testInfo: TestInfo,
  width: 390 | 768 | 1440,
  language: RegistrationLanguage
): Promise<void> {
  const liveBaseUrl = process.env.LIVE_BASE_URL
  if (!liveBaseUrl) throw new Error("LIVE_BASE_URL must be set by the live acceptance runner")

  const height = width === 390 ? 844 : width === 768 ? 1024 : 900
  await page.setViewportSize({ width, height })
  await page.emulateMedia({ reducedMotion: "reduce" })
  await context.addCookies([{ name: "ue:language", value: language, url: liveBaseUrl }])
  await page.addInitScript((locale) => window.localStorage.setItem("ue:language", locale), language)
  await stubBreachedPasswordLookup(page)
  await page.goto("/register", { waitUntil: "domcontentloaded" })
  await page.waitForFunction(() => window.__APP_HYDRATED === true)
  await expect(page.locator("html")).toHaveAttribute("lang", language)
  await expect(
    page.getByRole("heading", { name: COPY[language].heading, exact: true })
  ).toBeVisible()
  await expect(page.locator("#register-role-trigger")).toHaveText(COPY[language].student)
  expect(await page.evaluate(() => window.innerWidth)).toBe(width)

  const account = createOwnedResetAccount(testInfo.project.name, randomUUID())
  const password = freshPassword()
  await page.locator("#full_name").fill(account.fullName)
  await page.locator("#email").fill(account.email)
  await page.locator("#password").fill(password)
  await page.locator("#confirmPassword").fill(password)
  const submit = page.locator("#register-submit")
  await expect(submit).toBeVisible()
  await expect(submit).toBeEnabled()
  await submit.scrollIntoViewIfNeeded()

  let registrationSubmitAttempted = false
  let registrationPageClosed = false
  let registerPostCount = 0
  const registrationCompletions: Array<Promise<boolean>> = []
  const createdUser: { id: string | undefined } = { id: undefined }

  // Register cleanup before the click: a disconnected client cannot prove that
  // the server did not create the account.
  registerOwnedSessionCleanup(async (cleanupBrowser, cleanupDeadlineAtMs) => {
    if (!registrationSubmitAttempted && registerPostCount === 0) return
    const requestsCompleted =
      registrationPageClosed &&
      (await waitForRegistrationCompletion(
        registrationCompletions,
        boundedTimeout(cleanupDeadlineAtMs)
      ))
    const cleanupContext = await cleanupBrowser.newContext({
      baseURL: ownedSessionOrigin(),
      ignoreHTTPSErrors: true,
      locale: "ru-RU",
    })
    try {
      const adminPage = await cleanupContext.newPage()
      await loginAs(adminPage, "admin", cleanupDeadlineAtMs, 5_000)
      const cleanupUserId =
        createdUser.id ??
        (await findOwnedResetUserId(
          adminPage.request,
          ownedSessionOrigin(),
          account,
          boundedTimeout(cleanupDeadlineAtMs)
        ))
      const deletion = await adminPage.evaluate(
        async ({ userId, timeoutMs }) => {
          const csrfCookie = document.cookie
            .split(";")
            .map((part) => part.trim())
            .find((part) => part.startsWith("csrf_token="))
          if (!csrfCookie) return { status: 0, deleted: false }

          const controller = new AbortController()
          const timer = window.setTimeout(() => controller.abort(), timeoutMs)
          try {
            const response = await fetch(`/api/v1/users/${encodeURIComponent(userId)}`, {
              method: "DELETE",
              credentials: "same-origin",
              redirect: "error",
              signal: controller.signal,
              headers: {
                Accept: "application/json",
                "X-CSRF-Token": decodeURIComponent(csrfCookie.slice("csrf_token=".length)),
                "X-Requested-With": "XMLHttpRequest",
              },
            })
            const body = (await response.json().catch(() => null)) as { deleted?: unknown } | null
            return { status: response.status, deleted: body?.deleted === true }
          } finally {
            window.clearTimeout(timer)
          }
        },
        { userId: cleanupUserId, timeoutMs: boundedTimeout(cleanupDeadlineAtMs) }
      )
      if (deletion.status !== 200 || !deletion.deleted) {
        throw new Error("Owned registration account cleanup could not be verified")
      }
      if (!requestsCompleted) {
        throw new Error("Owned registration request completion could not be verified")
      }
    } finally {
      await cleanupContext.close()
    }
  })

  const countRegistrationPosts = (request: Request) => {
    if (!isRegistrationPost(request)) return
    registerPostCount += 1
    registrationCompletions.push(
      request
        .response()
        .then(async (response) => {
          if (!response) return false
          return (await response.finished()) === null
        })
        .catch(() => false)
    )
  }
  page.on("request", countRegistrationPosts)

  await withRegistrationDetach(
    async () => {
      const registrationResponse = await withLiveRegistrationAdmission(page, 1, async () => {
        const responsePromise = page
          .waitForResponse((response) => isRegistrationPost(response.request()), {
            timeout: 15_000,
          })
          .catch(() => null)
        registrationSubmitAttempted = true
        await submit.click()
        const response = await responsePromise
        if (!response) throw new Error("Registration request did not receive a response")
        return response
      })
      const registrationBody: unknown = await registrationResponse.json().catch(() => null)
      expect(registrationResponse.status()).toBe(200)
      expect(isOpaqueRegistrationReceipt(registrationBody)).toBe(true)
      expect(registerPostCount).toBe(1)
      await expect(page).toHaveURL(/\/login$/u)
      await expect(page.locator("section.auth-shell--login")).toBeVisible()
      await expect(page.locator("html")).toHaveAttribute("lang", language)

      await page.close()
      registrationPageClosed = true
      // The shared owned-login fixture uses Russian labels. A fresh page keeps
      // that cleanup/identity path independent from the tested form locale.
      await context.addCookies([{ name: "ue:language", value: "ru", url: liveBaseUrl }])
      const identityPage = await context.newPage()
      try {
        await identityPage.addInitScript(() => window.localStorage.setItem("ue:language", "ru"))
        await loginWith(identityPage, account.email, password)
        const deadlineAtMs = liveTestSlotDeadlineAtMs(testInfo)
        if (deadlineAtMs === null)
          throw new Error("Owned registration identity deadline unavailable")
        createdUser.id = await readOwnedResetUserId(
          identityPage.request,
          ownedSessionOrigin(),
          account,
          boundedTimeout(deadlineAtMs)
        )
      } finally {
        await identityPage.close()
      }
      expect(registerPostCount, "registration dispatched once before the page closed").toBe(1)
    },
    async () => {
      try {
        if (!page.isClosed()) {
          await page.close()
          registrationPageClosed = true
        }
      } finally {
        page.off("request", countRegistrationPosts)
      }
    },
    () => {
      testInfo.annotations.push({
        type: "registration-page-cleanup",
        description: "The registration page could not be closed",
      })
    }
  )
}

test("ordinary registration at 390px in RU", async ({ page, context }, testInfo) => {
  await runRegistration(page, context, testInfo, 390, "ru")
})

test("ordinary registration at 768px in RU", async ({ page, context }, testInfo) => {
  await runRegistration(page, context, testInfo, 768, "ru")
})

test("ordinary registration at 1440px in RU", async ({ page, context }, testInfo) => {
  await runRegistration(page, context, testInfo, 1440, "ru")
})

test("ordinary registration at 390px in EN", async ({ page, context }, testInfo) => {
  await runRegistration(page, context, testInfo, 390, "en")
})

test("ordinary registration at 768px in EN", async ({ page, context }, testInfo) => {
  await runRegistration(page, context, testInfo, 768, "en")
})

test("ordinary registration at 1440px in EN", async ({ page, context }, testInfo) => {
  await runRegistration(page, context, testInfo, 1440, "en")
})
