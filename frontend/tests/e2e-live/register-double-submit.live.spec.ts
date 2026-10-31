import { type Request } from "@playwright/test"
import {
  withLiveRegistrationAdmission,
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

function isRegistrationPost(request: Request): boolean {
  const url = new URL(request.url())
  return (
    request.method() === "POST" &&
    url.origin === ownedSessionOrigin() &&
    url.pathname === "/api/v1/auth/register"
  )
}

function boundedCleanupTimeout(deadlineAtMs: number): number {
  const timeoutMs = liveDeadlineBoundedTimeoutMs(deadlineAtMs, 5_000)
  if (timeoutMs === null) throw new Error("Owned registration cleanup deadline exhausted")
  return timeoutMs
}

test("rapid double submit on a 360px registration form creates one account", async ({
  page,
  context,
}, testInfo) => {
  const liveBaseUrl = process.env.LIVE_BASE_URL
  if (!liveBaseUrl) throw new Error("LIVE_BASE_URL must be set by the live acceptance runner")

  await page.setViewportSize({ width: 360, height: 800 })
  await context.addCookies([{ name: "ue:language", value: "ru", url: liveBaseUrl }])
  await page.addInitScript(() => window.localStorage.setItem("ue:language", "ru"))
  await stubBreachedPasswordLookup(page)
  await page.goto("/register", { waitUntil: "domcontentloaded" })
  await page.waitForFunction(() => window.__APP_HYDRATED === true)

  // The existing owned-identity helper binds project, UUID, name, email and
  // role. Registration deliberately does not return a public user id.
  const account = createOwnedResetAccount(testInfo.project.name, crypto.randomUUID())
  const { email, fullName } = account
  const password = freshPassword()
  await page.locator("#full_name").fill(fullName)
  await page.locator("#email").fill(email)
  await page.locator("#password").fill(password)
  await page.locator("#confirmPassword").fill(password)

  const submitButton = page.locator("#register-submit")
  await expect(submitButton).toBeVisible()
  await expect(submitButton).toBeEnabled()
  await submitButton.scrollIntoViewIfNeeded()

  let registerPostCount = 0
  let registrationSubmitAttempted = false
  let registrationPageClosed = false
  const registrationCompletions: Array<Promise<boolean>> = []
  const createdUser: { id: string | undefined } = { id: undefined }
  registerOwnedSessionCleanup(async (cleanupBrowser, cleanupDeadlineAtMs) => {
    if (!registrationSubmitAttempted && registerPostCount === 0) return
    const requestsCompleted =
      registrationPageClosed &&
      (await waitForRegistrationCompletion(
        registrationCompletions,
        boundedCleanupTimeout(cleanupDeadlineAtMs)
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
          boundedCleanupTimeout(cleanupDeadlineAtMs)
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
        { userId: cleanupUserId, timeoutMs: boundedCleanupTimeout(cleanupDeadlineAtMs) }
      )
      if (deletion.status !== 200 || !deletion.deleted) {
        throw new Error("Owned registration account cleanup could not be verified")
      }
      if (!requestsCompleted) {
        // The server can still commit after a client disconnect; an exact
        // best-effort delete alone does not establish that cleanup is final.
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

  const cdp = await context.newCDPSession(page)

  await withRegistrationDetach(
    async () => {
      await cdp.send("Network.enable")
      const registrationResponse = await withLiveRegistrationAdmission(page, 2, async () => {
        const registrationResponsePromise = page
          .waitForResponse((response) => isRegistrationPost(response.request()), {
            timeout: 15_000,
          })
          .catch(() => null)
        // Keep the real API path but give the UI time to enter its pending state
        // before the second physical input arrives, as on a slow mobile connection.
        await cdp.send("Network.emulateNetworkConditions", {
          offline: false,
          latency: 250,
          downloadThroughput: 1_500_000,
          uploadThroughput: 750_000,
          connectionType: "cellular3g",
        })

        if (testInfo.project.name.toLowerCase().includes("mobile")) {
          const bounds = await submitButton.boundingBox()
          if (!bounds) throw new Error("Registration submit control is not visible")
          const x = bounds.x + bounds.width / 2
          const y = bounds.y + bounds.height / 2
          registrationSubmitAttempted = true
          await page.touchscreen.tap(x, y)
          await page.touchscreen.tap(x, y)
        } else {
          registrationSubmitAttempted = true
          await submitButton.dblclick({ delay: 0 })
        }

        await cdp.send("Network.emulateNetworkConditions", {
          offline: false,
          latency: 0,
          downloadThroughput: -1,
          uploadThroughput: -1,
          connectionType: "none",
        })

        const response = await registrationResponsePromise
        if (!response) throw new Error("Registration request did not receive a response")
        return response
      })
      const registrationBody: unknown = await registrationResponse.json().catch(() => null)

      expect(registrationResponse.status()).toBe(200)
      expect(isOpaqueRegistrationReceipt(registrationBody)).toBe(true)
      expect(registerPostCount).toBe(1)
      await expect(page).toHaveURL(/\/login$/u)
      await expect(page.locator("section.auth-shell--login")).toBeVisible()
      await loginWith(page, email, password)
      const identityDeadlineAtMs = liveTestSlotDeadlineAtMs(testInfo)
      if (identityDeadlineAtMs === null)
        throw new Error("Owned registration identity deadline unavailable")
      createdUser.id = await readOwnedResetUserId(
        page.request,
        ownedSessionOrigin(),
        account,
        boundedCleanupTimeout(identityDeadlineAtMs)
      )
      expect(
        registerPostCount,
        "no extra registration request during navigation and identity verification"
      ).toBe(1)
    },
    async () => {
      try {
        await cdp.detach()
      } finally {
        try {
          await page.close()
          registrationPageClosed = true
        } finally {
          page.off("request", countRegistrationPosts)
        }
      }
    },
    () => {
      testInfo.annotations.push({
        type: "registration-cdp-cleanup",
        description: "The registration browser session could not be detached",
      })
    }
  )
  expect(registerPostCount, "no extra registration request before the page closed").toBe(1)
})
